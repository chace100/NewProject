"""Acceptance checks for the issue #5 research card (REQ_DONE artifact).

These tests pin issue #5's acceptance criteria so that a truncated, gutted or
internally inconsistent artifact fails CI instead of silently unblocking #6.

They are deliberately row-scoped: a value is asserted *inside the table row
that is supposed to carry it*, never as a bare substring of the whole document.
An unanchored ``assertIn("1.00", text)`` is satisfied by a date, a version
number or a different row, which is exactly the hole earlier revisions of this
file had.

What is covered:

* the artifact exists, is marked ``REQ_DONE``, and a missing artifact or a
  missing section heading is reported as one readable failure rather than a
  ``ValueError`` traceback;
* the technology comparison is a real table naming both render libraries and
  all four physics options, each with a measured size, and the §1.2 bundle
  sizes are asserted in their own rows;
* each borrowable case carries prose plus a transferable-design bullet list;
* the card's stated friction parameters reproduce the sliding-distance ratio
  it claims, and the *measured* ratios from §1.5(c)/(d) are asserted above the
  card's own ">= 3x" acceptance line;
* the physics conclusions found in review are documented and pinned: the
  single-argument ``world.step(1/60)`` row, the friction *product* rule with
  the character material at ``1.00``, the adapter-layer Coulomb impulse, the
  ``tan(theta) <= mu`` ramp thresholds, and the ground length that follows
  from the shipped 12 m/s cap;
* the harness that produced the numbers is committed and referenced.
"""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CARD = (
    REPO_ROOT
    / "docs"
    / "research"
    / "issue-005-3d-web-game-tech-selection-and-inertia-game-design.md"
)
HARNESS = REPO_ROOT / "docs" / "research" / "exp.mjs"

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

# Acceptance line the card sets for itself (§1.5 and the §3.4 rationale column).
MIN_CONTRAST = 3.0
# Gravity the card's harness pins (docs/research/exp.mjs: ``const G = 9.82``).
# Re-deriving §1.5(d)'s deviation column needs the same constant, and hard-coding
# it here keeps this test pure Python: the repo's CI has no Node step.
G_ACCEL = 9.82
# Measured doubling ratios for d ~ v0^2 (§1.5(d)); analytic value 4.000.
DOUBLING_BOUNDS = (3.6, 4.4)


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
    """Return the text of ``heading`` up to the next heading of the same rank.

    Raises ``AssertionError`` (not ``ValueError``) when the heading is absent,
    so a renamed section reads as a test failure instead of a traceback.
    """
    try:
        start = text.index(heading)
    except ValueError:
        raise AssertionError(
            f"card is missing the section heading {heading!r}"
        ) from None
    match = re.search(stop, text[start + len(heading):], flags=re.MULTILINE)
    end = start + len(heading) + (match.start() if match else len(text) - start)
    return text[start:end]


def _rows(text, pattern):
    """Return *every* table row matching ``pattern``, or fail readably.

    Named ``_rows`` (not ``_row``) because it returns a list: §1.5(d) has one
    row per medium and several callers iterate both. Callers that expect a
    single row assert ``len(...) == 1`` at the call site rather than relying on
    an undocumented guarantee here.
    """
    rows = [
        line
        for line in text.splitlines()
        if re.match(pattern, line.strip()) and line.strip().startswith("|")
    ]
    if not rows:
        raise AssertionError(f"no table row matching {pattern!r}")
    return rows


def _row(text, pattern):
    """Return the single table row matching ``pattern``.

    A thin wrapper over :func:`_rows` for the rows that are genuinely unique:
    it fails if the pattern is ambiguous instead of silently returning the
    first of several, so an over-broad pattern is reported as a failure here
    rather than as a confusing downstream assertion.
    """
    rows = _rows(text, pattern)
    if len(rows) != 1:
        raise AssertionError(
            f"expected exactly one row matching {pattern!r}, found {len(rows)}: "
            + "; ".join(r[:40] for r in rows)
        )
    return rows[0]


