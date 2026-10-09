# 视频项目数据约定

版本：1.0。以下为待实现生产程序与执行者共同遵守的数据合同，不代表对应程序已经存在。

## 1. 目录

```text
VideoCut/
  AGENTS.md
  WORKFLOW.md
  README.md
  docs/
  templates/brief.example.json
  inbox/                         # 原始文章、录屏、配音与授权材料，只读保留
  library/                       # 已验证字体、音乐、素材；保存各自授权
  .claude/skills/<技能名>/        # 各环节独立技能：SKILL.md、scripts/、tests/；Remotion 工程与锁文件在渲染技能目录内
  .env                           # 密钥（Git 忽略），模板见 .env.example
  projects/YYYYMMDD-slug/
    brief.json
    project.json
    research/sources.json
    research/claims.json
    research/topic-options.md
    assets/assets.json
    assets/index.json
    assets/work/                 # 转码、遮挡和裁切后的工作副本
    assets/ocr-cache.json        # 截图 OCR 缓存（script-check terms 写入，按图片 SHA-256）
    generated/jobs.json          # 外部生成任务及结果
    variants/douyin/
      script.md
      voiceover.txt
      speech.json
      jev-check.json            # 配音前语义提示结果（jev-check review 写入）
      terms-check.json          # 平台敏感词检查结果（script-check terms 写入）
      doubao-review.json        # 豆包平台风险审核结果（doubao-review review 写入）
      doubao-review.waivers.json # 主理人确认误判后的放行记录（doubao-review waive 写入）
      shots.json
      timeline.json
      actions.json              # 画面动作标记（remotion-render actions，音效对点依据）
      audio/                    # 语段、voice.wav、music.wav、sfx.wav、sfx.json（音效轨记录）、mix.wav、mix.json（混音记录）
      captions/captions.json
      captions/subtitles.srt
      cover.props.json          # 封面文字与布局参数（可编辑，重渲染封面用）
      preview/                  # 审片静帧、总览图、低清粗剪
      exports/picture-v001.mp4  # remotion-render 输出的无声画面，旁附 .render.json
      exports/final-v001.mp4    # 旁附 .export.json
      exports/voice-only-v001.mp4
      exports/cover-v001.png    # 旁附 .render.json
      publish.md
    variants/channels/           # 仅当 platforms 含 channels，与 douyin 同构
    qa/report.json
    qa/frames/<平台>-<成片校验值前 8 位>/      # 从成片解码的审阅帧
    qa/contact-sheet-<平台>-<校验值前 8 位>.png # 审阅帧总览
    costs/ledger.json
    delivery.json
    metrics/observations.json
    retro/production-retro.md    # 制作复盘记录与规则修改建议（模板 templates/production-retro.md），Markdown，无 JSON 合同
```

示例中的 `voice-only` 指无配乐母版，仍保留视频、字幕、人声和必要标识；若需保留演示原声，则在交付清单注明。无配乐不等于去字幕或去标识。

## 2. 通用规则

- JSON 编码为 UTF-8；字段名使用英文，正文可使用中文。所有合同文件包含 `schema_version`。
- `id` 稳定且唯一；常用前缀：`claim_`、`source_`、`asset_`、`seg_`、`shot_`。修改内容增加 `revision`，不要通过重编号打断关联。
- 项目内 `path` 一律相对项目根目录，使用 `/`；程序解析后验证仍在获准目录内。外部输入以导入清单保存真实位置，禁止任意路径穿越。
- `null` 表示未知或未完成；不能用 `0`、空文件或虚构路径表示已经测得的时长、成本和产物。
- 真实测量字段附 `measured_by`、`measured_at` 或验证记录。模拟数据标记 `is_example: true`，不能进入正式验收。
- 时间点使用带时区的 ISO 8601 字符串；默认观察时区 `Asia/Singapore`。
- 媒体时间使用毫秒，`fps` 与帧数单独保存。所有区间为左闭右开 `[start, end)`。
- 文件清单包含 `path`、`sha256`、`bytes` 和用途。只有真实存在的文件可写入已完成产物列表。

## 3. brief.json：任务输入

