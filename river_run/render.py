"""Pygame drawing. Reads the game state and never changes it."""

from __future__ import annotations

import pygame

from .config import (
    CHANNEL_LEFT,
    CHANNEL_RIGHT,
    EXPLOSION_FRAMES,
    FUEL_MAX,
    HUD_HEIGHT,
    LOW_FUEL,
    MISSILE_H,
    MISSILE_W,
    PLAY_HEIGHT,
    PLAYER_H,
    PLAYER_W,
    SLICE_H,
    SPEED_FAST,
    SPEED_NORMAL,
    WIDTH,
)
from .game import Game
from .world import Entity

WATER = (45, 50, 184)
LAND = (110, 156, 66)
ROAD = (70, 70, 70)
ROAD_LINE = (220, 200, 90)
BRIDGE = (184, 150, 72)
BRIDGE_DARK = (104, 80, 40)
PLAYER = (232, 232, 74)
SHIP_HULL = (28, 28, 28)
SHIP_DECK = (204, 74, 74)
HELI = (72, 188, 96)
ROTOR = (230, 230, 230)
JET = (96, 204, 236)
FUEL_RED = (214, 82, 82)
FUEL_WHITE = (240, 240, 240)
HUD_BG = (142, 142, 142)
HUD_TEXT = (250, 236, 110)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
LOW_FUEL_RED = (230, 60, 60)


