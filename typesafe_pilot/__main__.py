"""Let TypeSafe play River Run.

    python -m typesafe_pilot                          # watch; the game keeps running while Jev decides
    python -m typesafe_pilot --lockstep               # watch; the game waits for every decision
    python -m typesafe_pilot --headless --frames 5000 # no window; prints a summary
    python -m typesafe_pilot --record play.mp4 --seconds 60   # save a video (needs ffmpeg)
    python -m typesafe_pilot --human                  # fly it yourself (works with --record too)

Needs TYPESAFE_API_KEY in the environment, except with --human.
"""

from __future__ import annotations

import argparse
import subprocess
import time
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

from typesafe_sdk import TypeSafeAuthenticationError, TypeSafeError

from river_run.config import DEFAULT_SEED, FPS, HEIGHT, PLAYER_H, PLAYER_VX, PLAYER_W, WIDTH
from river_run.game import Action, Game

from .pilot import DEAD_END_PX, Plan, SteeringConfig, TypeSafePilot
from .scene import LANE_COUNT, LANE_W, frames_to_reach, lane_center, lane_of

DECIDE_EVERY = 10  # frames between decisions in lockstep mode
MAX_ERRORS_IN_A_ROW = 5


@dataclass
class Stats:
    decisions: int = 0
    errors: int = 0
    errors_in_a_row: int = 0
    latency_ms: float = 0.0
    tokens: int = 0
    deaths: Counter = field(default_factory=Counter)
    kills: Counter = field(default_factory=Counter)

    def record(self, plan: Plan) -> None:
        self.decisions += 1
        self.errors_in_a_row = 0
        self.latency_ms += plan.latency_ms
        self.tokens += plan.tokens

    def record_error(self, error: Exception) -> None:
        if isinstance(error, TypeSafeAuthenticationError):
            raise SystemExit("TypeSafe rejected the API key. Check TYPESAFE_API_KEY.") from error
        self.errors += 1
        self.errors_in_a_row += 1
        print(f"TypeSafe request failed: {error!r}")
        if self.errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
            raise SystemExit(f"Stopping after {MAX_ERRORS_IN_A_ROW} failed requests in a row.") from error

    def record_events(self, events: list[str]) -> None:
        for event in events:
            kind, _, detail = event.partition(":")
            if kind == "death":
                self.deaths[detail] += 1
            elif kind == "destroyed":
                self.kills[detail] += 1

    def summary(self, game: Game) -> str:
        average = self.latency_ms / self.decisions if self.decisions else 0
        return (
            f"frames {game.frame} ({game.frame / FPS:.0f} s)  score {game.score}  bridges {game.bridges}  "
            f"lives left {game.lives}{'  GAME OVER' if game.game_over else ''}\n"
            f"deaths {dict(self.deaths)}  destroyed {dict(self.kills)}\n"
            f"decisions {self.decisions}  errors {self.errors}  avg latency {average:.0f} ms  tokens {self.tokens}"
        )


def fly(game: Game, plan: Plan | None) -> Action:
    """Steer toward the plan's blended target; hold the planned throttle and trigger."""
    if plan is None:
        return Action()
    x = game.player_x + PLAYER_W / 2
    target = plan.target_x
    if frames_to_reach(game, x, target) is None:
        # The in-between spot can't be reached without touching land: use the top lane itself.
        target = lane_center(plan.lane)
    offset = target - x
    steer = 0 if abs(offset) <= PLAYER_VX / 2 else (1 if offset > 0 else -1)
    return Action(steer, plan.throttle, plan.fire)


def decide(pilot: TypeSafePilot, game: Game, stats: Stats) -> Plan | None:
    try:
        plan = pilot.decide(pilot.describe(game))
    except TypeSafeError as error:
        stats.record_error(error)
        return None
    stats.record(plan)
    return plan


def steering_config(args: argparse.Namespace) -> SteeringConfig:
    return SteeringConfig(
        mode=args.steering, block_score=args.block_score, min_probability=args.blend_min_prob, dead_end_px=args.dead_end_px
    )


