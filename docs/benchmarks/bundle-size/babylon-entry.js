// "最小可用场景"入口:ARCHITECTURE.md §1.2 的 Babylon.js 一行(按需 import + 必要的副作用 import)。
import { Engine } from '@babylonjs/core/Engines/engine';
import { Scene } from '@babylonjs/core/scene';
import { ArcRotateCamera } from '@babylonjs/core/Cameras/arcRotateCamera';
import { HemisphericLight } from '@babylonjs/core/Lights/hemisphericLight';
import { MeshBuilder } from '@babylonjs/core/Meshes/meshBuilder';
import '@babylonjs/core/Materials/standardMaterial';
import '@babylonjs/core/Meshes/Builders/boxBuilder';
import '@babylonjs/core/Meshes/Builders/groundBuilder';

const canvas = document.createElement('canvas');
const engine = new Engine(canvas);
const scene = new Scene(engine);
const camera = new ArcRotateCamera('camera', 0, 0, 10, undefined, scene);
new HemisphericLight('light', undefined, scene);
MeshBuilder.CreateBox('actor', {}, scene);
MeshBuilder.CreateGround('ground', {}, scene);
console.log(engine, camera);
