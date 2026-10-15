"""Acceptance checks for the issue #5 research card (REQ_DONE artifact).

These tests do not judge the research quality; they pin the acceptance
criteria that issue #5 states explicitly, so an accidental truncation or
deletion of the artifact fails in CI instead of silently unblocking #6:

* the artifact exists and is marked ``REQ_DONE``;
* the technology comparison names both render libraries and all four
  physics options and states one explicit recommendation with reasons;
* at least three borrowable cases are present;
* the MVP loop and the five-level knowledge-point layout are present.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CARD = (
    REPO_ROOT
    / "docs"
    / "research"
    / "issue-005-3d-web-game-tech-selection-and-inertia-game-design.md"
)

RENDER_LIBRARIES = ["Three.js", "Babylon.js"]
PHYSICS_OPTIONS = ["cannon-es", "Rapier", "Ammo.js", "自写简化刚体"]
CASE_TITLES = ["PhET", "Poly Bridge", "Sonic", "Algodoo"]
LEVEL_NAMES = ["起跑与刹车", "冰面还是橡胶地", "速度翻倍", "直着飞出去", "综合路线"]


class ResearchCardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CARD.read_text(encoding="utf-8")

    def test_artifact_exists_and_is_marked_req_done(self):
        self.assertTrue(CARD.is_file(), f"missing artifact: {CARD}")
        self.assertIn("REQ_DONE", self.text)

    def test_states_an_explicit_recommendation(self):
        self.assertRegex(self.text, r"推荐:\s*Three\.js\s*\+\s*cannon-es")
        self.assertIn("理由", self.text)

    def test_compares_both_render_libraries(self):
        for library in RENDER_LIBRARIES:
            self.assertIn(library, self.text)

    def test_compares_all_four_physics_options(self):
        for option in PHYSICS_OPTIONS:
            self.assertIn(option, self.text)

    def test_has_at_least_three_borrowable_cases(self):
        sections = re.findall(r"^### 2\.\d+ ", self.text, flags=re.MULTILINE)
        self.assertGreaterEqual(len(sections), 3)
        for title in CASE_TITLES:
            self.assertIn(title, self.text)
        self.assertGreaterEqual(self.text.count("可迁移"), 3)

    def test_has_sliding_distance_ratio_argument(self):
        # "ice vs rubber >= 3x" must be argued, not asserted by feel.
        self.assertIn("d = v₀² / (2μg)", self.text)
        self.assertGreaterEqual(self.text.count("≥3"), 2)

    def test_has_five_level_knowledge_point_layout(self):
        for name in LEVEL_NAMES:
            self.assertIn(name, self.text)
        rows = re.findall(r"^\| [1-5] \| ", self.text, flags=re.MULTILINE)
        self.assertGreaterEqual(len(rows), 5)

    def test_records_measured_bundle_sizes(self):
        for size in ["157,226", "388,788", "1,652,055"]:
            self.assertIn(size, self.text)


if __name__ == "__main__":
    unittest.main()