| 字段 | 类型 / 规则 |
|---|---|
| schema_version | 字符串，初始为 `1.0` |
| is_example | 布尔；模板为 true，实际任务须经读取确认后建立真实记录 |
| project_id | 日期与主题短名；项目内唯一 |
| topic、audience、core_question | 中文字符串 |
| audience_segment | `ai_office / ai_learning / ai_transformation / fde / beginner / smb_owner`，每条只取一个 |
| hook | `{type: pain/benefit, text}`；开场第一句，优势类数字须关联 claim |
| input_type | `topic / article / footage / audio / revision` |
| inputs | 输入对象数组：`kind`、`path_or_url`、`usage`、`rights_status`；无输入时为 [] |
| platforms | `douyin`、`channels` 的非空数组；只列本期要做的平台，默认 `["douyin"]`（AGENTS 第 3 节） |
| target_duration_seconds | 平台键映射 `{min, max}`；是目标范围，不是实测值 |
| mode | `hybrid / footage / remotion` |
| voice | `{mode: tts/imported, provider, model, voice_id, language, cloning_authorized}`；未定字段为 null |
| music | `{mode: licensed_library/generated/none, asset_id}` |
| aigc | `{final_implicit_label: none/provenance_tag, explicit_overlay: corner_badge/none, decision_ref}`；成片容器是否另写 AI 隐式标识、画面是否画「AI 合成配音」角标的决定。拼接、转码会丢失服务商写在原始配音里的签名标识，`final_implicit_label: none` 表示成片不写；`explicit_overlay: none` 表示画面与封面不画角标，只靠发布时的平台 AI 声明（系列默认见 `docs/DESIGN.md`），`remotion-render` 与 `av-export` 都读这个字段；缺省按 `corner_badge`；未决定时整个字段为 null |
| budget | `{currency, authorized_max, authorization_ref, allow_new_paid_calls}`；未授权默认 0、null、false |
| visual | `{backdrop_theme}`：底图题材组名或组名数组（`office`、`blueprint`、`tech`、`city`、`nature`，见 `docs/DESIGN.md` 第 3 节）；`remotion-render` 给没写 `wallpaper` 的底图镜头按组轮换分配；为 null 时退回各场景默认风景图 |
| publish | `{authorized, account_ref, authorization_ref}`；默认 false、null、null |
| constraints | 明确限制数组 |

只有持有凭据不构成计费授权。预算上限有币种，多个币种的费用先保留原币，再按带日期的汇率估算；汇率未知时不得声称折算精确。

## 4. project.json：项目与阶段状态

根字段包含 `schema_version`、`project_id`、`revision`、`created_at`、`updated_at`、`capabilities`、`shared_stages`、`variants`、`blockers`。

`capabilities` 每项记录 `available / configured / tested` 三个独立布尔值，以及版本、测试证据和最近检查日期。例如发现 Node.js 只能将 available 设为 true，不能因此将视频渲染 tested 设为 true。

公共阶段：`intake`、`research`、`asset_index`。平台阶段：`script`、`speech`、`captions`、`visuals`、`edit`、`mix`、`render`、`qa`、`delivery`。`publish` 是独立授权阶段，不参与本地交付是否完成的判定。

每阶段记录：

| 字段 | 规则 |
|---|---|
| status | `pending / running / passed / blocked / failed / stale` |
| applicability | `required / optional / waived`；豁免须有任务依据，不能默默省略 |
| input_hash、config_hash | 规范化输入和参数摘要；密钥不进入摘要内容或日志 |
| tool_versions | 实际工具与版本 |
| output_files | 文件清单；未运行为空数组 |
| checks | 检查项、结果、证据路径 |
| attempt、started_at、finished_at | 次数和实际时间；未发生为 null |
| error_code、recovery_action | 失败时填写；成功为 null |

只有条件满足且输出经过检查才可从 running 转为 passed；上游输入改变将下游设为 stale。豁免阶段可以 passed，但 checks 必须指向明确的豁免依据，不能伪装为执行成功。

## 5. 事实、素材与生成任务

### sources.json 与 claims.json

来源条目：`source_id`、`title`、`url_or_path`、`publisher`、`published_at`、`checked_at`、`version_or_scope`、`evidence_path`。只保存必要摘录与核验笔记，不整篇复制网页。

事实条目：`claim_id`、`statement`、`status`、`source_ids`、`test_evidence_paths`、`limitations`、`last_verified_at`。`status` 为 `verified_source / verified_test / opinion / unverified`；解释性判断写明判断依据。分镜通过 `claim_ids` 引用。

