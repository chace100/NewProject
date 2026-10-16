/**
 * Reproduces every cannon-es@0.20.0 measurement quoted in §1.5 of
 * `issue-005-3d-web-game-tech-selection-and-inertia-game-design.md`.
 *
 *   npm install cannon-es@0.20.0
 *   node exp.mjs            # print all tables
 *   node exp.mjs --assert   # exit 1 if a load-bearing number drifts
 *
 * Deterministic: no randomness, a fixed body list, a fixed iteration order, and
 * BODY_Y0 / SETTLE_STEPS pinned as named constants. Re-running prints identical
 * digits. cannon-es@0.20.0 is pinned; friction handling is version sensitive.
 *
 * The one non-deterministic path is `world.step(dt, timeSinceLastCalled,
 * maxSubSteps)` in §1.5(a) — it consults `performance.now()`, which is exactly
 * the defect that section demonstrates. The wall-clock bail-out can only end
 * the substep loop early, never extend it, so §1.5(a) asserts what the defect
 * cannot move: position == substeps·dt·v0, and the library clock reading
 * 3.000 s while the substep counter reads less. The raw substep counts are
 * printed but not pinned to exact integers, because `performance.now()` is
 * what decides them.
 *
 * WHY EVERY DISTANCE HERE IS QUOTED WITH ITS SEATING
 * --------------------------------------------------
 * A box's sliding distance in this engine is a knife-edge function of how deep
 * it is seated in the ground at t=0. Seating a 0.5 m half-extent cube at
 * `y = HALF` instead of `y = HALF + 0.002` moves the free-rotation result from
 * 1.08 m to 795.84 m on the same scene. `BODY_Y0` and `SETTLE_STEPS` below are
 * therefore part of the measurement, not incidental setup, and the card quotes
 * them beside every distance.
 */
import * as CANNON from 'cannon-es'

// ---------------------------------------------------------------- constants
const G = 9.82 // m/s², the value the card specifies
const DT = 1 / 60
const ICE = 0.05
const RUBBER = 0.9
const CHAR = 1.0 // the character's own friction (§3.4)
const HALF = 0.5 // character half-extent: a 1 m cube, "半边长 0.5 m"

/** Centre height of the cube at rest on a flat ground whose top face is y=0. */
const BODY_Y0 = HALF
/** Steps run before the impulse, so the contact has settled. */
const SETTLE_STEPS = 180
/** Steps over which a sliding distance is accumulated (5 s). */
const MEASURE_STEPS = 300
/** Shipping horizontal speed cap (§3.4). */
const V_MAX = 12

const f = (x, d = 4) => (x == null ? 'n/a' : Number(x).toFixed(d))
const rule = (t) => console.log(`\n=== ${t} ===`)

const failures = []
const check = (ok, msg) => {
  if (!ok) failures.push(msg)
  return ok
}

// ---------------------------------------------------------------- utilities
function makeWorld(iterations = 10) {
  const world = new CANNON.World({ gravity: new CANNON.Vec3(0, -G, 0) })
  world.broadphase = new CANNON.SAPBroadphase(world)
  world.solver.iterations = iterations
  world.solver.tolerance = 0.001
  world.allowSleep = false
  return world
}

function flatGround(world, friction, half = 400) {
  const mat = new CANNON.Material('ground')
  mat.friction = friction
  const body = new CANNON.Body({
    mass: 0,
    material: mat,
    shape: new CANNON.Box(new CANNON.Vec3(half, 0.5, half)),
  })
  body.position.set(0, -0.5, 0)
  world.addBody(body)
  return body
}

/**
 * The character: a TRUE CUBE of half-extent HALF, per §6.3's "1 kg 立方体
 * (半边长 0.5 m)". Half-extents (HALF, HALF, HALF) — not a slab.
 */
