"""Stdlib-only contract checks for the level format and its documented example.

Why this file exists next to ``test_level_schema.py``: the repository CI
(``.github/workflows/ci.yml``) installs only ``pytest``, so the ``jsonschema``
based checks in the other file are skipped there and drift would go unnoticed.
Everything here uses the standard library only, so it runs on every CI run.

It is deliberately *not* a general JSON Schema validator. It reads the
constraints that matter out of ``docs/schema/level.schema.json`` (required
fields, enums, numeric ranges, ``$defs`` references, ``if/then`` branch
requirements) and applies them to the example level embedded in
``docs/ARCHITECTURE.md`` -- so the doc and the schema cannot drift apart
silently. The full validator still runs wherever ``jsonschema`` is available.
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "level.schema.json"
ARCH_DOC_PATH = REPO_ROOT / "docs" / "ARCHITECTURE.md"
JSON_FENCE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)

# §2.10 is the parameter table in ARCHITECTURE.md; the reference integrator in the
# sibling test file carries the same numbers as fallbacks. Both must agree with the
# schema ``default``, which §3.6 designates as the single source of truth.
SECTION_2_10 = re.compile(r"### 2\.10 .*?\n(.*?)\n\n", re.DOTALL)
SECTION_6_3 = re.compile(r"### 6\.3 .*?\n(.*?)\n## ", re.DOTALL)

# 文档内嵌的那个示例关卡是这两个测试唯一的真实输入,而它没有 `obstacles` 数组、也没有
# 任何带 `lateralMin`/`lateralMax` 的 zone。于是 §6.1 断言 10 里"障碍引用完整性"与
# "`lateralMin < lateralMax`"这两条在示例上**没有样本**。
#
# 早先的写法把"没有样本"当成了"通过":`for obstacle in self.example.get("obstacles", [])`
# 与 `if "lateralMin" in zone and "lateralMax" in zone:` 都让循环体一次都不执行,测试
# 全绿,而 §6.3 却声称这两条"在当前 CI 上真实执行"。现在改法有两半,缺一不可:
#   1. 用下面这两个**合成样本**把同一段检查跑通 —— 死分支变成活分支,逻辑本身有覆盖;
#   2. 把缺口登记进 `EMPTY_SAMPLE_GAPS`,由 `test_documented_coverage_gaps_are_declared`
#      断言 §6.3 如实写明它们"在真实关卡上尚未执行"。
# 两半合起来才既不静默通过、也不谎称已覆盖。#7 接入真实关卡后,合成样本不再是唯一输入。
SYNTHETIC_OBSTACLES = (
    {"id": "synthetic-box", "shape": "box", "segmentId": "runway", "at": 1.0,
     "size": {"x": 0.5, "y": 0.5, "z": 0.5}},
    {"id": "synthetic-cylinder", "shape": "cylinder", "segmentId": "runway", "at": 2.0,
     "radius": 0.4, "height": 1.0},
)
SYNTHETIC_LATERAL_ZONE = {"segmentId": "?", "from": 1.0, "to": 2.0, "lateralMin": -1.0, "lateralMax": 1.0}
EMPTY_SAMPLE_GAPS = ("lateralMin < lateralMax", "obstacles 引用完整性", "defaultSurface 解析",
                     "arc/ramp 分支必填字段")

# 引擎内置材质 id。schema 里这个清单**只以散文形式存在**(`properties.surfaces`
# 的描述说"引擎内置 ice/normal/rubber 默认值,关卡可覆盖"),没有任何机器可读的
# 约束 —— 这正是 finding 14 说的 `defaultSurface` 是"裸字符串"。
#
# 它**不能**通过在 schema 里给 `defaultSurface` 加 `"enum": ["ice","normal","rubber"]`
# 来修:`surfaces` 的 `additionalProperties` 是自由的 `$defs/surface`,关卡完全可以
# 定义自定义材质(如"熔岩")并把它设为兜底;那个 enum 会连带否掉这种**合法**关卡,
# 用一个假阳性换一个假阴性。正确做法是把这个清单写成下面这个常量,由
# `test_builtin_surface_list_matches_the_documented_prose` 钉住它与文档散文一致,
# 再让 `assert_surface_resolves` 用"本关 surfaces 键 ∪ 内置清单"做解析。
BUILTIN_SURFACES = ("ice", "normal", "rubber")

# 合成关卡:一个自定义材质被 terrain 与 defaultSurface 同时引用(必须通过),
# 以及一个拼错的 defaultSurface(必须被拒)。示例关卡没有 `physics.defaultSurface`,
# 所以这条规则在真实关卡上没有样本,见模块头与 `EMPTY_SAMPLE_GAPS`。
SYNTHETIC_LEVEL_WITH_CUSTOM_DEFAULT_SURFACE = {
    "surfaces": {"lava": {"mu": 0.9, "color": "#ff2200"}},
    "terrain": [{"id": "s1", "surface": "lava"}],
    "physics": {"defaultSurface": "lava"},
}
SYNTHETIC_LEVEL_WITH_TYPOD_DEFAULT_SURFACE = {
    "surfaces": {"lava": {"mu": 0.9, "color": "#ff2200"}},
    "terrain": [{"id": "s1", "surface": "lava"}],
    "physics": {"defaultSurface": "laval"},
}


def load_sibling_test_module():
    """Import ``test_example_level_physics`` by path (no package, no sys.path games)."""
    path = REPO_ROOT / "tests" / "test_example_level_physics.py"
    spec = importlib.util.spec_from_file_location("_reference_integrator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def iter_refs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            yield from iter_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_refs(item)


class LevelFormatContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        blocks = [json.loads(block) for block in JSON_FENCE.findall(ARCH_DOC_PATH.read_text(encoding="utf-8"))]
        if not blocks:
            raise AssertionError("ARCHITECTURE.md should embed an example level JSON block")
        cls.example = blocks[0]
        cls.defs = cls.schema["$defs"]

    # --- the schema file itself -------------------------------------------------

    def test_schema_declares_2020_12_and_an_object_root(self):
        self.assertEqual(self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.schema["type"], "object")
        self.assertIs(self.schema["additionalProperties"], False)

    def test_schema_requires_the_fields_every_level_needs(self):
        required = set(self.schema["required"])
        self.assertLessEqual(
            {"schemaVersion", "id", "order", "title", "knowledgePoint", "spawn", "surfaces", "terrain", "goal", "teaching"},
            required,
        )

    def test_every_ref_resolves_to_a_defined_subschema(self):
        missing = {
            ref for ref in iter_refs(self.schema)
            if ref.startswith("#/$defs/") and ref.removeprefix("#/$defs/") not in self.defs
        }
        self.assertEqual(missing, set())

    # --- the documented example against the schema ------------------------------

    def test_example_has_exactly_the_declared_top_level_fields(self):
        required = set(self.schema["required"])
        allowed = set(self.schema["properties"])
        keys = set(self.example)
        self.assertEqual(required - keys, set(), "example is missing required top-level fields")
        self.assertEqual(keys - allowed, set(), "example has fields the schema rejects")

    def test_example_goal_uses_one_of_the_declared_discriminators(self):
        branches = self.schema["$defs"]["goal"]["oneOf"]
        by_type = {branch["properties"]["type"]["const"]: branch for branch in branches}
        goal_type = self.example["goal"]["type"]
        self.assertIn(goal_type, by_type)
        branch = by_type[goal_type]
        self.assertEqual(set(branch["required"]) - set(self.example["goal"]), set())
        self.assertEqual(set(self.example["goal"]) - set(branch["properties"]), set())

    def test_example_terrain_and_obstacle_branches_are_satisfied(self):
        self.assert_terrain_branch_requirements(self.example["terrain"])
        # 示例关卡的三个段**全是 `straight`**,所以 `arc`/`ramp` 两条腿在它上面一次都
        # 不执行(finding 14 附带指出的死分支,与 finding 8/9 同类)。这里补两个合成段
        # 把 `allOf` 的 if/then 逐条跑一遍,`assert_terrain_branch_requirements` 会照着
        # schema 查必填字段,而不是把"没样本"当成"通过"。
        # 合成样本若被清空,上面那行会静默通过(空集合上循环零次 = 没测)。所以这里
        # 反向断言:schema `allOf` 里出现的**每一个** branch 类型,必须在"示例关卡 ∪
        # 合成样本"里至少有一段真的走进去过。`assert_terrain_branch_requirements` 返回
        # 它实际命中过的类型集合,断言这个集合覆盖 schema 声明的全部 branch。
        exercised = self.assert_terrain_branch_requirements(self.example["terrain"])
        exercised |= self.assert_terrain_branch_requirements(self.synthetic_terrain_branches())
        self.assertEqual(exercised, self.terrain_branch_types(),
                         "有 allOf 分支在示例与合成样本上都没被走进 —— 空样本会静默通过")
        terrain_ids = {s["id"] for s in self.example["terrain"]}
        shapes = set(self.defs["obstacle"]["properties"]["shape"]["enum"])
        for obstacle in self.assert_obstacle_branches(self.example, terrain_ids):
            # 引用完整性:障碍必须落在真实存在的段上(schema 只查类型,不查存在性)。
            self.assertIn(obstacle["segmentId"], terrain_ids, obstacle.get("id"))
        for obstacle in self.assert_obstacle_branches({"obstacles": SYNTHETIC_OBSTACLES}):
            self.assertIn(obstacle["segmentId"], terrain_ids, obstacle.get("id"))
        self.assertIn("box", shapes)
        self.assertIn("cylinder", shapes)

    def synthetic_terrain_branches(self):
        """`arc` 与 `ramp` 各一个合成段,字段取自 §2.7 的语义。"""
        return [
            {"id": "synthetic-arc", "type": "arc", "length": 10.0, "width": 4.0,
             "surface": "normal", "curvature": 15.0},
            {"id": "synthetic-ramp", "type": "ramp", "length": 10.0, "width": 4.0,
             "surface": "normal", "grade": 20.0},
        ]

    def assert_terrain_branch_requirements(self, terrain):
        """照抄 `terrainSegment.allOf` 的 if/then,而不是硬编码 arc/ramp。

        硬编码会让测试与 schema 各说各话:schema 改了 branch 绑定,这里照旧通过。
        逐条读 `allOf` 则把"schema 说要什么"与"数据有没有"对上 —— 这也是
        finding 14 断言"`arc` 段可以不写 curvature"能否成立的关键。
        """
        exercised = set()
        for segment in terrain:
            segment_type = segment["type"]
            self.assertIn(segment_type, self.defs["terrainSegment"]["properties"]["type"]["enum"])
            for branch in self.defs["terrainSegment"]["allOf"]:
                condition = branch["if"]
                if segment_type != condition["properties"]["type"]["const"]:
                    continue
                exercised.add(segment_type)
                for field in branch["then"].get("required", []):
                    self.assertIn(field, segment,
                                  f"{segment['id']} (type={segment_type}) 缺少 schema 要求的 {field}")
        return exercised

    def terrain_branch_types(self):
        """`terrainSegment.allOf` 里每个 `if` 判别出来的类型 —— 即"必须被走进"的清单。

        从 schema 读,不硬编码:新增第三个 branch 时这个集合自动变大,上面那条覆盖
        断言立刻要求样本跟上,不会出现"schema 加了分支、样本没加、测试照旧绿"。
        """
        return {branch["if"]["properties"]["type"]["const"]
                for branch in self.defs["terrainSegment"]["allOf"]}

    def assert_obstacle_branches(self, level, terrain_ids=None):
        """障碍的 shape 判别式与 shape 专属必填字段。

        示例关卡没有 `obstacles`,所以这个循环体在示例上跑了**零次** —— 这正是
        finding 9 指出的死分支。调用方因此传两个输入:示例(目前为空)与
        `SYNTHETIC_OBSTACLES`(保证 box/cylinder 两条腿都被执行到)。
        """
        obstacles = list(level.get("obstacles") or [])
        shapes = set(self.defs["obstacle"]["properties"]["shape"]["enum"])
        for obstacle in obstacles:
            self.assertIn(obstacle["shape"], shapes, obstacle.get("id"))
            if obstacle["shape"] == "box":
                self.assertIn("size", obstacle)
            else:
                self.assertIn("radius", obstacle)
                self.assertIn("height", obstacle)
        return obstacles

    def test_example_enums_come_from_the_schema(self):
        def enum_of(*path):
            node = self.schema
            for key in path:
                node = node[key]
            return node

        surface_enum = enum_of("$defs", "surface", "properties", "pattern", "enum")
        for surface in self.example["surfaces"].values():
            if "pattern" in surface:
                self.assertIn(surface["pattern"], surface_enum)

        wall_enum = enum_of("$defs", "wall", "properties", "type", "enum")
        for segment in self.example["terrain"]:
            for wall in segment.get("walls", {}).values():
                self.assertIn(wall["type"], wall_enum)

        failure_enum = enum_of("$defs", "failure", "properties", "outOfBounds", "enum")
        if "outOfBounds" in self.example.get("failure", {}):
            self.assertIn(self.example["failure"]["outOfBounds"], failure_enum)

        shadow_enum = enum_of("$defs", "environment", "properties", "shadowQuality", "enum")
        if "shadowQuality" in self.example.get("environment", {}):
            self.assertIn(self.example["environment"]["shadowQuality"], shadow_enum)

    def test_example_numbers_are_inside_the_schema_ranges(self):
        mu_bounds = self.defs["surface"]["properties"]["mu"]
        for name, surface in self.example["surfaces"].items():
            self.assertGreaterEqual(surface["mu"], mu_bounds["minimum"], name)
            self.assertLessEqual(surface["mu"], mu_bounds["maximum"], name)

        length_bounds = self.defs["terrainSegment"]["properties"]["length"]
        for segment in self.example["terrain"]:
            self.assertGreater(segment["length"], length_bounds["exclusiveMinimum"], segment["id"])
            self.assertGreater(segment["width"], self.defs["terrainSegment"]["properties"]["width"]["exclusiveMinimum"])

        self.assertGreaterEqual(self.example["order"], self.schema["properties"]["order"]["minimum"])

    def test_goal_zone_stays_inside_its_segment(self):
        zone = self.example["goal"]["zone"]
        lengths = {segment["id"]: segment["length"] for segment in self.example["terrain"]}
        self.assertIn(zone["segmentId"], lengths)
        self.assertLess(zone["from"], zone["to"])
        self.assertLessEqual(zone["to"], lengths[zone["segmentId"]])

    def test_cross_field_comparisons_hold(self):
        """§6.1 断言 10 的跨字段部分:JSON Schema 2020-12 表达不了的大小关系。

        §4.1 的注释把断言 10/11 的自动化版本记在 `tests/levels/`(#7 起),但这三条
        是标准库就能查的,而且漂移代价高:`lateralMin >= lateralMax` 或
        `zone.from >= zone.to` 的判定区是空集 —— schema 全部通过,关卡却永远
        不可能过关。缺省 lateral 表示"取该段全宽"(schema 的 zone.lateralMin/
        lateralMax 描述),那时无需比较。
        """
        terrain_ids = {s["id"] for s in self.example["terrain"]}
        checked = 0
        for name, zone in self.zones():
            self.assertIn(zone["segmentId"], terrain_ids, name)
            self.assertLess(zone["from"], zone["to"], name)
            # 示例的 `goal.zone` 只有 from/segmentId/to,所以这个 `if` 在示例上恒假 ——
            # finding 8 指出的死分支。改成无条件调用 `assert_lateral_bounds`,它对
            # "两侧都缺省 / 只缺一侧 / 只给一侧"三种情形都给出明确结论,于是同一段
            # 逻辑在示例上也有执行路径,而不是悄悄跳过。
            checked += self.assert_lateral_bounds(zone, name)
        # 再拿一个**合成**的带横向边界的 zone 把 `lateralMin < lateralMax` 这条
        # 大小关系本身跑一遍(示例没有样本,见模块头 `EMPTY_SAMPLE_GAPS`)。
        checked += self.assert_lateral_bounds(dict(SYNTHETIC_LATERAL_ZONE, segmentId="stopzone"),
                                              "synthetic.lateral")
        self.assertGreater(checked, 0, "横向边界检查一次都没执行")

    def assert_lateral_bounds(self, zone, name):
        """返回实际比较过的横向边界对数(0 或 1)。

        缺省语义来自 schema 的 `zone.lateralMin`/`lateralMax` 描述:两侧都缺省表示
        "取该段全宽",此时无需求比较;只给一侧是**非法**的,因为另一侧会退化成
        段宽而不是显式值,判定区间的宽度将取决于关卡几何而非作者意图。
        """
        has_min = "lateralMin" in zone
        has_max = "lateralMax" in zone
        if not has_min and not has_max:
            return 0
        self.assertTrue(has_min and has_max,
                        f"{name}: lateralMin/lateralMax 必须成对出现(缺省 = 全宽)")
        self.assertLess(zone["lateralMin"], zone["lateralMax"], name)
        return 1

    def assert_surface_resolves(self, level, name):
        """`terrain[].surface` 与 `physics.defaultSurface` 的解析规则是同一条。

        schema 的 `terrainSegment.surface` 描述写的是"必须存在于本关 `surfaces`
        (或引擎内置默认材质)",`defaultSurface` 的描述写的是"`surfaces` 中作为兜底
        的材质 id" —— 后者漏了"或内置"这半句,而它恰恰是 `defaultSurface` 的默认值
        `"normal"` 合法的唯一理由(关卡可以不声明 `surfaces` 里的 `normal`)。两条
        规则必须是同一条,否则默认值自己就违反了描述。
        """
        declared = set(level.get("surfaces") or {})
        resolvable = declared | set(BUILTIN_SURFACES)
        used = {segment["surface"] for segment in level.get("terrain", [])}
        self.assertEqual(used - resolvable, set(), f"{name}: terrain 引用了无法解析的材质")
        fallback = (level.get("physics") or {}).get("defaultSurface")
        if fallback is not None:
            self.assertIn(fallback, resolvable,
                          f"{name}: defaultSurface={fallback!r} 既不在本关 surfaces 里,也不是内置材质")
        return fallback is not None

    def test_default_surface_resolves_like_a_terrain_surface(self):
        """finding 14 的第 4 条:schema 里两者都是裸 `{"type": "string"}`。

        `additionalProperties` 自由的 `$defs/surface` 意味着关卡可以自带材质,所以
        这里**不能**退化成"断言 defaultSurface ∈ {ice,normal,rubber}" —— 那会把
        `defaultSurface: "lava"` 这种合法关卡判成非法。要查的是**可解析性**。
        """
        self.assertFalse(self.assert_surface_resolves(self.example, "documented"),
                         "示例关卡没有 physics.defaultSurface,缺口应由 EMPTY_SAMPLE_GAPS 声明")
        # 自定义材质同时被 terrain 与 defaultSurface 引用:必须通过。
        self.assertTrue(self.assert_surface_resolves(
            SYNTHETIC_LEVEL_WITH_CUSTOM_DEFAULT_SURFACE, "synthetic.custom"))
        # 拼错的 defaultSurface:必须被拒。
        with self.assertRaises(AssertionError):
            self.assert_surface_resolves(SYNTHETIC_LEVEL_WITH_TYPOD_DEFAULT_SURFACE, "synthetic.typo")
        # 裸关卡(无 surfaces)靠内置 id 兜底 —— 默认值 "normal" 的合法性来源。
        self.assertTrue(self.assert_surface_resolves({"physics": {"defaultSurface": "normal"}}, "bare"))

    def test_builtin_surface_list_matches_the_documented_prose(self):
        """`BUILTIN_SURFACES` 是 schema 散文里那份清单的可执行副本,必须一致。

        schema 没有机器可读的内置材质表(`surfaces` 的描述只有散文),所以常量成了
        唯一真源;这条断言防止散文改了、常量没改 —— 那种漂移会让上面那条解析测试
        悄悄放行一个拼错的材质 id。
        """
        prose = self.schema["properties"]["surfaces"]["description"]
        for name in BUILTIN_SURFACES:
            self.assertIn(name, prose, f"schema 的 surfaces 描述未提及内置材质 {name}")
        self.assertEqual(len(BUILTIN_SURFACES), len(set(BUILTIN_SURFACES)), "内置材质清单不得重复")

    def test_documented_coverage_gaps_are_declared(self):
        """示例关卡盖不到的那两条,§6.3 必须写明"尚未执行",不能声称已覆盖。

        finding 13 的要害不是"少写了一条测试",而是**§6.3 把一个没有执行的检查说成
        在执行**。修完之后示例仍无 `obstacles`、仍无带横向边界的 zone,所以
        `EMPTY_SAMPLE_GAPS` 依然非空;这条测试保证文档不会忘记承认它。等 #7 接入
        真实关卡、缺口真的关上时,这条会失败并提醒把 §6.3 的分母改掉。
        """
        text = ARCH_DOC_PATH.read_text(encoding="utf-8")
        section = SECTION_6_3.search(text)
        self.assertIsNotNone(section, "ARCHITECTURE.md 应有 §6.3 一节")
        body = section.group(1)
        self.assertTrue(EMPTY_SAMPLE_GAPS, "缺口清单为空时应删掉这条测试与 §6.3 的免责句")
        for gap in EMPTY_SAMPLE_GAPS:
            self.assertIn(gap, body, f"§6.3 未声明 '{gap}' 在真实关卡上尚未执行")
        self.assertIn("尚未执行", body, "§6.3 应用'尚未执行'而不是含糊措辞描述缺口")

    def zones(self):
        """示例关卡里所有"段内里程 + 横向区间"的判定区间,带可读名字。

        ``stopInZone``/``reachGoal``/``maintainSpeed`` 用 ``zone``,``passGates`` 用
        ``gates``(数组,元素是同一个 ``$defs/zone``)—— 后者的顺序也有意义
        (schema:"必须按数组顺序依次通过"),所以逐项查而不是只查第一个。
        """
        goal = self.example["goal"]
        if "zone" in goal:
            yield "goal.zone", goal["zone"]
        for index, gate in enumerate(goal.get("gates", [])):
            yield f"goal.gates[{index}]", gate

    # --- defaults: schema ``default`` is the single source of truth (§3.6) -------

    def test_documented_defaults_match_schema(self):
        """§2.10 表 / 参考实现的兜底值 / schema 的 ``default`` 三者必须一致。

        §3.6 把 schema 的 ``default`` 定为唯一真源,但默认值在仓库里有三份拷贝
        (schema、§2.10 表、``ReferenceModel`` 的 ``.get(...)`` 兜底)。没有这条
        断言时,三份拷贝可以各自漂移,而"加关卡不改代码"恰恰依赖它们相等 ——
        尤其 ``restThreshold``(物理层)与 ``maxStopSpeed``(判定层)是两个
        职责不同的量(§2.10),漂移后会把"没停住"当成"停稳了"。
        """
        physics = self.defs["physicsOverrides"]["properties"]
        self.assertEqual(physics["restThreshold"]["default"], 0.05)
        self.assertEqual(physics["maxSpeed"]["default"], 12)
        self.assertEqual(physics["accel"]["default"], 12)
        self.assertEqual(physics["gravity"]["default"], 9.82)
        self.assertEqual(physics["airDrag"]["default"], 0)
        self.assertEqual(physics["defaultSurface"]["default"], "normal")

        turn = physics["turnAuthority"]["properties"]
        self.assertEqual(turn["vRef"]["default"], 8)
        self.assertEqual(turn["floor"]["default"], 0.3)
        self.assertEqual(turn["maxTurnRate"]["default"], 120)

        jump = physics["jump"]["properties"]
        self.assertEqual(jump["initialVerticalSpeed"]["default"], 5.5)
        self.assertEqual(jump["coyoteSeconds"]["default"], 0.1)

    def test_goal_mode_thresholds_have_schema_defaults(self):
        """``stopInZone`` 的 ``holdSeconds`` / ``maxStopSpeed`` 必须有 schema 默认值。

        判定层的阈值不像物理参数那样集中在 ``$defs.physicsOverrides`` 里,而是
        挂在各 ``goal`` 分支上,所以单独查一遍:漏掉 ``default`` 时 §2.10 的那两行
        就没有真源可比对。
        """
        branches = {b["properties"]["type"]["const"]: b for b in self.defs["goal"]["oneOf"]}
        stop = branches["stopInZone"]["properties"]
        self.assertEqual(stop["holdSeconds"]["default"], 0.5)
        self.assertEqual(stop["maxStopSpeed"]["default"], 0.3)
        # 判定层阈值必须比物理层静止阈宽松(§2.10 的论证),否则玩家还按着前进键时
        # 会被判失败。
        self.assertGreater(stop["maxStopSpeed"]["default"],
                           self.defs["physicsOverrides"]["properties"]["restThreshold"]["default"])

    def test_reference_integrator_fallbacks_equal_schema_defaults(self):
        """参考积分器的兜底值必须等于 schema 的 ``default``(§6.1 断言 14)。

        积分器用 ``physics.get(name, fallback)`` 读关卡;兜底只在示例关卡没写该字段
        时生效,而示例只写了 ``gravity``/``accel``/``maxSpeed``(其余为空档)。这里直
        接把兜底值和 schema 比一遍,而不是信任两处字面量恰好相同。
        """
        reference = load_sibling_test_module()
        physics = self.defs["physicsOverrides"]["properties"]
        # 空档(没有 physics 块)⇒ 每个属性都取兜底字面量。
        bare = reference.ReferenceModel({"terrain": [], "surfaces": {}})
        for schema_name, attribute in (
            ("gravity", "gravity"),
            ("accel", "accel"),
            ("maxSpeed", "max_speed"),
            ("restThreshold", "rest_threshold"),
        ):
            self.assertEqual(getattr(bare, attribute), physics[schema_name]["default"], schema_name)

    def test_documented_table_quotes_the_schema_defaults(self):
        """§2.10 表格里逐字写出的默认值必须与 schema 一致。

        文档表格是玩家和关卡作者实际会读的那份;只断言代码里的兜底值不够,表格
        自己也会漂移(它已经漂过一次:``maxStopSpeed`` 一度只存在于 schema 里)。
        """
        text = ARCH_DOC_PATH.read_text(encoding="utf-8")
        table = SECTION_2_10.search(text)
        self.assertIsNotNone(table, "ARCHITECTURE.md should keep a §2.10 parameter table")
        rows = table.group(1)
        physics = self.defs["physicsOverrides"]["properties"]

        def row_for(name):
            matches = [line for line in rows.splitlines()
                       if re.match(rf"\|\s*`?{re.escape(name)}`?\s*\|", line)]
            self.assertEqual(len(matches), 1, f"expected exactly one §2.10 row for {name}")
            return matches[0]

        self.assertIn("9.82", row_for("gravity"))
        self.assertIn("12 m/s", row_for("maxSpeed"))
        self.assertIn("12 m/s²", row_for("accel"))
        self.assertIn("0.05 m/s", row_for("restThreshold"))
        self.assertIn("0.3 m/s", row_for("stopInZone.maxStopSpeed"))
        self.assertIn("1/60 s", row_for("FIXED_DT"))
        self.assertEqual(physics["restThreshold"]["default"], 0.05)

    def test_rest_threshold_is_not_the_goal_stop_threshold(self):
        """两个阈值必须同时出现在 §2.10 表里,且不相等(§2.10 的区分段)。

        F-02 的形态是"schema 有一个 0.3、文档只讲 0.05":表格吞掉其中一个后,读者
        会以为物理层和判定层共用 0.05。这里断言两行都在,且文档确实做了区分。
        """
        text = ARCH_DOC_PATH.read_text(encoding="utf-8")
        rows = SECTION_2_10.search(text).group(1)
        self.assertIn("`restThreshold`", rows)
        self.assertIn("`stopInZone.maxStopSpeed`", rows)
        stop = {b["properties"]["type"]["const"]: b for b in self.defs["goal"]["oneOf"]}["stopInZone"]
        self.assertNotEqual(
            self.defs["physicsOverrides"]["properties"]["restThreshold"]["default"],
            stop["properties"]["maxStopSpeed"]["default"],
        )


if __name__ == "__main__":
    unittest.main()