### assets.json

素材条目至少包括：`asset_id`、`kind`、`original_path`（导入来源）、`stored_path`（项目内只读副本，`assets/original/<asset_id>.<ext>`）、`work_path`、`bytes`、`sha256`、`duration_ms`、`width`、`height`、`fps`、`has_audio`、`origin`、`rights`、`privacy_checked`、`ai_generated`、`label_info`。

`origin` 为来源 URL、作者和导入时间；`rights` 为 `status`、授权证明、适用平台、是否允许商业使用、是否要求署名、到期时间。`rights.status` 为 `confirmed / unconfirmed / restricted`；仅 confirmed 或满足全部限制条件的 restricted 素材可入片。

自有录屏记录所有权声明，同时检查界面中第三方内容和个人信息。`ai_generated` 不替代权利与标识检查。背景音乐、字体和音效同样纳入素材表。

### index.json

片段条目：`clip_id`、`asset_id`、`source_in_ms`、`source_out_ms`、`action`、`screen_text`、`spoken_text`、`claim_ids`、`crop_hint`、`verified_by`。入点小于出点且不超过源文件长度；索引摘要需经候选片段抽查。

### jobs.json

记录 `job_id`、`provider`、`region`、`model`、`prompt_path`、`reference_asset_ids`、`request_hash`、`provider_task_id`、`state`、`reserved_cost`、`actual_cost`、`result_files`、`submitted_at`、`last_checked_at`。

任务状态为 `prepared / submitted / running / succeeded / failed / unknown`。submitted 后恢复先查询原任务；unknown 保留预算占用，不直接重新生成。远程结果保存本地并检查后才可为 succeeded。

## 6. 语音、字幕与画面合同

### speech.json

平台独立保存 `provider`、`model`、`voice_id`、`voice_settings`、`pronunciation_revision`、`segments`、`master_audio`。

每个自然语段包含：

- `segment_id`、`display_text`、`spoken_text`、`pronunciations`。
- `audio_path`、`sha256`、`duration_ms`、`global_start_ms`、`global_end_ms`。
- `timing_source`：`provider / asr_corrected / manual_verified`。
- `timing_granularity`：`sentence / word`，按实得粒度填写。
- `verified_pronunciation`、`provider_request_id` 和费用条目 ID。
- 可选 `display_replacements`（`[[朗读写法, 屏幕写法]]`，字幕里换回屏幕写法）与 `caption_breaks`（朗读文本中的短语列表，字幕在其后强制断行，防止按宽度硬切断词）。

音频未生成时路径和时长为 null。最终音轨的拼接停顿必须计入总长，不能把各语段口播时间相加当作整片时长。

### captions.json

根字段：`schema_version`、`variant`、`audio_sha256`、`timebase: ms`、`entries`。

每条为 `{id, segment_id, start_ms, end_ms, text, timing_source, verified}`。逐词数据另设可选 `words`；没有真实词时间戳时省略。所有 start 小于 end，字幕按时间排序，默认不相互重叠。

### shots.json

每个镜头包含：`shot_id`、`segment_ids`、`claim_ids`、`purpose`、`mode`、`scene_type`、`asset_ids`、`screen_text`、`source_crop`、`requires_demo_evidence`、`label_text`、`status`。

`mode` 为 `footage / remotion / generated_image / generated_video`。`source_crop` 使用 0～1 的标准化坐标 `{x,y,width,height}`；坐标和尺寸之和不得超出画面。初步分镜的意图不等于最终时间轴。

### timeline.json

平台根字段：`schema_version`、`variant`、`revision`、`width`、`height`、`fps`、`duration_ms`、`duration_frames`、`voice_audio_sha256`、`tracks`。每个平台各有时间轴，不能引用另一版的字幕时间戳。

轨道为 `visual / voice / music / sfx / caption / overlay`。每个片段含 `id`、`shot_id` 或 `segment_id`、`asset_id` 或 `scene_type`、`start_ms`、`end_ms`、`start_frame`、`end_frame`、`params`。

素材片段增加 `source_in_ms`、`source_out_ms`、`playback_rate`；画面不够长时使用明确的替代镜头、允许的定格或延展参数，不能越界读取素材。

时间规则：