function character(world, { friction = CHAR, material = true, fixedRotation = true } = {}) {
  const opts = { mass: 1 }
  if (material) {
    const mat = new CANNON.Material('character')
    mat.friction = friction
    opts.material = mat
  }
  opts.shape = new CANNON.Box(new CANNON.Vec3(HALF, HALF, HALF))
  const body = new CANNON.Body(opts)
  body.linearDamping = 0
  body.angularDamping = 0
  body.fixedRotation = fixedRotation
  body.updateMassProperties()
  return body
}

const muEff = (world) =>
  world.frictionEquations[0] ? world.frictionEquations[0].maxForce / G : null

/** Rotate +θ about z; unit down-slope tangent and outward normal. */
const rampAxes = (deg) => {
  const t = (deg * Math.PI) / 180
  return {
    t,
    tangent: new CANNON.Vec3(-Math.cos(t), -Math.sin(t), 0), // points downhill
    normal: new CANNON.Vec3(-Math.sin(t), Math.cos(t), 0),
  }
}

/**
 * The solver's contact friction is an impulse capped by the solver's own
 * convergence, not by μN·dt. Reproducing Coulomb therefore means turning
 * contact friction OFF on both bodies and applying the friction impulse in the
 * adapter layer.
 *
 * `predict` adds the velocity gravity will add during the coming step before
 * sizing the impulse. Without it the impulse cancels the current velocity, the
 * solver then re-adds g·sinθ·dt, and the body creeps downhill forever at
 * ~0.001 m/step below the Coulomb threshold. With it the hold/release boundary
 * lands on tan θ = μ to the degree.
 */
function applyCoulomb(body, { mu, normal, tangent, predictSinTheta = 0 }) {
  const vt = body.velocity.dot(tangent) + predictSinTheta * G * DT
  if (Math.abs(vt) < 1e-12) return
  const capacity = mu * G * Math.max(normal.y, 0) * DT
  const dv = Math.min(capacity, Math.abs(vt))
  body.applyImpulse(tangent.scale(-Math.sign(vt) * dv), body.position)
}

/** Flat-ground slide under the adapter-layer Coulomb model. */
function slideCoulomb(mu, v0) {
  const world = makeWorld()
  flatGround(world, 0) // contact friction deliberately OFF
  const body = character(world, { friction: 0 })
  body.position.set(0, BODY_Y0, 0)
  world.addBody(body)
  for (let i = 0; i < SETTLE_STEPS; i++) world.step(DT)
  const x0 = body.position.x
  body.velocity.set(v0, 0, 0)
  body.angularVelocity.set(0, 0, 0)
  // Run past the analytic stop time (v0/μg) so the distance is not truncated:
  // ice at 12 m/s needs 24.4 s, and a 20 s budget would silently cut it short.
  const budget = Math.ceil((v0 / (mu * G)) * 60) + 120
  let stopped = -1
  for (let i = 0; i < budget; i++) {
    applyCoulomb(body, { mu, normal: new CANNON.Vec3(0, 1, 0), tangent: new CANNON.Vec3(1, 0, 0) })
    world.step(DT)
    if (stopped < 0 && body.velocity.length() <= 1e-6) stopped = i + 1
  }
  return { d: body.position.x - x0, stop: stopped < 0 ? null : stopped / 60, y: body.position.y }
}

