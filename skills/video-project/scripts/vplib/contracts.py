"""
INPUT: 无运行时依赖；取值来自 docs/DATA_CONTRACTS.md
OUTPUT: 平台、阶段、状态、素材类型、授权状态、受众细分等常量，以及阶段失效映射
POS: 数据合同的代码映射。改合同时先改文档，再同步这里；其余模块只从这里取常量。
"""

SCHEMA_VERSION = "1.0"

PLATFORMS = ("douyin", "channels")
# 新项目默认只做抖音一版（主理人 2026-10-07：点名哪个平台只做哪个，没点名只做抖音）；两个都要时 init 传 --platforms douyin,channels
DEFAULT_PLATFORMS = ("douyin",)
SHARED_STAGES = ("intake", "research", "asset_index")
# 顺序即依赖顺序：某阶段重新产出后，排在它后面的已完成阶段全部失效
VARIANT_STAGES = ("script", "speech", "captions", "visuals", "edit", "mix", "render", "qa", "delivery")
STAGE_STATUSES = ("pending", "running", "passed", "blocked", "failed", "stale")
APPLICABILITY = ("required", "optional", "waived")

# 公共阶段变化时，各平台从哪个阶段开始失效：
# 选题与事实变化影响脚本及全部下游；素材索引变化只影响画面及之后
SHARED_STAGE_FIRST_AFFECTED = {"intake": "script", "research": "script", "asset_index": "visuals"}

ASSET_KINDS = ("footage", "image", "music", "voice", "sfx", "font")
RIGHTS_STATUSES = ("confirmed", "unconfirmed", "restricted")
AUDIENCE_SEGMENTS = ("ai_office", "ai_learning", "ai_transformation", "fde", "beginner", "smb_owner")

DEFAULT_TARGET_SECONDS = {"douyin": {"min": 60, "max": 120}, "channels": {"min": 60, "max": 180}}

# 与 .claude/skills/minimax-tts/config.json 保持一致的默认配音
DEFAULT_VOICE = {
    "mode": "tts",
    "provider": "minimax",
    "model": "speech-2.8-hd",
    "voice_id": "Chinese (Mandarin)_Gentleman",
    "language": "zh-CN",
    "cloning_authorized": False,
}

PROJECT_DIRS = (
    "research",
    "assets/original",
    "assets/work",
    "generated",
    "qa",
    "costs",
    "metrics",
)
VARIANT_DIRS = ("audio", "captions", "preview", "exports")
