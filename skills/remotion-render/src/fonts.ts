/**
 * INPUT: public/fonts/NotoSansSC-VF.ttf（由 scripts/setup-fonts.mjs 下载并校验，OFL 许可）
 * OUTPUT: 注册名为 NotoSansSC 的可变字重字体
 * POS: 字体加载的唯一入口。使用本地文件，渲染时不访问网络；delayRender 等待字体就绪后才开始截帧，避免中文回退字体。
 */

import { loadFont } from "@remotion/fonts";
import { cancelRender, continueRender, delayRender, staticFile } from "remotion";
import { FONT_FAMILY } from "./theme";

const handle = delayRender("加载 NotoSansSC 字体");

loadFont({
  family: FONT_FAMILY,
  url: staticFile("fonts/NotoSansSC-VF.ttf"),
  // 可变字体：一个文件覆盖 100～900 全部字重
  weight: "100 900",
  display: "block",
})
  .then(() => continueRender(handle))
  .catch((error: unknown) => {
    // 字体缺失时立即终止渲染，不允许用系统回退字体渲染出错误的中文字形。
    // 用 cancelRender 而不是 throw：Promise 里的 throw 只会变成未处理的拒绝，渲染会一直等到 delayRender 超时。
    cancelRender(new Error(`字体加载失败，请先运行 npm run setup:fonts：${String(error)}`));
  });