// ------------------------------------------------------------------ §1.5(a)
rule('§1.5(a) the 3-argument world.step() starves substeps at low frame rates')
{
  // Frictionless, so x reads out *simulated time* directly: x = substeps·dt·v0.
  // That proportionality is the measurement, not an artefact. The library's own
  // counters (`world.stepnumber`, `world.time`) are returned alongside x so the
  // three can be compared: stepnumber is the number of internalStep() calls the
  // engine actually ran, and time is what the engine *reports* as elapsed.
  const run = (fps) => {
    const world = makeWorld()
    flatGround(world, 0)
    const body = character(world, { friction: 0, fixedRotation: true })
    body.position.set(0, BODY_Y0, 0)
    world.addBody(body)
    for (let i = 0; i < SETTLE_STEPS; i++) world.step(DT)
    const x0 = body.position.x
    const steps0 = world.stepnumber
    const time0 = world.time // both are cumulative; the deltas are the reading
    body.velocity.set(V_MAX, 0, 0)
    if (fps === null) {
      for (let i = 0; i < 180; i++) world.step(DT)
    } else {
      for (let i = 0; i < 3 * fps; i++) world.step(DT, 1 / fps, 3)
    }
    return {
      d: body.position.x - x0,
      steps: world.stepnumber - steps0, // substeps the engine really ran
      time: world.time - time0, // what the engine reports as time elapsed
    }
  }
  const ideal = 3 * V_MAX
  console.log(`  frictionless, v0=${V_MAX} m/s, 3 s of wall time, ideal ${ideal} m`)
  console.log('  call form                        x (m)  stepnumber  Δworld.time  of ideal')
  const rows = []
  const single = run(null)
  rows.push({ label: 'world.step(1/60) × 180', r: single, singleArg: true })
  console.log(
    `  world.step(1/60) × 180          ${f(single.d, 3).padStart(7)}  ${String(single.steps).padStart(10)}  ${f(single.time, 3).padStart(10)}  ${f((100 * single.d) / ideal, 1).padStart(6)}%`,
  )
  for (const fps of [60, 30, 10, 5]) {
    const r = run(fps)
    rows.push({ label: `world.step(1/60, 1/${fps}, 3) × ${3 * fps}`, r, singleArg: false })
    console.log(
      `  world.step(1/60, 1/${String(fps).padEnd(2)}, 3) × ${String(3 * fps).padEnd(4)} ${f(r.d, 3).padStart(7)}  ${String(r.steps).padStart(10)}  ${f(r.time, 3).padStart(10)}  ${f((100 * r.d) / ideal, 1).padStart(6)}%`,
    )
  }
  console.log('  1-arg is exact and repeatable. The 3-arg form caps substeps at')
  console.log('  maxSubSteps per *call*, then discards the remainder with')
  console.log('  `accumulator %= dt`, so at 5 fps only a quarter of the time is')
  console.log('  simulated. It also consults performance.now() to bail out, which')
  console.log('  makes the substep count machine-dependent — see DIST/12508-12551.')
  console.log('  The last two columns are the point, and both are read off the')
  console.log('  world object after the run (`world.stepnumber`, `world.time`), not')
  console.log('  derived from x. `this.time += timeSinceLastCalled` is unconditional,')
  console.log('  so Δworld.time is 3.000 s on every row, while the engine ran only')
  console.log('  180/180/90/45/180 substeps. The clock a game loop would read is')
  console.log('  therefore ahead of the simulation by the discarded substeps — that')
  console.log('  is the defect, and it is measured here rather than inferred from x.')
  check(Math.abs(single.d - ideal) < 1e-9, '§1.5(a): 1-arg step is not exact')
  for (const { label, r, singleArg } of rows) {
    // Discarded substeps are truncated, not invented: every substep is counted.
    const implied = r.steps * DT * V_MAX
    check(
      Math.abs(r.d - implied) < 1e-6,
      `§1.5(a) ${label}: x=${r.d.toFixed(4)} m but ${r.steps} substeps imply ${implied.toFixed(4)} m`,
    )
    // `this.time += timeSinceLastCalled` runs regardless of how many substeps
    // were taken, so the reported clock advances 3.000 s on every row. The
    // tolerance here is float noise only: this is the claim the card makes.
    check(
      Math.abs(r.time - 3) < 1e-9,
      `§1.5(a) ${label}: Δworld.time=${r.time} is not 3.000 s`,
    )
    check(
      r.steps <= 180 && r.steps > 0,
      `§1.5(a) ${label}: stepnumber=${r.steps} outside [1, 180]`,
    )
    if (singleArg) {
      check(r.steps === 180, `§1.5(a) 1-arg stepnumber ${r.steps} != 180`)
    }
  }
  // The starvation itself, asserted at the two extremes rather than as exact
  // integers: the wall-clock bail-out can only shorten a row, never lengthen it.
  const at5 = rows.find((r) => r.label.includes('1/5,'))
  check(
    at5.r.steps <= 50,
    `§1.5(a): 5 fps row ran ${at5.r.steps} substeps, not the starved ≤50`,
  )
  const at60 = rows.find((r) => r.label.includes('1/60,'))
  check(at60.r.steps > at5.r.steps * 2, '§1.5(a): 60 fps row did not outrun the 5 fps row')
}

