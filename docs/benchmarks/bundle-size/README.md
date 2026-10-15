# §1.2 体积实测的复现方式

`ARCHITECTURE.md` §1.2 的体积数字**对入口极敏感**(例如 Babylon.js 按需 import 与桶导入能差 6 倍),
所以把当时用的入口源码一并提交在这里,而不是只留一张表。

```bash
# Node v24.21.0,esbuild 0.28.x
mkdir -p /tmp/bundle-bench && cd /tmp/bundle-bench && npm init -y
npm i three@0.186.1 @babylonjs/core@9.30.0 cannon-es@0.20.0 \
      @dimforge/rapier3d-compat@0.21.0 react@19 react-dom@19 esbuild
cp <本目录>/*-entry.js .
mkdir -p out
for entry in *-entry.js; do
  npx esbuild "$entry" --bundle --minify --format=esm --outfile="out/${entry%.js}.js"
  raw=$(stat -c%s "out/${entry%.js}.js")
  gz=$(gzip -9 -c "out/${entry%.js}.js" | wc -c)
  printf '%-18s %6d KB min  %6d KB gzip\n' "$entry" $((raw/1024)) $((gz/1024))
done
```

2026-10-15 的结果:

| 入口 | min | gzip |
| --- | --- | --- |
| `three-entry.js` | 545 KB | **136 KB** |
| `babylon-entry.js` | 1 615 KB | **381 KB** |
| `rapier-entry.js` | 4 233 KB | **1 613 KB** |
| `cannon-entry.js` | 121 KB | **35 KB** |
| `react-entry.js` | 217 KB | **67 KB** |

已知差异(如实记录,不掩盖):

- 研究卡(#5)测到的 Three.js 最小场景是 154 KB gzip,因为它的入口里多了一个刚体世界与角色刚体;
  本文的入口只含渲染所需的最小集合,所以更小。
- `cannon-entry.js` 是整库入口。只 import `World/Body/Box/Vec3` 时 tree-shaking 后约 24 KB gzip
  (独立 QA 复现),差异来自入口面而非选型结论。
- Babylon.js 的数字随"按需 import 到哪一层"变化很大(262 KB ↔ 1 658 KB 区间都有实测),
  本文固定用 `babylon-entry.js` 这一份入口,保证表格可复算。
