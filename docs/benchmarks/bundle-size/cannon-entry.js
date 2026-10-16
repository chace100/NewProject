// 复现:npm i cannon-es@0.20.0 esbuild
// 整库入口(实测 121 KB min / 35 KB gzip)。只取 World/Body/Box/Vec3 等子集还能更小(QA 独立测得 24 KB gzip),
// 但 WebGL 场景里通常还需要 Shape/ContactMaterial/Solver,故以整库为准,并对入口敏感性如实标注。
import * as CANNON from 'cannon-es';
console.log(CANNON);