// ------------------------------------------------------------------ §1.5(b)
rule('§1.5(b) effective friction is the PRODUCT, and the character material is mandatory')
{
  console.log('  ground μ   character μ   μ_eff measured   μ_g·μ_c')
  // expected = μ_g·μ_c, except where the product is 0: `if (friction > 0)` in
  // createFrictionEquationsFromContact then creates NO friction equation at all,
  // so μ_eff is not 0 but "nothing was measured" — `null`, printed `n/a`. That
  // case is carried as an explicit expectation rather than short-circuited away.
  for (const [gm, cm] of [
    [ICE, CHAR],
    [RUBBER, CHAR],
    [ICE, 0.3],
    [RUBBER, 0.3],
    [ICE, 0.0],
    [RUBBER, 0.0],
  ]) {
    const world = makeWorld()
    flatGround(world, gm)
    const body = character(world, { friction: cm })
    body.position.set(0, BODY_Y0 + 0.002, 0)
    world.addBody(body)
    for (let i = 0; i < SETTLE_STEPS; i++) world.step(DT)
    const eff = muEff(world)
    const expected = gm * cm === 0 ? null : gm * cm
    console.log(
      `  ${String(gm).padEnd(10)} ${String(cm).padEnd(13)} ${f(eff).padEnd(16)} ${f(gm * cm)}`,
    )
    if (expected === null) {
      check(
        eff === null,
        `§1.5(b): μ_eff ${eff} with μ_g·μ_c = 0 — expected no friction equation (n/a)`,
      )
      console.log(
        `  ${' '.repeat(10)}   ↑ product is 0, so \`if (friction > 0)\` is false and no`,
      )
      console.log(
        `  ${' '.repeat(10)}     friction equation exists: the surfaces are frictionless.`,
      )
    } else {
      check(
        eff !== null && Math.abs(eff - expected) < 5e-4,
        `§1.5(b): μ_eff ${eff} != μ_g·μ_c = ${expected}`,
      )
    }
  }
  console.log('  -- character body with NO Material --')
  // Every ground value gives the same 0.3000 — but each is measured in its own
  // world, so the row is three measurements, not one repeated claim. Note the
  // μ_g = 0 ground is included: with the character's material missing, the
  // product rule never runs and the ground's own value is discarded, so even a
  // zero-friction ground falls through to defaultContactMaterial.
  for (const gm of [ICE, RUBBER, 0.0]) {
    const world = makeWorld()
    flatGround(world, gm)
    const body = character(world, { material: false })
    body.position.set(0, BODY_Y0 + 0.002, 0)
    world.addBody(body)
    for (let i = 0; i < SETTLE_STEPS; i++) world.step(DT)
    const eff = muEff(world)
    console.log(
      `  ${String(gm).padEnd(10)} ${'(none)'.padEnd(13)} ${f(eff).padEnd(16)} defaultContactMaterial = 0.30`,
    )
    check(
      eff !== null && Math.abs(eff - 0.3) < 5e-4,
      `§1.5(b): fallthrough μ_eff ${eff} (ground μ=${gm}) != 0.30`,
    )
  }
  console.log('  The `matA && matB && ...` guard in createFrictionEquationsFromContact')
  console.log('  (DIST/10440-10489) falls through to cm.friction when EITHER body')
  console.log('  lacks a Material, so the ground value is silently discarded.')
}