def run_headless(args: argparse.Namespace) -> None:
    game, stats, pilot = Game(seed=args.seed), Stats(), TypeSafePilot(steering_config(args))
    plan = None
    try:
        while game.frame < args.frames and not game.game_over:
            if game.dying:
                plan = None
            elif game.frame % DECIDE_EVERY == 0:
                plan = decide(pilot, game, stats) or plan
            stats.record_events(game.step(fly(game, plan)))
            if game.frame % 600 == 0:
                print(f"  {game.frame / FPS:.0f} s: score {game.score}, bridges {game.bridges}, lives {game.lives}", flush=True)
    finally:
        pilot.close()
    print(stats.summary(game))


def run_window(args: argparse.Namespace) -> None:
    import pygame

    from river_run.controls import keyboard_action
    from river_run.render import Renderer
    from river_run.sound import Sound

    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("River Run" if args.human else "River Run - TypeSafe pilot")
    clock = pygame.time.Clock()
    renderer, sound = Renderer(screen), Sound(muted=args.mute)
    game, stats = Game(seed=args.seed), Stats()
    pilot = None if args.human else TypeSafePilot(steering_config(args))
    executor = ThreadPoolExecutor(max_workers=1)
    pending: Future | None = None
    plan: Plan | None = None
    paused = False
    recorder = Recorder(args.record, sound) if args.record else None
    frames_shown = 0
    game_over_at: int | None = None

    try:
        while args.seconds is None or frames_shown < args.seconds * FPS:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                    paused = not paused
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                    sound.toggle_mute()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN and game.game_over:
                    print(stats.summary(game))
                    game.reset()
                    stats, plan = Stats(), None

            events: list[str] = []
            if not paused and not game.game_over:
                if args.human:
                    pass
                elif args.lockstep:
                    if not game.dying and game.frame % DECIDE_EVERY == 0:
                        plan = decide(pilot, game, stats) or plan
                else:
                    # Real time: keep flying the last plan while the next decision is on its way.
                    if pending is not None and pending.done():
                        try:
                            plan = pending.result()
                            stats.record(plan)
                        except TypeSafeError as error:
                            stats.record_error(error)
                        pending = None
                    if pending is None and not game.dying:
                        pending = executor.submit(pilot.decide, pilot.describe(game))
                if game.dying:
                    plan = None
                events = game.step(keyboard_action() if args.human else fly(game, plan))
                stats.record_events(events)

            sound.update(game, events, playing=not paused and not game.game_over)
            if game.game_over:
                renderer.draw(game, "GAME OVER", f"Score {game.score}\nEnter: fly again    Esc: quit")
            elif paused:
                renderer.draw(game, "PAUSED", "Press P to continue")
            else:
                renderer.draw(game)
                if not args.human:
                    _draw_pilot_overlay(screen, renderer, game, plan)
            pygame.display.flip()
            if recorder:
                recorder.write(screen)
            frames_shown += 1
            if game.game_over and args.seconds is not None:
                # With a time limit set (e.g. when recording), end a few seconds after game over.
                game_over_at = frames_shown if game_over_at is None else game_over_at
                if frames_shown - game_over_at > 3 * FPS:
                    break
            clock.tick(FPS)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        if pilot:
            pilot.close()
        if recorder:
            recorder.close()
            print(f"saved {args.record}")
        pygame.quit()
        print(stats.summary(game))


class Recorder:
    """Saves an MP4: frames are piped to ffmpeg, then the game sounds are mixed in as the audio track.

    Sounds are rebuilt from the log of what played on which frame, so this works without an audio device.
    """

    def __init__(self, path: str, sound):
        self.path, self.sound, self.frames = path, sound, 0
        self.video_path, self.audio_path = f"{path}.video.mp4", f"{path}.audio.wav"
        sound.log = [] if sound.enabled else None
        self.process = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}",
             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", self.video_path],
            stdin=subprocess.PIPE,
        )

    def write(self, screen) -> None:
        import pygame

        self.process.stdin.write(pygame.image.tobytes(screen, "RGB"))
        self.frames += 1

    def close(self) -> None:
        import os

        self.process.stdin.close()
        self.process.wait()
        if self.sound.log is None:
            os.replace(self.video_path, self.path)
            return
        self.sound.write_log_wav(self.audio_path, self.frames)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", self.video_path, "-i", self.audio_path,
             "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", self.path],
            check=True,
        )
        os.remove(self.video_path)
        os.remove(self.audio_path)


