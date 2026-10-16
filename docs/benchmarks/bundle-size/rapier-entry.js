// 复现:npm i @dimforge/rapier3d-compat@0.21.0 esbuild
// compat 包把 WASM 以 base64 内联进 JS,因此这一个 import 就是首屏代价(实测 1 613 KB gzip)。
import RAPIER from '@dimforge/rapier3d-compat';
console.log(RAPIER);