// ------------------------------------------------------------------ §1.5(c)
rule('§1.5(c) raw contact friction does NOT deliver the Coulomb contrast')
{
  const launch = (mu, { fixedRotation = true, iterations = 10 } = {}) => {
    const world = makeWorld(iterations)
    flatGround(world, mu)
    const body = character(world, { fixedRotation })
    body.position.set(0, BODY_Y0, 0)
    world.addBody(body)
    for (let i = 0; i < SETTLE_STEPS; i++) world.step(DT)
    const x0 = body.position.x
    body.velocity.set(5, 0, 0)
    body.angularVelocity.set(0, 0, 0)
    let airborne = 0
    for (let i = 0; i < MEASURE_STEPS; i++) {
      world.step(DT)
      if (world.contacts.length === 0) airborne++
    }
    return { d: body.position.x - x0, y: body.position.y, airborne }
  }

  console.log(`  v0=5 m/s, ${MEASURE_STEPS} steps, BODY_Y0=${BODY_Y0}, SETTLE_STEPS=${SETTLE_STEPS}`)
  console.log('  fixedRot  iters  ice d (m)            rubber d (m)           ratio   ideal 18')
  for (const fixedRotation of [true, false]) {
    for (const iterations of [10, 50]) {
      const ice = launch(ICE, { fixedRotation, iterations })
      const rub = launch(RUBBER, { fixedRotation, iterations })
      console.log(
        `  ${String(fixedRotation).padEnd(9)} ${String(iterations).padEnd(6)} ` +
          `${f(ice.d, 4).padEnd(8)} (air ${String(ice.airborne).padStart(3)})  ${f(rub.d, 4).padEnd(8)} (air ${String(rub.airborne).padStart(3)})  ` +
          `${f(ice.d / rub.d, 2).padEnd(7)}`,
      )
    }
  }
  const iceR = launch(ICE, { fixedRotation: false })
  const rubR = launch(RUBBER, { fixedRotation: false })
  const rawRatio = iceR.d / rubR.d
  console.log('  what the engine does on the first steps (μ_ice, fixedRotation):')
  {
    const world = makeWorld()
    flatGround(world, ICE)
    const body = character(world, {})
    body.position.set(0, BODY_Y0, 0)
    world.addBody(body)
    for (let i = 0; i < SETTLE_STEPS; i++) world.step(DT)
    body.velocity.set(5, 0, 0)
    for (let i = 0; i < 3; i++) {
      const v0 = body.velocity.x
      world.step(DT)
      console.log(
        `    step ${i}: Δvx=${f(v0 - body.velocity.x, 5)} m/s  y=${f(body.position.y)}  contacts=${world.contacts.length}  (μ_eff·g·dt = ${f(ICE * G * DT, 5)})`,
      )
    }
  }
  console.log('  With rotation FIXED the ratio looks fine (10.07) because the body')
  console.log('  stops in two large impulses, before the ice/rubber difference can')
  console.log('  accumulate — a coincidence, not contrast. The shipping character')
  console.log('  must roll (fixedRotation=false), and there the ratio collapses:')
  console.log('  a 19-step airborne hop on contact, then the same handful of')
  console.log('  solver-sized impulses on landing for both surfaces.')
  check(rawRatio < 2.0, `§1.5(c): free-rotation raw ratio ${rawRatio.toFixed(2)} is >= 2`)
}

