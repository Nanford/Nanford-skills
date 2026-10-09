/**
 * INPUT: Root.tsx
 * OUTPUT: 注册 Remotion 根组件
 * POS: bundler 与 Studio 的入口文件。
 */

import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";

registerRoot(RemotionRoot);