def _cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


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

    def test_render_library_sizes_are_pinned_in_their_own_row(self):
        section = _section(self.text, "### 1.2 ")
        cells = _cells(_row(section, r"\|\s*最小可玩场景体积"))
        self.assertIn("154 KB gzip", cells[1], "Three.js bundle size row changed")
        self.assertIn("380 KB gzip", cells[2], "Babylon.js bundle size row changed")
        self.assertIn(
            "157,228 B",
            cells[1],
            "the byte-exact Three.js figure must stay beside the rounded one",
        )
        self.assertIn(
            "388,788 B",
            cells[2],
            "the byte-exact Babylon.js figure must stay beside the rounded one",
        )

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
        rubber_row = _row(self.text, r"\|\s*`?μ_橡胶`?\s*\|")
        ice_row = _row(self.text, r"\|\s*`?μ_冰面`?\s*\|")
        rubber = float(_cells(rubber_row)[1])
        ice = float(_cells(ice_row)[1])
        ratio = rubber / ice
        self.assertGreaterEqual(
            ratio, MIN_CONTRAST, "stated μ ratio violates the >=3x requirement"
        )
        # the §3.4 row must state the *derived* ratio, not just the two inputs:
        # an unanchored search for "18" would also hit the 2026-10-15 date
        self.assertRegex(
            ice_row,
            r"0\.90\s*/\s*0\.05\s*=\s*18",
            "the §3.4 冰面 row must show the μ_rubber/μ_ice division explicitly",
        )

    def test_measured_contrast_clears_the_acceptance_line(self):
        """The card's own numbers, not the ideal ratio, must clear >= 3x.

        QA's blocker was that §1.5 claimed a 7.49x contrast the engine does
        not deliver. The values asserted here are the measured ones from
        §1.5(d), which is what the acceptance line is supposed to apply to.
        """
        block = _section(self.text, "#### (d)")
        measured = [
            float(v) for v in re.findall(r"\*\*([0-9]+\.[0-9]+)×\*\*", block)
        ]
        self.assertTrue(measured, "§1.5(d) records no measured contrast")
        for value in measured:
            self.assertGreaterEqual(
                value, MIN_CONTRAST, f"measured contrast {value} is below >=3x"
            )
        # and the failing engine-configuration reading must be recorded as
        # failing, not quietly dropped
        raw = _section(self.text, "#### (c)")
        self.assertRegex(
            raw,
            r"\|[^\n]*1\.07[^\n]*\|",
            "§1.5(c) must keep the measured 1.07x free-rotation ratio",
        )
        self.assertIn("3 倍", raw, "§1.5(c) must say 1.07 is below the >=3x line")

    def test_measured_doubling_ratio_supports_level_three(self):
        """Level 3's answer key must be backed by a measured d(4)/d(2).

        The row layout is pinned, so moving the column or swapping in a
        hard-coded "4" fails here rather than silently retuning the answer key.
        """
        rows = _rows(self.text, r"\|\s*(?:冰面|橡胶)")
        self.assertGreaterEqual(len(rows), 2, "§1.5(d) needs both media rows")
        measured = {}
        for row in rows:
            cells = _cells(row)
            self.assertRegex(
                cells[5],
                r"^\*\*[0-9]+\.[0-9]+\*\*$",
                f"the d(4)/d(2) column must be a bold measured value: {cells[5]!r}",
            )
            ratio = float(cells[5].strip("*"))
            medium = "冰面" if "冰面" in cells[0] else "橡胶"
            measured[medium] = ratio
            low, high = DOUBLING_BOUNDS
            self.assertTrue(
                low <= ratio <= high,
                f"{medium} d(4)/d(2) = {ratio} is outside {DOUBLING_BOUNDS}",
            )
        self.assertEqual(set(measured), {"冰面", "橡胶"})
        self.assertIn("d ∝ v₀²", self.text)
        # the shipped v0 (12 m/s) must stay inside the range the table measured
        ice = [row for row in rows if "冰面" in _cells(row)[0]]
        self.assertIn(
            "146.540 m",
            _cells(ice[0])[4],
            "the v₀=12 ice column must stay measured, not extrapolated",
        )

    def test_adapter_deviations_match_the_analytic_law(self):
        """The §1.5(d) deviation column must be derivable from the same row.

        The measured distances are already pinned by
        ``test_measured_doubling_ratio_supports_level_three``; this test closes
        the remaining hole by recomputing ``(d - v0^2/(2*mu*g)) / analytic``
        from *those same cells* and comparing against the percentages printed
        in the row. A column copied from the neighbouring row — the defect this
        guards — reproduces the ratio column but not this one.
        """
        rows = _rows(self.text, r"\|\s*(?:冰面|橡胶)")
        self.assertGreaterEqual(len(rows), 2, "§1.5(d) needs both media rows")
        seen = {}
        for row in rows:
            cells = _cells(row)
            mu_match = re.search(r"μ\s*=\s*([0-9.]+)", cells[0])
            self.assertIsNotNone(mu_match, f"row states no μ: {cells[0]!r}")
            mu = float(mu_match.group(1))
            medium = "冰面" if "冰面" in cells[0] else "橡胶"
            # U+2212 MINUS SIGN, as the card uses throughout
            printed = [
                float(v.replace("−", "-").replace("%", ""))
                for v in re.findall(r"[−-][0-9]+\.[0-9]+%", cells[6])
            ]
            distances = [float(re.search(r"[0-9.]+", c).group()) for c in cells[1:5]]
            self.assertEqual(
                len(printed), 4, f"{medium} deviation column is not four values"
            )
            for v0, measured, claimed in zip((2, 4, 8, 12), distances, printed):
                analytic = v0 * v0 / (2 * mu * G_ACCEL)
                expected = 100.0 * (measured - analytic) / analytic
                # the card prints distances rounded to millimetres, so a cell
                # value can sit up to 5e-4 m away from the figure the harness
                # divided; widen the tolerance by exactly that much
                delta = 100.0 * 5e-4 / analytic + 0.01
                self.assertAlmostEqual(
                    claimed,
                    expected,
                    delta=delta,
                    msg=(
                        f"{medium} μ={mu} v0={v0}: card prints {claimed}% but "
                        f"{measured} m against {analytic:.3f} m is {expected:.2f}%"
                    ),
                )
            # and the rows genuinely differ, so one column is not the other's copy
            seen[medium] = printed
        self.assertEqual(set(seen), {"冰面", "橡胶"})
        self.assertNotEqual(
            seen["冰面"], seen["橡胶"], "the two media rows share a deviation column"
        )

    def test_determinism_row_pins_single_argument_step(self):
        cells = _cells(_row(self.text, r"\|\s*物理步进\s*\|"))
        self.assertIn(
            "world.step(1/60)",
            cells[1],
            "the §3.4 物理步进 row must pin the single-argument form",
        )
        self.assertIn("单参数", cells[1], "the row must say '单参数'")
        self.assertNotIn(
            "step(1/60,",
            cells[1],
            "the row must not prescribe the three-argument (wall-clock) form",
        )
        # the unsafe form is named and rejected in prose, not silently omitted
        self.assertIn("timeSinceLastCalled", self.text)
        self.assertIn("子步", self.text)

    def test_friction_combine_rule_and_character_material_are_documented(self):
        self.assertIn("乘积", self.text)
        self.assertIn("createFrictionEquationsFromContact", self.text)
        cells = _cells(_row(self.text, r"\|\s*角色材质\s*`friction`\s*\|"))
        self.assertRegex(
            cells[1],
            r"\*\*1\.00\*\*",
            "the §3.4 角色材质 friction row must state **1.00** as its value",
        )

    def test_adapter_layer_and_ramp_release_are_pinned(self):
        cells = _cells(_row(self.text, r"\|\s*接触摩擦\s*`Material\.friction`\s*\|"))
        self.assertIn("0", cells[1], "contact friction must be pinned off")
        cells = _cells(_row(self.text, r"\|\s*适配层摩擦冲量上限\s*\|"))
        self.assertIn("cosθ", cells[1], "the impulse cap must carry the cosθ factor")
        self.assertIn("dt", cells[1], "the impulse cap must be per-step")
        # the ramp story is stated with the textbook threshold, not a hand-tuned
        # angle table
        self.assertIn("tanθ ≤ μ", self.text)
        self.assertIn("atan(", self.text)
        self.assertRegex(
            _cells(_row(self.text, r"\|\s*地面长度"))[1],
            r"≥\s*160\s*m",
            "the ground must be longer than d_ice(12 m/s) = 146.5 m",
        )
        self.assertIn("146.5", self.text)

    def test_harness_is_committed_and_referenced(self):
        self.assertTrue(HARNESS.is_file(), f"missing harness: {HARNESS}")
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("--assert", source, "the harness must expose a --assert gate")
        for constant in ("G = 9.82", "DT = 1 / 60", "HALF = 0.5"):
            self.assertIn(constant, source, f"harness must pin {constant}")
        self.assertIn("exp.mjs", self.text, "the card must point at the harness")
        self.assertIn("--assert", self.text)

    def test_no_dangling_level_reference_or_unsound_inertia_wording(self):
        self.assertNotIn("关卡 7", self.text)
        self.assertNotIn("关卡7", self.text)
        level_three = _rows(self.text, r"\|\s*3\s*\|")
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

    def test_deviation_law_is_stated_as_a_discrete_under_travel(self):
        """§1.5(d)'s deviation must be explained with the right sign and law.

        Two review findings meet here. The first: the prose used to say the
        stopping Coulomb impulse *overshoots*, which predicts a positive
        deviation, while all eight printed deviations are negative. The second:
        the 1/v decay of the *relative* column was read as proof the model is
        right "because the numerator is fixed" — but the numerator
        ``|d_measured − d_analytic|`` is not fixed, it is ``v0 * dt / 2``,
        which is linear in v0 and independent of mu.

        Pinning the law here means a future edit cannot quietly restore either
        claim: the wrong sign fails on the mechanism words, the wrong law fails
        on ``v0·dt/2``.
        """
        block = _section(self.text, "#### (d)")
        self.assertIn("走少了", block, "§1.5(d) must state the sign of the deviation")
        self.assertIn(
            "不可能超调",
            block,
            "§1.5(d) must rule the overshoot out explicitly, since all eight "
            "printed deviations are negative",
        )
        self.assertNotIn(
            "必然超调",
            block,
            "§1.5(d) must not restore the claim that the stopping impulse "
            "necessarily overshoots: it predicts the opposite sign",
        )
        self.assertIn("v₀·dt/2", block, "§1.5(d) must state the discrete-step law")
        # and the law is the *absolute* one, independent of mu, so the card must
        # not claim the absolute error scales with the friction coefficient
        self.assertRegex(
            block,
            r"与\s*μ\s*无关|μ\s*无关",
            "§1.5(d) must say the absolute deviation is independent of μ",
        )

    def test_harness_runs_clean_when_node_and_deps_are_available(self):
        """Actually execute the harness, rather than grepping its source.

        ``test_harness_is_committed_and_referenced`` only checks that the
        harness *text* contains ``--assert`` and the pinned constants, so the
        harness could be numerically wrong — or unrunnable — and the suite
        would stay green. This test closes that hole where it can be closed
        without touching CI: ``.github/workflows/`` is deliberately left alone
        (issue #5 forbids editing it) and has no Node step, so this test
        *skips* when Node or ``cannon-es`` is unavailable instead of failing.
        On any machine with Node and the dependency present it is a real gate
        that runs the physics and asserts the exit status.

        Runtime is ~1.3 s, so no slow-test marker is warranted.
        """
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed; harness execution is skipped")
        # Resolve cannon-es from wherever the harness would resolve it. The
        # repo deliberately does not vendor node_modules, so a missing
        # dependency is a skip, never a failure.
        probe = subprocess.run(
            [node, "--input-type=module", "-e", "await import('cannon-es')"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if probe.returncode != 0:
            self.skipTest(
                "cannon-es is not resolvable from the repository; "
                "run `npm install cannon-es@0.20.0` to enable this gate"
            )
        run = subprocess.run(
            [node, str(HARNESS.relative_to(REPO_ROOT)), "--assert"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertEqual(
            run.returncode,
            0,
            "docs/research/exp.mjs --assert failed:\n"
            + run.stdout[-4000:]
            + run.stderr[-2000:],
        )
        self.assertIn(
            "OK: all measurements within tolerance",
            run.stdout,
            "the harness must print its all-clear line on success",
        )


if __name__ == "__main__":
    unittest.main()