1. 配音母轨是时间基准，声音与证据对齐。尾部留白必须显式记录。
2. 绝对边界按 `round(time_ms × fps / 1000)` 转为帧，同一边界复用同一结果；最终片长可按 `ceil(duration_ms × fps / 1000)` 补足最后一帧。
3. 主画面覆盖整条时间轴；允许重叠的仅为声明过的转场或叠加层，禁止无解释空洞。
4. 默认不启用重叠转场。启用时，重叠已反映在绝对起止时间内，渲染组件不能再次扣时长。
5. 变速素材消耗的源区间约为输出时间乘速度；配音默认不通过变速强行塞入画面。改变声音时长后重新生成对齐数据。

### 渲染、混音与封装记录

技能之间通过以下记录确认上下游对应关系，缺记录或校验值不符时下游拒绝执行：

- `<输出>.render.json`（remotion-render）：`input.timeline_sha256`、`input.voice_audio_sha256`（或封面的 `input.props_sha256`）、`input.backdrops`（按题材分配的底图：镜头与底图 id）、`settings`（编码参数、分辨率、帧数、`backdrop_theme`）、`output.sha256`、`output.bytes`、`tool_versions`、`rendered_at`。
- `actions.json`（remotion-render actions）：`timeline.sha256`、`fps`、`duration_frames`、`code_sha256`、`marks`（每个动作的 `shot_id`、全片 `frame`、`time_ms`、`kind`、`target`）。`kind` 取自 sfx-kit 的动作类型；排音效以 `frame` 为准，`time_ms` 只供阅读。目前只有文字动效 `KineticText` 导出动作，其他场景的动作仍按 `docs/EDITING_METHOD.md` 第 4.4 节人工标注。
- `audio/sfx.json`（av-export sfx，可选）：`inputs.actions.sha256`、`inputs.timeline_sha256`、`inputs.voice_sha256`、`library`（sfx-kit 配方版本、清单校验值、权利说明）、`level_db`（音效总线电平）、`placements`（每个音效的帧、采样点偏移、动作类型、音效 ID 与校验值）、`clipped_samples`、`output`（`sfx.wav` 校验值与采样点数，与母轨等长）。
- `audio/mix.json`（av-export mix）：`input.sha256`（须等于时间轴的 `voice_audio_sha256`）、`music`、`sfx`（`none`，或混入的 `sfx.wav` 校验值、`sfx.json` 校验值与电平）、`processing`（处理链、目标、处理前后响度、各次增益）、`output.sha256`、`source_aigc_labels`（各段原始配音的服务商 AIGC 隐式标识字段）、`tool_versions`。
- `exports/final-<版本>.mp4.export.json`（av-export mux）：`inputs.picture.sha256`、`inputs.timeline_sha256`、`inputs.mix.sha256`、`settings`、`output.sha256`、`voice_only`（无配乐时注明与成片相同）、`tool_versions`。

### jev-check.json：配音前语义提示

根字段：`schema_version`、`variant`、`question_set`、`model_alias`、`models`（接口返回的真实版本）、`model_warning`（版本与已校准版本不同时的提示，否则 null）、`checked_at`、`inputs`（`speech_sha256`、`brief_sha256`、`claims_sha256`）、`usage`（`requests`、`cache_hits`、`input_tokens`、`estimated_usd`、`price_source`）、`summary`、`results`。

每条结果为 `{check, where, verdict, message, detail}`。`check` 为 `hook_concrete / audience / exaggeration / support`；`verdict` 为 `passed / flagged / not_checked / skipped`；`detail` 保存 Noul 概率或 Choice 选项、置信度与各选项概率。结果只是提示，不决定阶段是否通过；`inputs` 中任一校验值与当前文件不符时视为过期，重跑。

### terms-check.json：平台敏感词检查

根字段：`platform`（词表平台键）、`terms_config`、`errors`、`warnings`、`screenshots`、`findings`。`screenshots` 每项为 `{path, status, lines}`，`status` 为 `passed`（已 OCR）/ `not_checked`（OCR 不可用或按 `--no-ocr` 跳过）/ `missing`（文件不存在）。`findings` 每项为 `{level, rule, where, message}`，`rule` 为 `terms.<词表类别>`、`terms.ocr_not_checked` 或 `terms.screenshot_missing`，`where` 指明语段、镜头参数、`publish.md#章节` 或截图路径。

