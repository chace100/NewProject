"""Acceptance checks for the issue #5 research card (REQ_DONE artifact).

These tests pin issue #5's acceptance criteria so that a truncated, gutted or
internally inconsistent artifact fails CI instead of silently unblocking #6.
They check structure and derived values, not just the presence of tokens:

* the artifact exists, is marked ``REQ_DONE``, and a missing artifact is
  reported as one readable failure rather than a stack trace;
* the technology comparison is a real table naming both render libraries and
  all four physics options, each with a measured size;
* each borrowable case carries prose plus a transferable-design bullet list;
* the card's own stated friction parameters reproduce the sliding-distance
  ratio it claims;
* the physics constraints found in review are documented: single-argument
  ``world.step(1/60)``, the friction *product* rule and the character material,
  and no dangling level reference or "inertia grows with speed" wording.
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
PHYSICS_OPTIONS = ["**cannon-es**", "**Rapier**", "**Ammo.js**", "**自写简化刚体**"]
CASE_TITLES = ["PhET", "Poly Bridge", "Sonic", "Algodoo"]
LEVEL_NAMES = ["起跑与刹车", "冰面还是橡胶地", "速度翻倍", "直着飞出去", "综合路线"]
PINNED_VERSIONS = [
    "three@0.186.1",
    "@babylonjs/core@9.30.0",
    "cannon-es@0.20.0",
    "@dimforge/rapier3d-compat@0.21.0",
]


def _tables(text):
    """Yield each markdown table in ``text`` as a list of row cell-lists."""
    rows = []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):  # separator row
                continue
            rows.append(cells)
        elif rows:
            yield rows
            rows = []
    if rows:
        yield rows


def _section(text, heading, stop=r"^#{2,3} "):
    start = text.index(heading)
    match = re.search(stop, text[start + len(heading):], flags=re.MULTILINE)
    end = start + len(heading) + (match.start() if match else len(text) - start)
    return text[start:end]


class ResearchCardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CARD.read_text(encoding="utf-8") if CARD.is_file() else ""

    def setUp(self):
        if not self.text:
            self.fail(f"missing artifact: {CARD}")

    def test_artifact_exists_and_is_marked_req_done(self):
        self.assertTrue(CARD.is_file(), f"missing artifact: {CARD}")
        self.assertIn("REQ_DONE", self.text)

    def test_render_library_comparison_is_a_table_with_measured_sizes(self):
        section = _section(self.text, "### 1.2 ")
        rows = [row for table in _tables(section) for row in table]
        cells = [cell for row in rows for cell in row]
        self.assertTrue(rows, "§1.2 must contain a comparison table")
        for library in RENDER_LIBRARIES:
            self.assertTrue(
                any(library in cell for cell in cells),
                f"{library} missing from the §1.2 table",
            )
        # the comparison must be a real table: several evaluated dimensions, at
        # least two of which carry measured gzip figures rather than claims
        self.assertGreaterEqual(len(rows), 8, "§1.2 comparison table is too thin")
        measured = [row for row in rows if any("gzip" in cell for cell in row)]
        self.assertGreaterEqual(len(measured), 2, "§1.2 rows must carry gzip figures")

    def test_physics_comparison_covers_all_four_options_in_rows(self):
        section = _section(self.text, "### 1.3 ")
        table_rows = [row for table in _tables(section) for row in table]
        for option in PHYSICS_OPTIONS:
            self.assertTrue(
                any(option in row[0] for row in table_rows),
                f"{option} is not the subject of a §1.3 comparison row",
            )
            self.assertTrue(
                any(
                    option in row[0] and re.search(r"[0-9][0-9,]*\s*B|KB|MB", " ".join(row))
                    for row in table_rows
                ),
                f"{option} row carries no measured size",
            )
        self.assertIn("推荐", self.text)
        self.assertRegex(self.text, r"推荐:\*{0,2}Three\.js \+ cannon-es")

    def test_each_case_has_prose_and_transferable_design_bullets(self):
        sections = re.findall(r"^### 2\.\d+ .*$", self.text, flags=re.MULTILINE)
        self.assertGreaterEqual(len(sections), 3)
        for title in CASE_TITLES:
            self.assertIn(title, self.text)
        for heading in sections:
            body = _section(self.text, heading)
            bullets = [ln for ln in body.splitlines() if ln.startswith("- ")]
            self.assertGreaterEqual(
                len(bullets), 3, f"{heading} has no transferable-design bullet list"
            )
            self.assertGreater(len(body), 250, f"{heading} has no case description")
            self.assertIn("可迁移", body)

    def test_stated_friction_parameters_reproduce_the_claimed_ratio(self):
        rubber = re.search(r"\|\s*`?μ_橡胶`?\s*\|\s*([0-9.]+)\s*\|", self.text)
        ice = re.search(r"\|\s*`?μ_冰面`?\s*\|\s*([0-9.]+)\s*\|", self.text)
        self.assertIsNotNone(rubber, "μ_橡胶 missing from the §3.4 parameter table")
        self.assertIsNotNone(ice, "μ_冰面 missing from the §3.4 parameter table")
        ratio = float(rubber.group(1)) / float(ice.group(1))
        self.assertGreaterEqual(ratio, 3.0, "stated μ ratio violates the >=3x requirement")
        # the card claims the ideal ratio equals μ_rubber/μ_ice (18 here)
        self.assertIn(str(int(round(ratio))), self.text)
        # and a *measured* ratio, also above the acceptance line
        measured = re.findall(r"实测比?约?\s*([0-9.]+)|实测比\s*([0-9.]+)", self.text)
        values = [float(a or b) for a, b in measured]
        self.assertTrue(values, "no measured sliding-distance ratio recorded")
        self.assertTrue(
            all(v >= 3.0 for v in values),
            f"measured ratios below the >=3x line: {values}",
        )

    def test_determinism_guidance_pins_single_argument_step(self):
        self.assertIn("world.step(1/60)", self.text)
        self.assertIn("单参数", self.text)
        # the unsafe three-argument form must be called out, not recommended
        self.assertIn("timeSinceLastCalled", self.text)
        self.assertIn("子步", self.text)

    def test_friction_combine_rule_and_character_material_are_documented(self):
        self.assertIn("乘积", self.text)
        self.assertIn("createFrictionEquationsFromContact", self.text)
        self.assertRegex(self.text, r"角色材质\s*`friction`")
        self.assertIn("1.00", self.text)

    def test_no_dangling_level_reference_or_unsound_inertia_wording(self):
        self.assertNotIn("关卡 7", self.text)
        self.assertNotIn("关卡7", self.text)
        level_three = [ln for ln in self.text.splitlines() if re.match(r"\|\s*3\s*\|", ln)]
        self.assertTrue(level_three, "level 3 row missing")
        for row in level_three:
            self.assertNotIn(
                "惯性大小与速度有关",
                row,
                "level 3 must not claim inertia depends on speed",
            )

    def test_five_level_rows_are_complete(self):
        for name in LEVEL_NAMES:
            self.assertIn(name, self.text)
        rows = [ln for ln in self.text.splitlines() if re.match(r"\|\s*[1-5]\s*\|", ln)]
        self.assertGreaterEqual(len(rows), 5)
        for row in rows:
            self.assertGreaterEqual(
                row.count("|"), 7, f"level row has too few columns: {row[:40]}"
            )

    def test_records_measurement_method_and_versions(self):
        self.assertIn("esbuild", self.text)
        self.assertIn("gzip -9", self.text)
        for pinned in PINNED_VERSIONS:
            self.assertIn(pinned, self.text)
        self.assertIn("2026-10-15", self.text)


if __name__ == "__main__":
    unittest.main()
