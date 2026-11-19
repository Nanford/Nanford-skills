"""通过本机 Edge / Chrome 无头模式将 SVG 导出为 PNG 预览。"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def find_browser() -> str | None:
    cands = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    return next((c for c in cands if c and Path(c).exists()), None)


def export_png(svg_path: Path, png_path: Path, w: int, h: int) -> bool:
    browser = find_browser()
    if not browser:
        print("[warn] 未找到 Edge/Chrome，跳过 PNG 预览", file=sys.stderr)
        return False
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--screenshot={png_path.resolve()}",
        f"--window-size={w},{h}",
        svg_path.resolve().as_uri(),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    return png_path.exists()
