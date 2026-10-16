// "最小可用场景"入口:ARCHITECTURE.md §1.2 的 Three.js 一行。
// 复现:npm i three@0.186.1 esbuild && npx esbuild three-entry.js --bundle --minify --format=esm --outfile=out/three.js
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
const renderer = new THREE.WebGLRenderer();
new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshStandardMaterial());
new THREE.DirectionalLight();
new THREE.AmbientLight();
new OrbitControls(camera, renderer.domElement);
console.log(scene, camera, renderer);
