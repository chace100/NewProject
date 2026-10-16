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
        if v > self.max_speed:
            # 越限输入(``spawn.speed`` 无上界,``maxSpeed`` 又是关卡可覆盖的)必须
            # 在这里、且在 ``a == 0`` 与"本步内停住"**之前**拦住:那两个分支只看
            # ``v + a * dt``,会把越限状态当成普通一步放过去,``ds`` 于是冲破
            # ``maxSpeed*dt``(a == 0、v == 40 时是 0.6667,3.33 倍)。原先的守卫写作
            # ``a > 0 and v >= max_speed``,于是越限状态只要落在无摩擦(a == 0)或
            # 滑行(a == -μg < 0)的段上就完全不受限速约束。限速是硬上限,一步回到
            # ``maxSpeed``:本步位移按 ``maxSpeed*dt`` 算,之后 ``v <= maxSpeed``,
            # 分派即恢复正常(滑行段照常减速,不会被永久钉在限速上)。
            return self.max_speed - v, self.max_speed * dt
        if a == 0:
            return 0.0, v * dt                       # 无摩擦:匀速直线(也避免 0/0)
        if a < 0 and v + a * dt <= 0:
            return -v, (v * v) / (-2 * a)            # 本步内停住:s = v²/(2|a|)
        v_unclamped = v + a * dt
        if a > 0 and v_unclamped > self.max_speed:
            # 本步内到达限速:在 t_cap = (vmax - v)/a 处拆成两段解析推进,
            # 与"停住步"同一个手法。饱和步(v == vmax)因此正好推进 vmax*dt。
            # 上面的越限拦截保证这里 ``v <= vmax``,所以 ``t_cap >= 0`` —— 两段式
            # 不会退化成 ``maxSpeed*dt - (v-maxSpeed)²/(2a)``(它在 v 越过
            # √(2·a·maxSpeed·dt) 时变负)。这条退化现在是结构上不可能的,不再需要
            # 单独一条 ``v >= max_speed`` 守卫。
            t_cap = (self.max_speed - v) / a
            ds = v * t_cap + 0.5 * a * t_cap * t_cap
            ds += self.max_speed * (dt - t_cap)
            return self.max_speed - v, ds
        return v_unclamped - v, v_unclamped * dt - 0.5 * a * dt * dt

    def simulate(self, spawn, thrust_segments, max_seconds=120.0, dt=FIXED_DT,
                 clamp_in_caller=False, stop_x_only=False):
        """示例关卡的唯一主循环;所有变体(调用方截断、变 dt、只要终点 x)都走它。

        ``thrust_segments``: 在这些段 id 上按住前进键,其余段松开。

        本函数是**同一条轨迹循环的唯一副本**。此前 ``stop_x_with_caller_clamp`` 与
        ``stop_x_at_timestep`` 各自逐字复制了一份(段查找、``mu`` 查找、推力选择、
        停止判据),三份必须同步;而它们断言的那些数(81.3849 / 81.3989 / dt 梯子)
        只有在三份对"停止判据"和"材质查找"的理解一致时才有意义 —— 改一份而漏掉
        另一份,容差分析会静默失效。现在三者是同一个循环的三个参数:

        - ``clamp_in_caller=True``:复刻 F-01 的缺陷读法(先 ``min(maxSpeed, v+a*dt)``
          截断、再用截断后的 ``v`` 算 ``v*dt - 0.5*a*dt²``),用来证明 §3.5 那条
          0.3 容差**区分不了**两种读法。
        - ``dt=1/hz``:给容差分析用的 dt 梯子。
        - ``stop_x_only=True``:只返回 ``x``(梯子与缺陷读法都只要终点)。
        """
        x = self.starts[spawn["segmentId"]] + spawn.get("at", 0.0)
        v = spawn.get("speed", 0.0)
        elapsed = 0.0
        status = "timeout"
        while elapsed < max_seconds:
            segment = self.segment_at(x)
            if segment is None:
                status = "left-track"
                break
            mu = self.surfaces[segment["surface"]]["mu"]
            thrust = self.accel if segment["id"] in thrust_segments else 0.0
            a = thrust - mu * self.gravity
            if clamp_in_caller:
                # 缺陷读法:截断在**调用方**,位移仍按未截断的梯形公式算。饱和步
                # 因此每步短掉 ``0.5*a*dt²``(0.001326 m / 58 步 = 0.078 m)。
                if a < 0 and v + a * dt <= 0:
                    x += (v * v) / (-2 * a)
                    v = 0.0
                else:
                    v = min(self.max_speed, v + a * dt)
                    x += v * dt - 0.5 * a * dt * dt
            else:
                dv, ds = self.advance(v, a, dt)
                v += dv
                x += ds
            elapsed += dt
            if v <= self.rest_threshold and segment["id"] not in thrust_segments:
                status = "stopped"
                break
        if stop_x_only:
            return x
        return {"status": status, "x": x, "v": v, "time": elapsed}

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
        # F-01 的缺陷读法:先 `v = min(maxSpeed, v + a*dt)` **截断**,再用**已截断的**
        # `v` 去算 `v*dt - 0.5*a*dt²`。那个式子是梯形恒等式,只在末速度未被截断时才
        # 等于真实位移,所以每个饱和步都短掉 `0.5*a*dt²`。这曾经是 `simulate` 主循环
        # 的第二份逐字副本(finding 7),现在只是同一个循环的一个参数 —— 否则两份对
        # "停止判据/材质查找"的理解一旦分叉,下面这几个数就悄悄失去意义。
        fixed = self.model.simulate(self.level["spawn"], thrust_segments={"runway"})["x"]
        defective = self.model.simulate(self.level["spawn"], thrust_segments={"runway"},
                                        clamp_in_caller=True, stop_x_only=True)

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
        ladder = {hz: self.model.simulate(self.level["spawn"], thrust_segments={"runway"},
                                          dt=1 / hz, stop_x_only=True)
                  for hz in (30, 60, 120, 240, 480)}
        span = max(ladder.values()) - min(ladder.values())
        self.assertEqual(sorted(ladder), [30, 60, 120, 240, 480])
        self.assertAlmostEqual(ladder[30], 81.5993, delta=1e-3)
        self.assertAlmostEqual(ladder[480], 81.3319, delta=1e-3)
        self.assertAlmostEqual(span, 0.2675, delta=1e-3)
        self.assertGreater(span, 0.2, "梯子全距超过 0.2 ⇒ 容差 0.2 不可用")
        self.assertLess(span, 0.3, "梯子全距仍在 0.3 之内 ⇒ 容差 0.3 够用")

    def test_over_cap_step_never_moves_backwards(self):
        """``v > maxSpeed`` 是合法输入,越限步的位移必须非负(§2.4 的越限拦截)。

        ``spawn.speed`` 在 schema 里只有 ``minimum: 0``、没有最大值,``maxSpeed``
        又是逐关可覆盖的,所以 ``v`` 已经高于限速是**可达状态**,不是防御性假设。
        未加拦截时 ``t_cap = (maxSpeed - v)/a`` 为负,两段式退化成
        ``ds = maxSpeed*dt - (v-maxSpeed)²/(2a)``,越过 ``√(2·a·maxSpeed·dt)``
        (本关 1.954 m/s)后位移变负 —— 角色第一帧倒退,随后跑出赛道起点被判失败。

        **三种 ``a`` 都要探。** 只探推力中的 ``a > 0`` 会让"越限守卫带 ``a > 0``
        合取词"这个缺陷全绿地通过:一旦合取词在,``a == 0``(冰面 ``mu = 0``,
        schema 允许)与 ``a < 0``(任何滑行段)的越限状态就绕过守卫,直接落到
        ``advance`` 末尾的通用返回,``ds`` 是 ``v*dt`` 而非 ``maxSpeed*dt`` ——
        ``a == 0, v == 40`` 时 0.6667 m,3.33 倍于文档上界。``a = -2.455`` 取本关
        普通地面滑行的减速度(``mu = 0.25``),是真实的第二种符号。

        本测试直接探 ``advance``:本关 ``spawn.speed`` 为 0,``simulate``
        ``/coast_distance`` 一般从 ``v <= maxSpeed`` 起步;但关卡数据给出
        ``spawn.speed > maxSpeed`` 时它们走得到,端到端版本见
        ``test_level_with_spawn_speed_over_the_cap_stays_on_the_track``。
        """
        thrust_a = self.model.accel - self.level["surfaces"]["normal"]["mu"] * self.model.gravity
        coast_a = -self.level["surfaces"]["normal"]["mu"] * self.model.gravity
        self.assertGreater(thrust_a, 0)
        self.assertLess(coast_a, 0)

        for a in (thrust_a, 0.0, coast_a):
            cap = self.model.max_speed * FIXED_DT
            # 只有 a > 0 才存在"本步内到达限速"的临界速度(也是两段式退化的临界点)。
            # a <= 0 时它没有实根 —— 那正是需要"守卫独立于 a"的原因。
            probes = [self.model.max_speed, 13.0, 14.1, 20.0, 40.0]
            if a > 0:
                probes.append(self.model.max_speed
                              + (2 * a * self.model.max_speed * FIXED_DT) ** 0.5)
            for v in probes:
                dv, ds = self.model.advance(v, a)
                self.assertGreaterEqual(ds, 0.0, f"a={a} v={v} 的位移为负")
                self.assertLessEqual(dv, 0.0, f"a={a} v={v} 越限时不得再加速")
                # 越限步也只按限速推进:既不能倒退,也不能比 vmax*dt 走得更远
                self.assertLessEqual(ds, cap + 1e-12, f"a={a} v={v} 越限步超过 vmax*dt")
            if a >= 0:
                # 恰在限速上时与解析拆分一致(两分支在 v == maxSpeed 处必须重合)。
                # a < 0 时不该重合:v == maxSpeed 并未越限,角色只是正常减速,
                # 位移是 0.19966 而非 0.2 —— 把那条也算进来会误伤正确实现。
                self.assertAlmostEqual(self.model.advance(self.model.max_speed, a)[1],
                                       cap, places=12)

    def test_zero_friction_surface_cannot_uncap_an_over_speed_spawn(self):
        """``mu = 0`` 是 schema 合法值(``minimum: 0``),它让 ``a == 0`` 可达。

        越限守卫一旦带 ``a > 0`` 合取词,``mu = 0`` 的冰面就把限速完全关掉:
        ``spawn.speed = 40`` 时角色一路滑到赛道尽头 x = 89.328,而文档关卡在
        81.406 停住 —— 7.9 m 的额外行程,整套测试当时没有一条看得见。这里把
        schema 边界接到物理层上:``mu = 0`` 只该让**减速**消失,不该让**限速**
        消失,所以越限的那一帧仍然只推进 ``maxSpeed*dt``。
        """
        level = json.loads(json.dumps(self.level))
        level["surfaces"]["ice"] = dict(level["surfaces"]["ice"], mu=0.0)
        model = ReferenceModel(level)
        self.assertEqual(level["surfaces"]["ice"]["mu"], 0.0)

        # 单帧:越限且在无摩擦段上,a == 0,位移必须仍被限速钳住。
        dv, ds = model.advance(40.0, 0.0)
        self.assertLessEqual(ds, model.max_speed * FIXED_DT + 1e-12, "无摩擦越限步超过 vmax*dt")
        self.assertLess(dv, 0.0, "越限状态必须被拉回限速")

        # 整关:无摩擦冰面不会停住角色(没有减速),所以它必然滑到赛道尽头 ——
        # 这是关卡数据本身的性质,不是限速失效。断言的是"越限的初速没有把
        # 第一帧的位移放大",而不是终点位置。
        level["spawn"]["speed"] = 40.0
        model = ReferenceModel(level)
        result = model.simulate(level["spawn"], thrust_segments={"runway"})
        self.assertNotEqual(result["status"], "left-track",
                            "越限 + 无摩擦不得把角色推出赛道起点一侧")
        self.assertGreaterEqual(result["x"], 0.0)

    def test_level_with_spawn_speed_over_the_cap_stays_on_the_track(self):
        """整关复现:``spawn.speed`` 越限 / ``maxSpeed`` 被调低时,不许倒退跑出赛道。

        这是上面那条单步断言的端到端版本,也是复审给出的两条合法路径。
        收敛值也一并钉住,免得"状态恰好不是 left-track"这种巧合让断言失效:
        越限的初速很快被限速与冰面摩擦吃掉,所以 20 和 40 收敛到同一个终点;
        ``maxSpeed = 6`` 的那一关则因为限速更低而提前停在判定区之前 —— 那是
        正确的(关卡设计如此),不是"倒退跑出赛道"。

        但**收敛值本身不区分实现**:任何"越限帧多跑几米、之后照样收在同一处"
        的实现都满足它。真正有判别力的是第一帧的位移上界,所以两行都加断言。
        """
        thrust_a = self.model.accel - self.level["surfaces"]["normal"]["mu"] * self.model.gravity
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
            # 判别式:越限的第一帧必须被限速钳住(§6.1 断言 13 对 v > maxSpeed 的承诺)。
            dv0, ds0 = model.advance(spawn_speed, thrust_a)
            self.assertLessEqual(ds0, model.max_speed * FIXED_DT + 1e-12,
                                 f"spawn.speed={spawn_speed} 的首帧位移超过 vmax*dt")

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
