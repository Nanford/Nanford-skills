# 网络依据与采用范围

核验日期：2026-09-29。来源以项目原仓库、厂商官方文档和官方规则为主。文档中的制作参数、内容策略和技术组合是本方案的设计判断；来源不构成对流量、生成质量或本地已接通能力的保证。

## 1. 现有完整方案

| 来源 | 已核验事实 | 对应采用范围 |
|---|---|---|
| [MoneyPrinterTurbo 原项目](https://github.com/harry0703/MoneyPrinterTurbo) | 项目说明覆盖文案、素材、配音、字幕、配乐、视频合成及多种操作入口 | 借鉴阶段划分、本地素材输入、任务设置与打样方式；不把所列海外发布平台等同于国内平台 |
| [MoneyPrinterTurbo LICENSE](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/LICENSE) | 核验时原项目标示 MIT 许可证 | 软件复用保留许可；音乐、素材、接口的权利另行判断 |
| [NarratoAI 原项目](https://github.com/linyqh/NarratoAI) | 定位包含已有视频理解、解说和自动化剪辑 | 借鉴素材索引、片段选择和解说流程；不把影视素材默认视为可用于账号运营 |
| [NarratoAI LICENSE](https://github.com/linyqh/NarratoAI/blob/main/LICENSE) | 本次读取的原仓库 main 分支 LICENSE 为 MIT | 采用版本必须固定并再次读取其许可；旧文章或其他 fork 的许可表述不能替代原版本核验 |

| [videocut（Claude Code 技能）](https://github.com/jaychou6868/videocut) | MIT；公开了「转写 → Hook → Remotion 参数 → 手机安全区检查 → 双版本渲染」的智能体工作流及调试记录，例如用 `OffthreadVideo` 避免渲染抖动 | 参考阶段划分与踩坑记录，不直接复制其模板与品牌素材 |
| [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft) | Apache-2.0；可生成剪映草稿；自动导出仅 Windows 下 6.8 及以下版本；新版剪映草稿常为加密格式 | 可选扩展，交付供剪映精修的草稿；按实际剪映版本验证后才承诺可导入 |

上述项目的广告、赞助模型列表、速度与收益宣传不作为本方案的性能或费用依据。

## 2. 视频画面与渲染

| 来源 | 已核验事实 | 对应采用范围 |
|---|---|---|
| [Remotion Agent Skills](https://www.remotion.dev/docs/ai/skills) | 官方提供面向代码智能体的制作、字幕、渲染等技能说明 | 建设时选用官方技能和当前文档，降低组件与接口误用 |
| [calculateMetadata](https://www.remotion.dev/docs/calculate-metadata) | 支持通过元数据计算配置视频属性 | 将音频实测时长和输入数据用于确定合成属性 |
| [renderMedia](https://www.remotion.dev/docs/renderer/render-media) | 提供程序化渲染能力及相关输出选项 | 本地生成正式文件，并记录参数与版本 |
| [Remotion 字幕转写](https://www.remotion.dev/docs/captions/transcribing) | 官方提供音频转写与字幕处理路径 | 按可用环境选择转写方案，输出后仍校正中文词句 |
| [Remotion 许可证](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md) | 按主体条件区分免费与公司许可，页面还提示后续版本许可变化 | 部署时按锁定版本、主体和使用方式核对，不简单归类为无限制免费开源 |
| [FFmpeg 滤镜文档](https://ffmpeg.org/ffmpeg-filters.html) | 包含媒体裁切、音频混合、响度处理及侧链压缩等滤镜 | 处理媒体、生成混音并辅助检查；具体阈值由本项目设定 |

Remotion、素材文件、字体与外部 API 是不同依赖；拥有其中一种使用权不代表其余全部可用。生成页面、组件源码和 MP4 成品也属于不同交付物。

## 3. 配音、转写与生成素材

| 来源 | 已核验事实 | 对应采用范围 |
|---|---|---|
| [MiniMax 同步 TTS](https://platform.minimax.io/docs/api-reference/speech-t2a-http) | 提供声音、读音与字幕相关参数；文档区分句级/词级字幕粒度 | 首选候选 TTS，落地时对当前模型、区域和声音实测；不硬编码本次页面的最新模型别名 |
| [Azure Speech 语音合成](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-speech-synthesis) | 提供语音合成及 WordBoundary 等事件示例 | 备选正式配音服务，转换时间单位后统一保存 |
| [豆包语音 大模型 HTTP 非流式接口](https://docs.volcengine.com/docs/6561/1257584?lang=zh) | 检索结果中的官方文档摘要显示支持字级时间戳，SSML 文本类型不支持；页面本次未能完整渲染读取 | 中文首选 TTS 候选之一；接入时读取完整文档并实测时间戳字段 |
| [FunASR](https://github.com/modelscope/FunASR) | 开源语音识别工具包；Paraformer 中文模型提供字级时间戳 | 无服务时间戳时的中文转写与对齐首选；安装于独立 Python 环境 |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 提供词级时间戳选项与 VAD 能力 | 多语种转写备选；中文专业词仍需校正 |
| [Qwen-Image 官方 API](https://help.aliyun.com/zh/model-studio/qwen-image-api) | 提供文生图接口，不同地区的凭据与地址须匹配 | 独立流水线的候选生图适配器；准确文字由后期排版负责 |
| [火山方舟视频任务查询](https://docs.volcengine.com/docs/ark/list-video-generation-tasks-api?lang=zh) | 文档列出视频任务 ID、模型与任务状态等数据 | 生视频采用异步任务方式，保存 ID 后查询与恢复 |
| [火山方舟 Seedance 官方说明](https://docs.volcengine.com/docs/ark/seedance-1-5-pro?lang=zh) | 文档介绍视频生成提示词与任务接口关系 | 作为生视频能力接入依据，不据此承诺当前账号已开通或某模型为最新版本 |
| [Pexels 素材许可](https://www.pexels.com/license/) | 说明图片/视频的使用许可与限制 | 可选补充素材来源；逐项保存来源并检查人物、品牌及使用情境 |

MiniMax 本次可完整读取的是国际站文档；中国站具体端点、模型、价格与账号使用范围在接入时另查。不混用地区凭据与接口地址。生图、生视频和 AI 作曲的商用范围均须以实际服务与套餐条款为准。

## 4. 调度与发布规则

| 来源 | 已核验事实 | 对应采用范围 |
|---|---|---|
| [n8n Execute Command](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.executecommand/) | n8n Cloud 不提供此节点；Docker 内执行与宿主机不同 | 不采用；编排改由 Claude Code / Codex 调用本地命令完成 |
| [网信办关于标识办法的说明](https://www.cac.gov.cn/2025-03/14/c_1743654685899683.htm) | 标识办法于 2025-09-01 施行，涉及显式、隐式标识及不得恶意删除等要求 | 保存生成来源、处理已有标识，发布前执行当前平台声明流程 |
| [抖音用户服务协议](https://www.douyin.com/agreements/?id=6773906068725565448) | 协议涉及非真实音视频与可能引起误认内容的显著标识要求 | 标识与实际使用情况一致，发布前核对现行规则 |

视频号具体发布界面、封面裁切、指标定义和声明入口未在本次公开网页核验中充分确认；正式发布前通过实际账号及其官方规则核对，不能用普通媒体转述替代。文档没有给出「平台流量已全部转移」或固定爆款公式的事实结论。

## 5. 文稿语义检查

| 来源 | 已核验事实 | 对应采用范围 |
|---|---|---|
| [TypeSafe API 参考](https://docs.typesafe.ai/api.md) | `POST https://api.typesafe.ai/v1/systemone`，Bearer 鉴权；问题类型为 noul（是/否概率）、choice（多选一，最多 255 个选项）、score（2～10 级）；401 密钥无效、422 请求体不合法、429 限流、529 过载，后两者应退避重试 | `jev-check` 的请求格式与重试规则 |
| [TypeSafe 模型说明](https://docs.typesafe.ai/models.md) | jev-1.13.0 每百万输入 token 0.042 美元、输出免费；单次请求 64k token，state 加最长问题 32k；只接受文字；以英语为主，含中日韩在内的其他语言可用但准确度不稳定；别名 jev-latest / jev-preview 当前都指向 jev-1.13.0；不用客户请求训练，零数据保留仅限企业版 | 单价与每月上限按此设置；中文效果以本项目试点为准，不引用官方英文效果 |
| [Jev 1.13 能力边界](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md) | 擅长常识性判断；不是计算器，数值判断弱于语义判断；与决策无关的内容越多准确度越低；未训练生成文字 | 数字与时长检查保留在 `script-check`；每项检查只发送必要文字 |
| [置信度说明](https://docs.typesafe.ai/confidence.md)、[Noul](https://docs.typesafe.ai/primitives/noul.md)、[Choice](https://docs.typesafe.ai/primitives/choice.md) | choice 返回置信度与各选项概率；noul 只返回概率、没有置信度；低置信度的结果应交人工或其他系统 | noul 按概率中间带、choice 按置信度划出「待人工」 |
| [引用核对示例](https://docs.typesafe.ai/cookbooks/citation_check.md) | 用 supports / contradicts / says_nothing 三分类核对说法与原文，示例以 0.8 置信度作为自动放行线 | `support` 检查的结构与 0.8 阈值 |

以上页面于 2026-09-29 读取；同日用免费的 `GET /v1/models` 验证了本账号密钥可用。中文检查效果来自本项目 2026-09-29 的试点与校准（样例见 `.claude/skills/jev-check/calibration/cases.json`），不是官方数据。

## 6. 剪辑方法参考

| 来源 | 已核对内容 | 对应采用范围 |
|---|---|---|
| 创作者「桌子的频道」讲解其 Agent + Remotion 视频制作流程的一期视频（主理人本地保存的视频文件 `微信视频2026-09-29_230919_843.mp4`，7 分 31 秒，2026-09-29 查看） | 逐段读取画面字幕并抽看文档画面：工具分工、AGENTS / DESIGN / SOP 分工、静态与动态设计测试、按配音拆制作大段表（声音已说 / 画面新增 / 必须上屏）、先设计图与样片后整段、动作时间戳与音效对点、开场单独打磨、封面双参考图、制作复盘提示词、固定时间线的边界 | 对照本项目后采纳的方法见 [EDITING_METHOD.md](EDITING_METHOD.md)；视频提到的公开仓库 Table-VideoSOP 未访问；其中的工具推荐未核验，不进入工具表 |

该视频是个人创作者的经验分享，不是官方资料；采纳的做法以本项目实际生产中的验证结果为准。

## 7. 实施时需复核的项目

模型 ID 与可用区域、音色与价格、商用范围、软件许可、字体许可、素材使用限制、平台上传限制和标识规则。在项目中记录复核日期与证据；来源发生变化时只更新受影响的配置和规则。
