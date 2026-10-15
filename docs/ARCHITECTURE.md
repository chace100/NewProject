# 3D 惯性跑酷 —— 架构设计文档

| 项 | 值 |
| --- | --- |
| 状态 | **ARCH_DONE** —— 待人工 `/approve` 后进入开发(本单元 hitl:done) |
| 对应 issue | #6 Architecture: 技术栈定稿、物理模型与关卡数据格式设计 |
| 上游依赖 | #5 Research: 3D 网页游戏技术选型与惯性教学游戏设计调研 |
| 下游消费方 | #7 脚手架 / #8 物理核心 / #9 关卡与进度 / #10 游戏感打磨 |
| 最后更新 | 2026-10-15 |
| 配套文件 | [`docs/schema/level.schema.json`](./schema/level.schema.json)(机器可读的关卡 schema) |

## 0. 关于上游研究卡

#5 的产出(req 卡)最终没有落到仓库里:该 issue 被关闭时只留下了编排器的状态评论([#5 评论](https://github.com/chace100/NewProject/issues/5)),agent 自述"在发布步骤中断"。因此本文自己补完了研究单元要求的选型对比,并且**不引用二手结论,全部用可复现的一手数据**:

- 包体积:2026-10-15 在本机用 `esbuild --minify` 对最小可用场景打包后测量(方法见 §1.2)。
- 维护活跃度/许可证:同日通过 GitHub API 读取仓库元数据。

也就是说:本文的第 1 节同时承担了"研究卡缺失时的技术选型决策"职责,下游 #7 可以直接照此落地。若后续 #5 补出正式研究卡,只需核对第 1 节结论是否冲突,不需要改本文结构。

## 1. 技术栈定稿

### 1.1 决策一览