// ------------------------------------------------------------------ §1.5(d)
rule('§1.5(d) the adapter-layer Coulomb model delivers both the ratio and d ∝ v0²')
{
  console.log('  contact friction OFF on both bodies; friction applied as an')
  console.log('  impulse of at most μ·g·dt opposing the tangential velocity.')
  console.log('  μ       v0    d measured   analytic v0²/(2μg)   abs err   v0·dt/2   rel err    stop')
  // The impulse is applied *before* each world.step, so each step's displacement
  // uses the already-reduced velocity and the discrete sum loses exactly
  // v0·dt/2 m — the half-step of velocity the first impulse removes but which
  // the analytic integral keeps. The absolute error is therefore μ-independent
  // and linear in v0; the *relative* error 100·μ·g·dt/v0 carries the μ ratio.
  // That relative law is the absolute law divided by d_analytic = v0²/(2μg),
  // so it inherits the same O(dt²) slack from the finite step count: at v0=2
  // the block stops in ~13 steps and the sum departs from the integral by
  // 3.1e-4 m, which is 0.14% of a 0.23 m rubber slide. Both residuals are
  // therefore asserted in metres, where the two laws share one bound.
  const worst = { abs: 0, rel: 0 }
  for (const [mu, label] of [
    [ICE, 'ice 0.05'],
    [RUBBER, 'rubber 0.90'],
  ]) {
    for (const v0 of [2, 4, 8, V_MAX]) {
      const r = slideCoulomb(mu, v0)
      const analytic = (v0 * v0) / (2 * mu * G)
      const absErr = Math.abs(r.d - analytic)
      const halfStep = (v0 * DT) / 2
      const relErr = (100 * (r.d - analytic)) / analytic
      console.log(
        `  ${label.padEnd(11)} ${String(v0).padStart(2)}  ${f(r.d, 3).padStart(9)} m   ${f(analytic, 3).padStart(9)} m   ${f(absErr, 4).padStart(7)}   ${f(halfStep, 4).padStart(7)}   ${f(relErr, 2).padStart(6)}%  ${f(r.stop, 2)} s`,
      )
      worst.abs = Math.max(worst.abs, Math.abs(absErr - halfStep))
      // both are negative (under-travel), so compare signed values; scale the
      // relative law back to metres so it shares the one bound above
      worst.rel = Math.max(worst.rel, (Math.abs(relErr + (100 * mu * G * DT) / v0) * analytic) / 100)
    }
  }
  console.log(`  |d_meas − d_analytic| tracks v0·dt/2 to ${worst.abs.toExponential(1)} m across both`)
  console.log('  media: the discretisation error is μ-independent and linear in v0.')
  console.log(`  The *relative* error 100·μ·g·dt/v0 reproduces to ${worst.rel.toExponential(1)} m`)
  console.log('  of slide distance — i.e. the μ ratio (18×) lives in that column only.')
  check(worst.abs < 1e-3, `§1.5(d): |abs err − v0·dt/2| reached ${worst.abs}`)
  check(
    worst.rel < 1e-3,
    `§1.5(d): rel err does not track 100·μ·g·dt/v0 (off by ${worst.rel.toExponential(1)} m)`,
  )
  const ice2 = slideCoulomb(ICE, 2).d
  const ice4 = slideCoulomb(ICE, 4).d
  const rub2 = slideCoulomb(RUBBER, 2).d
  const rub4 = slideCoulomb(RUBBER, 4).d
  const doubleIce = ice4 / ice2
  const doubleRub = rub4 / rub2
  console.log(`  d(4)/d(2) = ${f(doubleIce, 3)} (ice)  ${f(doubleRub, 3)} (rubber)   Coulomb predicts 4.000`)
  const i5 = slideCoulomb(ICE, 5).d
  const r5 = slideCoulomb(RUBBER, 5).d
  const i12 = slideCoulomb(ICE, V_MAX).d
  const r12 = slideCoulomb(RUBBER, V_MAX).d
  console.log(`  contrast ice/rubber: v0=5 → ${f(i5 / r5, 2)}×   v0=${V_MAX} → ${f(i12 / r12, 2)}×   ideal ${f(RUBBER / ICE, 1)}×`)
  console.log(`  ground half-extent must exceed d_ice(${V_MAX}) = ${f(i12, 2)} m.`)
  console.log(`  Box(30,0.5,30) is NOT big enough; use an infinite Plane, or Box(400,0.5,400).`)
  // The design's acceptance line.
  check(i5 / r5 >= 3.0, `§1.5(d): adapter contrast ${(i5 / r5).toFixed(2)}× is below the 3× line`)
  check(doubleIce >= 3.6 && doubleIce <= 4.4, `§1.5(d): ice doubling ratio ${doubleIce.toFixed(3)} leaves [3.6, 4.4]`)
  // The rubber row is the one with the large discretisation deviation (-7.23%
  // at v0=2), so it is the row most likely to drift. Guard it too.
  check(doubleRub >= 3.6 && doubleRub <= 4.4, `§1.5(d): rubber doubling ratio ${doubleRub.toFixed(3)} leaves [3.6, 4.4]`)
  check(i12 <= 400, `§1.5(d): d_ice(${V_MAX}) = ${i12.toFixed(1)} m exceeds the recommended ground`)
  // Every check above is a *law* — a doubling ratio, a contrast, a bound on
  // the ground — and all of them are invariant under a rescaled μ. That makes
  // them blind to a wrong constant: this harness exits 0 with `const ICE = 0.07`
  // (verified by mutation), which would silently invalidate every distance the
  // card publishes. These two pin the card's own §1.5(d) cells as literal
  // expectations, so a constant or integrator change that moves a published
  // distance is caught here instead of only in the card's prose.
  // Tolerance is 1 mm: the card prints these to millimetres.
  check(Math.abs(i12 - 146.54) < 1e-3, `§1.5(d): d_ice(${V_MAX}) = ${i12.toFixed(4)} m != card's 146.540 m`)
  check(Math.abs(r12 - 8.047) < 1e-3, `§1.5(d): d_rubber(${V_MAX}) = ${r12.toFixed(4)} m != card's 8.047 m`)
  check(Math.abs(i5 / r5 - 18.52) < 0.01, `§1.5(d): adapter contrast ${(i5 / r5).toFixed(4)}× != card's 18.52×`)
}

