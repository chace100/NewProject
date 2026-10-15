# 3D 惯性跑酷 —— 架构设计文档

| 项 | 值 |
| --- | --- |
| 状态 | **ARCH_DONE** —— 待人工 `/approve` 后进入开发(本单元 hitl:done) |
| 对应 issue | #6 Architecture: 技术栈定稿、物理模型与关卡数据格式设计 |
| 上游依赖 | #5 Research: 3D 网页游戏技术选型与惯性教学游戏设计调研 —— 产出 `docs/research/issue-005-3d-web-game-tech-selection-and-inertia-game-design.md`(`REQ_DONE`,commit `3d26149`) |
| 下游消费方 | #7 脚手架 / #8 物理核心 / #9 关卡与进度 / #10 游戏感打磨 |
| 最后更新 | 2026-10-15(修订 2:与 #5 研究卡对账、修正示例关卡与物理参数、补充可复现的实测证据) |
| 配套文件 | [`docs/schema/level.schema.json`](./schema/level.schema.json)(机器可读的关卡 schema)、[`docs/benchmarks/`](./benchmarks/)(本文所有实测数字的复现脚本) |

## 0. 与上游研究卡(#5)的关系

本文初稿成稿时,仓库里还没有 #5 的产出;研究卡随后落地在 `openhands/issue-5` 分支的 commit `3d26149`(文件 `docs/research/issue-005-3d-web-game-tech-selection-and-inertia-game-design.md`,标记 `REQ_DONE`)。**本修订逐条对账过该卡**,结论见 §1.5:渲染库、参数、控制器约束、关卡参数全部与卡一致;唯一分歧是"是否引入 cannon-es 作为物理引擎",本文用 §1.4 的实测数据支持不引入,并按该卡 §5.1 的建议保留了可替换缝。

两条纪律沿用卡的口径:

- 物理只要求**定性正确**,但"定性正确"必须能被自动化测试量化验收(本文 §2.9、§6.1)。
- 教学文案的用词需与教材一致(如"惯性"与"惯性定律"的区分),这是本单元唯一留给人工复核的点(§8)。

## 1. 技术栈定稿

### 1.1 决策一览

| 维度 | 定稿 | 一句话理由 |
| --- | --- | --- |
| 渲染库 | **Three.js**(ESM,`^0.186`) | 最小场景实测 **136 KB gzip**,约为 Babylon.js(381 KB)的三分之一;MIT;社区体量第一(116k stars) |
| 物理方案 | **自写运动学 + 解析带状地形碰撞(不引入物理引擎)** | 关卡 2 的验收要求是"同初速下冰面 / 橡胶滑行距离比 ≥3"且可复现;实测 cannon-es 的滑动摩擦与 `dt`、接触点数耦合(§1.4),自写模型给出与帧率无关的闭式解 |
| 语言 | **TypeScript**(`strict`) | 关卡 JSON → 类型化运行时对象,字段写错在编译期就报错 |
| 构建 | **Vite** | 原生 ESM dev server + Rollup 生产构建,零配置支持 `npm run dev` / `npm run build`(#7 要求) |
| UI | **原生 DOM + CSS(不引框架)** | HUD 只有速度/材质/计时/提示卡;引 React 要多付 67 KB gzip(实测),在首屏预算里不划算 |
| 单元/物理测试 | **Vitest** | 与 Vite 共用转换管线;`sim/` 是纯函数,可在 Node 里跑,无需 WebGL |
| 冒烟/E2E | **Playwright** | 能在 CI 里用 SwiftShader 起真实 WebGL,验证"页面能开、能操作角色" |
| 关卡格式校验 | **JSON Schema(draft 2020-12)+ ajv** | schema 是唯一的格式契约;测试期校验所有关卡,新增关卡改数据不改代码 |
| 顶层参数 | 见 §2.10(`g = 9.82`、`maxSpeed = 12`、`μ = 0.05/0.25/0.90`、`1/60 s` 定步长) | 与研究卡 §3.4 逐项一致 |
| 进度存储 | `localStorage` | 无后端、无登录(epic 约束) |

### 1.2 体积实测(2026-10-15)

方法:在临时目录 `npm i <包>` 后用 `esbuild --bundle --minify --format=esm` 打包"最小可用场景",对产物取 `gzip -9` 大小。**各入口源码已提交到 [`docs/benchmarks/bundle-size/`](./benchmarks/bundle-size/),任何人可用同一命令复现下表**(最小场景的体积对入口极敏感,不提交入口等于不可复现)。

| 打包入口 | 内容 | min | **gzip** |
| --- | --- | --- | --- |
| `three-entry.js` | Scene + PerspectiveCamera + WebGLRenderer + BoxGeometry + MeshStandardMaterial + 方向光/环境光 + OrbitControls | 545 KB | **136 KB** |
| `babylon-entry.js` | Engine + Scene + ArcRotateCamera + HemisphericLight + MeshBuilder + standardMaterial + box/ground builder | 1 615 KB | **381 KB** |
| `rapier-entry.js` | 仅 `import RAPIER`(compat 包,内嵌 WASM 的 base64) | 4 233 KB | **1 613 KB** |
| `cannon-entry.js` | 整库 `import * as CANNON` | 121 KB | **35 KB** |
| `react-entry.js` | react + react-dom 的最小函数组件 | 217 KB | **67 KB** |

活跃度与许可(同日 GitHub API):`mrdoob/three.js` 116 428 stars,MIT,当日有提交;`BabylonJS/Babylon.js` 26 166 stars,Apache-2.0,当日有提交;`dimforge/rapier` 5 862 stars,Apache-2.0;`pmndrs/cannon-es` 2 064 stars,MIT,**最后一次提交 2024-01-06(近两年未动)**。

> 入口敏感性的说明:研究卡测到的 Three.js 最小场景是 154 KB gzip(它的入口多了一个刚体世界与角色刚体),Babylon.js 是 380 KB(与本文一致),cannon-es 是 35 KB(与本文一致)。量级结论不受影响:Three.js 最小、且小于 Babylon.js 的一半。cannon-es 只算最小子集时还能更小(QA 独立测得 24 KB),但**这不是选型依据**,见 §1.4。

### 1.3 为什么不选 Babylon.js(与研究卡一致)

Babylon.js 在工具箱完整度上有优势(自带 debug 层、材质库、PBR、动画系统)。但本项目的场景非常小:一条带状赛道 + 一个胶囊体角色 + 几个装饰物。为此要付的代价是**同场景 381 KB gzip vs 136 KB gzip**,接近三倍——而省下的能力(RTT、节点材质、后处理、物理插件)一个都不会用。这与研究卡 §1.2 / §1.6 的结论一致。

### 1.4 为什么不引入物理引擎(本文与研究卡的唯一分歧,附实测)

研究卡 §1.4 推荐 **Three.js + cannon-es + 适配层**,理由是"cannon-es 只要 36 KB,库仑摩擦下 `a = μg`、`d = v₀²/(2μg)` 无需自写,且能在 Node 里无渲染跑物理";卡 §1.5 同时把"角色控制层必须自写、禁止直接设速度"列为硬约束。

**本文不采纳该推荐,理由是实测出来的:在 cannon-es 0.20.0 上,静止刚体的滑动摩擦既不等于 `μ·g`,也不与步长无关。**

复现脚本:[`docs/benchmarks/physics-engine/cannon-es-friction.cjs`](./benchmarks/physics-engine/cannon-es-friction.cjs)(`npm i cannon-es@0.20.0 && node cannon-es-friction.cjs`)。实验设置:1 kg 长方体(半宽 0.4、半高 0.8)置于静态平面,`world.gravity = (0, -9.82, 0)`、`linearDamping = 0`、`angularDamping = 0`、`defaultContactMaterial.friction = μ`,初速 10 m/s 水平滑行,速度 < 0.05 m/s 视为停住。解析解 `s = v₀²/(2μg) = 101.83 m`(μ = 0.05)。

| 条件 | 实测滑行距离 | 与解析解之比 |
| --- | --- | --- |
| `dt = 1/60`(卡建议的定步长) | **0.426 m** | 0.004 |
| `dt = 1/30` | 0.852 m | 0.008 |
| `dt = 1/120` | 0.213 m | 0.002 |
| `dt = 1/240` | 0.106 m | 0.001 |
| 球形刚体(单接触点),`dt = 1/60` | 1.615 m | 0.016 |

机制可以从源码看明白:`Narrowphase.createFrictionEquationsFromContact()` 用
`mug = friction * |world.frictionGravity || world.gravity|` 与 `maxForce = mug * reducedMass`
给**每一个接触点**建一对摩擦方程,而这个上限在求解器里是**每步作用的冲量**:实测每步速度衰减恒为 `μ·g·N_contacts`(N=4 时恰为 `0.05 × 9.82 × 4 = 1.964 m/s` 每步),与 `dt` 无关。于是滑行距离 ∝ `dt`(上表),且随形状的接触点数变化(同一个 μ,长方体 0.426 m、圆柱 0.207 m、球 1.615 m)。

准确地说:首步因为接触还在建立,衰减是稳态的一半(实测 0.982 m/s),第二步起稳定在 1.964 m/s——即 `μ·g·N`;理论上应为 `μ·g·dt = 0.0082 m/s`,实测是它的 **240 倍**(= `N/dt`)。

卡里提到的"用 `frictionGravity` 调摩擦"确实是唯一的官方出口,但它的补偿量必须写成 `g·dt/N_contacts`,即**同时依赖帧率和接触点数**:脚本里按 `g·dt/4` 补偿后三种步长都能精确复现 101.83 m,但同一个补偿量换成圆柱体就只能滑 67.80 m。也就是说,要让教学游戏的核心关系成立,得为每种形状、每个帧率手动凑一个伪重力——这正是"旋钮汤"。

对教学游戏的后果:

1. **角色几乎立刻停住**。冰面上 `μ = 0.05` 实测滑行 0.43 m,而"冰面滑得远"正是本游戏的第一个教学点;0.43 m 与 8 m(橡胶地)之间没有玩家能感知的差异。
2. **滑行距离随设备帧率变化**。低端机掉到 30 fps 后,同一操作的滑行距离翻倍——与 epic 验收标准 3"同一操作在不同摩擦/速度下产生可观察的不同结果"直接冲突。
3. **断言变成形状依赖**。`≥3 倍` 的比值在纯 `μ` 上仍然成立(实测 30.7 倍),但绝对距离依赖接触点数,后续给角色换碰撞体(盒子 → 胶囊 → 多球)就会让测试数字整体漂移。

本文的方案因此是:**角色运动与地面摩擦自写**(研究卡 §1.5 本身也要求输入只能映射为有限加速度、禁止直接设速度,所以控制器无论如何都是自写的),地形接触用解析的"中心线 + 半宽"模型(§2.8),`sim/` 保持零依赖、纯函数、可在 Node 里跑。

**采纳研究卡的"可替换"建议**:`sim/` 只通过 `stepSim(state, input, level, dt)` 对外,渲染层不碰物理。若出现下列触发条件之一,再接 cannon-es(36 KB)并把地面摩擦交给自写层:

| 触发条件 | 为什么那时值得引入引擎 |
| --- | --- |
| 关卡需要任意网格 / 可旋转地形 / 移动平台 | 解析带状模型覆盖不到,碰撞求解器开始回本 |
| 场上动态刚体数 > 8(可推倒的障碍、碎块) | 需要真正的接触求解与休眠 |
| 角色需要"飞出去摔在斜坡上再滚"这类演出 | 引擎的接触响应比自写更省事 |
| §6.1 的断言在自写模型下无法满足(目前未出现) | 说明自写模型的边界不够用 |

引入时的已知代价,直接引用上面的测量:**必须先用 `frictionGravity` 补偿帧率与接触点数,否则地面摩擦与 `dt` 强耦合**;这一点写在这里,避免下一个接手的人重新踩一遍。

### 1.5 与研究卡逐条对账

| 议题 | #5 研究卡的结论 | 本文定稿 | 依据 |
| --- | --- | --- | --- |
| 渲染库 | Three.js(卡 §1.2/§1.4) | **一致** | §1.2 实测 136 KB vs 381 KB |
| 物理引擎 | cannon-es + 适配层(卡 §1.4) | **分歧**:不引入,角色运动学与地面摩擦自写;保留适配缝与触发条件 | §1.4 实测(摩擦与 dt、接触点数耦合) |
| 重力 | 9.82 m/s²(与教材一致,卡 §3.4) | **一致** | §2.10 |
| 摩擦系数 | `μ_橡胶 = 0.90`、`μ_冰面 = 0.05`(18 倍,卡 §3.4) | **一致**(另加普通地面 0.25,构成 1 : 5 : 18) | §2.9 |
| 水平速度上限 | 12 m/s(卡 §3.4) | **一致** | §2.10 |
| 物理定步长 | 1/60 s(卡 §3.4) | **一致** | §2.3 |
| 静止判定阈 | 0.05 m/s(卡 §3.4) | **一致**(`physics.restThreshold`) | §2.10 |
| 过关容差梯度 | 关 1 ±1.5 m → 关 5 ±0.4 m(卡 §3.4) | **一致**(由关卡的 `zone` 宽度表达) | §3.3 |
| 首屏预算 | JS + WASM ≤ 400 KB gzip(卡 §3.4) | **一致且更严**:本栈无 WASM,预算收紧到 ≤ 220 KB | §5.1 |
| 角色控制层 | 输入 → 有限加速度,禁止直接设速度(卡 §1.5 硬约束) | **一致**,并扩展为 §2.4/§2.5 的公式 | §2.4 |
| 视觉可感知 | 建材颜色/反光/脚步声区分摩擦(卡 §2.3) | **一致**:`surfaces[].color/pattern/label` | §3.3 |
| 关卡数据格式 | 由 #6 定义(卡 §5.5) | §3 的 schema | §3 |
| 低端设备降级 | 请 #6 明确(卡 §5.2) | §5.3 的降级档位表 | §5.3 |
| 教学文案口径 | 建议人工/教师复核(卡 §5.6) | 列为 §8 的待确认项 | §8 |

### 1.6 工具链与脚本约定

```jsonc
// package.json(供 #7 落地时参考)
{
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "typecheck": "tsc --noEmit",
    "lint": "eslint .",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test"
  }
}
```

运行时依赖白名单(MVP 只允许这些;新增依赖需要先改本文):

| 依赖 | 类型 | 版本约束 | 说明 |
| --- | --- | --- | --- |
| `three` | runtime | `^0.186` | 唯一渲染依赖;`three/addons/*` 按需引入 |
| `typescript` | dev | `^5` | 若工具链稳定可评估升级,本文不锁死 |
| `vite` | dev | `^8` | 构建 |
| `vitest` | dev | `^5` | 单元测试 |
| `@playwright/test` | dev | `^1` | 冒烟 E2E |
| `ajv` | dev(运行时仅 dev 校验) | `^8` | JSON Schema 校验 |
| `eslint`(+ typescript-eslint) | dev | 最新 | 含 §4.3 的依赖边界规则 |

不引入的类别:UI 框架、状态管理库、动画库(tween)、后处理库、通用物理引擎、CSS 框架、图表库。理由统一是首屏预算与"避免为一次性需求付长期维护成本"。

## 2. 物理模型方案

### 2.1 分层:哪些"用引擎"、哪些自写

| 层 | 归属 | 内容 |
| --- | --- | --- |
| 运动学(位置/速度/朝向积分) | **自写**,`src/sim/` | 固定步长半隐式欧拉积分;地面摩擦减速;转向权衰减;跳跃竖直速度 |
| 地形接触判定 | **自写**,`src/sim/collision.ts` | 中心线带状地形的解析判定(段内里程 `s` + 横向偏移 `u` + 地面高度 `y_ground`);障碍用解析形状重叠 |
| 渲染 | Three.js | 由同一份 Level 数据生成网格;不允许渲染层参与物理判定 |
| 阴影/材质/相机 | Three.js | 视觉层,不反馈给 `sim/` |

**硬性规则**(与研究卡 §1.5 的"禁止直接设速度"同源):`src/sim/` 不 import `three`、不碰 DOM、不使用 `requestAnimationFrame`;输入只能改变**加速度**与朝向角速度,任何"直接给速度赋值"的写法都视为破坏教学意图的缺陷。这条规则由 §6.3 的边界测试强制。

### 2.2 状态、坐标与单位

```ts
// src/sim/state.ts
export interface SimState {
  position: { x: number; y: number; z: number };  // 世界坐标(米),y 向上
  velocity: { x: number; y: number; z: number };  // 世界坐标(米/秒)
  heading: number;                                 // 朝向(弧度,绕 y 轴)
  grounded: boolean;
  contact: { segmentId: string; s: number; u: number } | null; // 当前地形段内里程/横向偏移
  elapsed: number;                                 // 关卡计时(秒)
  status: 'running' | 'cleared' | 'failed';
}
```

**单位铁律(角度)**:关卡 JSON 里所有角度都是**度**,运行时状态一律是**弧度**,换算只发生在 `levels/load.ts` 这一处,并且**只在加载时做一次**。所以:

- `physics.turnAuthority.maxTurnRate`(度/秒)在 `load.ts` 里换算成 `maxTurnRateRad`(弧度/秒),`sim/` 只接收 `maxTurnRateRad`;
- `camera.pitch`、`terrain[].curvature`、`spawn.heading` 同理,`sim/` 与 `render/` 都不得再乘一次 `π/180`。

```ts
// src/levels/load.ts(唯一换算点)
const maxTurnRateRad = (raw.physics?.turnAuthority?.maxTurnRate ?? 120) * Math.PI / 180; // 120°/s → 2.094 rad/s
```

### 2.3 固定步长积分(确定性的前提)

```ts
export const FIXED_DT = 1 / 60;         // 秒

// src/app/loop.ts
accumulator += Math.min(frameDelta, 0.25);   // 防止切后台回来时"时间债"爆炸
while (accumulator >= FIXED_DT) {
  state = stepSim(state, input.sample(), level, FIXED_DT);
  accumulator -= FIXED_DT;
}
```

物理永远以 `FIXED_DT` 推进,渲染帧率与物理步长解耦:低端机掉到 30 fps 时,**视觉变卡、物理结论不变**。这是 §5.3 降级策略成立的基础,也让 §6 的断言与设备无关。(对照 §1.4:cannon-es 的滑动摩擦做不到这一条,这是本文自写模型的主要原因。)

积分用半隐式欧拉(先更新速度、再更新位置),这是跑酷手感与数值稳定性的平衡点;本项目要的是"定性正确且可复现",不是弹道学精度。

### 2.4 摩擦与惯性

**输入是加速度的来源,不是速度的赋值。**

```ts
// 地面,沿运动方向的标量模型(方向由速度矢量给出)
const aFriction = mu * gravity;                    // 摩擦减速度,方向与速度相反
const aInput    = input.forward ? accel : 0;       // 玩家输入
const aNet      = aInput - aFriction;              // 净加速度(符号决定加速/减速)
```

三条教学上必须成立的性质:

1. **不按前进键时,速度不会自己清零。** 玩家松手后,角色按当前速度与所在路面摩擦继续滑行。
2. **滑行距离只由初速与摩擦系数决定。** `s = v² / (2μg)`,同初速下摩擦越小滑得越远。
3. **空中不减速。** 默认 `airDrag = 0`,腾空时水平速度严格不变,抛物线落点只由水平速度和滞空时间决定。这是刻意的教学取舍:加一点"空气阻力"手感更"游戏",但会破坏"没有外力,运动状态不改变"的演示;该字段保留为可调(供 #10 逐关覆盖),而不是写死。

**离散化的坑(必须处理)**:直接写 `v -= a * dt` 时,当 `v < a*dt` 速度会被减成负数或抖动到零附近,滑行距离因此依赖 `dt`。因此本步位移用**解析求解**,并显式处理三种"本步中途发生状态切换"的情形:`a = 0`(无摩擦段,§6.1 断言 3)、**本步内减速到 0**、以及**本步内加速到限速**:

```ts
// src/sim/friction.ts
export function advanceAlongDirection(
  v: number,
  a: number,
  dt: number,
  maxSpeed = Infinity,                                // §2.10 的 maxSpeed;关卡可逐项覆盖(§3.3)
): { dv: number; ds: number } {
  if (a === 0) return { dv: 0, ds: v * dt };          // 无摩擦:匀速直线运动(牛顿第一定律的直接体现)
  if (a < 0 && v + a * dt <= 0) {                     // 本步内停住:s = v²/(2|a|),与 dt 无关
    return { dv: -v, ds: (v * v) / (-2 * a) };
  }
  if (a > 0 && v + a * dt > maxSpeed) {               // 本步内到达限速:tCap 处拆成两段
    const tCap = (maxSpeed - v) / a;                  // v 已在限速上时 tCap = 0,位移正好 maxSpeed*dt
    const ds = v * tCap + 0.5 * a * tCap * tCap + maxSpeed * (dt - tCap);
    return { dv: maxSpeed - v, ds };
  }
  const vNext = v + a * dt;
  return { dv: a * dt, ds: vNext * dt - 0.5 * a * dt * dt };
}
```

这样"停住那一步"的距离是精确的 `v²/(2|a|)`,整段滑行距离等于闭式解,与帧率无关,断言可以写成严格不等式而不是容差区间。`μ = 0` 的段(无摩擦)也不会再产生 `NaN` —— 旧版草稿在这里会除以零,已修正。

**限速由本函数负责,调用方不得再截断一次。** `min(maxSpeed, v + a*dt)` 不能留在调用方:一旦末速度在函数外被截断,而函数内部仍返回 `v*dt + 0.5*a*dt*dt`,这一步就短掉了 `0.5*a*dt²`。原因是梯形恒等式

```
v_new*dt - 0.5*a*dt² == 0.5*(v_old + v_new)*dt     只在 v_new = v_old + a*dt 未被截断时成立
```

饱和步(`v == maxSpeed`、仍在按前进键)是最容易看出问题的一步:位移必须正好是 `maxSpeed * dt`,而"先算出 `v + a*dt`、截断后再减去 `0.5*a*dt²`"会给出 `maxSpeed*dt - 0.5*a*dt²`。本关 `a_net = 12 - 0.25×9.82 = 9.545 m/s²`、`dt = 1/60`,每步短 **0.001326 m**;§3.5 那条路线有 58 个饱和步,累计短 **0.078 m**。所以上面的写法把限速解析地并入同一步:在 `tCap = (maxSpeed - v)/a` 处切开,前段按 `a` 推进、后段按恒速 `maxSpeed` 推进,饱和步因此正好是 `maxSpeed*dt`(§6.1 断言 13)。这与"本步内停住"用的是同一个手法,不是特例补丁。

### 2.5 转向:运动状态保持的第二条可感证据

```ts
// maxTurnRateRad 由 levels/load.ts 从关卡 JSON 的“度/秒”换算而来(§2.2),sim/ 不再做换算
const authority = Math.max(floor, 1 / (1 + speed / vRef));   // vRef 默认 8 m/s,floor 默认 0.3
heading += input.steer * maxTurnRateRad * authority * dt;
```

默认 `maxTurnRateRad = 120°/s = 2.094 rad/s`:满转向权时每步转过 2°(1/60 s),而不是 50.9°。速度越高转向权越低:高速时按方向键,角色先"冲过头"再拐过来。**这是手感层,不是物理层**,文档与 UI 都不把它说成物理定律;参数放在 `physics.turnAuthority`,允许 #10 逐关调。

### 2.6 跳跃:水平速度决定落点

```ts
vy = jump.initialVerticalSpeed;                       // 默认 5.5 m/s
// 平地被: T = 2J/g ; 落点比起点低 Δy 时: T = (J + sqrt(J² + 2gΔy)) / g
horizontalRange = speed * T;                          // 空中水平速度不变
```

默认 `g = 9.82 m/s²`、`J = 5.5 m/s` → 平跳滞空 **1.12 s**、跳高 **1.54 m**。水平速度 6 / 10 / 12 m/s 对应落点 **6.7 / 11.2 / 13.4 m**。第 4 关的"跳过冰缝"就建立在"落点 = 水平速度 × 滞空时间"这条可预判关系上。

> 手感注:平台跳跃类游戏常用 2–4 倍真实重力来获得"干脆"的落地。本文选择与教材一致的 `g = 9.82`(研究卡 §3.4 的口径),把"干脆"交给 `J` 与关卡尺度;若 #10 认为落地太飘,正确做法是调 `J` 与镜头节奏,而不是偷偷把 `g` 改回 20 —— 后者会让"把数字代进 `s = v²/(2μg)` 的学生"对不上账。

### 2.7 坡度

`type: "ramp"` 的段用 `grade`(%)描述。**`grade` 是正切值(`tanθ = grade/100`),必须换算成正弦/余弦后再用**,不能把百分比直接当 `sinθ`:

```ts
const theta = Math.atan(grade / 100);
const aNet = aInput - mu * gravity * Math.cos(theta) - gravity * Math.sin(theta);
```

上坡自然减速、下坡自然加速,不需要额外代码路径。误差量级:把 `grade/100` 当 `sinθ` 在 `grade = 60` 时偏差 **16.6%**(`sin(atan 0.6) = 0.5145` vs `0.6000`),在 `grade = 10` 时偏差 0.5%;本项目坡度多取 ±10% 以内,但仍按正确的关系写,免得后续复算对不上。

陡坡上的**静摩擦**判定只需一句比较:坡度足够陡时(`|tanθ| > μ_s`)角色应沿坡下滑而不是被摩擦"粘"住,`μ_s` 取与动摩擦相同值(教学上不做动静摩擦区分,`cosθ ≈ 1` 时两者差异对直觉无影响)。这正好回应研究卡"自写模型扛不住斜坡"的担心:带状地形上的坡面接触是闭式判定,不需要求解器。

### 2.8 地形与接触:解析而不是网格

地形由**中心线 + 半宽**的带子构成(见 §3),接触判定是纯解析的。判定顺序(与 schema 的 `walls` / `failure.outOfBounds` 描述一致):

1. **贴地**:把位置投影到段中心线,得到段内里程 `s` 与横向偏移 `u`。若 `0 ≤ s ≤ length` 且 `|u| ≤ width/2`,地面高度 `y_ground = centerlineY(s)`;若 `y ≤ y_ground + ε` 且 `vy ≤ 0`,则 `y = y_ground`、`vy = 0`、`grounded = true`,否则走 §2.6 的抛物线。
2. **材质采样**:当前段的 `surface` 就是这一步的摩擦系数来源。**摩擦分区是"路径上的区间",不需要任何网格采样或贴图读取**。
3. **横向越界**:当 `|u| > width/2` 且 `y` 不高于该侧墙高时,按 `walls.left/right` 处理 —— `solid` 撞停、`bounce` 按 `restitution` 反弹、`none` 直接滑出去。**段的 `walls` 优先于全局 `failure.outOfBounds`。**
4. **兜底**:只有当角色越过墙顶(或所在段没有墙)时才走 `failure.outOfBounds`(`block` 推回边界 / `fail` 判失败);而 `failure.fallBelowY` 是独立终止条件,优先级最高,也负责"飞出去掉下去"这类演出(#10 要用)。
5. **障碍**:`box` / `cylinder` 与角色胶囊做解析重叠检测,法向推出 + `restitution` 反弹;`behavior: "hazard"` 的障碍接触即失败。
6. **性能**:MVP 单关段数 ≤ 32、障碍 ≤ 16,线性扫描足够;超过 64 段再加 AABB 空间索引,不进 MVP。

### 2.9 定性正确性论证:≥3 倍关系为什么稳

摩擦减速下 `s = v²/(2μg)`,因此**同初速下两种材质的滑行距离之比 = 摩擦系数之比的倒数**:

```
s_冰 / s_橡胶 = μ_橡胶 / μ_冰 = 0.90 / 0.05 = 18 ×
s_冰 / s_普通 = μ_普通 / μ_冰 = 0.25 / 0.05 = 5 ×
```

验收要求是 ≥3 倍,默认系数给出 18 倍余量(普通地 vs 冰面 5 倍);即使 #10 为提高手感把橡胶 μ 调到 0.3,仍有 6 倍。**比值由数据决定,不由求解器迭代决定**——这是自写模型的直接收益(§1.4)。

数值自检(默认 `g = 9.82 m/s²`,`s = v²/(19.64μ)`):

| 初速 | 冰面(μ=0.05) | 普通(μ=0.25) | 橡胶(μ=0.90) | 橡胶 vs 冰面 |
| --- | --- | --- | --- | --- |
| 6 m/s | 36.7 m | 7.3 m | 2.0 m | 18 × |
| 10 m/s | 101.8 m | 20.4 m | 5.7 m | 18 × |
| 12 m/s(速度上限) | 146.6 m | 29.3 m | 8.2 m | 18 × |

减速度:冰面 `a = 0.491 m/s²`、普通 `2.455 m/s²`、橡胶 `8.838 m/s²`。关卡设计直接读这两张表下料:例如"冰面段 40 m + 出场后再给 30 m 普通地"就是 §3.5 的示例关卡(§6.1 断言 11 用参考积分器逐帧验证它可通)。

### 2.10 默认参数表(`src/app/config.ts` 的唯一真源,与研究卡 §3.4 对齐)

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `FIXED_DT` | 1/60 s | 物理定步长,与渲染帧率解耦 |
| `gravity` | **9.82 m/s²** | 与教材口径一致,便于学生用 `s = v²/(2μg)` 自行验算 |
| `airDrag` | 0 | 腾空不减速,服务"外力停止则运动状态保持"的演示 |
| `accel` | 12 m/s² | 前进键地面加速度;普通地面上净加速度 `12 − 2.455 = 9.545 m/s²` |
| `maxSpeed` | 12 m/s | 速度上限;0 → 12 m/s 需要 **7.54 m**(解析 `v²/(2a)`)或 **7.66 m**(离散 1/60,§2.4 的限速步) |
| `restThreshold` | 0.05 m/s | **物理层**静止阈:积分器在 `v ≤ restThreshold` 时认为"已停住"、退出滑行。与 `stopInZone.maxStopSpeed` 是**两个不同的量**,见下 |
| `stopInZone.maxStopSpeed` | 0.3 m/s | **判定层**过关阈:`stopInZone` 关卡检查"当前速度 ≤ 本值"即算停稳(§3.3 目标表) |
| `turnAuthority` | `vRef = 8 m/s`,`floor = 0.3`,`maxTurnRate = 120 °/s` | 高速转向衰减;夹角速度 = `maxTurnRateRad × authority` |
| `jump.initialVerticalSpeed` | 5.5 m/s | 滞空 1.12 s、跳高 1.54 m |
| `jump.coyoteSeconds` | 0.1 s | 离地宽限,手感 |
| 材质 `ice` | μ = 0.05 | 见 §2.9 |
| 材质 `normal` | μ = 0.25 | |
| 材质 `rubber` | μ = 0.90 | |
| 角色胶囊 | 半径 0.4 m,高 1.6 m | 与障碍/墙的碰撞体积 |

**`restThreshold` 与 `stopInZone.maxStopSpeed` 不是同一个量,不要合并。** 两者阈值接近,职责不同,分别属于物理层与判定层:

- `restThreshold`(**物理**):积分器在 `v ≤ restThreshold` 时把速度归零、退出"滑行中"状态,`surfaceChanged` 等事件也以此为准(§2.8)。它决定**运动何时停止**。
- `maxStopSpeed`(**判定**):`stopInZone` 目标在 `holdSeconds` 内检查 `v ≤ maxStopSpeed` 才算"停稳"。它决定**停稳是否被认可**。

默认值有意让判定层更宽松(`0.3 > 0.05`),而且**不是冗余**:判定用的速度是**玩家输入后的当前速度**,玩家在判定区内按住前进键时速度会被重新推起来(`restThreshold` 此时根本不参与),宽松阈值才不会把"已进区但手上还有一点速度"误判为失败。反过来,物理层的 0.05 必须紧,否则滑行距离会依赖阈值。两者都由关卡 JSON 覆盖:`physics.restThreshold`(§3.3 `physics` 字段)与 `goal.maxStopSpeed`(仅 `stopInZone` 有);**schema 的 `default` 是唯一真源**——本表、`src/app/config.ts` 与参考积分器的兜底值都必须与之一致,`tests/test_level_doc_contract.py` 把这条锁成断言。

### 2.11 确定性要求

- 同样的 `(初始状态, 输入序列, 关卡, FIXED_DT)` 必须得到逐位相同的轨迹;`sim/` 里不允许出现 `Math.random()`、`Date.now()`、`performance.now()`。
- 视觉特效(粒子、镜头抖动)可以随机,但只能存在于渲染层,且不得回写 `sim/` 状态。
- 测试用 `simulate(state, inputs, level, { steps })` 这种纯函数入口跑固定输入序列,而不是等真实帧。

## 3. 关卡数据格式

### 3.1 设计目标

1. **数据驱动**:新增/调整关卡只改 JSON,不改引擎代码(#9 的硬性要求,研究卡 §5.5 同款要求)。
2. **引擎无关**:字段名描述"关卡长什么样",而不是"three.js 里怎么建"。
3. **可校验**:有机器可读 schema,CI 能拦住手写错的关卡。
4. **可教学**:过关/失败/预判文案有固定挂载点,#10 不需要新开字段。
5. **可判定**:过关条件能表达成"沿段内里程的区间判定",不需要网格求交。

### 3.2 结构与判定模型

关卡是一条**由地形段串联而成的带子**。第 `n+1` 段入口接第 `n` 段出口,每段有自己的长度、宽度、材质、曲率/坡度与两侧墙。所有空间判定都建立在"段 id + 段内里程 `s` + 横向偏移 `u`"三元组上:

```
terrain[0] ──► terrain[1] ──► … ──► terrain[n]
   │              │                    │
 材质区间      材质区间             材质区间
        goal.zone / gates / spawn 都引用 (segmentId, from, to)
```

由此得到四条重要性质:`terrain[].surface` 天然构成摩擦分区;`goal` 的区间判定与地形解耦(改关卡长度不影响判定逻辑);起点/终点/检查点都用同一种 `zone` 结构表达;引擎侧不需要任何按关卡名的 `if`。

### 3.3 字段语义(自上而下)

| 字段 | 必填 | 语义 |
| --- | --- | --- |
| `schemaVersion` | ✔ | 格式版本,当前 `1`;加载顺序见 §3.6 |
| `id` / `order` | ✔ | 关卡标识(也是进度存储键)与解锁顺序 |
| `title` / `knowledgePoint` | ✔ | 关卡中文名 / 本关知识点(关卡选择界面与图鉴卡片用) |
| `environment` | – | 天空色、环境光强度、阴影档位、雾 |
| `physics` | – | 对 §2.10 默认参数的**逐项**覆盖(重力、空气阻力、限速、加速度、静止阈、转向、跳跃、兜底材质);嵌套对象允许只覆盖其中一个子字段 |
| `spawn` | ✔ | 起点:`segmentId` + 段内里程 `at` + 横向 `lateral` + 朝向 `heading` + 初速 `speed` |
| `surfaces` | ✔ | 本关材质表:`{ "ice": { "mu": 0.05, "color": "#9fd8ff", "pattern": "ice", "label": "冰面" } }`,字段名无条件单位 |
| `terrain[]` | ✔ | 地形段:`type`(`straight`/`arc`/`ramp`)、`length`、`width`、`surface`、`curvature`(arc)、`grade`(ramp)、`walls`、`scenery` |
| `obstacles[]` | – | 障碍:`shape`(box/cylinder)、`segmentId` + `at` + `lateral`、尺寸、`behavior`(solid/hazard) |
| `goal` | ✔ | 过关条件,四种判别式之一(见下);`zone` 的宽度即研究卡 §3.4 的"过关容差" |
| `failure` | – | 失败条件:坠落高度 `fallBelowY`(优先级最高)、超时 `timeoutSeconds`、越界兜底 `outOfBounds`、危险物处理 |
| `teaching` | ✔ | **教学文案挂载点**:`intro`、`hint`、`onClear`/`onFail`(各含 `principle` + `tip`)、`prediction`(预测-验证交互) |
| `rewards` | – | 计时星级阈值 `starThresholds`、`parTimeSeconds` |
| `camera` | – | 跟随相机距离/高度/俯仰/FOV(角度,加载时换算) |
| `i18n` | – | 预留的多语言覆盖表,MVP 只发中文 |

**过关条件(`goal`)支持四种模式**,与研究卡 §3.3 的五关排布一一对应:

| 模式 | 语义 | 用在(研究卡 §3.3 的关) |
| --- | --- | --- |
| `reachGoal` | 抵达指定区间(可要求 `minSpeed`/`maxSpeed`) | ①起跑与刹车、⑤综合路线 |
| `stopInZone` | 在指定区间内停住并保持 `holdSeconds` | ②冰面还是橡胶地 |
| `passGates` | 按顺序通过若干门 | ③速度翻倍 |
| `maintainSpeed` | 在区间内不低于 `minSpeed` 通过 | ④直着飞出去 |

### 3.4 完整 JSON Schema

机器可读的完整定义在 [`docs/schema/level.schema.json`](./schema/level.schema.json)(JSON Schema draft 2020-12)。它规定了每个字段的类型、取值域、单位与默认值,并用 `oneOf` 表达 `goal` 的四种判别式、`allOf/if/then` 表达 `arc` 必须有 `curvature`、`ramp` 必须有 `grade`、`box` 必须有 `size`、`cylinder` 必须有 `radius`+`height` 等条件约束。

使用方式(#9 落地时):

```ts
import Ajv from 'ajv/dist/2020.js';
import schema from './schema/level.schema.json';

export const validateLevel = new Ajv({ allErrors: true, strict: true }).compile(schema);
```

- **构建/测试期**:`tests/levels/*.test.ts` 遍历 `levels/*.json` 逐个校验,任何一个不合 schema 就让 CI 红。
- **运行时**:dev 模式下校验并打印可读错误;生产构建跳过(校验器不进产物包)。
- **改动纪律**:任何字段新增/改名都必须先改 `level.schema.json` 并同步更新本文 §3.3,再改关卡数据。
- **schema 表达不了的两类约束**(由测试负责,见 §6.1 断言 10/11):
  1. **跨字段比较**:JSON Schema 2020-12 没有"属性 A < 属性 B"的关键字(`$data` 是非标准扩展),所以 `zone.from < to`、`lateralMin < lateralMax` 只能由测试保证;
  2. **引用完整性**:`terrain[].surface` 必须存在于 `surfaces`,`goal`/`spawn`/`obstacles` 引用的 `segmentId` 必须存在于 `terrain`。

### 3.5 示例关卡(第 2 关:冰面还是橡胶地)

该示例同时是 schema 的自测样例与物理自洽性样例(§6.1 断言 10/11 会对它逐条验算)。设计要点:**同一段路,把中间 40 m 换成冰面还是橡胶地,结果差 53 m**。

```json
{
  "schemaVersion": 1,
  "id": "level-02",
  "order": 2,
  "title": "冰面还是橡胶地",
  "knowledgePoint": "摩擦力越小,运动状态越难改变",
  "environment": { "skyColor": "#bfe3ff", "shadowQuality": "medium" },
  "physics": { "gravity": 9.82, "accel": 12, "maxSpeed": 12 },
  "spawn": { "segmentId": "runway", "at": 1, "lateral": 0, "speed": 0 },
  "surfaces": {
    "normal": { "mu": 0.25, "color": "#8d99ae", "pattern": "grid", "label": "普通地面" },
    "ice": { "mu": 0.05, "color": "#9fd8ff", "pattern": "ice", "label": "冰面" },
    "rubber": { "mu": 0.9, "color": "#2f2f2f", "pattern": "rubber", "label": "橡胶地" }
  },
  "terrain": [
    { "id": "runway", "type": "straight", "length": 20, "width": 6, "surface": "normal" },
    { "id": "icefield", "type": "straight", "length": 40, "width": 6, "surface": "ice" },
    { "id": "stopzone", "type": "straight", "length": 30, "width": 6, "surface": "normal" }
  ],
  "goal": {
    "type": "stopInZone",
    "zone": { "segmentId": "stopzone", "from": 15, "to": 25 },
    "holdSeconds": 0.5,
    "description": "滑过冰面,在绿色区域里停下来"
  },
  "failure": { "fallBelowY": -10, "outOfBounds": "fail" },
  "teaching": {
    "intro": "前面 40 米是冰面。猜猜:一直按住前进,然后在冰面上松手,你会停在哪里?",
    "hint": { "afterSeconds": 12, "text": "冰面几乎不减速,你会在冰面之后那片普通地面上才停下来。" },
    "onClear": { "principle": "摩擦力越小,运动状态越难改变", "tip": "同样松开方向键,橡胶地不到 10 米就停,冰面要滑 40 多米。" },
    "onFail": { "principle": "没有力,速度就不会自己改变", "tip": "你冲过头了,是因为冰面几乎不给你减速——下次早点松手。" },
    "prediction": {
      "prompt": "同样的初速,把中间 40 米换成橡胶地,你会在哪里停下?",
      "options": [
        { "id": "before", "label": "刚进橡胶地不久就停(10 米以内)" },
        { "id": "middle", "label": "滑到橡胶地中间(约 20 米)" },
        { "id": "after", "label": "冲过橡胶地,停在后面" }
      ],
      "correctOptionId": "before",
      "onCorrect": "对:橡胶地的摩擦是冰面的 18 倍。",
      "onWrong": "再想想:摩擦越大,同样的初速停得越近。"
    }
  },
  "rewards": { "parTimeSeconds": 18, "starThresholds": [15, 20, 28] },
  "camera": { "mode": "follow", "distance": 8, "height": 2.6, "fov": 62 }
}
```

逐条验算(默认模型,§6.1 断言 11 自动执行):

| 路线 | 计算 | 结果 |
| --- | --- | --- |
| 跑道(0–20 m)全程按住前进 | 解析 0 → 12 m/s 需 7.54 m;离散 1/60 在 **7.657 m** 处到限速,余下 11.34 m 保持 12 m/s | 进入冰面时 **12.0000 m/s**(x = 20.057 m) |
| 冰面(20–60 m)松手 | `v² = 144 − 2×0.491×40 = 104.7` | 出场速度 **10.2324 m/s**(x = 60.075 m) |
| 判定段(60–90 m)松手 | 再滑 `104.7/(2×2.455) = 21.3 m` | **停在 81.399 m**,落在 `stopzone` 的 [75, 85] m 判定区内 ✅ |
| 同样路线但中场换成橡胶地 | 入场 12 m/s,`144/(2×8.838) = 8.2 m` 就停(`2×8.838×40 = 707 >> 144`,根本走不完这 40 m) | **停在 28.203 m**(橡胶地中段就停住,到不了判定区)——同一操作,相差 53 m |

> **读数说明(避免验算对不上账):** "计算"列里的 `104.7`、`2×2.455`、`144/(2×8.838)` 都是**连续模型**的解析中间量(给学生用 `s = v²/(2μg)` 手算用的);而"结果"列**加粗的最终位置**是**离散定步长模型**(§2.3,`FIXED_DT = 1/60`)逐帧积分出来的,两者相差一个步长的量级。所以直接拿"计算"列的解析链算到底会得到 `60 + 21.3 = 81.3`、`20 + 8.1 = 28.1`,比加粗值小 0.1 m 上下 —— 这不是矛盾,是解析解与离散解的差异;`tests/test_example_level_physics.py` 断言的是后者(81.4 / 28.2,容差 0.3),精度与容差见 §6.1。
>
> 表里的离散值随积分器对**限速步**的处理而变(§2.4)。三种读法(实测,`dt = 1/60`):
>
> | 读法 | 终点(示例关 / 橡胶替换) | 说明 |
> | --- | --- | --- |
> | 限速截断留在调用方,位移仍写 `v*dt − 0.5*a*dt²` | 81.385 m / 28.325 m | 每个饱和步短掉 `0.5*a*dt²`,整关累计短 0.078 m |
> | **在 `tCap` 处解析拆成两段(本文采用)** | **81.399 m** / **28.203 m** | 饱和步正好推进 `maxSpeed*dt`,即表中加粗值 |
> | 完全不设限速 | 126.48 m(跑道外) | 90 m 处已冲出跑道(`v ≈ 13.4 m/s`);只有把跑道一路延长下去才会在 126.48 m 停住,已不是本关设计的操作 |
>
> 也就是说,**同一份关卡数据会因为限速写在哪一层而给出三个不同的终点**。本文取中间那行,并把判别式写进 §6.1 断言 13(饱和步 `ds == maxSpeed*dt`),让"读法不同"在这种关卡上不可能悄悄发生。

### 3.6 版本演进与校验纪律

- `schemaVersion` 只在**破坏性**变更时递增(删字段、改语义、改单位)。
- **顺序是硬约定:先读版本 → 再迁移 → 后校验。** `schemaVersion` 是唯一在读之前不校验的字段(否则 v2 文件会被 v1 schema 直接拒掉);加载器读出版本后,按 `migrate[v] → v+1` 的链式迁移把文件升到当前版本,再用本文件描述的 schema 校验。当前只有 v1,迁移表为空。
- **每个版本一份 schema**:本文件描述"当前版本"。v2 出现时,把本文件改名为 `level.v1.schema.json` 并新增描述 v2 的 `level.schema.json`;历史版本文件仍可被校验(用于 `npm run migrate` 之类的离线工具)。
- 新增**可选**字段不递增版本;引擎必须容忍缺省(默认值写在 schema 的 `default` 与 `src/app/config.ts` 两处,以 schema 为准)。
- `levels/*.json` 与 schema 必须同 PR 更新;CI 的 schema 校验是这条纪律的执行者(§6.3)。

## 4. 项目结构与模块职责

### 4.1 目录规划

```text
NewProject/
├─ index.html                  # 唯一入口页(Vite 入口)
├─ public/assets/              # 静态资源(音频、必要的纹理);首选程序化生成,减少体积
├─ levels/                     # ★ 关卡数据:纯 JSON,与引擎解耦
│  ├─ level-01.json … level-05.json
│  └─ index.json               # 关卡清单与解锁顺序(order 的单一来源)
├─ docs/
│  ├─ ARCHITECTURE.md          # 本文
│  ├─ schema/level.schema.json # 关卡 JSON Schema
│  ├─ research/                # #5 研究卡(REQ_DONE)
│  └─ benchmarks/              # 本文实测数字的复现脚本(体积入口 + 物理引擎对照)
├─ src/
│  ├─ main.ts                  # 组装根:创建 Game,启动循环,挂载到 #app
│  ├─ app/
│  │  ├─ Game.ts               # 顶层编排:加载关卡 → 建场景 → 循环 → 关卡状态机
│  │  ├─ loop.ts               # 固定步长 accumulator(§2.3)
│  │  └─ config.ts             # §2.10 默认参数唯一真源
│  ├─ sim/                     # ★ 纯逻辑:不 import three / 不碰 DOM
│  │  ├─ state.ts              # SimState 定义与从 spawn 初始化
│  │  ├─ step.ts               # stepSim(state, input, level, dt) → { state, events }
│  │  ├─ friction.ts           # 解析减速与停止距离(§2.4,含 a=0/a>0 分支)
│  │  ├─ kinematics.ts         # 速度积分、转向权(用 maxTurnRateRad)、跳跃、坡度
│  │  ├─ collision.ts          # 中心线带状地形 + 障碍的解析接触(§2.8 的判定顺序)
│  │  └─ goal.ts               # 过关/失败判定(读 goal / failure)
│  ├─ levels/
│  │  ├─ types.ts              # 由 schema 派生的 Level 类型
│  │  ├─ load.ts               # fetch + 版本迁移 + ajv 校验 + 归一化(度→弧度、补默认值)
│  │  └─ registry.ts           # 关卡清单、解锁规则、当前关卡指针
│  ├─ render/                  # three.js:唯一允许 import three 的目录
│  │  ├─ Renderer.ts           # WebGLRenderer、尺寸/DPR、降级档位
│  │  ├─ SceneBuilder.ts       # 由 Level 数据生成地形网格(渲染层唯一读 Level 的模块)
│  │  ├─ CameraRig.ts          # 跟随相机(读 camera 配置,角度已换算)
│  │  ├─ ActorView.ts          # 角色网格与动画(只读 sim 状态,不回写)
│  │  └─ surfaces.ts           # 材质 μ/color/pattern → MeshStandardMaterial
│  ├─ input/
│  │  ├─ KeyboardInput.ts      # 原始按键 → Input 结构
│  │  └─ InputBuffer.ts        # 保证每个固定步长都能取到一致的输入快照
│  ├─ ui/                      # 原生 DOM/CSS HUD
│  │  ├─ Hud.ts                # 速度、当前材质、计时(把摩擦可视化)
│  │  ├─ LevelSelect.ts        # 关卡选择与解锁状态
│  │  ├─ TeachingCard.ts       # 教学文案与预测-验证交互(读 teaching.*)
│  │  └─ styles.css
│  └─ progress/
│     └─ storage.ts            # localStorage 读写 + 版本迁移 + 容错
└─ tests/
   ├─ test_level_doc_contract.py    # 当前(标准库):schema ↔ 文档示例的一致性门禁,schema 驱动
   ├─ test_example_level_physics.py # 当前(标准库):§3.5 示例关卡的参考积分验算
   ├─ test_level_schema.py          # 当前(需 jsonschema):完整 draft 2020-12 校验,缺包时跳过
   ├─ sim/                     # (#7 起)物理与判定断言(§6.1)
   ├─ levels/                  # (#7 起)关卡数据自洽性
   ├─ arch/                    # (#7 起)依赖边界测试(§6.3)
   └─ e2e/smoke.spec.ts        # (#7 起)Playwright 冒烟
```

### 4.2 模块职责边界

| 模块 | 职责 | 明确不做 |
| --- | --- | --- |
| `app/Game.ts` | 生命周期编排:加载关卡、创建渲染/输入/UI、驱动循环、维护 running/cleared/failed 状态机 | 物理公式、渲染细节、DOM 结构 |
| `app/loop.ts` | 把真实帧时间切成固定步长 | 任何游戏逻辑 |
| `sim/*` | 物理与判定:给定状态与输入产出新状态和事件;所有角度输入均为弧度 | 渲染、DOM、计时器、随机、`three` 类型、度→弧度换算 |
| `levels/*` | 读 JSON、版本迁移、按 schema 校验、归一化(度→弧度、补默认值)、暴露关卡清单 | 物理计算、渲染 |
| `render/*` | 把 `Level` 与 `SimState` 画出来 | 改物理状态;除 `SceneBuilder` 外不读关卡数据 |
| `input/*` | 键盘 → 与固定步长对齐的 `Input` 快照 | 直接改状态 |
| `ui/*` | HUD、关卡选择、教学卡与预测交互 | 直接改物理状态(通过 `Game` 暴露的动作) |
| `progress/storage.ts` | 通关记录读写与容错 | 解锁规则判断(属于 `levels/registry.ts`) |

### 4.3 依赖方向与强制手段

```text
                 ┌──────────────┐
                 │  app (Game)  │
                 └──────┬───────┘
      ┌────────┬────────┼────────┬─────────┐
      ▼        ▼        ▼        ▼         ▼
   sim/*   render/*  input/*   ui/*   levels/*, progress/*
      ▲
      └── 只能被上层依赖,自己什么都不依赖
```

规则:`sim/` 与 `levels/types.ts` 不得 import `three`、DOM 类型或任何 `render/`、`ui/` 模块;`render/` 不得 import `sim/step.ts`。用 ESLint `no-restricted-imports` 声明,并配 `tests/arch/import-boundaries.test.ts` 扫描 `src/sim/**` 的 import 做兜底断言(§6.3)。收益是物理测试永远不需要浏览器,CI 上跑得快、也稳定。

### 4.4 运行时数据流

```
levels/level-0X.json ──► levels/load.ts(读版本 → 迁移 → ajv 校验 → 度→弧度)──► Level
                                                              │
                     ┌────────────────────────────────────────┼───────────────────────┐
                     ▼                                        ▼                       ▼
        render/SceneBuilder(建地形)              sim/state(由 spawn 初始化)     ui/Hud(材质标签)
                     │                                        │
                     ▼                                        ▼
                three.js 场景 ◄──── render/ActorView ◄──── stepSim(input, FIXED_DT)
                                                              │
                                                              ▼
                                             sim/goal(判定)──► app/Game 状态机 ──► ui/TeachingCard
                                                              │
                                                              ▼
                                                    progress/storage(通关记录)
```

事件从 `stepSim` 以返回值形式冒出来(`{ type: 'grounded' | 'surfaceChanged' | 'wallHit' | 'cleared' | 'failed', … }`),由 `Game` 分发给渲染与 UI —— `sim/` 因此不需要任何回调或事件总线。

## 5. 性能与加载预算

### 5.1 首屏预算(桌面优先)

研究卡 §3.4 给的预算是"JS + WASM ≤ 400 KB gzip";本栈不含 WASM(§1.4),因此**内部目标收紧到 ≤ 220 KB**:

| 指标 | 目标 | 上限 | 依据 |
| --- | --- | --- | --- |
| 首屏 JS(压缩后 gzip) | ≤ 190 KB | **≤ 220 KB** | three 最小场景实测 136 KB + 应用代码约 50 KB |
| 首屏 CSS + HTML | ≤ 12 KB | 20 KB | 原生 CSS,HUD 规模小 |
| 首屏关卡 JSON | ≤ 4 KB | 8 KB | 只加载第 1 关 |
| 首屏资源(音频/纹理) | 0(程序化生成) | ≤ 150 KB | 纹理走 `surfaces.pattern` 程序化生成,音效懒加载到首次播放 |
| 交互就绪时间(TTI) | ≤ 2.5 s(中端笔记本) | ≤ 5 s(低端 / 4× CPU 降速) | 首屏无网络请求阻塞,渲染器初始化是主成本 |
| 稳态帧率 | 55–60 fps | 低端 ≥ 30 fps | 场景 ≤ 20k 三角形/关,单方向光 + 阴影 |

### 5.2 分包策略

1. **只为首屏加载第 1 关。** `levels/index.json` 与 `level-01.json` 同步请求;其余关卡用动态 `import()` 在进入时拉取。
2. **`three` 单列 vendor chunk** 并长期缓存(hash 命名);应用代码与关卡数据独立 chunk,改关卡不失效缓存。
3. **禁忌**:不要为了小功能引 `three/addons/*` 的重资产(`GLTFLoader`、`EffectComposer`、`Water`)。实测"最小场景 + OrbitControls"已经 545 KB min;每引一个 addon 都要重新核对 §5.1。
4. `ajv` 只在 dev/测试里使用,生产构建不得引入(`import.meta.env.DEV` 条件分支 + 构建产物检查)。

### 5.3 低端设备降级策略(研究卡 §5.2 要求 #6 明确的部分)

判定方式:启动时读 `navigator.hardwareConcurrency`、`deviceMemory`(可得时)与首次 2 秒的平均帧时间,给出初始档位;运行中持续监测,连续 2 秒低于阈值就降一档(只降不升,避免抖动)。

| 档位 | 渲染分辨率 | 阴影 | 抗锯齿 | 粒子/装饰 | 目标帧率 | 物理 |
| --- | --- | --- | --- | --- | --- | --- |
| high | `min(DPR, 2)` | 2048 阴影贴图 | MSAA ×4 | 全量 | 60 | FIXED_DT 不变 |
| medium(默认) | `min(DPR, 1.5)` | 1024 阴影贴图 | FXAA | 全量 | 60 | FIXED_DT 不变 |
| low | `min(DPR, 1)` | 关闭 | 无 | 减半,`scenery` 只保留 `spacing ≥ 4 m` 的 | ≥30 | FIXED_DT 不变,渲染跳帧 |

关键约束(与研究卡 §5.2 的诉求一致):**降级只动渲染,不动物理步长。** 低端机上角色可能看起来更卡,但**滑行距离**——冰面上从松手到停住的那一段——与高档机完全一致(§6.1 断言 2,实测步长取 1/30…1/240 的离散度 ~1.8e-11,即闭式解 `v²/(2μg)` 与 dt 无关);这也是 §1.4 拒绝 cannon-es 时点出的"滑行距离 ∝ dt"问题的正面反面。

> 需要说准的一点:与 dt 无关的是**纯滑行段**,不是**整关结果**。整关里还有"跑道推进 + 限速步"这段带加速度的过程,它按步长离散,所以终点会有**亚米级**漂移:同一策略实测 1/30 停在 81.60 m、1/60 停在 81.40 m、1/120 停在 81.40 m、1/240 停在 81.35 m(1/30 与 1/120 相差 0.20 m / 0.25%,步长 1/30…1/480 全距 0.27 m)。判定区有 10 m 宽,这点漂移不影响过关,但"与高档机完全一致"的说法只对滑行距离成立,对整关结果应表述为"亚米级一致"。
>
> 这里给出的是 §2.4 那版**解析限速步**的数字。若把限速截断留在调用方(饱和步短掉 `0.5*a*dt²`),同一策略在 1/60 下会小 0.014 m、且因为"每步缺口 ∝ dt"而让粗步长的漂移看起来更小:实测该读法 1/30 停 81.443、1/60 停 81.385、1/120 停 81.361、1/240 停 81.346(1/30…1/240 全距 0.097 m),而解析限速步同一梯子是 81.599 / 81.399 / 81.399 / 81.349(同梯子全距 0.250 m)。也就是说"截断留在调用方"的**离散度反而更小**,但那是每步固定的缺口(1/30 时 0.159 m)与步长误差凑巧相消,不是更高精度——它的 1/60 值离连续解 81.327 更远。§6.1 断言 13 用饱和步 `ds == maxSpeed*dt` 把这两种读法区分开;而断言 2 钉住的只是**纯滑行段**的 dt 无关性(全距 ~1.8e-11),上面这些"整关终点"的漂移不在它的断言范围内。

### 5.4 测量方式(可执行)

- `npm run build` 后用 `gzip -9 -c dist/assets/*.js | wc -c` 核对 §5.1 的 JS 预算(CI 里做成一条脚本,超预算即失败)。
- Playwright 冒烟里断言首屏无 4xx、canvas 存在、`window.__perf.firstInteractiveMs` 上报值存在。
- 帧率用 `requestAnimationFrame` 的 60 帧滑动平均记录到 `window.__perf`;CI 的 SwiftShader 只断言"不报错、能通关第 1 关",不做帧率硬门槛(CI 机器不可代表真机)。
- 人工核对用 Chrome DevTools Performance + Lighthouse(桌面 preset),记录在 PR 描述里。
- 体积数字的复现入口见 [`docs/benchmarks/bundle-size/README.md`](./benchmarks/bundle-size/README.md)。

## 6. 测试策略(物理行为怎么自动化测)

### 6.1 纯物理测试(Vitest,Node 环境,无 WebGL)

测试重心在这里,可行性来自 §2.1 的分层:物理是纯函数,给固定输入序列就能拿到确定性轨迹。

```ts
// tests/sim/friction.test.ts(示意)
import { simulate } from '../../src/sim/step';

const level = makeLevel({ surfaces: { ice: { mu: 0.05 }, rubber: { mu: 0.90 } } });

test('同初速下冰面滑行距离至少是橡胶地的 3 倍', () => {
  const dIce = simulate({ level, surface: 'ice', v0: 10, input: 'none' }).travelDistance;
  const dRubber = simulate({ level, surface: 'rubber', v0: 10, input: 'none' }).travelDistance;
  expect(dIce / dRubber).toBeGreaterThanOrEqual(3);      // 默认系数下实际为 18×
  expect(dIce).toBeCloseTo(101.83, 1);                   // 并且与 s = v²/(2μg) 一致
});
```

必须覆盖的断言清单(每条都对应 #8 / #9 的 Verify):

| # | 断言 | 关卡/性质 |
| --- | --- | --- |
| 1 | 同初速下冰面滑行距离 / 橡胶地滑行距离 ≥ 3(默认系数下 ≈ 18) | #8 验收 |
| 2 | 滑行距离等于闭式解 `v²/(2μg)`,且 `FIXED_DT` 取 1/60、1/120、1/30 时结果一致(±1e-9) | 证明 §2.4 的解析离散化有效、与帧率无关 |
| 3 | 无摩擦段(μ=0)上不给输入时速度恒定、位置线性推进,且不出现 `NaN` | "运动状态保持" + `a = 0` 分支 |
| 4 | 腾空水平速度不变(`airDrag=0`),落点 = `v_h × T`,且对 `v_h` 单调递增 | #8 跳跃与水平速度 |
| 5 | 上坡段相同初速滑行距离显著短于平地,且用 `θ = atan(grade/100)` 计算(不是 `grade/100`) | §2.7 |
| 6 | 同一 `(状态, 输入序列, 关卡)` 跑两次结果完全相同(深比较) | 确定性 |
| 7 | 四种 `goal` 模式各有一组"刚好过 / 刚好不过"的边界用例 | #9 判定 |
| 8 | 段材质切换时 `surfaceChanged` 事件在正确的里程处触发 | 摩擦分区 |
| 9 | 越界/坠落/危险物接触分别在正确条件下返回 `failed` 及原因,且 `walls` 优先于 `failure.outOfBounds` | §2.8 判定顺序 |
| 10 | 关卡数据通过 schema 校验,且 `goal`/`spawn`/`obstacles` 引用的 `segmentId`、`terrain[].surface` 引用的材质 id 都存在;`zone.from < to`、`lateralMin < lateralMax` 成立 | schema 表达不了的跨字段约束 |
| 11 | 文档 §3.5 的示例关卡用参考积分器跑一遍:能到达冰面、按文档策略停在判定区内、把中场换成橡胶地则停在区外 | 示例关卡自洽(防止文档与数据漂移) |
| 12 | 角度换算只发生一次:`load.ts` 之后的 `maxTurnRateRad = 2.094 rad/s`(±1e-6),`sim/` 内不再出现 `π/180` | §2.2 单位铁律 |
| 13 | **限速步的判别式**:在 `v == maxSpeed` 且仍在加速的一步上 `ds == maxSpeed * dt`(±1e-12),即 §2.4 的解析拆分成立;并断言 0 → `maxSpeed` 的离散里程 ≈ 7.66 m、与解析 `v²/(2a)` 相差不超过 0.2 m | §2.4 限速由积分器负责 |
| 14 | §2.10 表里的默认值与 schema 的 `default` 逐项一致(`gravity`/`airDrag`/`maxSpeed`/`accel`/`restThreshold`/`turnAuthority`/`jump`/`holdSeconds`/`maxStopSpeed`),且参考实现的兜底值等于 schema 默认 | §3.6 "以 schema 为准" |

第 10–14 条是 schema 与单位约定表达不了的部分,用测试补齐,"加关卡不改代码"才真的安全。

本单元已经落地的部分:`tests/test_example_level_physics.py` 实现了断言 1/2/10/11/13 的可执行版本(参考积分器 + 数据自洽性),`tests/test_level_doc_contract.py` 实现了 schema ↔ 文档的一致性门禁(含断言 14 的默认值比对);两者都只用标准库,因此在当前 CI 上真实执行(§6.3)。#8 落地 `src/sim/` 后,把它们替换成 `tests/sim/*.test.ts` 的 Vitest 版本,并保留同一组断言编号。

### 6.2 冒烟与交互测试(Playwright)

- 页面能打开、WebGL 上下文创建成功(`--use-gl=swiftshader` 在 CI 里可跑)。
- 按键 → 角色位移:通过 `window.__game` 暴露只读测试钩子(位置、速度、状态),断言按前进键 1 秒后位置沿 +Z 前进。
- 通关第 1 关后 `localStorage` 出现通关记录,刷新后关卡选择界面显示已解锁(覆盖 #9 的进度持久化)。
- 失败后按 R 能立即重试,且物理状态被完全重置(位置/速度回到 `spawn`)。

E2E 不测数值精度——精度由 §6.1 的纯函数测试负责。

### 6.3 CI 门禁

仓库当前的 CI(`.github/workflows/ci.yml`)只有 `pip install pytest` 一步,因此任何依赖第三方包的断言都会在门禁上被 skip。本单元的处理方式与理由:

1. **不在本分支改 `ci.yml`。** 该文件是随 `main` 一起进入仓库的(commit `21f22c0`),而本分支的基底早于它(本分支上根本没有这个路径)。**注意复现方式**:在本分支当前状态下直接跑 `git merge-tree --write-tree main <branch>` 是**不会**报冲突的(本分支没有这个路径,git 直接取 `main` 的版本,实测 exit 0)——冲突只在"本分支真的新增了这个文件、且内容与 `main` 不同"时才出现,也就是 QA 建议的那一行改动本身:
   ```
   $ git show main:.github/workflows/ci.yml | sed 's/pip install pytest/pip install pytest jsonschema/' \
       > .github/workflows/ci.yml && git add -A && git commit -m tmp
   $ git merge-tree --write-tree --name-only main HEAD
   CONFLICT (add/add): Merge conflict in .github/workflows/ci.yml
   ```
   所以结论不变(这条改动会制造冲突,让 PR 被标成不可合并),但"在本分支上直接复现冲突"的说法是错的,按上面的方式才可复现。需要补 `jsonschema` 的一行改动应由 `main` 的维护者或 #7(它会把 CI 换成 npm 流水线)来做。
2. **把门禁做成不依赖第三方包的形态。** 新增 `tests/test_level_doc_contract.py`,只 import 标准库:它从 `docs/schema/level.schema.json` 里读出真正要守的约束(必需字段、枚举、数值区间、`$defs` 引用是否可解析、`if/then` 分支要求),再逐条应用到文档里内嵌的示例关卡;此外 `tests/test_example_level_physics.py` 用参考积分器验算示例关卡的物理自洽性。因此**在现有 CI 上真实执行**(模拟 `pip install pytest` 环境实测:`19 passed, 4 skipped`,其中 4 条 skip 的是需要 `jsonschema` 的深度校验层;改动前是 `1 passed, 4 skipped`)。
3. **深度校验层保留。** `tests/test_level_schema.py` 仍用 `jsonschema` 做完整 draft 2020-12 校验(它能发现标准库检查发现不了的 schema 关键字错误),在装了该包的环境与后续 #7 的流水线里生效。

`python -m pytest tests/ -q`(本仓库当前的测试入口)→ 后续 #7 接管为 `npm run build`(含 `tsc --noEmit`)→ `npm run test` → `npm run test:e2e`。另外三条轻量但重要的检查:

- **依赖边界测试**:覆盖 §2.1 与 §4.3 的全部硬性规则,而不只是 import 语句——(a) 扫描 `src/sim/**` 与 `src/levels/types.ts` 的 import,出现 `three`、DOM、`render/`、`ui/` 即失败;(b) 扫描同一批文件里出现 `requestAnimationFrame`、`Math.random()`、`Date.now()`、`performance.now()` 即失败(§2.1 的帧循环禁令与 §2.11 的确定性要求:这四个都是**全局**,import 扫描看不见,必须单独查标识符);(c) 反向断言 `src/render/**` 不 import `src/sim/step.ts`(§4.3 的后半条,规则是对称的,只扫 `sim/` 会漏掉它)。
- **体积预算检查**:构建产物 gzip 后超过 §5.1 上限即失败。
- **关卡数据自洽性**:§6.1 断言 10/11 的自动化版本,新增关卡不通过就不许合并。其中跨字段部分(§6.1 断言 10 的 `zone.from < to`、`lateralMin < lateralMax`)与断言 11 的示例关卡验算已经由 `tests/test_level_doc_contract.py`、`tests/test_example_level_physics.py` **在当前 CI 上真实执行**(标准库,无需 `jsonschema`);#7 把它扩到 `tests/levels/` 下的全部关卡。

## 7. 与后续任务(#7–#10)的对应关系

| 任务 | 直接采用本文的哪部分 |
| --- | --- |
| #7 项目脚手架 | §1.6 依赖白名单与脚本、§4.1 目录骨架、§4.3 依赖边界、§5.2 分包、§6.3 CI 门禁 |
| #8 物理核心 | §2 全部(定步长、摩擦解析解、转向权、跳跃、坡度、解析接触)、§2.10 参数与 §2.9 的系数、§6.1 断言 1–6、12 |
| #9 关卡与进度 | §3 的 schema 与判定模型、§6.1 断言 7–11、§4.1 的 `levels/` 与 `progress/` 边界 |
| #10 游戏感打磨 | §3.3 的 `teaching.*` 与 `prediction` 挂载点、§5.3 降级档位对特效的约束、§2.6 的手感注 |

## 8. 待人工确认(本单元在此暂停)

本单元带 `hitl:done`:文档产出后暂停,等人工 `/approve` 再进入 #7。请重点确认:

1. **物理方案(与研究卡的唯一分歧)**:维持"自写运动学、不接物理引擎",依据是 §1.4 的实测(0.05 摩擦在冰面上只能滑 0.43 m,且滑行距离随帧率变化)。若仍希望按 #5 卡原推荐接 cannon-es,代价明确:必须为每种碰撞体形状与帧率手动补偿 `frictionGravity`,并把 §6.1 断言 1/2 从严格等式降级为容差断言。
2. **重力取值**:与研究卡一致取 `g = 9.82 m/s²`(教材口径),"干脆的跳跃"改为调 `J = 5.5 m/s`(滞空 1.12 s)。若团队认为落地太飘,应在本单元改,而不是在 #8 里偷偷调。
3. **系数语义**:冰 0.05 / 普通 0.25 / 橡胶 0.90(与研究卡 §3.4 一致),给出 18 倍与 5 倍余量;这次明确写了"橡胶 μ 调到 0.3 仍有 6 倍"作为正交验算。
4. **UI 技术**:维持"原生 DOM + CSS",不引 UI 框架(省 67 KB gzip)。若希望用 React 做图鉴/关卡选择界面,需要重排 §5.1 的预算。
5. **教学文案**:按研究卡 §5.6 的建议,`teaching.*` 的措辞(尤其"惯性"与"惯性定律"的区分)需要教师/人工复核一次,这是唯一建议 HITL 的文案项。

以上任何一条被否决,都应先改本文对应章节,再开始 #7。
