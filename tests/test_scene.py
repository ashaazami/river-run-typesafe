from types import SimpleNamespace

import pytest

from river_run.config import PLAYER_H, PLAYER_W, SIZES, WIDTH
from river_run.game import Game
from river_run.world import Entity
from typesafe_pilot.__main__ import fly
from typesafe_pilot.pilot import Plan, SteeringConfig, TypeSafePilot, build_questions, steering_target
from typesafe_pilot.scene import LANE_COUNT, describe, lane_center, lane_of


def _place_plane(game: Game, lane: int) -> None:
    game.player_x = lane_center(lane) - PLAYER_W / 2


def _first_section(game: Game) -> list[Entity]:
    game.world.active(0, 1)  # sections are generated on first use
    return game.world.entities[0]


def test_start_lane_is_reachable_and_land_lanes_are_not():
    scene = describe(Game())
    plane_lane = scene["plane"]["lane"]
    assert scene["lanes"][plane_lane]["position"] == "current lane"
    assert "lane_0" not in scene["lanes"] and f"lane_{LANE_COUNT - 1}" not in scene["lanes"]


def test_enemy_level_with_plane_moving_toward_it_is_reported():
    game = Game()
    _first_section(game).clear()
    lane = lane_of(WIDTH / 2)
    _place_plane(game, lane)
    w, h = SIZES["helicopter"]
    heli = Entity("helicopter", lane_center(lane) - PLAYER_W / 2 - w - 4, game.player_y + PLAYER_H, w, h, vx=1.5)
    _first_section(game).append(heli)
    scene = describe(game)
    assert [o["kind"] for o in scene["lanes"][f"lane_{lane}"]["objects_ahead"]] == ["helicopter"]
    assert scene["lanes"][f"lane_{lane}"]["objects_ahead"][0]["in_lane_now"] is False
    assert scene["line_of_fire"]


def test_line_of_fire_holds_the_bridge_ahead():
    game = Game()
    section = _first_section(game)
    section[:] = [e for e in section if e.kind == "bridge"]
    bridge = section[0]
    game.camera_y = bridge.y - 400
    _place_plane(game, lane_of(bridge.x + bridge.w / 2))
    assert [o["kind"] for o in describe(game)["line_of_fire"]] == ["bridge"]


def test_lane_question_offers_exactly_the_reachable_lanes():
    scene = describe(Game())
    assert len(scene["lanes"]) > 1
    lane = build_questions(scene)["lane"]
    criteria = lane["criteria"] if isinstance(lane, dict) else lane.criteria
    assert set(criteria) == set(scene["lanes"])


BLEND = SteeringConfig()


def test_blend_averages_a_block_of_neighboring_lanes():
    lane, x = steering_target({"lane_5": 0.54, "lane_6": 0.46, "lane_8": 0.0}, BLEND)
    assert lane == 5
    assert x == pytest.approx(0.54 * lane_center(5) + 0.46 * lane_center(6))


def test_blend_does_not_average_across_an_island():
    # Lanes 4 and 5 are the island, so they are never offered: lanes 3 and 6 are separate blocks.
    assert steering_target({"lane_3": 0.55, "lane_6": 0.45}, BLEND) == (3, lane_center(3))


def test_blend_picks_the_block_with_most_total_probability():
    probabilities = {"lane_3": 0.31, "lane_5": 0.30, "lane_6": 0.28, "lane_9": 0.11}
    lane, x = steering_target(probabilities, BLEND)
    assert lane == 5
    assert x == pytest.approx((0.30 * lane_center(5) + 0.28 * lane_center(6)) / 0.58)
    assert steering_target(probabilities, SteeringConfig(block_score="max")) == (3, lane_center(3))


def test_unlikely_lane_splits_blocks():
    assert steering_target({"lane_2": 0.3, "lane_3": 0.05, "lane_4": 0.65}, BLEND) == (4, lane_center(4))


# Real answer from Jev with an island in lanes 7-8, 90 px ahead of the plane (default river, after bridge 3).
ISLAND_PROBABILITIES = {"lane_6": 0.44, "lane_7": 0.12, "lane_8": 0.22, "lane_9": 0.20, "lane_10": 0.01, "lane_11": 0.01, "lane_12": 0.0}
ISLAND_OPEN_WATER = {"lane_6": 476, "lane_7": 108, "lane_8": 108, "lane_9": 364, "lane_10": 360, "lane_11": 356, "lane_12": 212}


def test_dead_end_lanes_in_front_of_an_island_split_blocks():
    lane, x = steering_target(ISLAND_PROBABILITIES, BLEND, ISLAND_OPEN_WATER)
    assert (lane, x) == (6, lane_center(6))


def test_without_the_dead_end_rule_the_blend_lands_in_front_of_the_island():
    lane, x = steering_target(ISLAND_PROBABILITIES, SteeringConfig(dead_end_px=0), ISLAND_OPEN_WATER)
    assert lane_of(x) == 7


def test_dead_end_rule_ignores_bends_where_every_lane_is_short():
    open_water = {"lane_5": 160, "lane_6": 150, "lane_7": 140}
    lane, x = steering_target({"lane_5": 0.5, "lane_6": 0.3, "lane_7": 0.2}, BLEND, open_water)
    assert x == pytest.approx(0.5 * lane_center(5) + 0.3 * lane_center(6) + 0.2 * lane_center(7))


def test_top_mode_uses_the_most_likely_lane():
    assert steering_target({"lane_3": 0.31, "lane_5": 0.30, "lane_6": 0.28}, SteeringConfig(mode="top")) == (3, lane_center(3))


def test_fly_falls_back_to_top_lane_when_blend_point_is_unreachable():
    game = Game()
    lane = lane_of(WIDTH / 2)
    _place_plane(game, lane)
    plan = Plan(lane=lane, target_x=5.0, throttle=0, fire=False, lane_confidence=1.0,
                fire_probability=0.0, throttle_choice="normal", latency_ms=0.0, tokens=0)
    assert fly(game, plan).steer == 0


class _FakeClient:
    """Stands in for TypeSafeClient: answers every question with a fixed spread of probabilities."""

    def system_one(self, state, questions):
        lane_ids = list(_criteria(questions["lane"])) if "lane" in questions else []
        probabilities = {lane_id: (0.6 if i == 0 else 0.4 / max(1, len(lane_ids) - 1)) for i, lane_id in enumerate(lane_ids)}
        choices = {"throttle": SimpleNamespace(choice="normal", confidence=0.9, probabilities={"normal": 1.0})}
        if lane_ids:
            choices["lane"] = SimpleNamespace(choice=lane_ids[0], confidence=0.5, probabilities=probabilities)
        return SimpleNamespace(choices=choices, nouls={"fire": SimpleNamespace(noul=0.7)},
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    def close(self):
        pass


def _criteria(question):
    return question["criteria"] if isinstance(question, dict) else question.criteria


@pytest.mark.parametrize("steering", [SteeringConfig(mode="top"), SteeringConfig(), SteeringConfig(block_score="max"),
                                      SteeringConfig(min_probability=0.0), SteeringConfig(min_probability=0.9),
                                      SteeringConfig(dead_end_px=0), SteeringConfig(dead_end_px=10_000)])
def test_every_steering_setting_produces_a_plan(steering):
    game = Game()
    pilot = TypeSafePilot(steering, client=_FakeClient())
    plan = pilot.decide(pilot.describe(game))
    assert f"lane_{plan.lane}" in pilot.describe(game)["lanes"]
    assert 0 <= plan.target_x <= WIDTH and plan.fire
    fly(game, plan)
