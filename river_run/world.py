"""Procedural river and the objects on it.

World coordinates: x runs left to right across the screen, y is distance up the river
(larger y is further ahead). Every object's y is its bottom edge; it extends up to y + h.
Sections are generated from the seed, so rebuilding one gives exactly the same river.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .config import (
    BANK_MIN,
    BANK_SHIFT,
    BRIDGE_CHANNEL_SLICES,
    BRIDGE_SLICE,
    CHANNEL_LEFT,
    CHANNEL_RIGHT,
    FUNNEL_SLICES,
    MAX_RUN,
    MIN_CHANNEL,
    MIN_OVERLAP,
    MIN_RUN,
    SECTION_LEN,
    SECTION_SLICES,
    SIZES,
    SLICE_H,
    START_SLICES,
    WIDTH,
)


@dataclass(frozen=True)
class Slice:
    """One horizontal band of river: banks at left/right, optional island in between."""

    left: int
    right: int
    island: tuple[int, int] | None = None

    def water(self) -> list[tuple[int, int]]:
        if self.island is None:
            return [(self.left, self.right)]
        return [(self.left, self.island[0]), (self.island[1], self.right)]

    def contains(self, x0: float, x1: float) -> bool:
        return any(a <= x0 and x1 <= b for a, b in self.water())


CHANNEL = Slice(CHANNEL_LEFT, CHANNEL_RIGHT)


@dataclass
class Entity:
    kind: str  # ship, helicopter, jet, fuel or bridge
    x: float
    y: float
    w: int
    h: int
    vx: float = 0.0
    section: int = 0
    alive: bool = True

    def overlaps(self, x: float, y: float, w: float, h: float) -> bool:
        return x < self.x + self.w and self.x < x + w and y < self.y + self.h and self.y < y + h


def passable(prev: Slice, nxt: Slice) -> bool:
    """True if every water channel in prev leads into a channel of nxt wide enough to fly through."""
    return all(
        any(min(b1, b2) - max(a1, a2) >= MIN_OVERLAP for a2, b2 in nxt.water())
        for a1, b1 in prev.water()
    )


class World:
    def __init__(self, seed: int):
        self.seed = seed
        self.slices: dict[int, Slice] = {}
        self.entities: dict[int, list[Entity]] = {}

    def slice_at(self, y: float) -> Slice:
        g = int(y // SLICE_H)
        if g < 0:
            return CHANNEL
        self._ensure(g // SECTION_SLICES)
        return self.slices[g]

    def in_water(self, x: float, y: float, w: float, h: float) -> bool:
        first, last = int(y // SLICE_H), int((y + h - 1) // SLICE_H)
        return all(self.slice_at(g * SLICE_H).contains(x, x + w) for g in range(first, last + 1))

    def active(self, y0: float, y1: float) -> list[Entity]:
        """Entities (alive or not) overlapping the world band y0..y1."""
        found = []
        for s in range(max(0, int(y0 // SECTION_LEN)), int(y1 // SECTION_LEN) + 1):
            self._ensure(s)
            found.extend(e for e in self.entities[s] if e.y < y1 and e.y + e.h > y0)
        return found

    def reset_from(self, section: int) -> None:
        """Restore every object from this section on, as after losing a life."""
        for s in [s for s in self.entities if s >= section]:
            del self.entities[s]

    def _ensure(self, section: int) -> None:
        if section not in self.entities:
            self._generate(section)

    def _generate(self, section: int) -> None:
        rng = random.Random(self.seed * 1_000_003 + section)
        difficulty = min(section, 10) / 10

        rows = [CHANNEL] * START_SLICES
        prev = CHANNEL
        random_end = SECTION_SLICES - FUNNEL_SLICES - BRIDGE_CHANNEL_SLICES
        while len(rows) < random_end:
            seg = _next_segment(rng, prev, difficulty)
            rows.extend([seg] * min(rng.randint(MIN_RUN, MAX_RUN), random_end - len(rows)))
            prev = seg
        funnel = Slice(min(prev.left, CHANNEL_LEFT - 40), max(prev.right, CHANNEL_RIGHT + 40))
        rows.extend([funnel] * FUNNEL_SLICES)
        rows.extend([CHANNEL] * BRIDGE_CHANNEL_SLICES)

        base = section * SECTION_SLICES
        for i, row in enumerate(rows):
            self.slices[base + i] = row
        self.entities[section] = _spawn_entities(rng, rows, section, difficulty)


def _next_segment(rng: random.Random, prev: Slice, difficulty: float) -> Slice:
    min_width = int(220 - 100 * difficulty)
    for _ in range(30):
        left = _clamp(prev.left + rng.randint(-BANK_SHIFT, BANK_SHIFT), BANK_MIN, WIDTH - BANK_MIN - min_width)
        right = _clamp(prev.right + rng.randint(-BANK_SHIFT, BANK_SHIFT), left + min_width, WIDTH - BANK_MIN)
        island = None
        if right - left >= 2 * MIN_CHANNEL + 40 and rng.random() < 0.3:
            size = rng.randint(40, right - left - 2 * MIN_CHANNEL)
            start = rng.randint(left + MIN_CHANNEL, right - MIN_CHANNEL - size)
            island = (start, start + size)
        candidate = Slice(left, right, island)
        if passable(prev, candidate):
            return candidate
    return Slice(prev.left, prev.right)


def _spawn_entities(rng: random.Random, rows: list[Slice], section: int, difficulty: float) -> list[Entity]:
    base_y = section * SECTION_LEN
    entities = []
    mover_chance = 0.35 + 0.5 * difficulty
    kinds, weights = ["ship", "helicopter", "fuel", "jet"], [0.35, 0.3, 0.27, 0.08 if section else 0.0]

    y = (START_SLICES + 3) * SLICE_H + rng.randint(0, 60)
    end = (SECTION_SLICES - BRIDGE_CHANNEL_SLICES - 3) * SLICE_H
    while y < end:
        kind = rng.choices(kinds, weights)[0]
        w, h = SIZES[kind]
        if kind == "jet":
            speed = 2.5 + difficulty
            entities.append(Entity(kind, rng.randint(0, WIDTH - w), base_y + y, w, h, rng.choice((-speed, speed)), section))
        else:
            covered = rows[y // SLICE_H : (y + h - 1) // SLICE_H + 1]
            for _ in range(12):
                a, b = rng.choice(covered[0].water())
                if b - a < w + 8:
                    continue
                x = rng.randint(a + 4, b - w - 4)
                if all(row.contains(x, x + w) for row in covered):
                    vx = 0.0
                    if kind != "fuel" and rng.random() < mover_chance:
                        speed = (0.8 + 0.8 * difficulty) if kind == "ship" else (1.2 + 1.0 * difficulty)
                        vx = rng.choice((-speed, speed))
                    entities.append(Entity(kind, x, base_y + y, w, h, vx, section))
                    break
        y += rng.randint(int(150 - 60 * difficulty), int(240 - 80 * difficulty))

    w, h = SIZES["bridge"]
    entities.append(Entity("bridge", CHANNEL_LEFT, base_y + BRIDGE_SLICE * SLICE_H - 2, w, h, section=section))
    return entities


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))