def _draw_pilot_overlay(screen, renderer, game: Game, plan: Plan | None) -> None:
    import pygame

    from river_run.config import PLAY_HEIGHT, PLAYER_OFFSET

    if plan is None:
        text = "TypeSafe: thinking..."
    else:
        white = (255, 255, 255)
        # Corner brackets that stay on the plane.
        box = pygame.Rect(0, 0, PLAYER_W + 12, PLAYER_H + 12)
        box.center = (int(game.player_x + PLAYER_W / 2), PLAY_HEIGHT - PLAYER_OFFSET - PLAYER_H // 2)
        for corner, dx, dy in ((box.topleft, 1, 1), (box.topright, -1, 1), (box.bottomleft, 1, -1), (box.bottomright, -1, -1)):
            pygame.draw.line(screen, white, corner, (corner[0] + 6 * dx, corner[1]), 2)
            pygame.draw.line(screen, white, corner, (corner[0], corner[1] + 6 * dy), 2)
        # Lane strip along the bottom: outline = plane's lane, filled = lane TypeSafe chose.
        plane_lane = lane_of(game.player_x + PLAYER_W / 2)
        for lane in range(LANE_COUNT):
            cell = pygame.Rect(lane * LANE_W + 3, PLAY_HEIGHT - 11, LANE_W - 6, 7)
            if lane == plan.lane:
                pygame.draw.rect(screen, white, cell)
            elif lane == plane_lane:
                pygame.draw.rect(screen, white, cell, 1)
        # Tick under the strip at the blended steering target.
        tick_x = int(plan.target_x)
        pygame.draw.line(screen, white, (tick_x, PLAY_HEIGHT - 3), (tick_x, PLAY_HEIGHT - 1), 2)
        text = (
            f"TypeSafe  lane {plan.lane} ({plan.lane_confidence:.2f})  fire {plan.fire_probability:.2f}  "
            f"{plan.throttle_choice}  {plan.latency_ms:.0f} ms"
        )
    label = renderer.small.render(text, True, (255, 255, 255))
    screen.fill((0, 0, 0), label.get_rect(topleft=(6, 6)).inflate(8, 4))
    screen.blit(label, (6, 6))


def main() -> None:
    parser = argparse.ArgumentParser(description="Let TypeSafe play River Run.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--headless", action="store_true", help="no window; print a summary")
    parser.add_argument("--frames", type=int, default=5000, help="headless: frames to play at most (60 per second)")
    parser.add_argument("--lockstep", action="store_true", help="window: pause the game while waiting for each decision")
    parser.add_argument("--human", action="store_true", help="window: fly with the keyboard instead of TypeSafe")
    parser.add_argument("--steering", choices=("top", "blend"), default="blend",
                        help="top: fly to the most likely lane; blend: probability-weighted center of a block of neighboring lanes")
    parser.add_argument("--block-score", choices=("sum", "max"), default="sum",
                        help="blend: pick the block with the highest total probability (sum) or the single most likely lane (max)")
    parser.add_argument("--blend-min-prob", type=float, default=0.1,
                        help="blend: lanes below this probability split blocks (default: %(default)s)")
    parser.add_argument("--dead-end-px", type=int, default=DEAD_END_PX,
                        help="blend: lanes with less open water than this (and under half the best lane's) split blocks; 0 = off (default: %(default)s)")
    parser.add_argument("--mute", action="store_true")
    parser.add_argument("--record", metavar="FILE.mp4", help="window: save a video with sound (needs ffmpeg); don't combine with --mute")
    parser.add_argument("--seconds", type=float, help="window: stop after this many seconds")
    args = parser.parse_args()
    if args.human and (args.headless or args.lockstep):
        parser.error("--human needs the window and can't be combined with --headless or --lockstep")
    started = time.perf_counter()
    if args.headless:
        if not args.human:
            print(f"steering {steering_config(args)}")
        run_headless(args)
        print(f"wall time {time.perf_counter() - started:.0f} s")
    else:
        run_window(args)


if __name__ == "__main__":
    main()
