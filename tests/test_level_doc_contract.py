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
        for segment in self.example["terrain"]:
            segment_type = segment["type"]
            self.assertIn(segment_type, self.defs["terrainSegment"]["properties"]["type"]["enum"])
            if segment_type == "arc":
                self.assertIn("curvature", segment)
            if segment_type == "ramp":
                self.assertIn("grade", segment)
        for obstacle in self.example.get("obstacles", []):
            if obstacle["shape"] == "box":
                self.assertIn("size", obstacle)
            else:
                self.assertIn("radius", obstacle)
                self.assertIn("height", obstacle)

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
        for name, zone in self.zones():
            self.assertIn(zone["segmentId"], {s["id"] for s in self.example["terrain"]}, name)
            self.assertLess(zone["from"], zone["to"], name)
            if "lateralMin" in zone and "lateralMax" in zone:
                self.assertLess(zone["lateralMin"], zone["lateralMax"], name)

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
