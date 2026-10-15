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

    def advance(self, v, a, dt=FIXED_DT):
        """§2.4 的 ``advanceAlongDirection(v, a, dt, maxSpeed)``,返回 ``(dv, ds)``。

        速度上限(§2.10 的 ``maxSpeed``)由**本函数**负责,调用方不再截断 ——
        若把 ``min(vmax, v + a*dt)`` 留在调用方、这里却仍返回未截断的 ``dv`` 与
        ``vmax*dt - 0.5*a*dt²``,饱和步就会短掉 ``0.5*a*dt²``,而那个式子是梯形
        恒等式,只在末速度未被截断时才成立。
        """
        if a == 0:
            return 0.0, v * dt                       # 无摩擦:匀速直线(也避免 0/0)
        if a < 0 and v + a * dt <= 0:
            return -v, (v * v) / (-2 * a)            # 本步内停住:s = v²/(2|a|)
        v_unclamped = v + a * dt
        if a > 0 and v_unclamped > self.max_speed:
            # 本步内到达限速:在 t_cap = (vmax - v)/a 处拆成两段解析推进,
            # 与"停住步"同一个手法。饱和步(v == vmax)因此正好推进 vmax*dt。
            t_cap = (self.max_speed - v) / a
            ds = v * t_cap + 0.5 * a * t_cap * t_cap
            ds += self.max_speed * (dt - t_cap)
            return self.max_speed - v, ds
        return v_unclamped - v, v_unclamped * dt - 0.5 * a * dt * dt

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
            dv, ds = self.advance(v, a)
            v += dv
            x += ds
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
            dv, ds = self.advance(v, a, dt)
            v += dv
            x += ds
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
        # 文档 §3.5 写的是 81.4 m(离散模型值;解析链给 81.3,差一个步长量级)。
        # 容差取 0.3:实测 1/60 积分值 81.399,距 81.4 仅 0.001 m,但整关结果会随
        # dt 漂移(1/30 → 81.599,1/240 → 81.349,见 §5.3),0.2 的余量太薄,
        # 微调 restThreshold 就会假红。
        self.assertAlmostEqual(result["x"], 81.4, delta=0.3)

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
        self.assertAlmostEqual(result["x"], 28.2, delta=0.3)  # 文档 §3.5 写的是 28.2 m

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

    def test_saturated_step_advances_exactly_max_speed_times_dt(self):
        """达到限速后仍在加速的步,位移必须正好是 vmax*dt。

        这是 F-01 的判别式:把 ``min(vmax, v + a*dt)`` 留在调用方、位移仍写
        ``vmax*dt - 0.5*a*dt²`` 时,每一步都短掉 ``0.5*a*dt²``(本关 1/60 下
        0.001326 m,58 个饱和步累计 0.078 m),而那个式子是梯形恒等式,
        只在末速度未被截断时成立。解析拆分给出正好 vmax*dt。
        """
        a = self.model.accel - self.level["surfaces"]["normal"]["mu"] * self.model.gravity
        self.assertGreater(a, 0)
        dv, ds = self.model.advance(self.model.max_speed, a)
        self.assertEqual(dv, 0.0)                              # 已在限速上,不能再加速
        self.assertAlmostEqual(ds, self.model.max_speed * FIXED_DT, places=12)

    def test_ramp_to_max_speed_matches_the_documented_distance(self):
        """§2.10 / §3.5:0 → maxSpeed 在普通地面上需要 7.66 m(离散)。"""
        a = self.model.accel - self.level["surfaces"]["normal"]["mu"] * self.model.gravity
        x, v = 0.0, 0.0
        while v < self.model.max_speed:
            dv, ds = self.model.advance(v, a)
            self.assertGreater(dv, 0.0)                        # 必须会走到限速,不是死循环
            v += dv
            x += ds
        self.assertAlmostEqual(x, 7.66, delta=0.02)
        # 解析值 v²/(2a) = 144/(2×9.545) = 7.543 m,与离散值差一个步长的量级。
        self.assertAlmostEqual(x, 144 / (2 * a), delta=0.2)


if __name__ == "__main__":
    unittest.main()
