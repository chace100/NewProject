"""Data-consistency checks for the design doc's example level (issue #6).

`docs/ARCHITECTURE.md` §3.5 embeds a level that is used as the worked example of
the level format. A level that cannot be played, or whose numbers do not match
the model in §2, is a documentation bug -- so the claims are pinned here:

* every ``segmentId`` / ``surface`` reference resolves (JSON Schema cannot
  express referential integrity),
* ``zone.from < zone.to`` (JSON Schema 2020-12 has no relational keyword),
* the documented strategy actually reaches the ice and stops inside the goal
  zone, and swapping the middle surface for rubber stops short of it,
* the ice/rubber slide-distance ratio required by issue #8 holds (>= 3).

The integrator below is a *reference* implementation of the model in §2.3/§2.4
(semi-implicit Euler with the closed-form stop step) and is stdlib-only on
purpose: it must run in CI even when ``jsonschema`` is not installed. The
authoritative implementation for the game is #8's ``src/sim/``.
"""

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCH_DOC = REPO_ROOT / "docs" / "ARCHITECTURE.md"
JSON_FENCE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)

FIXED_DT = 1 / 60


class ReferenceModel:
    """§2.3/§2.4 的最小参考实现:定步长 + 解析停住步。"""

    def __init__(self, level):
        physics = level.get("physics", {})
        self.accel = physics.get("accel", 12.0)
        self.max_speed = physics.get("maxSpeed", 12.0)
        self.gravity = physics.get("gravity", 9.82)
        self.rest_threshold = physics.get("restThreshold", 0.05)
        self.segments = list(level["terrain"])
        self.surfaces = level["surfaces"]
        self.starts = {}
        position = 0.0
        for segment in self.segments:
            self.starts[segment["id"]] = position
            position += segment["length"]
        self.total_length = position

    def segment_at(self, x):
        for segment in self.segments:
            start = self.starts[segment["id"]]
            if start <= x <= start + segment["length"]:
                return segment
        return None

    def simulate(self, spawn, thrust_segments, max_seconds=120.0):
        """thrust_segments: 在这些段 id 上按住前进键,其余段松开。"""
        x = self.starts[spawn["segmentId"]] + spawn.get("at", 0.0)
        v = spawn.get("speed", 0.0)
        elapsed = 0.0
        while elapsed < max_seconds:
            segment = self.segment_at(x)
            if segment is None:
                return {"status": "left-track", "x": x, "v": v, "time": elapsed}
            mu = self.surfaces[segment["surface"]]["mu"]
            thrust = self.accel if segment["id"] in thrust_segments else 0.0
            a = thrust - mu * self.gravity
            if a < 0 and v + a * FIXED_DT <= 0:            # 本步内停住,距离为 v²/(2|a|)
                x += (v * v) / (-2 * a)
                v = 0.0
            else:
                v = min(self.max_speed, v + a * FIXED_DT)
                x += v * FIXED_DT - 0.5 * a * FIXED_DT * FIXED_DT
            elapsed += FIXED_DT
            if v <= self.rest_threshold and segment["id"] not in thrust_segments:
                return {"status": "stopped", "x": x, "v": v, "time": elapsed}
        return {"status": "timeout", "x": x, "v": v, "time": elapsed}

    def coast_distance(self, mu, v0, dt=FIXED_DT):
        """同初速、无输入的滑行距离,按同一离散模型逐帧推进。"""
        a = -mu * self.gravity
        x = 0.0
        v = v0
        while v > self.rest_threshold:
            if v + a * dt <= 0:
                x += (v * v) / (-2 * a)
                v = 0.0
            else:
                v += a * dt
                x += v * dt - 0.5 * a * dt * dt
        return x


def load_documented_level():
    doc = ARCH_DOC.read_text(encoding="utf-8")
    blocks = [json.loads(block) for block in JSON_FENCE.findall(doc)]
    if not blocks:
        raise AssertionError("ARCHITECTURE.md should embed an example level JSON block")
    return blocks[0]


class ExampleLevelDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.level = load_documented_level()
        cls.model = ReferenceModel(cls.level)

    def test_referenced_segment_ids_exist(self):
        segment_ids = {segment["id"] for segment in self.level["terrain"]}
        referenced = {self.level["spawn"]["segmentId"], self.level["goal"]["zone"]["segmentId"]}
        referenced |= {obstacle["segmentId"] for obstacle in self.level.get("obstacles", [])}
        self.assertEqual(referenced - segment_ids, set())

    def test_referenced_surfaces_exist(self):
        declared = set(self.level["surfaces"])
        used = {segment["surface"] for segment in self.level["terrain"]}
        self.assertEqual(used - declared, set())

    def test_goal_zone_ordering_and_bounds(self):
        zone = self.level["goal"]["zone"]
        self.assertLess(zone["from"], zone["to"])
        length = self.starts_length(zone["segmentId"])
        self.assertLessEqual(zone["to"], length)

    def starts_length(self, segment_id):
        for segment in self.level["terrain"]:
            if segment["id"] == segment_id:
                return segment["length"]
        raise AssertionError(f"unknown segment {segment_id}")

    def test_spawn_is_inside_the_runway(self):
        spawn = self.level["spawn"]
        self.assertLessEqual(spawn["at"], self.starts_length(spawn["segmentId"]))

    def test_documented_strategy_stops_inside_the_goal_zone(self):
        spawn = self.level["spawn"]
        result = self.model.simulate(spawn, thrust_segments={"runway"})
        self.assertEqual(result["status"], "stopped")

        goal_segment_start = self.model.starts[self.level["goal"]["zone"]["segmentId"]]
        zone = self.level["goal"]["zone"]
        low = goal_segment_start + zone["from"]
        high = goal_segment_start + zone["to"]
        self.assertGreaterEqual(result["x"], low)
        self.assertLessEqual(result["x"], high)
        self.assertAlmostEqual(result["x"], 81.4, delta=0.2)  # 文档 §3.5 写的是 81.4 m

    def test_actor_actually_reaches_the_ice(self):
        result = self.model.simulate(self.level["spawn"], thrust_segments={"runway"})
        self.assertEqual(result["status"], "stopped")
        ice_start = self.model.starts["icefield"]
        self.assertLess(ice_start, result["x"])

    def test_rubber_swap_falls_short_of_the_same_zone(self):
        swapped = json.loads(json.dumps(self.level))
        for segment in swapped["terrain"]:
            if segment["surface"] == "ice":
                segment["surface"] = "rubber"
        model = ReferenceModel(swapped)
        result = model.simulate(swapped["spawn"], thrust_segments={"runway"})
        zone_start = model.starts[swapped["goal"]["zone"]["segmentId"]]
        low = zone_start + swapped["goal"]["zone"]["from"]
        self.assertLess(result["x"], low)
        self.assertAlmostEqual(result["x"], 28.3, delta=0.3)  # 文档 §3.5 写的是 28.3 m

    def test_ice_rubber_slide_ratio_is_at_least_three(self):
        mu_ice = self.level["surfaces"]["ice"]["mu"]
        mu_rubber = self.level["surfaces"]["rubber"]["mu"]
        ice = self.model.coast_distance(mu_ice, v0=10.0)
        rubber = self.model.coast_distance(mu_rubber, v0=10.0)
        self.assertGreaterEqual(ice / rubber, 3.0)
        self.assertAlmostEqual(ice / rubber, 18.0, delta=0.05)
        self.assertAlmostEqual(ice, 101.83, delta=0.05)  # s = v²/(2μg),文档 §2.9

    def test_slide_distance_is_independent_of_timestep(self):
        mu_ice = self.level["surfaces"]["ice"]["mu"]
        distances = [self.model.coast_distance(mu_ice, v0=10.0, dt=1 / hz) for hz in (30, 60, 120, 240)]
        for distance in distances:
            self.assertAlmostEqual(distance, distances[0], places=6)


if __name__ == "__main__":
    unittest.main()