`assets/ocr-cache.json` 以图片 SHA-256 为键，值为 `{engine, source_name, lines}`；图片内容或 OCR 引擎、语言变化时重新识别。

### doubao-review.json：豆包平台风险审核

根字段：`schema_version`、`prompt_version`、`variant`、`platform`、`model`、`checked_at`、`scopes`（`script` / `publish`）、`inputs`（`speech.json`、`script.md`、`cover.props.json`、`publish.md` 的 SHA-256，缺文件为 null）、`requests`（每项 `{scope, request_hash, cached, model, input_tokens, output_tokens, cost_cny}`）、`usage`（新请求数、缓存命中数、token、`cost_cny`、`price_source`）、`summaries`（各范围一句话总结）、`items`、`counts`（未放行的 `high / medium / low`，以及 `waived`、`quote_not_found`）、`blocked`。

每条 `items` 为 `{item_id, scope, location, quote, category, category_label, risk, reason, suggestion, quote_found, waived}`。`risk` 为 `high / medium / low`；`quote_found` 为原文核对结果；`waived` 为 null 或 `{reason, approved_by, approved_at}`。`blocked` 为是否存在未放行的 high。`inputs` 中任一校验值与当前文件不符时视为过期，重审。

`doubao-review.waivers.json`：`{"waivers": [{scope, location, quote, category, risk, reason, approved_by, approved_at}]}`，按「范围 + 类别 + 原文（忽略空白）」匹配条目。

## 7. 修改影响范围

| 变更 | 必须失效重算 | 可以保留 |
|---|---|---|
| 选题主张或关键事实变化 | 相关脚本及其全部下游 | 不受影响且仍有使用权的素材 |
| 改口播或读音 | 对应语段音频；该位置之后的时间偏移、字幕、镜头、混音与导出 | 未改语段音频与事实来源 |
| 换音色/语速 | 该平台所有声音及其下游 | 事实、可复用画面素材 |
| 换某张图或录屏裁切 | 对应镜头、渲染与视觉验收 | 文案、音频、时间戳；时长不变时保留时间轴 |
| 改镜头动作、变速、截短、延长或镜头起点 | 该镜头的动作标记与音效时间点、渲染、混音、导出与视觉验收；`actions.json` → `sfx.wav` → `mix.wav` 按校验值链依次失效，mix 与 mux 会拒绝旧轨 | 配音、字幕、其他镜头 |
| 换 BGM | 混音、输出、音频与完整解码检查 | 配音、字幕、视觉布局 |
| 改封面/发布文案 | 对应包装文件与内容核验 | 未受影响的成片 |

## 8. 费用、验收与交付

`ledger.json` 的条目（由 `video-project` 技能的 `cost add` 写入，`settlement_status` 为 `estimated / reserved / settled / unknown`）包含服务、请求 ID、计费单位、数量、币种、单价来源及核验日期、预估额、预留额、实际额和结算状态。预算检查使用「已结算实际额 + 未结算占用额 + 下次请求最大额」，同一个请求只占用一次；结算后释放对应预留额。

`qa/report.json` 每项包含 `check_id`、`variant`、`artifact_path`、`artifact_sha256`、`method`、`result: passed/failed/not_checked`、`blocking`、`scope`、`detail`、`evidence_path`、`checked_by`、`checked_at`。`scope` 为 `render`（自动技术检查，决定 `render_complete`）、`delivery`（视听、事实、权利、可复用等，决定 `delivery_ready`）或 `publish`（平台预览，决定 `ready_to_publish`）；`detail` 保存测量值或审阅说明。不同版本的检查结果不能移用于修改后的文件。

`delivery.json` 包含实际文件清单、`render_complete`、`delivery_ready`、`ready_to_publish` 三个独立状态、尚待检查事项、授权状态、成本摘要、AIGC 标识情况（`aigc`：显式标识、各段来源隐式标识数量、成片是否带隐式标识）和重渲染说明。三个状态只由 `qa/report.json` 中绑定当前成片校验值的检查结果推导。成片可在尚未获得发布授权时完成本地交付。

`observations.json` 每条包含平台、作品 ID、版本、时长、发布时间、观察时间、原始指标、指标定义、原始数据文件。每个派生比例保存分子、分母和公式，缺失字段为 null。