class Renderer:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.play = screen.subsurface((0, 0, WIDTH, PLAY_HEIGHT))
        self.font = pygame.font.Font(None, 34)
        self.small = pygame.font.Font(None, 20)
        self.big = pygame.font.Font(None, 68)

    def draw(self, game: Game, message: str | None = None, hint: str | None = None) -> None:
        cam = int(game.camera_y)
        self._draw_river(game, cam)
        for e in game.world.active(cam - 60, cam + PLAY_HEIGHT + 60):
            self._draw_entity(e, cam, game.frame)
        if game.missile:
            mx, my = game.missile
            pygame.draw.rect(self.play, PLAYER, (int(mx), self._top(cam, my, MISSILE_H), MISSILE_W, MISSILE_H))
        if not game.dying and not game.game_over:
            self._draw_plane(int(game.player_x), self._top(cam, game.player_y, PLAYER_H))
        for ex in game.explosions:
            self._draw_explosion(ex.x, PLAY_HEIGHT - (int(ex.y) - cam), ex.timer)
        self._draw_hud(game)
        if message:
            self._draw_message(message, hint)

    @staticmethod
    def _top(cam: int, y: float, h: int) -> int:
        """Screen y of the top edge of something whose bottom is at world y."""
        return PLAY_HEIGHT - (int(y) + h - cam)

    def _draw_river(self, game: Game, cam: int) -> None:
        self.play.fill(WATER)
        first = cam // SLICE_H
        for g in range(first, first + PLAY_HEIGHT // SLICE_H + 2):
            s = game.world.slice_at(g * SLICE_H)
            top = self._top(cam, g * SLICE_H, SLICE_H)
            pygame.draw.rect(self.play, LAND, (0, top, s.left, SLICE_H))
            pygame.draw.rect(self.play, LAND, (s.right, top, WIDTH - s.right, SLICE_H))
            if s.island:
                pygame.draw.rect(self.play, LAND, (s.island[0], top, s.island[1] - s.island[0], SLICE_H))

    def _draw_entity(self, e: Entity, cam: int, frame: int) -> None:
        x, top = int(e.x), self._top(cam, e.y, e.h)
        if e.kind == "bridge":
            self._draw_bridge(e, top)
        elif not e.alive:
            return
        elif e.kind == "ship":
            self._draw_ship(x, top, e.vx >= 0)
        elif e.kind == "helicopter":
            self._draw_helicopter(x, top, e.vx >= 0, frame)
        elif e.kind == "jet":
            self._draw_jet(x, top, e.vx >= 0)
        elif e.kind == "fuel":
            self._draw_fuel(x, top, e.w, e.h)

    def _draw_bridge(self, e: Entity, top: int) -> None:
        # The road on the banks stays after the bridge is destroyed.
        for x0, x1 in ((0, CHANNEL_LEFT), (CHANNEL_RIGHT, WIDTH)):
            pygame.draw.rect(self.play, ROAD, (x0, top, x1 - x0, e.h))
            for dash in range(x0 + 6, x1 - 12, 28):
                pygame.draw.rect(self.play, ROAD_LINE, (dash, top + e.h // 2 - 1, 14, 3))
        if e.alive:
            pygame.draw.rect(self.play, BRIDGE, (e.x, top, e.w, e.h))
            pygame.draw.rect(self.play, BRIDGE_DARK, (e.x, top, e.w, 4))
            pygame.draw.rect(self.play, BRIDGE_DARK, (e.x, top + e.h - 4, e.w, 4))
            for post in range(int(e.x) + 8, int(e.x + e.w), 16):
                pygame.draw.rect(self.play, BRIDGE_DARK, (post, top + 4, 3, e.h - 8))

    def _draw_plane(self, x: int, top: int) -> None:
        pygame.draw.rect(self.play, PLAYER, (x + 10, top, 4, PLAYER_H))
        pygame.draw.polygon(self.play, PLAYER, [(x, top + 15), (x + 12, top + 8), (x + 24, top + 15), (x + 24, top + 18), (x, top + 18)])
        pygame.draw.rect(self.play, PLAYER, (x + 6, top + 21, 12, 3))

    def _draw_ship(self, x: int, top: int, facing_right: bool) -> None:
        pygame.draw.polygon(self.play, SHIP_HULL, [(x, top + 7), (x + 48, top + 7), (x + 42, top + 16), (x + 6, top + 16)])
        deck_x = x + 20 if facing_right else x + 8
        pygame.draw.rect(self.play, SHIP_DECK, (deck_x, top + 1, 20, 6))

    def _draw_helicopter(self, x: int, top: int, facing_right: bool, frame: int) -> None:
        def rect(dx: int, dy: int, w: int, h: int) -> pygame.Rect:
            return pygame.Rect(x + (dx if facing_right else 32 - dx - w), top + dy, w, h)

        pygame.draw.ellipse(self.play, HELI, rect(13, 5, 18, 12))
        pygame.draw.rect(self.play, HELI, rect(1, 9, 14, 3))
        pygame.draw.rect(self.play, HELI, rect(0, 5, 3, 9))
        pygame.draw.rect(self.play, HELI, rect(21, 2, 2, 4))
        blade = 26 if (frame // 4) % 2 else 12
        pygame.draw.rect(self.play, ROTOR, (x + 16 - blade // 2, top, blade, 2))

    def _draw_jet(self, x: int, top: int, facing_right: bool) -> None:
        shape = [(34, 6), (24, 2), (10, 2), (2, 0), (6, 6), (2, 12), (10, 10), (24, 10)]
        pygame.draw.polygon(self.play, JET, [(x + (px if facing_right else 34 - px), top + py) for px, py in shape])

    def _draw_fuel(self, x: int, top: int, w: int, h: int) -> None:
        band = h // 4
        for i, letter in enumerate("FUEL"):
            background, ink = (FUEL_RED, FUEL_WHITE) if i % 2 == 0 else (FUEL_WHITE, FUEL_RED)
            pygame.draw.rect(self.play, background, (x, top + i * band, w, band))
            text = self.small.render(letter, True, ink)
            self.play.blit(text, text.get_rect(center=(x + w // 2, top + i * band + band // 2 + 1)))

    def _draw_explosion(self, x: float, y: int, timer: int) -> None:
        radius = 4 + (EXPLOSION_FRAMES - timer)
        pygame.draw.circle(self.play, (255, 140, 30), (int(x), y), radius)
        pygame.draw.circle(self.play, (255, 230, 90), (int(x), y), radius // 2)

    def _draw_hud(self, game: Game) -> None:
        hud = pygame.Rect(0, PLAY_HEIGHT, WIDTH, HUD_HEIGHT)
        self.screen.fill(HUD_BG, hud)
        pygame.draw.rect(self.screen, BLACK, (0, PLAY_HEIGHT, WIDTH, 3))

        score = self.font.render(str(game.score), True, HUD_TEXT)
        self.screen.blit(score, score.get_rect(center=(WIDTH // 2, PLAY_HEIGHT + 17)))

        gauge = pygame.Rect(0, 0, 180, 24)
        gauge.center = (WIDTH // 2, PLAY_HEIGHT + 44)
        pygame.draw.rect(self.screen, BLACK, gauge)
        pygame.draw.rect(self.screen, WHITE, gauge, 2)
        for fraction, label in ((0.1, "E"), (0.5, "1/2"), (0.9, "F")):
            text = self.small.render(label, True, WHITE)
            self.screen.blit(text, text.get_rect(center=(gauge.left + int(gauge.width * fraction), gauge.centery)))
        needle_x = gauge.left + 8 + int(game.fuel / FUEL_MAX * (gauge.width - 16))
        low = game.fuel < LOW_FUEL and (game.frame // 15) % 2 == 0
        pygame.draw.rect(self.screen, LOW_FUEL_RED if low else HUD_TEXT, (needle_x - 2, gauge.top + 2, 4, gauge.height - 4))

        # Speed bar: fills from the bottom, full at top speed; the white tick marks normal speed.
        bar = pygame.Rect(14, PLAY_HEIGHT + 12, 12, HUD_HEIGHT - 20)
        pygame.draw.rect(self.screen, BLACK, bar)
        filled = int((bar.height - 4) * game.speed / SPEED_FAST)
        pygame.draw.rect(self.screen, HUD_TEXT, (bar.left + 2, bar.bottom - 2 - filled, bar.width - 4, filled))
        tick_y = bar.bottom - 2 - int((bar.height - 4) * SPEED_NORMAL / SPEED_FAST)
        pygame.draw.line(self.screen, WHITE, (bar.left - 3, tick_y), (bar.right + 2, tick_y), 1)
        self.screen.blit(self.small.render("SPEED", True, BLACK), (bar.right + 8, bar.top))

        lives = self.small.render(f"LIVES {game.lives}", True, BLACK)
        self.screen.blit(lives, (bar.right + 8, PLAY_HEIGHT + 58))
        bridges = self.small.render(f"BRIDGE {game.bridges}", True, BLACK)
        self.screen.blit(bridges, bridges.get_rect(topright=(WIDTH - 14, PLAY_HEIGHT + 58)))

    def _draw_message(self, message: str, hint: str | None) -> None:
        shade = pygame.Surface((WIDTH, PLAY_HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 140))
        self.play.blit(shade, (0, 0))
        title = self.big.render(message, True, HUD_TEXT)
        self.play.blit(title, title.get_rect(center=(WIDTH // 2, PLAY_HEIGHT // 2 - 30)))
        if hint:
            for i, line in enumerate(hint.split("\n")):
                text = self.small.render(line, True, WHITE)
                self.play.blit(text, text.get_rect(center=(WIDTH // 2, PLAY_HEIGHT // 2 + 20 + i * 22)))
