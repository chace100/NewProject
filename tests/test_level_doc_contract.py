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

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "level.schema.json"
ARCH_DOC_PATH = REPO_ROOT / "docs" / "ARCHITECTURE.md"
JSON_FENCE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)


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


if __name__ == "__main__":
    unittest.main()
