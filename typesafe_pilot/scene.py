"""Measures what the pilot needs to know about each lane. Plain code: no model calls here.

The screen is split into fixed vertical lanes. For every lane the plane can reach without
touching land, we measure how much open water lies ahead and which objects are in the lane
or will drift into it by the time the plane gets there.
"""

from __future__ import annotations

from river_run.config import FUEL_MAX, PLAY_HEIGHT, PLAYER_H, PLAYER_VX, PLAYER_W, SLICE_H, WIDTH
from river_run.game import Game
from river_run.world import Entity

LANE_W = 24  # one plane width: 20 lanes across the screen
LANE_COUNT = WIDTH // LANE_W
MAX_OBJECTS = 3
KIND_NAMES = {"fuel": "fuel_depot"}


def lane_of(x_center: float) -> int:
    return min(LANE_COUNT - 1, max(0, int(x_center // LANE_W)))


def lane_center(lane: int) -> float:
    return lane * LANE_W + LANE_W / 2


def describe(game: Game) -> dict:
    """Scene for the pilot. Lane ids look like "lane_4"; lanes the plane can't reach are left out."""
    x = game.player_x + PLAYER_W / 2
    plane_lane = lane_of(x)
    objects = [e for e in game.world.active(game.player_y - PLAYER_H, game.camera_y + PLAY_HEIGHT) if e.alive]

    lanes = {}
    for lane in range(LANE_COUNT):
        frames = frames_to_reach(game, x, lane_center(lane))
        if frames is None:
            continue
        lanes[f"lane_{lane}"] = {
            "position": _position(lane - plane_lane),
            "seconds_to_line_up": round(frames / 60, 2),
            "open_water_ahead_px": _open_water(game, lane_center(lane), frames),
            "objects_ahead": _objects_between(game, objects, lane_center(lane) - PLAYER_W / 2, lane_center(lane) + PLAYER_W / 2),
        }

    return {
        "plane": _plane(game, plane_lane),
        "line_of_fire": _objects_between(game, objects, x - 2, x + 2),
        "lanes": lanes,
    }


def _plane(game: Game, plane_lane: int) -> dict:
    return {
        "lane": f"lane_{plane_lane}",
        "fuel_percent": round(game.fuel / FUEL_MAX * 100),
        "speed": "slow" if game.speed < 1.5 else "fast" if game.speed > 3 else "normal",
        "missile_ready": game.missile is None,
    }


def frames_to_reach(game: Game, x: float, target: float) -> int | None:
    """Frames to line up with target by flying straight at it, or None if that path crosses land."""
    y, frames = game.player_y, 0
    if not game.world.in_water(x - PLAYER_W / 2, y, PLAYER_W, PLAYER_H):
        return None
    while abs(target - x) > PLAYER_VX / 2:
        x += PLAYER_VX if target > x else -PLAYER_VX
        y += game.speed
        frames += 1
        if not game.world.in_water(x - PLAYER_W / 2, y, PLAYER_W, PLAYER_H):
            return None
    return frames


def _open_water(game: Game, center: float, frames: int) -> int:
    """Pixels of water ahead of the plane in this lane, counted from where the plane lines up."""
    x0 = center - PLAYER_W / 2
    y = game.player_y + frames * game.speed + PLAYER_H
    view_top = game.camera_y + PLAY_HEIGHT
    while y < view_top and game.world.slice_at(y).contains(x0, x0 + PLAYER_W):
        y += SLICE_H
    return round(min(y, view_top) - game.player_y - PLAYER_H)


def _objects_between(game: Game, objects: list[Entity], x0: float, x1: float) -> list[dict]:
    """Objects between x0 and x1 now, or that will cross that strip before the plane has flown past them."""
    found = []
    for e in objects:
        ahead = e.y - (game.player_y + PLAYER_H)
        if e.y + e.h <= game.player_y:
            continue
        frames = max(0.0, ahead) / game.speed
        # Follow sideways movement until the plane is past the object, not just until it reaches it:
        # an enemy level with the plane can still fly into it.
        later_x = e.x + e.vx * (e.y + e.h - game.player_y) / game.speed
        in_lane_now = e.x < x1 and x0 < e.x + e.w
        if not in_lane_now and not (min(e.x, later_x) < x1 and x0 < max(e.x, later_x) + e.w):
            continue
        found.append(
            {
                "kind": KIND_NAMES.get(e.kind, e.kind),
                "ahead_px": max(0, round(ahead)),
                "seconds_away": round(frames / 60, 1),
                "in_lane_now": in_lane_now,
                "moving": "left" if e.vx < 0 else "right" if e.vx > 0 else "no",
            }
        )
    found.sort(key=lambda o: o["ahead_px"])
    return found[:MAX_OBJECTS]


def _position(offset: int) -> str:
    if offset == 0:
        return "current lane"
    side = "right" if offset > 0 else "left"
    return f"{abs(offset)} lane{'s' if abs(offset) > 1 else ''} to the {side}"