| 维度 | 定稿 | 一句话理由 |
| --- | --- | --- |
| 渲染库 | **Three.js**(ESM,`^0.186`) | 同类最小场景实测 136 KB gzip,是 Babylon.js 的三分之一;MIT;社区体量第一(116k stars) |
| 物理方案 | **自写运动学 + 解析地形碰撞(不接物理引擎)** | 需求是"定性正确 + 可自动化复现",自写模型可以用解析解把"冰面 / 橡胶滑行距离比"变成一条稳定的断言;现成刚体引擎既贵(Rapier compat 实测 1.6 MB gzip)又不确定性更高 |
| 语言 | **TypeScript**(`strict`) | 关卡 JSON → 类型化运行时对象,字段写错在编译期就报错 |
| 构建 | **Vite** | 原生 ESM dev server + Rollup 生产构建,零配置支持 `npm run dev` / `npm run build`(#7 要求) |
| UI | **原生 DOM + CSS(不引框架)** | HUD 只有速度/材质/计时/提示卡;引 React 要多付 67 KB gzip(实测),在首屏预算里不划算 |
| 单元/物理测试 | **Vitest** | 与 Vite 共用转换管线,`sim/` 是纯函数,可在 Node 里跑,无需 WebGL |
| 冒烟/E2E | **Playwright** | 能在 CI 里用 SwiftShader 起真实 WebGL,验证"页面能开、能操作角色" |
| 关卡格式校验 | **JSON Schema(draft 2020-12)+ ajv** | schema 是唯一的格式契约;测试期校验所有关卡,新增关卡改数据不改代码 |
| 进度存储 | `localStorage` | 无后端、无登录(epic 约束) |

### 1.2 体积实测(2026-10-15)

方法:在临时目录 `npm i <包>` 后用 `esbuild --bundle --minify --format=esm` 打包"最小可用场景",对产物取 `gzip -9` 大小。

| 打包入口 | 内容 | min | **gzip** |
| --- | --- | --- | --- |
| `three@0.186.1` | Scene + PerspectiveCamera + WebGLRenderer + BoxGeometry + MeshStandardMaterial + 方向光/环境光 + OrbitControls | 545 KB | **136 KB** |
| `@babylonjs/core@9.30.0` | Engine + Scene + ArcRotateCamera + HemisphericLight + Box/Ground(mesh builder 按需 import) | 1 615 KB | **381 KB** |
| `@dimforge/rapier3d-compat@0.21.0` | 仅 `import RAPIER`(含内嵌 WASM 的 base64) | 4 233 KB | **1 613 KB** |
| `cannon-es@0.20.0` | 整库 | 121 KB | **35 KB** |
| `react@19` + `react-dom@19` | 一个最小函数组件 | 217 KB | **67 KB** |

活跃度与许可(同日 GitHub API):`mrdoob/three.js` 116 428 stars,MIT,当日有提交;`BabylonJS/Babylon.js` 26 166 stars,Apache-2.0,当日有提交;`dimforge/rapier` 5 862 stars,Apache-2.0;`pmndrs/cannon-es` 2 064 stars,MIT,**最近一次提交 2024-01,已近两年未动**。

> 注:上表是"最小场景"的相对量级,不是最终应用产物。它足以支撑选型判断,最终产物由 §5 的预算约束把关。

### 1.3 为什么不选 Babylon.js

Babylon.js 在工具箱完整度上有优势(自带 debug 层、材质库、PBR、动画系统)。但本项目的场景非常小:一条带状赛道 + 一个胶囊体角色 + 几个装饰物。为此我们要付的代价是**同场景 381 KB gzip vs 136 KB gzip**,接近三倍——而省下的那些能力(RTT、节点材质、后处理、物理插件)我们一个都不会用。桌面浏览器优先、首屏即玩的定位下,首屏体积是硬约束,因此选 Three.js。

### 1.4 为什么不接物理引擎(这是本项目最关键的选型)

教学目标是"定性正确",但验收要求是"**可复现**":`#8` 的 Verify 明确要求"同一初速下冰面滑行距离与橡胶地面差异 ≥3 倍"能由自动化测试复现。这个要求把选型推向自写模型,原因是三重的:

1. **成本**。Rapier(唯一维护活跃、能力最全的 JS/WASM 刚体引擎)的 compat 包实测 1.6 MB gzip / 4.2 MB 未压缩,还带 WASM 实例化与首帧编译开销,直接吃掉 §5 的首屏预算。它换来的是我们不需要的能力(关节、连续碰撞检测、堆叠求解、多形状复合)。
2. **可控性**。跑酷关卡要的是"沿赛道走、按路面材质刹车、跳一个抛物线",本质是带约束的运动学;刚体引擎要额外做胶囊角色控制器、摩擦材质映射、冲量调参,出错面反而更大。
3. **可测性(决定性)**。这是教学游戏:我们需要能断言"μ_冰 = 0.05、μ_橡胶 = 1.0 时滑行距离比 = 20×"。自写模型里滑行距离有闭式解 `s = v² / (2μg)`,断言是精确的、与帧率无关的。刚体引擎的求解器会把结果交给迭代求解、接触冲量与睡眠阈值,数值随版本、步长、接触顺序漂移,测试只能退化成"大概是 5 倍以上"的弱断言——一旦测试变成这样,教学正确性就没有护栏了。

`cannon-es` 体积可接受(35 KB gzip),但它已近两年不更新,且同样存在求解器带来的噪声;不引入。

**明确的边界**:自写的是"运动学与地形接触",不是"通用刚体"。凡是关卡数据能解析描述的东西(直道/弯道/坡道/长方体/圆柱障碍),就用解析公式处理;不做通用网格碰撞。§2.8 定义了这套解析碰撞的完整范围——超出范围的需求应当先改本文,而不是现场接引擎。

### 1.5 工具链与脚本约定

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

依赖白名单(MVP 只允许这些运行时依赖,新增依赖需要先改本文):

| 依赖 | 类型 | 版本约束 | 说明 |
| --- | --- | --- | --- |
| `three` | runtime | `^0.186` | 唯一渲染依赖;`three/addons/*` 按需引入 |
| `typescript` | dev | `^5` | 若工具链稳定,可评估升级;本文件不锁死 |
| `vite` | dev | `^8` | 构建 |
| `vitest` | dev | `^5` | 单元测试 |
| `@playwright/test` | dev | `^1` | 冒烟 E2E |
| `ajv` | dev(+运行时仅 dev 校验) | `^8` | JSON Schema 校验 |
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

**硬性规则**:`src/sim/` 不 import `three`、不碰 DOM、不使用 `requestAnimationFrame`。它有输入(状态+输入+dt)与输出(新状态),可被 Vitest 反复运行。这条规则由 §6.3 的边界测试强制。

### 2.2 状态、坐标与单位

```ts
// src/sim/state.ts
export interface SimState {
  position: { x: number; y: number; z: number };  // 世界坐标(米),y 向上
  velocity: { x: number; y: number; z: number };  // 世界坐标(米/秒)
  heading: number;                                 // 朝向(弧度,绕 y 轴)
  grounded: boolean;                               // 是否贴地
  contact: { segmentId: string; s: number; u: number } | null; // 当前地形段内里程/横向偏移
  elapsed: number;                                 // 关卡计时(秒)
  status: 'running' | 'cleared' | 'failed';
}
```

约定:长度米、时间秒、角度弧度(关卡 JSON 里用度,加载时换算)、速度米/秒。所有速度都是**世界坐标向量**,不做"轨道坐标"的状态化,好处是腾空、被弹开、坠落都能自然表达。

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

物理永远以 `FIXED_DT` 推进,渲染帧率与物理步长解耦:低端机掉到 30 fps 时,**视觉变卡、物理结论不变**。这是 §5 降级策略能成立的基础,也让 §6 的断言与设备无关。

积分用半隐式欧拉(先更新速度、再更新位置),这是跑酷手感与数值稳定性的平衡点;不需要 RK4 之类的精度——本项目要的是"定性正确且可复现",不是弹道学。

### 2.4 摩擦与惯性

**输入是加速度的来源,不是速度的赋值。**

```ts
// 地面,沿运动方向的标量模型(方向由速度矢量给出)
const aFriction = mu * gravity;                    // 摩擦减速度,方向与速度相反
const aInput    = input.forward ? accel : 0;       // 玩家输入
const aNet      = aInput - aFriction;              // 净加速度(符号决定加速/减速)
```

三条教学上必须成立的性质:

1. **不按前进键时,速度不会自己清零。** 这是"运动状态保持"的最小可见证据:玩家松手后,角色按当前速度与当前路面摩擦继续滑行。
2. **滑行距离只由初速与摩擦系数决定。** `s = v² / (2μg)`。同初速下,摩擦越小滑得越远——这正是"冰面刹不住、橡胶地一刹就停"。
3. **空中不减速。** 默认 `airDrag = 0`(见 schema 默认值),腾空时水平速度严格不变,抛物线落点只由水平速度和滞空时间决定。**这是一个刻意的教学取舍**:加一点"空气阻力"手感会更"游戏",但它会直接破坏"没有外力,运动状态不改变"的演示。所以默认值为 0,并把该字段保留为可调,而不是写死在代码里(供 #10 打磨手感时按关覆盖)。

**离散化的坑(必须处理)**:如果直接写 `v -= a * dt`,当 `v < a*dt` 时速度会被减成负数或抖动到零附近,滑行距离因此依赖 `dt`,断言会变成一个不稳定的近似值。因此本步位移用**解析求解**:

```ts
// src/sim/friction.ts
export function advanceAlongDirection(v: number, a: number, dt: number): { dv: number; ds: number } {
  const stopTime = v / a;                       // 线性减速到 0 所需时间
  if (stopTime >= dt) {
    return { dv: a * dt, ds: v * dt - 0.5 * a * dt * dt };
  }
  return { dv: v, ds: 0.5 * v * stopTime };     // 本步内停住:s = v²/(2a),与 dt 无关
}
```

这样"停住那一步"的距离是精确的 `v²/(2a)`,整段滑行距离等于闭式解,与帧率无关,测试断言可以写成严格不等式而不是容差区间。

### 2.5 转向:运动状态保持的第二条可感证据

```ts
const authority = Math.max(floor, 1 / (1 + speed / vRef));   // vRef 默认 8,floor 默认 0.3
heading += input.steer * maxTurnRate * authority * dt;
```

速度越高,转向权越低:高速时按方向键,角色先"冲过头"再拐过来。**这是手感层,不是物理层**,文档与 UI 都不把它说成物理定律;它是"物体的运动状态难以瞬间改变"的可玩化表达。参数放在关卡 JSON 的 `physics.turnAuthority` 里,允许 #10 逐关调。

### 2.6 跳跃:水平速度决定落点

```ts
vy = jump.initialVerticalSpeed;                       // 默认 8 m/s
// 平地被: T = 2J/g ; 落点比起点低 Δy 时: T = (J + sqrt(J² + 2gΔy)) / g
horizontalRange = speed * T;                          // 空中水平速度不变
```

默认 `g = 20 m/s²`(见参数表说明),`J = 8 m/s` → 平跳滞空 0.8 s、跳高 1.6 m。水平速度 6 / 10 / 14 m/s 对应落点 4.8 / 8.0 / 11.2 m。第 4 关的"跳过冰缝"就建立在"落点 = 水平速度 × 滞空时间"这条可预判关系上。

### 2.7 坡度

`type: "ramp"` 的段用 `grade`(%)描述:沿坡方向重力分量 `g·sinθ ≈ g · grade/100`,净加速度变为

```
a = aInput − μ·g·cosθ − g·sinθ
```

上坡自然减速、下坡自然加速,不需要额外代码路径。MVP 里坡度只用于制造"同样的速度,上坡更快停住"的对比;直线路段的 `grade = 0` 时为 §2.4 的模型。

### 2.8 地形与碰撞:解析而不是网格

地形由**中心线 + 半宽**的带子构成(见 §3),因此接触判定是纯解析的:

- **贴地判定**:把角色位置投影到段中心线,得到段内里程 `s` 与横向偏移 `u`。若 `0 ≤ s ≤ length` 且 `|u| ≤ width/2`,则地面高度 `y_ground = centerlineY(s)`;若 `y ≤ y_ground + ε` 且 `vy ≤ 0`,则 `y = y_ground`、`vy = 0`、`grounded = true`。否则 `grounded = false`,走 §2.6 的抛物线。
- **材质采样**:当前段的 `surface` 就是这一步的摩擦系数来源——**摩擦分区因此是"路径上的区间",不需要任何网格采样或材质贴图读取**。这直接满足 #8"冰面 vs 橡胶地"的可测要求。
- **墙与越界**:段的 `walls.left/right` 决定横向越界后是撞停(`solid`)、按 `restitution` 反弹(`bounce`)还是直接滑出去(`none`,交给 `failure.fallBelowY` 判定坠落)。墙高 `height` 决定能否从上方越过。
- **障碍**:`box` / `cylinder` 与角色胶囊做解析重叠检测,法向推出 + `restitution` 反弹;`behavior: "hazard"` 的障碍接触即失败。
- **性能**:MVP 单关段数 ≤ 32、障碍 ≤ 16,线性扫描完全够用。若关卡规模超过 64 段再加 AABB 空间索引,不进 MVP。

### 2.9 定性正确性论证:≥3 倍关系为什么稳

摩擦减速下 `s = v²/(2μg)`,因此**同初速下两种材质的滑行距离之比 = 摩擦系数之比的倒数**:

```
s_冰 / s_橡胶 = μ_橡胶 / μ_冰 = 1.00 / 0.05 = 20 ×
s_普通 / s_冰 = μ_冰 关系: 0.25 / 0.05 = 5 ×
```

验收要求是 ≥3 倍,默认系数给出的余量是 20 倍(以及普通地 vs 冰面的 5 倍),即使后续 #10 为提高手感把橡胶 μ 调到 0.3 仍有 6 倍。**比值由数据决定,不由求解器迭代决定**,这就是自写模型的收益。

数值自检(默认 `g = 20 m/s²`,`s = v²/(40μ)`):

| 初速 | 冰面(μ=0.05) | 普通(μ=0.25) | 橡胶(μ=1.00) | 橡胶 vs 冰面 |
| --- | --- | --- | --- | --- |
| 6 m/s | 18.0 m | 3.6 m | 0.90 m | 20 × |
| 10 m/s | 50.0 m | 10.0 m | 2.50 m | 20 × |
| 14 m/s | 98.0 m | 19.6 m | 4.90 m | 20 × |

关卡设计直接读这张表下料,例如"第 2 关冰面段长度取 60 m、进场速度 10 m/s"就有明确依据。

### 2.10 默认参数表(`src/app/config.ts` 的唯一真源)

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `FIXED_DT` | 1/60 s | 物理定步长,与渲染帧率解耦 |
| `gravity` | 20 m/s² | 竖直重力。**游戏化取值**(真实 9.8 会让跳跃绵软);教学文案只讨论"重力使速度改变"的定性结论,不引用该数值 |
| `airDrag` | 0 | 腾空不减速,服务"外力停止则运动状态保持"的演示 |
| `accel` | 14 m/s² | 前进键地面加速度 |
| `maxSpeed` | 14 m/s | 速度上限,防数值爆炸 |
| `turnAuthority` | `vRef = 8 m/s`,`floor = 0.3`,`maxTurnRate = 120 °/s` | 高速转向衰减;实际角速度 = `maxTurnRate × authority` |
| `jump.initialVerticalSpeed` | 8 m/s | 跳高 1.6 m、平跳滞空 0.8 s |
| `jump.coyoteSeconds` | 0.1 s | 离地宽限,手感 |
| 材质 `ice` | μ = 0.05 | 见 §2.9 |
| 材质 `normal` | μ = 0.25 | |
| 材质 `rubber` | μ = 1.00 | |
| 角色胶囊 | 半径 0.4 m,高 1.6 m | 与障碍/墙的碰撞体积 |

### 2.11 确定性要求

- 同样的 `(初始状态, 输入序列, 关卡, FIXED_DT)` 必须得到逐位相同的轨迹;`sim/` 里不允许出现 `Math.random()`、`Date.now()`、`performance.now()`。
- 视觉特效(粒子、镜头抖动)可以随机,但只能存在于渲染层,且不得回写 `sim/` 状态。
- 测试里用 `simulate(state, inputs, level, { steps })` 这种纯函数入口跑固定输入序列,而不是等真实帧。

## 3. 关卡数据格式

### 3.1 设计目标

1. **数据驱动**:新增/调整关卡只改 JSON,不改引擎代码(#9 的硬性要求)。
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
| `schemaVersion` | ✔ | 格式版本,当前 `1`;破坏性变更时递增,加载器按版本迁移 |
| `id` / `order` | ✔ | 关卡标识(也是进度存储键)与解锁顺序 |
| `title` / `knowledgePoint` | ✔ | 关卡中文名 / 本关知识点(关卡选择界面与图鉴卡片用) |
| `environment` | – | 天空色、环境光强度、阴影档位、雾 |
| `physics` | – | 对 §2.10 默认参数的逐项覆盖(重力、空气阻力、限速、加速度、转向、跳跃、兜底材质) |
| `spawn` | ✔ | 起点:`segmentId` + 段内里程 `at` + 横向 `lateral` + 朝向 `heading` + 初速 `speed` |
| `surfaces` | ✔ | 本关材质表:`{ "ice": { "mu": 0.05, "color": "#9fd8ff", "pattern": "ice", "label": "冰面" } }`,字段名无条件单位 |
| `terrain[]` | ✔ | 地形段:`type`(`straight`/`arc`/`ramp`)、`length`、`width`、`surface`、`curvature`(arc)、`grade`(ramp)、`walls`、`scenery` |
| `obstacles[]` | – | 障碍:`shape`(box/cylinder)、`segmentId` + `at` + `lateral`、尺寸、`behavior`(solid/hazard) |
| `goal` | ✔ | 过关条件,四种判别式之一(见下) |
| `failure` | – | 失败条件:坠落高度 `fallBelowY`、超时 `timeoutSeconds`、越界与危险物处理 |
| `teaching` | ✔ | **教学文案挂载点**:`intro`(开局提示)、`hint`(卡关提示)、`onClear`/`onFail`(各含 `principle` 一句话原理 + `tip` 面向学生的建议)、`prediction`(预测-验证交互:prompt/options/correctOptionId/onCorrect/onWrong) |
| `rewards` | – | 计时星级阈值 `starThresholds`、`parTimeSeconds` |
| `camera` | – | 跟随相机距离/高度/俯仰/FOV |
| `i18n` | – | 预留的多语言覆盖表,MVP 只发中文 |

**过关条件(`goal`)支持四种模式**,覆盖 #9 的五关知识点排布:

| 模式 | 语义 | 用在 |
| --- | --- | --- |
| `reachGoal` | 抵达指定区间(可要求 `minSpeed`/`maxSpeed`) | ①匀速直线体验、⑤综合 |
| `stopInZone` | 在指定区间内停住并保持 `holdSeconds` | ②冰面刹不住 |
| `passGates` | 按顺序通过若干门 | ③速度与转向 |
| `maintainSpeed` | 在区间内不低于 `minSpeed` 通过 | ④跳跃距离与水平速度 |

### 3.4 完整 JSON Schema

机器可读的完整定义在 [`docs/schema/level.schema.json`](./schema/level.schema.json)(JSON Schema draft 2020-12)。它规定了每个字段的类型、取值域、单位与默认值,并用 `oneOf` 表达 `goal` 的四种判别式、`allOf/if/then` 表达 `arc` 必须有 `curvature`、`ramp` 必须有 `grade`、`box` 必须有 `size`、`cylinder` 必须有 `radius`+`height` 等条件约束。

使用方式(#9 落地时):

```ts
import Ajv from 'ajv/dist/2020';
import schema from './schema/level.schema.json';

export const validateLevel = new Ajv({ allErrors: true, strict: true }).compile(schema);
```

- **构建/测试期**:`tests/levels/*.test.ts` 遍历 `levels/*.json` 逐个校验,任何一个不合 schema 就让 CI 红。
- **运行时**:dev 模式下校验并打印可读错误;生产构建跳过(校验器不进产物包)。
- **改动纪律**:任何字段新增/改名都必须先改 `level.schema.json` 并同步更新本文 §3.3,再改关卡数据。

### 3.5 示例关卡(第 2 关:冰面刹不住)

该示例也用作 schema 的自测样例(验证"合法的关卡能通过校验"):

```json
{
  "schemaVersion": 1,
  "id": "level-02",
  "order": 2,
  "title": "刹不住的冰面",
  "knowledgePoint": "摩擦力越小,运动状态越难改变",
  "environment": { "skyColor": "#bfe3ff", "shadowQuality": "medium" },
  "physics": { "gravity": 20, "accel": 14, "maxSpeed": 14 },
  "spawn": { "segmentId": "runway", "at": 1, "lateral": 0, "speed": 10 },
  "surfaces": {
    "normal": { "mu": 0.25, "color": "#8d99ae", "pattern": "grid", "label": "普通地面" },
    "ice": { "mu": 0.05, "color": "#9fd8ff", "pattern": "ice", "label": "冰面" },
    "rubber": { "mu": 1.0, "color": "#2f2f2f", "pattern": "rubber", "label": "橡胶地" }
  },
  "terrain": [
    { "id": "runway", "type": "straight", "length": 12, "width": 6, "surface": "normal" },
    { "id": "icefield", "type": "straight", "length": 70, "width": 6, "surface": "ice" },
    { "id": "stopzone", "type": "straight", "length": 20, "width": 6, "surface": "normal" }
  ],
  "goal": {
    "type": "stopInZone",
    "zone": { "segmentId": "stopzone", "from": 2, "to": 12 },
    "holdSeconds": 0.5,
    "description": "滑过冰面,在绿色区域里停下来"
  },
  "failure": { "fallBelowY": -10, "outOfBounds": "fail" },
  "teaching": {
    "intro": "前面是冰面。猜猜松开方向键之后,你能滑多远?",
    "hint": { "afterSeconds": 12, "text": "冰面上几乎没有摩擦,速度不会自己消失——早点减速。" },
    "onClear": { "principle": "摩擦力越小,运动状态越难改变", "tip": "所以冰面上要提前很早就开始减速。" },
    "onFail": { "principle": "没有力,速度就不会自己改变", "tip": "你冲过去了,是因为冰面几乎不给你减速。" }
  },
  "rewards": { "parTimeSeconds": 18, "starThresholds": [15, 20, 28] },
  "camera": { "mode": "follow", "distance": 8, "height": 2.6, "fov": 62 }
}
```

### 3.6 版本演进与校验纪律

- `schemaVersion` 只在**破坏性**变更时递增(删字段、改语义、改单位)。加载器保留 `migrate[version] → version+1` 的链式迁移位,当前只有 v1,迁移表为空。
- 新增**可选**字段不递增版本;引擎必须容忍缺省(默认值写在 schema 的 `default` 与 `src/app/config.ts` 两处,以 schema 为准)。
- `levels/*.json` 与 schema 必须同 PR 更新;CI 的 schema 校验是这条纪律的执行者。

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
│  └─ schema/level.schema.json # 关卡 JSON Schema
├─ src/
│  ├─ main.ts                  # 组装根:创建 Game,启动循环,挂载到 #app
│  ├─ app/
│  │  ├─ Game.ts               # 顶层编排:加载关卡 → 建场景 → 循环 → 关卡状态机
│  │  ├─ loop.ts               # 固定步长 accumulator(§2.3)
│  │  └─ config.ts             # §2.10 默认参数唯一真源
│  ├─ sim/                     # ★ 纯逻辑:不 import three / 不碰 DOM
│  │  ├─ state.ts              # SimState 定义与从 spawn 初始化
│  │  ├─ step.ts               # stepSim(state, input, level, dt) → { state, events }
│  │  ├─ friction.ts           # 解析减速与停止距离(§2.4)
│  │  ├─ kinematics.ts         # 速度积分、转向权、跳跃、坡度
│  │  ├─ collision.ts          # 中心线带状地形 + 障碍的解析接触
│  │  └─ goal.ts               # 过关/失败判定(读 goal / failure)
│  ├─ levels/
│  │  ├─ types.ts              # 由 schema 派生的 Level 类型
│  │  ├─ load.ts               # fetch + ajv 校验 + 归一化(度→弧度、补默认值)
│  │  └─ registry.ts           # 关卡清单、解锁规则、当前关卡指针
│  ├─ render/                  # three.js:唯一允许 import three 的目录
│  │  ├─ Renderer.ts           # WebGLRenderer、尺寸/DPR、降级档位
│  │  ├─ SceneBuilder.ts       # 由 Level 数据生成地形网格(渲染层唯一读 Level 的模块)
│  │  ├─ CameraRig.ts          # 跟随相机(读 camera 配置)
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
   ├─ sim/                     # 物理与判定断言(§6.1)
   ├─ levels/                  # schema 校验 + 关卡数据自洽性
   ├─ arch/                    # 依赖边界测试(§6.3)
   └─ e2e/smoke.spec.ts        # Playwright 冒烟
```

### 4.2 模块职责边界

| 模块 | 职责 | 明确不做 |
| --- | --- | --- |
| `app/Game.ts` | 生命周期编排:加载关卡、创建渲染/输入/UI、驱动循环、维护 running/cleared/failed 状态机 | 物理公式、渲染细节、DOM 结构 |
| `app/loop.ts` | 把真实帧时间切成固定步长 | 任何游戏逻辑 |
| `sim/*` | 物理与判定:给定状态与输入产出新状态和事件 | 渲染、DOM、计时器、随机、`three` 类型 |
| `levels/*` | 读 JSON、按 schema 校验、归一化、暴露关卡清单 | 物理计算、渲染 |
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
      └── 只能被上层依赖,自己什么都不依赖(除 node 内置的纯计算能力)
```

规则:`sim/` 与 `levels/types.ts` 不得 import `three`、DOM 类型或任何 `render/`、`ui/` 模块;`render/` 不得 import `sim/step.ts`。用 ESLint `no-restricted-imports` 声明,并配一个 `tests/arch/import-boundaries.test.ts` 扫描 `src/sim/**` 的 import 做兜底断言(§6.3)。这样做的收益是"物理测试永远不需要浏览器",CI 上跑得快、也稳定。

### 4.4 运行时数据流

```
levels/level-0X.json ──► levels/load.ts(ajv 校验 + 归一化)──► Level
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

事件从 `stepSim` 以返回值形式冒出来(`{ type: 'grounded' | 'surfaceChanged' | 'wallHit' | 'cleared' | 'failed', … }`),由 `Game` 分发给渲染与 UI——`sim/` 因此不需要任何回调或事件总线。

## 5. 性能与加载预算

### 5.1 首屏预算(桌面优先)

| 指标 | 目标 | 上限 | 依据 |
| --- | --- | --- | --- |
| 首屏 JS(压缩后 gzip) | ≤ 190 KB | **≤ 220 KB** | three 最小场景实测 136 KB + 应用代码约 50 KB |
| 首屏 CSS + HTML | ≤ 12 KB | 20 KB | 原生 CSS,HUD 规模小 |
| 首屏关卡 JSON | ≤ 4 KB | 8 KB | 只加载第 1 关 |
| 首屏资源(音频/纹理) | 0(程序化生成) | ≤ 150 KB | 纹理走 `surfaces.pattern` 程序化生成,音效懒加载到首次播放 |
| 交互就绪时间(TTI) | ≤ 2.5 s(中端笔记本) | ≤ 5 s(低端 / 4× CPU 降速) | 首屏无网络请求阻塞,渲染器初始化是主成本 |
| 稳态帧率 | 55–60 fps | 低端 ≥ 30 fps | 场景 ≤ 20k 三角形/关,单方向光 + 阴影 |

### 5.2 分包策略

1. **只为首屏加载第 1 关。** `levels/index.json` 与 `level-01.json` 同步请求;其余关卡用动态 `import()` 在进入时拉取(`levels/*.json` 各成 chunk)。
2. **`three` 单列 vendor chunk** 并长期缓存(hash 命名);应用代码与关卡数据独立 chunk,改关卡不失效缓存。
3. **禁忌**:不要 `import * as THREE from 'three'` 之后又引 `three/addons/*` 的重资产(如 `GLTFLoader`、`EffectComposer`、`Water`)。实测"最小场景 + OrbitControls"已经是 545 KB min;每引一个 addon 都要重新核对 §5.1。
4. `ajv` 只在 dev/测试里使用,生产构建不得引入(用 `import.meta.env.DEV` 条件分支 + 构建产物检查)。

### 5.3 低端设备降级策略

判定方式:启动时读 `navigator.hardwareConcurrency`、`deviceMemory`(可得时)与首次 2 秒的平均帧时间,给出初始档位;运行中持续监测,连续 2 秒低于阈值就降一档(只降不升,避免抖动)。

| 档位 | 渲染分辨率 | 阴影 | 抗锯齿 | 粒子/装饰 | 目标帧率 | 物理 |
| --- | --- | --- | --- | --- | --- | --- |
| high | `min(DPR, 2)` | 2048 阴影贴图 | MSAA ×4 | 全量 | 60 | FIXED_DT 不变 |
| medium(默认) | `min(DPR, 1.5)` | 1024 阴影贴图 | FXAA | 全量 | 60 | FIXED_DT 不变 |
| low | `min(DPR, 1)` | 关闭 | 无 | 减半,`scenery` 只保留 `spacing ≥ 4 m` 的 | ≥30 | FIXED_DT 不变,渲染跳帧 |

关键约束:**降级只动渲染,不动物理步长。** 低端机上角色可能看起来更卡,但"冰面滑 50 m 才停"这个结论与高档机完全一致——这既保护教学正确性,也让 §6 的断言与设备无关。必要时用"每渲染帧推进 2 个物理步"来吸收 30 fps 的设备(视觉上是 30 Hz 采样,物理仍是 60 Hz)。

### 5.4 测量方式(可执行)

- `npm run build` 后用 `gzip -9 -c dist/assets/*.js | wc -c` 核对 §5.1 的 JS 预算(CI 里做成一条脚本,超预算即失败)。
- Playwright 冒烟里断言首屏无 4xx、canvas 存在、`window.__perf.firstInteractiveMs` 上报值存在。
- 帧率用 `requestAnimationFrame` 的 60 帧滑动平均记录到 `window.__perf`;低端回归靠 CI 的 SwiftShader 跑一遍 low 档,只断言"不报错、能通关第 1 关",不做帧率硬门槛(CI 机器不可代表真机)。
- 人工核对用 Chrome DevTools Performance + Lighthouse(桌面 preset),记录在 PR 描述里。

## 6. 测试策略(物理行为怎么自动化测)

### 6.1 纯物理测试(Vitest,Node 环境,无 WebGL)

这是本项目的测试重心,可行性来自 §2.1 的分层:物理是纯函数,给固定输入序列就能拿到确定性轨迹。

```ts
// tests/sim/friction.test.ts(示意)
import { simulate } from '../../src/sim/step';

const level = makeLevel({ surfaces: { ice: { mu: 0.05 }, rubber: { mu: 1.0 } } });

test('同初速下冰面滑行距离至少是橡胶地的 3 倍', () => {
  const dIce = simulate({ level, surface: 'ice', v0: 10, input: 'none' }).travelDistance;
  const dRubber = simulate({ level, surface: 'rubber', v0: 10, input: 'none' }).travelDistance;
  expect(dIce / dRubber).toBeGreaterThanOrEqual(3);      // 默认系数下实际为 20×
  expect(dIce).toBeCloseTo(50, 1);                       // 并且与解析解一致
});
```

必须覆盖的断言清单(每条都对应 #8 / #9 的 Verify):

| # | 断言 | 关卡/性质 |
| --- | --- | --- |
| 1 | `stopInZone` 条件下,冰面滑行距离 / 橡胶地滑行距离 ≥ 3(默认参数下 ≈ 20) | #8 验收 |
| 2 | 滑行距离等于闭式解 `v²/(2μg)`,与 `FIXED_DT` 取 1/60、1/120、1/30 时一致(±1e-6) | 证明 §2.4 的解析离散化有效 |
| 3 | 无摩擦段(μ=0)上不给输入时速度恒定,位置线性推进 | "运动状态保持" |
| 4 | 腾空水平速度不变(`airDrag=0`),落点 = `v_h × T`,且对 `v_h` 单调递增 | #8 跳跃与水平速度 |
| 5 | 上坡段相同初速滑行距离显著短于平地(坡度正确引入重力分量) | §2.7 |
| 6 | 同一 `(状态, 输入序列, 关卡)` 跑两次结果完全相同(深比较) | 确定性 |
| 7 | 四种 `goal` 模式各有一组"刚好过 / 刚好不过"的边界用例 | #9 判定 |
| 8 | 段材质切换时 `surfaceChanged` 事件在正确的里程处触发 | 摩擦分区 |
| 9 | 越界/坠落/危险物接触分别在正确条件下返回 `failed` 及原因 | 失败即时重试的基础 |
| 10 | 关卡数据全部通过 schema 校验,且 `goal`/`spawn` 引用的 `segmentId`、`surfaces` 里的材质 id 都存在(跨字段自洽) | 数据驱动 |

第 10 条的跨字段自洽检查是 schema 表达不了的部分(JSON Schema 无法校验"引用的 id 存在"),用测试补齐,这样"加关卡不改代码"才真的安全。

### 6.2 冒烟与交互测试(Playwright)

- 页面能打开、WebGL 上下文创建成功(`--use-gl=swiftshader` 在 CI 里可跑)。
- 按键 → 角色位移:通过 `window.__game` 暴露只读测试钩子(位置、速度、状态),断言按前进键 1 秒后位置沿 +Z 前进。
- 通关第 1 关后 `localStorage` 出现通关记录,刷新后关卡选择界面显示已解锁(覆盖 #9 的进度持久化)。
- 失败后按 R 能立即重试,且物理状态被完全重置(位置/速度回到 `spawn`)。

E2E 不测数值精度——精度由 §6.1 的纯函数测试负责。

### 6.3 CI 门禁

`npm run build`(含 `tsc --noEmit`)→ `npm run test` → `npm run test:e2e`。另外两条轻量但重要的检查:

- **依赖边界测试**:扫描 `src/sim/**` 与 `src/levels/types.ts` 的 import,出现 `three`、DOM、`render/`、`ui/` 即失败。
- **体积预算检查**:构建产物 gzip 后超过 §5.1 上限即失败,防止体积无声膨胀。

## 7. 与后续任务(#7–#10)的对应关系

| 任务 | 直接采用本文的哪部分 |
| --- | --- |
| #7 项目脚手架 | §1 依赖白名单与脚本、§4.1 目录骨架、§4.3 依赖边界、§5.2 分包、§6.3 三条 CI 门禁 |
| #8 物理核心 | §2 全部(固定步长、摩擦解析解、转向权、跳跃、坡度、解析碰撞)、§2.9 的系数、§6.1 断言 1–6 |
| #9 关卡与进度 | §3 的 schema 与判定模型、§6.1 断言 7–10、§4.1 的 `levels/` 与 `progress/` 边界 |
| #10 游戏感打磨 | §3.3 的 `teaching.*` 与 `prediction` 挂载点、§5.3 降级档位对特效的约束 |

## 8. 待人工确认(本单元在此暂停)

本单元带 `hitl:done`:文档产出后暂停,等人工 `/approve` 再进入 #7。请重点确认以下四个选择,它们都不可逆地影响后续实现成本:

1. **物理方案**:维持"自写运动学、不接物理引擎"(理由见 §1.4)。若希望更强的通用碰撞能力,替代方案是接 Rapier,代价是首屏多约 1.6 MB gzip,并把部分物理断言改为容差断言。
2. **UI 技术**:维持"原生 DOM + CSS",不引 UI 框架(省 67 KB gzip)。若后续希望用 React 做更复杂的图鉴/关卡选择界面,需要重排 §5.1 预算。
3. **系数语义**:冰面 μ=0.05、普通 μ=0.25、橡胶 μ=1.00 这组值是为了让"滑行距离 ≥3 倍"有 20 倍余量而定的;比值是设计约束,绝对值不是物理真值(§2.9、§2.10 已注明)。
4. **重力取值**:`g = 20 m/s²` 是手感调优值,教学文案只讲定性结论。若要求数值上也贴近 9.8,跳跃与滑行距离需要整体重调(§2.10)。

以上任何一条被否决,都应先改本文对应章节,再开始 #7。
