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
        if a > 0 and v >= self.max_speed:
            # 已在限速之上:先截断,位移只按限速算。不能落到下面的 t_cap 拆分 ——
            # v > max_speed 时 t_cap = (maxSpeed - v)/a < 0,两段式退化成
            # ds = maxSpeed*dt - (v-maxSpeed)²/(2a),越过 √(2·a·maxSpeed·dt) 就变负。
            return self.max_speed - v, self.max_speed * dt
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
        #
        # 容差 0.3 是被 dt 漂移逼出来的,不是为了宽松:整关终点 = 跑道推进 +
        # 限速步 + 滑行,前两段按步长离散,实测梯子 1/30 → 81.5993、1/60 →
        # 81.3989、1/120 → 81.3989、1/240 → 81.3489、1/480 → 81.3319(§5.3),
        # 全距 0.2675 m。容差 0.2 时 1/30 剩 0.0007 m 余量(偏离 0.1993)——
        # 恰好还通过,但已贴边界,任何合法改动都会挤出去,所以取 0.3。
        #
        # **但这条容差区分不了 F-01。** 把限速截断留在调用方(每个饱和步短掉
        # 0.5*a*dt²,整关累计 0.078 m)时,1/60 读数是 81.3849 —— 与修好后的
        # 81.3989 只差 0.014 m,两者都落在 [81.1, 81.7] 内。所以本断言只负责
        # "示例关卡自洽"(§6.1 断言 11),F-01 的判别式是断言 13 的
        # `ds == maxSpeed*dt`(±1e-12)与下面那条越限守卫,不是这里。
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

    def test_documented_tolerance_cannot_discriminate_the_clamp_placement(self):
        """上面那条 `81.4 ± 0.3` 的接受窗口**不是** F-01 的判别式,这里把它钉死。

        复审指出该断言的接受窗口是 [81.1, 81.7](原文在此处截断,能读到的就是
        "the accepted window is [81.1, 81.")。对,而且这正是问题所在:把限速截断
        留在调用方 —— 也就是 F-01 的缺陷读法 —— 1/60 下停在 81.3849,修好后停在
        81.3989,两者只差 0.014 m,**都在窗口内**。所以这条断言证明不了积分器
        写对了,只证明"示例关卡自洽"(§6.1 断言 11)。真正的判别式是断言 13 的
        `ds == maxSpeed*dt`(±1e-12)与 `test_over_cap_step_never_moves_backwards`。

        把"容差挡不住 F-01"与"容差不能再收紧"两件事都写成断言(而不只是注释):
        前者靠两种读法都落在窗口内,后者靠 dt 梯子的全距 —— 谁把容差改成 0.2 或
        更小,`span > 0.2` 这条会先红,而不是等到某个 1/30 的机器上偶发假红。
        """
        def stop_x_with_caller_clamp(level):
            """F-01 的缺陷读法,逐字复刻 5806db7 的 ``simulate`` 主循环。

            关键在顺序:先 ``v = min(maxSpeed, v + a*dt)`` **截断**,再用**已截断的**
            ``v`` 去算 ``v*dt - 0.5*a*dt²``。那个式子是梯形恒等式,只在末速度未被
            截断时才等于真实位移,所以每个饱和步都短掉 ``0.5*a*dt²``。
            """
            model = ReferenceModel(level)
            x = model.starts[level["spawn"]["segmentId"]] + level["spawn"].get("at", 0.0)
            v = level["spawn"].get("speed", 0.0)
            elapsed = 0.0
            while elapsed < 120.0:
                segment = model.segment_at(x)
                mu = model.surfaces[segment["surface"]]["mu"]
                thrust = model.accel if segment["id"] == "runway" else 0.0
                a = thrust - mu * model.gravity
                if a < 0 and v + a * FIXED_DT <= 0:            # 本步内停住,解析
                    x += (v * v) / (-2 * a)
                    v = 0.0
                else:
                    v = min(model.max_speed, v + a * FIXED_DT)  # 截断在调用方 —— 缺陷所在
                    x += v * FIXED_DT - 0.5 * a * FIXED_DT * FIXED_DT
                elapsed += FIXED_DT
                if v <= model.rest_threshold and segment["id"] != "runway":
                    break
            return x

        fixed = self.model.simulate(self.level["spawn"], thrust_segments={"runway"})["x"]
        defective = stop_x_with_caller_clamp(self.level)

        window = (81.4 - 0.3, 81.4 + 0.3)
        self.assertAlmostEqual(defective, 81.3849, delta=1e-4)       # 缺陷读法
        self.assertAlmostEqual(fixed, 81.3989, delta=1e-4)           # 修好的读法
        # 两种读法都落在接受窗口内 ⇒ 这条容差区分不了它们
        for read in (defective, fixed):
            self.assertLess(window[0], read)
            self.assertGreater(window[1], read)

        # 容差取 0.3 的真正理由:整关终点随 dt 漂移,梯子全距 ~0.27 m。
        # 容差 0.2 时 1/30 那端只剩 0.0007 m 余量(实测 81.5993,偏离 0.1993),
        # 也就是"刚好还在窗口里"——任何合法的小改动都会把它挤出去。容差必须
        # 覆盖整条梯子,这就是 0.3 的来源,而不是精度需要。
        ladder = {hz: self.stop_x_at_timestep(1 / hz) for hz in (30, 60, 120, 240, 480)}
        span = max(ladder.values()) - min(ladder.values())
        self.assertEqual(sorted(ladder), [30, 60, 120, 240, 480])
        self.assertAlmostEqual(ladder[30], 81.5993, delta=1e-3)
        self.assertAlmostEqual(ladder[480], 81.3319, delta=1e-3)
        self.assertAlmostEqual(span, 0.2675, delta=1e-3)
        self.assertGreater(span, 0.2, "梯子全距超过 0.2 ⇒ 容差 0.2 不可用")
        self.assertLess(span, 0.3, "梯子全距仍在 0.3 之内 ⇒ 容差 0.3 够用")

    def stop_x_at_timestep(self, dt):
        """示例关卡按文档策略走一遍,用给定的 dt(``simulate`` 固定 1/60)。"""
        model = self.model
        x = model.starts[self.level["spawn"]["segmentId"]] + self.level["spawn"].get("at", 0.0)
        v = self.level["spawn"].get("speed", 0.0)
        elapsed = 0.0
        while elapsed < 120.0:
            segment = model.segment_at(x)
            if segment is None:
                return x
            mu = model.surfaces[segment["surface"]]["mu"]
            thrust = model.accel if segment["id"] == "runway" else 0.0
            dv, ds = model.advance(v, thrust - mu * model.gravity, dt)
            v += dv
            x += ds
            elapsed += dt
            if v <= model.rest_threshold and segment["id"] != "runway":
                break
        return x

    def test_over_cap_step_never_moves_backwards(self):
        """``v > maxSpeed`` 是合法输入,越限步的位移必须非负(§2.4 的越限守卫)。

        ``spawn.speed`` 在 schema 里只有 ``minimum: 0``、没有最大值,``maxSpeed``
        又是逐关可覆盖的,所以 ``v`` 已经高于限速是**可达状态**,不是防御性假设。
        未加守卫时 ``t_cap = (maxSpeed - v)/a`` 为负,两段式退化成
        ``ds = maxSpeed*dt - (v-maxSpeed)²/(2a)``,越过 ``√(2·a·maxSpeed·dt)``
        (本关 1.954 m/s)后位移变负 —— 角色第一帧倒退,随后跑出赛道起点被判失败。

        本测试直接探 ``advance``:``simulate``/``coast_distance`` 两个调用点都从
        ``v <= maxSpeed`` 起步,**永远走不到这条分支**,所以只能在这里测。
        """
        a = self.model.accel - self.level["surfaces"]["normal"]["mu"] * self.model.gravity
        self.assertGreater(a, 0)
        threshold = self.model.max_speed + (2 * a * self.model.max_speed * FIXED_DT) ** 0.5

        for v in (self.model.max_speed, 13.0, threshold, 14.1, 20.0, 40.0):
            dv, ds = self.model.advance(v, a)
            self.assertGreaterEqual(ds, 0.0, f"v={v} 的位移为负")
            self.assertLessEqual(dv, 0.0, f"v={v} 越限时不得再加速")
            # 越限步也只按限速推进:既不能倒退,也不能比 vmax*dt 走得更远
            self.assertLessEqual(ds, self.model.max_speed * FIXED_DT + 1e-12, f"v={v}")
        # 恰在限速上时与解析拆分一致(两分支在 v == maxSpeed 处必须重合)
        self.assertAlmostEqual(self.model.advance(self.model.max_speed, a)[1],
                               self.model.max_speed * FIXED_DT, places=12)

    def test_level_with_spawn_speed_over_the_cap_stays_on_the_track(self):
        """整关复现:``spawn.speed`` 越限 / ``maxSpeed`` 被调低时,不许倒退跑出赛道。

        这是上面那条单步断言的端到端版本,也是复审给出的两条合法路径。
        收敛值也一并钉住,免得"状态恰好不是 left-track"这种巧合让断言失效:
        越限的初速很快被限速与冰面摩擦吃掉,所以 20 和 40 收敛到同一个终点;
        ``maxSpeed = 6`` 的那一关则因为限速更低而提前停在判定区之前 —— 那是
        正确的(关卡设计如此),不是"倒退跑出赛道"。
        """
        for spawn_speed, cap, expected_x in (
            (20.0, None, 81.4060),
            (40.0, None, 81.4060),
            (12.0, 6.0, 56.6580),
        ):
            level = json.loads(json.dumps(self.level))
            level["spawn"]["speed"] = spawn_speed
            if cap is not None:
                level["physics"]["maxSpeed"] = cap
            model = ReferenceModel(level)
            result = model.simulate(level["spawn"], thrust_segments={"runway"})
            self.assertEqual(result["status"], "stopped",
                             f"spawn.speed={spawn_speed} maxSpeed={cap}")
            self.assertAlmostEqual(result["x"], expected_x, delta=1e-3,
                                   msg=f"spawn.speed={spawn_speed} maxSpeed={cap}")
            self.assertGreaterEqual(result["x"], 0.0,
                                    f"spawn.speed={spawn_speed} maxSpeed={cap}")

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
