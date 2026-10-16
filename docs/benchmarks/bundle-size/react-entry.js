// 对照项:为什么 HUD 不引 UI 框架(实测 react19 + react-dom19 = 67 KB gzip)。
import { createElement, useState } from 'react';
import { createRoot } from 'react-dom/client';

function App() {
  const [n] = useState(0);
  return createElement('div', null, n);
}
console.log(createRoot, App);
