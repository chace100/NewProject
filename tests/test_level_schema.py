"""Guards for the architecture deliverables (issue #6).

The level JSON Schema is a committed contract: it must stay a valid JSON Schema
and every example embedded in the design doc must actually conform to it.
These tests skip cleanly when the optional ``jsonschema`` package is missing.
"""

import json
import re
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - dependency is optional for this repo
    Draft202012Validator = None

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "level.schema.json"
ARCH_DOC_PATH = REPO_ROOT / "docs" / "ARCHITECTURE.md"

# Matches ```json ... ``` blocks in the design doc, so the doc and the schema
# cannot drift apart silently.
JSON_FENCE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)


@unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
class LevelSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)
        cls.examples = [
            json.loads(block) for block in JSON_FENCE.findall(ARCH_DOC_PATH.read_text(encoding="utf-8"))
        ]

    def test_design_doc_contains_at_least_one_level_example(self):
        self.assertTrue(self.examples, "ARCHITECTURE.md should embed an example level JSON block")

    def test_documented_level_examples_are_valid(self):
        for example in self.examples:
            errors = sorted(self.validator.iter_errors(example), key=lambda error: error.path)
            self.assertEqual(errors, [], f"invalid example level: {[error.message for error in errors]}")

    def test_missing_required_field_is_rejected(self):
        example = json.loads(json.dumps(self.examples[0]))
        del example["goal"]
        self.assertTrue(list(self.validator.iter_errors(example)))

    def test_unknown_fields_are_rejected(self):
        example = json.loads(json.dumps(self.examples[0]))
        example["typoedField"] = 1
        self.assertTrue(list(self.validator.iter_errors(example)))


if __name__ == "__main__":
    unittest.main()
