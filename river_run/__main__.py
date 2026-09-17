"""Play River Run with the keyboard: python -m river_run"""

from __future__ import annotations

import argparse

import pygame

from .config import DEFAULT_SEED, FPS, HEIGHT, WIDTH
from .controls import keyboard_action
from .game import Game
from .render import Renderer
from .sound import Sound

CONTROLS = "Arrows or WASD: steer and change speed\nSpace: fire    P: pause    M: mute    Esc: quit"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="River Run, a river shooter inspired by Atari's River Raid.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="river layout (default: %(default)s)")
    parser.add_argument("--mute", action="store_true", help="start with sound off")
    args = parser.parse_args(argv)

    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("River Run")
    clock = pygame.time.Clock()
    game = Game(seed=args.seed)
    renderer = Renderer(screen)
    sound = Sound(muted=args.mute)
    mode = "title"

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                pygame.quit()
                return
            if event.key == pygame.K_m:
                sound.toggle_mute()
            elif mode == "title" and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                mode = "play"
            elif mode in ("play", "paused") and event.key == pygame.K_p:
                mode = "paused" if mode == "play" else "play"
            elif mode == "over" and event.key == pygame.K_RETURN:
                game.reset()
                mode = "play"

        events: list[str] = []
        if mode == "play":
            events = game.step(keyboard_action())
            if game.game_over:
                mode = "over"
        sound.update(game, events, playing=mode == "play")

        if mode == "title":
            renderer.draw(game, "RIVER RUN", "Press Enter to start\n\n" + CONTROLS)
        elif mode == "paused":
            renderer.draw(game, "PAUSED", "Press P to continue")
        elif mode == "over":
            renderer.draw(game, "GAME OVER", f"Score {game.score}\nPress Enter to play again")
        else:
            renderer.draw(game)
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