// ------------------------------------------------------------------ §1.5(e)
rule('§1.5(e) slope: the adapter model reproduces tan θ ≦ μ')
{
  const slope = (deg, { mu, adapter }) => {
    const { t, tangent, normal } = rampAxes(deg)
    const world = makeWorld()
    const gmat = new CANNON.Material('ground')
    gmat.friction = adapter ? 0 : mu
    const ground = new CANNON.Body({
      mass: 0,
      material: gmat,
      shape: new CANNON.Box(new CANNON.Vec3(400, 0.5, 400)),
    })
    ground.quaternion.setFromAxisAngle(new CANNON.Vec3(0, 0, 1), t)
    world.addBody(ground)

    const body = character(world, { friction: adapter ? 0 : CHAR, fixedRotation: true })
    // The lowest corner sits support = HALF·(|n_x|+|n_y|) below the centre.
    const support = HALF * (Math.abs(normal.x) + Math.abs(normal.y))
    const seat = 0.5 + support + 0.002
    body.position.set(normal.x * seat, normal.y * seat, 0)
    body.quaternion.setFromAxisAngle(new CANNON.Vec3(0, 0, 1), t)
    world.addBody(body)

    const step = () => {
      if (adapter) {
        applyCoulomb(body, { mu, normal, tangent, predictSinTheta: Math.sin(t) })
      }
      world.step(DT)
    }
    for (let i = 0; i < 300; i++) step()
    const x0 = body.position.x
    let moving = 0
    for (let i = 0; i < MEASURE_STEPS; i++) {
      step()
      if (body.velocity.length() > 0.05) moving++
    }
    return { drift: body.position.x - x0, moving }
  }
  for (const mu of [RUBBER, 0.3, ICE]) {
    const threshold = (Math.atan(mu) * 180) / Math.PI
    console.log(`\n  μ=${mu}: a real block holds to atan(${mu}) = ${f(threshold, 1)}°`)
    console.log('   deg  tan θ   must    raw contact friction     adapter Coulomb')
    for (const deg of [5, 15, 25, 30, 40, 42, 44, 50, 60, 75]) {
      const must = Math.tan((deg * Math.PI) / 180) > mu ? 'SLIDE' : 'hold'
      const a = slope(deg, { mu, adapter: false })
      const b = slope(deg, { mu, adapter: true })
      console.log(
        `  ${String(deg).padStart(4)} ${f(Math.tan((deg * Math.PI) / 180), 3).padStart(6)}  ${must}  ` +
          `${f(a.drift, 3).padStart(9)} m ${String(a.moving).padStart(3)}/300   ${f(b.drift, 3).padStart(9)} m ${String(b.moving).padStart(3)}/300`,
      )
    }
  }
  const hold30 = slope(30, { mu: RUBBER, adapter: true })
  const slide50 = slope(50, { mu: RUBBER, adapter: true })
  console.log('\n  Raw contact friction holds at 75° (tan θ = 3.73) where the block must')
  console.log('  slide: the solver cancels the small per-step tangential velocity')
  console.log('  outright instead of capping it at μN·dt. The adapter model lands on')
  console.log(`  the Coulomb boundary: holds at 30° (${f(hold30.drift, 3)} m), slides at 50° (${f(slide50.drift, 2)} m).`)
  check(Math.abs(hold30.drift) < 0.05, `§1.5(e): adapter does not hold at 30°/μ=0.9`)
  check(slide50.drift < -1, `§1.5(e): adapter does not slide at 50°/μ=0.9`)
}

