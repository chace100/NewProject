/**
 * ARCHITECTURE.md §1.4 的实测脚本:静止刚体在 cannon-es 0.20.0 上的滑动摩擦。
 *
 * 复现:
 *   mkdir -p /tmp/cannon-friction && cd /tmp/cannon-friction
 *   npm init -y && npm i cannon-es@0.20.0
 *   node <本文件路径>
 *
 * 期望(解析解):s = v0^2 / (2 * mu * g),mu = 0.05、g = 9.82、v0 = 10 -> 101.83 m
 * 实测:cannon-es 每步扣除的速度是 mu * g * N_contacts(与 dt 无关的冲量),
 *       于是滑行距离 ∝ dt(1/30 时 0.852 m,1/60 时 0.426 m,…),
 *       并且随形状的接触点数变化(长方体 0.426 m / 圆柱 0.207 m / 球 1.615 m)。
 *       `world.frictionGravity` 是官方补偿出口,但补偿量必须同时依赖 dt 与接触点数:
 *       按 g*dt/4 补偿后长方体精确回到 101.83 m,同一补偿量下圆柱只有 67.80 m。
 */
const CANNON = require('cannon-es');

const G = 9.82;
const V0 = 10;
const REST = 0.05;

function slide({ mu = 0.05, v0 = V0, dt = 1 / 60, shape = 'box', fixedRotation = true,
                 g = G, frictionGravityScale = 1 } = {}) {
  const world = new CANNON.World({ gravity: new CANNON.Vec3(0, -g, 0) });
  world.allowSleep = false;
  world.frictionGravity = new CANNON.Vec3(0, -g * frictionGravityScale, 0);
  world.defaultContactMaterial.friction = mu;

  const ground = new CANNON.Body({ mass: 0, shape: new CANNON.Plane() });
  ground.quaternion.setFromEuler(-Math.PI / 2, 0, 0);
  world.addBody(ground);

  let shapeDef, y;
  if (shape === 'box') { shapeDef = new CANNON.Box(new CANNON.Vec3(0.4, 0.8, 0.4)); y = 0.8; }
  else if (shape === 'sphere') { shapeDef = new CANNON.Sphere(0.5); y = 0.5; }
  else { shapeDef = new CANNON.Cylinder(0.4, 0.4, 1.6, 12); y = 0.8; }

  const body = new CANNON.Body({ mass: 1, shape: shapeDef, linearDamping: 0, angularDamping: 0 });
  body.position.set(0, y, 0);
  body.velocity.set(v0, 0, 0);
  body.fixedRotation = fixedRotation;
  body.updateMassProperties();
  world.addBody(body);

  const stepDv = () => { const v = body.velocity.x; world.step(dt); return v - body.velocity.x; };

  const dvFirstStep = stepDv();      // 首步接触尚未稳定,约为稳态值的一半
  const dvSteady = stepDv();         // 第二步即达到稳态
  let t = 2 * dt;
  while (t < 300) {
    world.step(dt);
    t += dt;
    if (body.velocity.length() < REST) break;
  }
  return { distance: body.position.x, dvFirstStep, dvSteady, seconds: t };
}

const analytic = (mu, v0 = V0) => (v0 * v0) / (2 * mu * G);

console.log(`解析解 (mu=0.05, g=9.82, v0=10): s = ${analytic(0.05).toFixed(2)} m`);
console.log('\n[1] 步长依赖(长方体, mu=0.05, v0=10)');
for (const dt of [1 / 30, 1 / 60, 1 / 120, 1 / 240]) {
  const r = slide({ dt });
  console.log(`    dt=1/${Math.round(1 / dt)} -> ${r.distance.toFixed(3)} m  (解析解之比 ${(r.distance / analytic(0.05)).toFixed(4)})`);
}

console.log('\n[2] 形状/接触点数依赖(1/60, mu=0.05, v0=10)');
for (const shape of ['box', 'sphere', 'cylinder']) {
  const r = slide({ shape });
  console.log(`    ${shape.padEnd(8)} -> ${r.distance.toFixed(3)} m`);
}

console.log('\n[3] 每步速度衰减 vs 理论值');
{
  const r = slide({});
  const theoretical = 0.05 * G / 60;               // mu*g*dt
  console.log(`    实测首步 dv   = ${r.dvFirstStep.toFixed(4)} m/s(接触尚未稳定,约为稳态一半)`);
  console.log(`    实测稳态 dv   = ${r.dvSteady.toFixed(4)} m/s = mu*g*N_contacts = ${(0.05 * G * 4).toFixed(4)}`);
  console.log(`    理论 dv/step  = mu*g*dt = ${theoretical.toFixed(6)} m/s -> 稳态实测是它的 ${(r.dvSteady / theoretical).toFixed(0)} 倍(= 1/dt * N_contacts)`);
}

console.log('\n[4] 官方补偿出口 world.frictionGravity(= g*dt/N)');
for (const dt of [1 / 30, 1 / 60, 1 / 120]) {
  const r = slide({ dt, frictionGravityScale: dt / 4 });
  console.log(`    dt=1/${Math.round(1 / dt)} 补偿 g*${(dt / 4).toFixed(5)} -> ${r.distance.toFixed(2)} m`);
}
{
  const r = slide({ shape: 'cylinder', frictionGravityScale: (1 / 60) / 4 });
  console.log(`    同一补偿量换圆柱(接触点数不同) -> ${r.distance.toFixed(2)} m  <-- 补偿量不可复用到其他形状`);
}

console.log('\n[5] 比值本身仍然满足验收(说明问题不在比值,而在绝对标度与帧率稳定性)');
const ice = slide({ mu: 0.05 }).distance;
const rubber = slide({ mu: 0.9 }).distance;
console.log(`    ice/rubber = ${(ice / rubber).toFixed(2)}  (要求 >= 3)`);
console.log(`    但冰面上 10 m/s 只滑 ${ice.toFixed(2)} m —— 玩家感知不到"冰面滑得远"`);
