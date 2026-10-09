/**
 * INPUT: google/fonts 仓库固定提交中的 Noto Sans SC 可变字体与 OFL 许可文本
 * OUTPUT: public/fonts/NotoSansSC-VF.ttf 与 public/fonts/OFL.txt；校验 SHA-256，不匹配时删除并报错；fetch 连不上时改用 curl（走代理环境变量）
 * POS: 字体准备步骤。字体文件约 17 MB，不进 Git，由本脚本按固定版本下载，保证每台机器渲染出的字形一致。
 */

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SKILL_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const FONT_DIR = join(SKILL_ROOT, "public", "fonts");
// 2026-03-25 的 google/fonts 提交；上游为 notofonts/noto-cjk 523d033d，许可为 SIL OFL 1.1
const COMMIT = "a85815a42757630ce188fdad368c2dfc444d4773";
const BASE = `https://raw.githubusercontent.com/google/fonts/${COMMIT}/ofl/notosanssc`;
const FILES = [
  { url: `${BASE}/NotoSansSC%5Bwght%5D.ttf`, name: "NotoSansSC-VF.ttf", sha256: "a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da" },
  { url: `${BASE}/OFL.txt`, name: "OFL.txt", sha256: "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9" },
];

const sha256 = (buffer) => createHash("sha256").update(buffer).digest("hex");

/**
 * 先用 Node 自带 fetch；失败时改用 curl。Node 的 fetch 默认不读 HTTPS_PROXY，走代理上网的机器上会直接连接失败，
 * curl（Windows 10+、macOS、Linux 自带）会按代理环境变量连接。两种方式下载的内容都要过同一个校验值。
 */
async function download(url) {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return Buffer.from(await response.arrayBuffer());
  } catch (error) {
    console.log(`fetch 失败（${error.cause?.code ?? error.message}），改用 curl 重试`);
    return execFileSync("curl", ["-sS", "-L", "--fail", "--max-time", "300", url], { maxBuffer: 64 * 1024 * 1024 });
  }
}

async function existingMatches(path, expected) {
  try {
    return sha256(await readFile(path)) === expected;
  } catch {
    return false;
  }
}

async function fetchVerified({ url, name, sha256: expected }) {
  const target = join(FONT_DIR, name);
  if (await existingMatches(target, expected)) {
    console.log(`已存在且校验通过：${name}`);
    return;
  }
  const buffer = await download(url);
  if (sha256(buffer) !== expected) {
    await rm(target, { force: true });
    throw new Error(`${name} 校验值不符，已放弃写入`);
  }
  await writeFile(target, buffer);
  console.log(`已下载并校验：${name}（${buffer.length} 字节）`);
}

await mkdir(FONT_DIR, { recursive: true });
for (const file of FILES) {
  await fetchVerified(file);
}
