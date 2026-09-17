"""Keyboard controls shared by every way of playing."""

import pygame

from .game import Action


def keyboard_action() -> Action:
    keys = pygame.key.get_pressed()
    return Action(
        steer=(keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a]),
        throttle=(keys[pygame.K_UP] or keys[pygame.K_w]) - (keys[pygame.K_DOWN] or keys[pygame.K_s]),
        fire=bool(keys[pygame.K_SPACE]),
    )
