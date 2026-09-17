import random

from river_run.config import DEATH_FRAMES, PLAYER_W, SECTION_SLICES, SLICE_H, START_LIVES
from river_run.game import Action, Game
from river_run.world import World, passable

SECTIONS = 30


def test_river_is_always_passable():
    for seed in (1, 7, 1982):
        world = World(seed)
        rows = [world.slice_at(g * SLICE_H) for g in range(SECTIONS * SECTION_SLICES)]
        for row in rows:
            assert all(b - a > PLAYER_W + 40 for a, b in row.water())
        for prev, nxt in zip(rows, rows[1:]):
            assert passable(prev, nxt)


def test_boats_and_fuel_start_on_water():
    world = World(1982)
    for s in range(SECTIONS):
        world.slice_at(s * SECTION_SLICES * SLICE_H)
        for e in world.entities[s]:
            if e.kind in ("ship", "helicopter", "fuel", "bridge"):
                assert world.in_water(e.x, e.y, e.w, e.h), e


def test_same_seed_plays_the_same():
    def run() -> dict:
        game, rng = Game(seed=5), random.Random(0)
        for _ in range(1500):
            game.step(Action(rng.choice((-1, 0, 1)), rng.choice((-1, 0, 1)), rng.random() < 0.3))
        return game.observation()

    assert run() == run()


def test_running_out_of_fuel_costs_a_life():
    game = Game()
    game.fuel = 0.01
    assert "death:fuel" in game.step()
    for _ in range(DEATH_FRAMES):
        game.step()
    assert game.lives == START_LIVES - 1
    assert game.fuel == 100.0


def test_destroying_a_bridge_moves_the_checkpoint():
    game = Game()
    bridge = next(e for e in game.world.active(0, 2000) if e.kind == "bridge")
    game.camera_y = bridge.y - 300
    game.missile = [bridge.x + 20, bridge.y - 5]
    events = game.step()
    assert "destroyed:bridge" in events
    assert game.checkpoint == 1 and game.bridges == 1 and game.score == 500


def test_long_random_play_does_not_crash():
    game, rng = Game(seed=3), random.Random(1)
    for _ in range(30_000):
        game.step(Action(rng.choice((-1, 0, 1)), rng.choice((-1, 0, 1)), rng.random() < 0.5))
        if game.game_over:
            game.reset()
        if game.frame % 500 == 0:
            game.observation()
