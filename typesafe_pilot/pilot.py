"""The TypeSafe pilot: one System One request per decision, three questions answered in parallel.

- lane (Choice): which reachable lane to fly in
- fire (Noul): whether to fire the missile now
- throttle (Choice): slow, normal or fast

Code builds the scene, turns the answers into a Plan and flies it; the model makes the calls.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from typesafe_sdk import Choice, Noul, NoulCriteria, RetryPolicy, TypeSafeClient

from .scene import describe, lane_center

RULES = [
    "The plane flies up a river, seen from above. It always moves forward, and can steer between lanes and change speed.",
    "Touching land, a ship, a helicopter, a jet or an intact bridge destroys the plane.",
    "Fuel drains all the time. Flying over a fuel depot refuels the plane; shooting a depot destroys it. At 0% fuel the plane crashes.",
    "The missile flies straight ahead from the plane's exact position and destroys the first ship, helicopter, jet, fuel depot or bridge it hits. Only one missile can be in the air at a time.",
    "A bridge crosses the whole river at the end of each section and must be shot before the plane reaches it.",
    "Distances are pixels ahead of the plane. The view reaches about 470 pixels ahead. At normal speed the plane covers 120 pixels per second.",
]

THROTTLE = {"slow": -1, "normal": 0, "fast": 1}
FIRE_THRESHOLD = 0.5
SEEK_FUEL_BELOW_PERCENT = 30  # below this, the lane question strongly prefers lanes with a fuel depot
DEAD_END_PX = 250  # a lane with less open water than this ends soon (used in the question and in steering)


@dataclass(frozen=True)
class SteeringConfig:
    """How the lane answer becomes a steering target.

    - "top": fly to the center of the single most likely lane.
    - "blend": group likely lanes (probability >= min_probability) into blocks of neighbors, pick the
      block by `block_score` ("sum" = total probability, "max" = its most likely lane), then fly to the
      probability-weighted center of that block. Lanes that aren't offered always split blocks, and so
      do dead ends: lanes with under `dead_end_px` of open water and under half the best lane's. That
      keeps the lanes in front of an island from joining the channels on either side of it.
      dead_end_px = 0 turns the dead-end rule off.
    """

    mode: str = "blend"
    block_score: str = "sum"
    min_probability: float = 0.1
    dead_end_px: int = DEAD_END_PX


@dataclass(frozen=True)
class Plan:
    lane: int  # most likely lane of the chosen block (or overall, in "top" mode)
    target_x: float  # where to steer; see SteeringConfig
    throttle: int
    fire: bool
    lane_confidence: float
    fire_probability: float
    throttle_choice: str
    latency_ms: float
    tokens: int


def build_questions(scene: dict) -> dict:
    lane_ids = list(scene["lanes"])
    questions = {
        "fire": Noul(
            instructions={
                "question": "Should the plane fire its missile right now?",
                "inspect": ["`line_of_fire`", "`plane.missile_ready`", "`plane.fuel_percent`"],
            },
            criteria=NoulCriteria(
                true={
                    "what": "The missile is ready and `line_of_fire` holds a ship, helicopter, jet or bridge",
                    "also": "A fuel depot in `line_of_fire` when `plane.fuel_percent` is above 80",
                },
                false={
                    "what": "`line_of_fire` is empty or the missile is not ready",
                    "not_for": "Shooting a fuel depot the plane needs because `plane.fuel_percent` is 80 or less",
                },
            ),
        ),
        "throttle": Choice(
            instructions={
                "question": "How fast should the plane fly for the next moment?",
                "inspect": ["`plane`", f"`lanes.{scene['plane']['lane']}`"],
            },
            criteria={
                "slow": "Land or an enemy is close ahead (under about 150 px), or the plane needs time to steer into a safer lane",
                "normal": "Some objects or bends ahead, but nothing needs an immediate reaction",
                "fast": "Long open water ahead (over 350 px) with no enemies or bridge in the plane's lane",
            },
        ),
    }
    if len(lane_ids) > 1:
        questions["lane"] = Choice(
            instructions={
                "question": "Which lane should the plane fly in next?",
                "inspect": ["`lanes`", "`plane`"],
                "priorities": [
                    f"Survive first. A lane with under {DEAD_END_PX} px of `open_water_ahead_px` runs into land soon: if another lane has much more open water, choose that lane now, even if it is several lanes away. Waiting until the land is close is too late to steer around it.",
                    "Avoid lanes where a ship, helicopter or jet is less than 1 second away.",
                    "An enemy or bridge at least 1 second away is fine, because the plane can shoot it first.",
                    f"When `plane.fuel_percent` is below {SEEK_FUEL_BELOW_PERCENT}, strongly prefer a lane with a fuel_depot ahead.",
                    "Only when lanes are about equally safe, prefer the one closest to the plane.",
                ],
            },
            criteria={lane_id: f"Fly in `lanes.{lane_id}`, {scene['lanes'][lane_id]['position']}" for lane_id in lane_ids},
        )
    return questions


def steering_target(
    probabilities: dict[str, float], config: SteeringConfig, open_water: dict[str, int] | None = None
) -> tuple[int, float]:
    """Returns (lane, target_x): the lane to report and fall back to, and where to steer.

    open_water maps lane ids to `open_water_ahead_px`; without it the dead-end rule is skipped.
    """
    by_lane = {int(lane_id.removeprefix("lane_")): p for lane_id, p in probabilities.items()}
    top = max(by_lane, key=by_lane.get)
    if config.mode == "top":
        return top, lane_center(top)

    dead_ends: set[int] = set()
    if open_water and config.dead_end_px > 0:
        limit = min(config.dead_end_px, max(open_water.values()) / 2)
        dead_ends = {int(lane_id.removeprefix("lane_")) for lane_id, px in open_water.items() if px < limit}

    blocks: list[list[int]] = []
    for lane in sorted(lane for lane, p in by_lane.items() if p >= config.min_probability and lane not in dead_ends):
        if blocks and lane == blocks[-1][-1] + 1:
            blocks[-1].append(lane)
        else:
            blocks.append([lane])
    if not blocks:
        return top, lane_center(top)

    score = sum if config.block_score == "sum" else max
    block = max(blocks, key=lambda b: score(by_lane[lane] for lane in b))
    total = sum(by_lane[lane] for lane in block)
    return max(block, key=by_lane.get), sum(by_lane[lane] * lane_center(lane) for lane in block) / total


class TypeSafePilot:
    def __init__(self, steering: SteeringConfig = SteeringConfig(), client: TypeSafeClient | None = None):
        self.steering = steering
        self.describe = describe  # builds the scene from the game; call on the game's thread
        # A late decision is useless, so fail fast instead of retrying for long.
        self.client = client or TypeSafeClient(timeout=3.0, retry=RetryPolicy(max_retries=1, backoff_initial=0.1))

    def close(self) -> None:
        self.client.close()

    def decide(self, scene: dict) -> Plan:
        start = time.perf_counter()
        response = self.client.system_one(state={"rules": RULES, **scene}, questions=build_questions(scene))
        latency_ms = (time.perf_counter() - start) * 1000

        plane_lane = int(scene["plane"]["lane"].removeprefix("lane_"))
        lane = response.choices.get("lane")
        fire = response.nouls["fire"].noul
        throttle = response.choices["throttle"]
        target_lane, target_x = (
            steering_target(lane.probabilities, self.steering, {k: v["open_water_ahead_px"] for k, v in scene["lanes"].items()})
            if lane
            else (plane_lane, lane_center(plane_lane))
        )
        return Plan(
            lane=target_lane,
            target_x=target_x,
            throttle=THROTTLE[throttle.choice],
            fire=fire >= FIRE_THRESHOLD,
            lane_confidence=lane.confidence if lane else 1.0,
            fire_probability=fire,
            throttle_choice=throttle.choice,
            latency_ms=latency_ms,
            tokens=(response.usage.input_tokens or 0) + (response.usage.output_tokens or 0),
        )
