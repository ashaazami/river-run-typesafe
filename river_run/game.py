"""River Run game rules. No pygame here: the game can run headless, one frame per step()."""

from __future__ import annotations

from dataclasses import dataclass

from .config import (
    DEATH_FRAMES,
    DEFAULT_SEED,
    EXPLOSION_FRAMES,
    EXTRA_LIFE_EVERY,
    FUEL_DRAIN,
    FUEL_MAX,
    FUEL_REFILL,
    MISSILE_H,
    MISSILE_VY,
    MISSILE_W,
    PLAY_HEIGHT,
    PLAYER_H,
    PLAYER_OFFSET,
    PLAYER_VX,
    PLAYER_W,
    SCORES,
    SECTION_LEN,
    SLICE_H,
    SPEED_ACCEL,
    SPEED_FAST,
    SPEED_NORMAL,
    SPEED_SLOW,
    START_LIVES,
    WIDTH,
)
from .world import Entity, World


@dataclass(frozen=True)
class Action:
    """Controls held down for one frame."""

    steer: int = 0  # -1 left, 0 straight, 1 right
    throttle: int = 0  # -1 slow down, 0 cruise, 1 speed up
    fire: bool = False


@dataclass
class Explosion:
    x: float
    y: float
    timer: int = EXPLOSION_FRAMES


TARGET_SPEED = {-1: SPEED_SLOW, 0: SPEED_NORMAL, 1: SPEED_FAST}