// ------------------------------------------------------------------ §3.4 cap
rule(`§3.4 cap: shipping character at v0=${V_MAX} m/s, ${MEASURE_STEPS} steps`)
{
  const launch = (mu, fixedRotation) => {
    const world = makeWorld()
    flatGround(world, mu)
    const body = character(world, { fixedRotation })
    body.position.set(0, BODY_Y0, 0)
    world.addBody(body)
    for (let i = 0; i < SETTLE_STEPS; i++) world.step(DT)
    const x0 = body.position.x
    body.velocity.set(V_MAX, 0, 0)
    body.angularVelocity.set(0, 0, 0)
    let airborne = 0
    for (let i = 0; i < MEASURE_STEPS; i++) {
      world.step(DT)
      if (world.contacts.length === 0) airborne++
    }
    return { d: body.position.x - x0, airborne }
  }
  // These are the only measurements of the SHIPPING configuration — character
  // body at v0 = V_MAX with free rotation, i.e. the setup the game will use —
  // so they are asserted, not merely printed. What must hold: the raw contact
  // friction does NOT reach the 3× acceptance line on the configuration that
  // ships, and the free-rotation body does not stay glued to the ground.
  for (const fixedRotation of [true, false]) {
    const ice = launch(ICE, fixedRotation)
    const rub = launch(RUBBER, fixedRotation)
    const ratio = ice.d / rub.d
    console.log(
      `  raw contact friction, fixedRotation=${String(fixedRotation).padEnd(5)}  ice d=${f(ice.d, 4)} (air ${String(ice.airborne).padStart(3)})   ` +
        `rubber d=${f(rub.d, 4)} (air ${String(rub.airborne).padStart(3)})   ratio=${f(ratio, 2)}`,
    )
    if (fixedRotation) {
      // Pinned rotation: the ratio looks fine, which is exactly why the card
      // must not quote it as the shipping number. Both distances stay tiny.
      check(ratio >= 3.0, `§3.4 cap: fixed-rotation ratio ${ratio.toFixed(2)}× below the 3× line`)
      check(
        ice.d < 1 && rub.d < 1,
        `§3.4 cap: fixed-rotation distances ${ice.d.toFixed(4)} / ${rub.d.toFixed(4)} m left [0, 1)`,
      )
    } else {
      // Free rotation is what ships. Here the contrast collapses below the
      // acceptance line — the finding the adapter layer exists to fix — and the
      // body leaves the ground, so the "ratio" is not a sliding ratio at all.
      check(
        ratio < 3.0,
        `§3.4 cap: free-rotation ratio ${ratio.toFixed(2)}× no longer shows the collapse`,
      )
      check(
        ice.airborne > 0 && rub.airborne > 0,
        `§3.4 cap: free-rotation body stayed on the ground (air ${ice.airborne}/${rub.airborne}); the collapse is no longer demonstrated`,
      )
    }
  }
  console.log('  Under the adapter model the same cap gives the §1.5(d) numbers.')
}

console.log()
if (process.argv.includes('--assert')) {
  if (failures.length) {
    console.error(`FAIL: ${failures.length} measurement(s) out of tolerance`)
    for (const m of failures) console.error(`  - ${m}`)
    process.exit(1)
  }
  console.log(`OK: all measurements within tolerance`)
}
