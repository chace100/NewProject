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
 * the defect that section demonstrates. Its numbers are therefore reported but
 * not asserted on.
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
  // That proportionality is the measurement, not an artefact.
  const run = (fps) => {
    const world = makeWorld()
    flatGround(world, 0)
    const body = character(world, { friction: 0, fixedRotation: true })
    body.position.set(0, BODY_Y0, 0)
    world.addBody(body)
    for (let i = 0; i < SETTLE_STEPS; i++) world.step(DT)
    const x0 = body.position.x
    body.velocity.set(V_MAX, 0, 0)
    if (fps === null) {
      for (let i = 0; i < 180; i++) world.step(DT)
    } else {
      for (let i = 0; i < 3 * fps; i++) world.step(DT, 1 / fps, 3)
    }
    return body.position.x - x0
  }
  const ideal = 3 * V_MAX
  console.log(`  frictionless, v0=${V_MAX} m/s, 3 s of wall time, ideal ${ideal} m`)
  console.log('  call form                       x (m)     simulated   of ideal')
  const single = run(null)
  console.log(
    `  world.step(1/60) × 180          ${f(single, 3).padStart(7)}   ${f(single / V_MAX, 3)} s     ${f((100 * single) / ideal, 1)}%`,
  )
  for (const fps of [60, 30, 10, 5]) {
    const d = run(fps)
    console.log(
      `  world.step(1/60, 1/${String(fps).padEnd(2)}, 3) × ${String(3 * fps).padEnd(4)} ${f(d, 3).padStart(7)}   ${f(d / V_MAX, 3)} s     ${f((100 * d) / ideal, 1)}%`,
    )
  }
  console.log('  1-arg is exact and repeatable. The 3-arg form caps substeps at')
  console.log('  maxSubSteps per *call*, then discards the remainder with')
  console.log('  `accumulator %= dt`, so at 5 fps only a quarter of the time is')
  console.log('  simulated. It also consults performance.now() to bail out, which')
  console.log('  makes the substep count machine-dependent — see DIST/12510-12549.')
  check(Math.abs(single - ideal) < 1e-9, '§1.5(a): 1-arg step is not exact')
}

// ------------------------------------------------------------------ §1.5(b)
rule('§1.5(b) effective friction is the PRODUCT, and the character material is mandatory')
{
  console.log('  ground μ   character μ   μ_eff measured   μ_g·μ_c')
  for (const [gm, cm] of [
    [ICE, CHAR],
    [RUBBER, CHAR],
    [ICE, 0.3],
    [RUBBER, 0.3],
    [ICE, 0.0],
  ]) {
    const world = makeWorld()
    flatGround(world, gm)
    const body = character(world, { friction: cm })
    body.position.set(0, BODY_Y0 + 0.002, 0)
    world.addBody(body)
    for (let i = 0; i < SETTLE_STEPS; i++) world.step(DT)
    const eff = muEff(world)
    console.log(
      `  ${String(gm).padEnd(10)} ${String(cm).padEnd(13)} ${f(eff).padEnd(16)} ${f(gm * cm)}`,
    )
    check(eff == null || Math.abs(eff - gm * cm) < 5e-4, `§1.5(b): μ_eff ${eff} != ${gm * cm}`)
  }
  console.log('  -- character body with NO Material --')
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
    check(eff == null || Math.abs(eff - 0.3) < 5e-4, `§1.5(b): fallthrough μ_eff ${eff} != 0.30`)
  }
  console.log('  The `matA && matB && ...` guard in createFrictionEquationsFromContact')
  console.log('  (DIST/10448-10475) falls through to cm.friction when EITHER body')
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
  console.log('  μ       v0    d measured   analytic v0²/(2μg)   error     stop')
  for (const [mu, label] of [
    [ICE, 'ice 0.05'],
    [RUBBER, 'rubber 0.90'],
  ]) {
    for (const v0 of [2, 4, 8, V_MAX]) {
      const r = slideCoulomb(mu, v0)
      const analytic = (v0 * v0) / (2 * mu * G)
      console.log(
        `  ${label.padEnd(11)} ${String(v0).padStart(2)}  ${f(r.d, 3).padStart(9)} m   ${f(analytic, 3).padStart(9)} m      ${f((100 * (r.d - analytic)) / analytic, 2).padStart(6)}%  ${f(r.stop, 2)} s`,
      )
    }
  }
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
  check(doubleIce >= 3.6 && doubleIce <= 4.4, `§1.5(d): doubling ratio ${doubleIce.toFixed(3)} leaves [3.6, 4.4]`)
  check(i12 <= 400, `§1.5(d): d_ice(${V_MAX}) = ${i12.toFixed(1)} m exceeds the recommended ground`)
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
  for (const fixedRotation of [true, false]) {
    const ice = launch(ICE, fixedRotation)
    const rub = launch(RUBBER, fixedRotation)
    console.log(
      `  raw contact friction, fixedRotation=${String(fixedRotation).padEnd(5)}  ice d=${f(ice.d, 4)} (air ${String(ice.airborne).padStart(3)})   ` +
        `rubber d=${f(rub.d, 4)} (air ${String(rub.airborne).padStart(3)})   ratio=${f(ice.d / rub.d, 2)}`,
    )
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