class Game:
    def __init__(self, seed: int = DEFAULT_SEED):
        self.seed = seed
        self.reset()

    def reset(self) -> None:
        self.world = World(self.seed)
        self.score = 0
        self.lives = START_LIVES
        self.next_extra_life = EXTRA_LIFE_EVERY
        self.bridges = 0
        self.checkpoint = 0
        self.frame = 0
        self.game_over = False
        self.explosions: list[Explosion] = []
        self.events: list[str] = []
        self._respawn()

    def _respawn(self) -> None:
        self.world.reset_from(self.checkpoint)
        self.camera_y = float(self.checkpoint * SECTION_LEN)
        self.player_x = (WIDTH - PLAYER_W) / 2
        self.speed = SPEED_NORMAL
        self.fuel = FUEL_MAX
        self.missile: list[float] | None = None
        self.dying = 0
        self.refueling = False

    @property
    def player_y(self) -> float:
        return self.camera_y + PLAYER_OFFSET

    def step(self, action: Action = Action()) -> list[str]:
        """Advance one frame and return what happened, e.g. "destroyed:ship" or "death:land"."""
        self.events = []
        self.frame += 1
        for explosion in self.explosions:
            explosion.timer -= 1
        self.explosions = [e for e in self.explosions if e.timer > 0]

        if self.game_over:
            return self.events
        if self.dying:
            self.dying -= 1
            if self.dying == 0:
                if self.lives == 0:
                    self.game_over = True
                    self.events.append("game_over")
                else:
                    self.lives -= 1
                    self._respawn()
                    self.events.append("respawn")
            return self.events

        target = TARGET_SPEED[_sign(action.throttle)]
        if self.speed < target:
            self.speed = min(target, self.speed + SPEED_ACCEL)
        else:
            self.speed = max(target, self.speed - SPEED_ACCEL)
        self.camera_y += self.speed
        self.player_x = min(max(self.player_x + _sign(action.steer) * PLAYER_VX, 0), WIDTH - PLAYER_W)

        nearby = self.world.active(self.camera_y - 60, self.camera_y + PLAY_HEIGHT + 60)
        self._move_entities(nearby)
        self._update_missile(action.fire, nearby)
        self._update_fuel(nearby)
        if not self.dying:
            self._check_collisions(nearby)
        return self.events

    def _move_entities(self, nearby: list[Entity]) -> None:
        screen_top = self.camera_y + PLAY_HEIGHT
        for e in nearby:
            # Objects only start moving once they come into view.
            if not e.alive or not e.vx or e.y > screen_top:
                continue
            if e.kind == "jet":
                e.x += e.vx
                if e.x > WIDTH:
                    e.x = -e.w
                elif e.x < -e.w:
                    e.x = WIDTH
            elif self.world.in_water(e.x + e.vx, e.y, e.w, e.h):
                e.x += e.vx
            else:
                e.vx = -e.vx

    def _update_missile(self, fire: bool, nearby: list[Entity]) -> None:
        if fire and self.missile is None:
            self.missile = [self.player_x + (PLAYER_W - MISSILE_W) / 2, self.player_y + PLAYER_H]
            self.events.append("fire")
        if self.missile is None:
            return
        self.missile[1] += MISSILE_VY + self.speed
        mx, my = self.missile
        if my > self.camera_y + PLAY_HEIGHT:
            self.missile = None
            return
        for e in nearby:
            if e.alive and e.overlaps(mx, my, MISSILE_W, MISSILE_H):
                e.alive = False
                self.missile = None
                self._explode(e)
                self._add_score(SCORES[e.kind])
                self.events.append(f"destroyed:{e.kind}")
                if e.kind == "bridge":
                    self.bridges += 1
                    self.checkpoint = e.section + 1
                return

    def _update_fuel(self, nearby: list[Entity]) -> None:
        px, py = self.player_x, self.player_y
        self.refueling = any(
            e.alive and e.kind == "fuel" and e.overlaps(px, py, PLAYER_W, PLAYER_H) for e in nearby
        )
        if self.refueling:
            self.fuel = min(FUEL_MAX, self.fuel + FUEL_REFILL)
        else:
            self.fuel -= FUEL_DRAIN
        if self.fuel <= 0:
            self.fuel = 0.0
            self._die("fuel")

    def _check_collisions(self, nearby: list[Entity]) -> None:
        px, py = self.player_x, self.player_y
        if not self.world.in_water(px, py, PLAYER_W, PLAYER_H):
            self._die("land")
            return
        for e in nearby:
            if e.alive and e.kind != "fuel" and e.overlaps(px, py, PLAYER_W, PLAYER_H):
                e.alive = False
                self._explode(e)
                self._die(e.kind)
                return

    def _die(self, reason: str) -> None:
        self.dying = DEATH_FRAMES
        self.missile = None
        self.explosions.append(Explosion(self.player_x + PLAYER_W / 2, self.player_y + PLAYER_H / 2))
        self.events.append(f"death:{reason}")

    def _explode(self, e: Entity) -> None:
        self.explosions.append(Explosion(e.x + e.w / 2, e.y + e.h / 2))

    def _add_score(self, points: int) -> None:
        self.score += points
        while self.score >= self.next_extra_life:
            self.lives += 1
            self.next_extra_life += EXTRA_LIFE_EVERY
            self.events.append("extra_life")

    def observation(self) -> dict:
        """What the pilot can see this frame, measured from the plane. Meant for automated players.

        "ahead" values are distances above the plane's bottom edge; x values are screen pixels.
        """
        px, py = self.player_x, self.player_y
        view_top = self.camera_y + PLAY_HEIGHT

        river: list[dict] = []
        g = int(py // SLICE_H)
        while g * SLICE_H < view_top:
            water = [list(interval) for interval in self.world.slice_at(g * SLICE_H).water()]
            start = round(g * SLICE_H - py)
            if river and river[-1]["water"] == water:
                river[-1]["to"] = start + SLICE_H
            else:
                river.append({"from": start, "to": start + SLICE_H, "water": water})
            g += 1

        objects = [
            {"kind": e.kind, "x": round(e.x), "ahead": round(e.y - py), "w": e.w, "h": e.h, "vx": e.vx}
            for e in self.world.active(py - PLAYER_OFFSET, view_top)
            if e.alive
        ]
        return {
            "frame": self.frame,
            "screen_width": WIDTH,
            "player": {"x": round(px), "w": PLAYER_W, "h": PLAYER_H},
            "speed": round(self.speed, 2),
            "fuel": round(self.fuel, 1),
            "fuel_max": FUEL_MAX,
            "score": self.score,
            "lives": self.lives,
            "bridges": self.bridges,
            "missile_ready": self.missile is None,
            "dying": self.dying > 0,
            "game_over": self.game_over,
            "river": river,
            "objects": objects,
        }


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)
