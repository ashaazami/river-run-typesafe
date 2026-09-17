"""Sound effects, synthesized at startup so the game needs no audio files."""

from __future__ import annotations

import random
import wave
from array import array
from collections.abc import Iterable, Iterator

import pygame

from .config import FPS, FUEL_MAX, LOW_FUEL, SPEED_FAST, SPEED_NORMAL, SPEED_SLOW
from .game import Game

ENGINE_SPEEDS = (SPEED_SLOW, SPEED_NORMAL, SPEED_FAST)


class Sound:
    def __init__(self, muted: bool = False):
        self.muted = muted
        self.frame = 0
        # When set, every sound started is logged as (frame, sound) so a recording can get a soundtrack.
        self.log: list[tuple[int, pygame.mixer.Sound | None]] | None = None
        self.engine_log: list[tuple[int, int | None]] = []
        self.enabled = pygame.mixer.get_init() is not None
        if not self.enabled:
            return
        self.rate, _, self.channels = pygame.mixer.get_init()
        rng = random.Random(0)

        # Engine: a looping buzz of held noise. Shorter holds sound higher, so faster speeds use shorter ones.
        self.engines = [self._make(self._noise(rng, 0.5, 0.10, hold, fade=False)) for hold in (9, 6, 3)]
        self.engine_channel = pygame.mixer.Channel(0)
        pygame.mixer.set_reserved(1)
        self.engine_playing: int | None = None

        self.fire = self._make(self._tone(1400, 300, 0.14, 0.18))
        self.boom = self._make(self._noise(rng, 0.45, 0.35, 4, slowdown=10))
        self.big_boom = self._make(self._noise(rng, 1.2, 0.5, 6, slowdown=24))
        self.refuel = [self._make(self._tone(500 + 90 * i, 500 + 90 * i, 0.05, 0.12)) for i in range(8)]
        self.alarm = self._make([*self._tone(880, 880, 0.08, 0.15), *self._tone(660, 660, 0.08, 0.15)])
        self.extra_life = self._make([s for f in (523, 659, 784, 1047) for s in self._tone(f, f, 0.09, 0.18)])

    def toggle_mute(self) -> None:
        self.muted = not self.muted
        if self.enabled and self.muted:
            pygame.mixer.stop()
            self.engine_playing = None

    def update(self, game: Game, events: list[str], playing: bool) -> None:
        """Call once per rendered frame with the events game.step() returned (empty if it didn't step)."""
        self.frame += 1
        if not self.enabled or self.muted:
            return
        flying = playing and not game.dying and not game.game_over
        self._set_engine(_engine_index(game.speed) if flying else None)

        for event in events:
            if event == "fire":
                self._play(self.fire)
            elif event == "destroyed:bridge" or event.startswith("death:"):
                self._play(self.big_boom)
            elif event.startswith("destroyed:"):
                self._play(self.boom)
            elif event == "extra_life":
                self._play(self.extra_life)

        if flying and game.refueling and game.frame % 6 == 0:
            self._play(self.refuel[min(7, int(game.fuel / FUEL_MAX * 8))])
        elif flying and game.fuel < LOW_FUEL and game.frame % 40 == 0:
            self._play(self.alarm)

    def _play(self, sound: pygame.mixer.Sound) -> None:
        sound.play()
        if self.log is not None:
            self.log.append((self.frame, sound))

    def _set_engine(self, index: int | None) -> None:
        if index == self.engine_playing:
            return
        if self.log is not None:
            self.engine_log.append((self.frame, index))
        if index is None:
            self.engine_channel.stop()
        else:
            self.engine_channel.play(self.engines[index], loops=-1)
        self.engine_playing = index

    def write_log_wav(self, path: str, frames: int) -> None:
        """Mix everything logged since self.log was set into a WAV lasting `frames` video frames."""
        per_frame = self.rate / FPS
        width = self.channels
        mix = array("i", bytes(4 * int(frames * per_frame) * width))

        def add(samples: array, start: int, length: int | None = None) -> None:
            start -= start % width
            end = min(len(mix), start + (len(samples) if length is None else length))
            for i in range(start, end):
                mix[i] += samples[(i - start) % len(samples)]

        engine = self.engine_log + [(frames, None)]
        for (frame, index), (next_frame, _) in zip(engine, engine[1:]):
            if index is not None:
                start = int(frame * per_frame) * width
                add(array("h", self.engines[index].get_raw()), start, int(next_frame * per_frame) * width - start)
        for frame, sound in self.log or []:
            add(array("h", sound.get_raw()), int(frame * per_frame) * width)

        out = array("h", (max(-32768, min(32767, v)) for v in mix))
        with wave.open(path, "wb") as wav:
            wav.setnchannels(width)
            wav.setsampwidth(2)
            wav.setframerate(self.rate)
            wav.writeframes(out.tobytes())

    def _make(self, samples: Iterable[float]) -> pygame.mixer.Sound:
        data = array("h")
        for s in samples:
            data.extend([int(max(-1.0, min(1.0, s)) * 32767)] * self.channels)
        return pygame.mixer.Sound(buffer=data.tobytes())

    def _tone(self, start_hz: float, end_hz: float, seconds: float, volume: float) -> Iterator[float]:
        """Square wave sliding from start_hz to end_hz, fading out."""
        n = int(self.rate * seconds)
        phase = 0.0
        for i in range(n):
            t = i / n
            phase += (start_hz + (end_hz - start_hz) * t) / self.rate
            yield (1.0 if phase % 1 < 0.5 else -1.0) * volume * (1 - t)

    def _noise(
        self, rng: random.Random, seconds: float, volume: float, hold: int, fade: bool = True, slowdown: int = 0
    ) -> Iterator[float]:
        """Crunchy 8-bit noise: each random value is held for `hold` samples, growing by `slowdown` over time."""
        n = int(self.rate * seconds)
        scale = self.rate / 22050  # keep the same pitch whatever rate the mixer opened at
        value, left = 0.0, 0
        for i in range(n):
            t = i / n
            if left <= 0:
                value = rng.uniform(-1, 1)
                left = int((hold + slowdown * t) * scale)
            left -= 1
            yield value * volume * ((1 - t) if fade else 1)


def _engine_index(speed: float) -> int:
    return min(range(len(ENGINE_SPEEDS)), key=lambda i: abs(ENGINE_SPEEDS[i] - speed))
