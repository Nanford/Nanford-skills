# scripts 目录说明

图文扩展：`visual_assets.py` 检查图片来源、检查记录和哈希；`build_response_docx.py` 支持普通模块边框与 `panel-grid-start` 连续分隔线框、组图、原生图题表题及列宽；`text_gates.py` 将表题纳入正文检查，排除列宽等布局元数据；`final_gate.py` 与 `check_qingtian_final.py` 检查源图片、清单及 DOCX 内嵌图片构建后变化。工具发现与工程视觉判断仍由当前 Agent 执行，见 `references/visual-layout.md`。

`prepare_project.py` 和 `render_format_sample.py` 默认出框式格式样张；`--plain-sample` 改为无分块线框样张，保持原有字体、字号和格式锁规则。

`export_response_pdf.py` 在 DOCX 门禁放行后本机导出、清理、复核完整 PDF。`--reviewed` 记录逐页验收，`--check` 核对交付版哈希。图文清单中的必要配图作业由 `visual_assets.py` 核对完成情况，生成器核对实际小节。

本目录存放 `qingtian-bid` 的脚本。迁移来源和对应提交记在上一级 `CHANGELOG.md` 的《脚本来源》。运行依赖见上一级的 `requirements.txt`。

| 脚本 | 阶段 | 职责 |
|---|---|---|
| `check_env.py` | 开工前 | 环境自检，只读：查 Python 版本（下限 3.10 从代码推出，实测 3.13 和 3.14）、`requirements.txt` 里每个包的版本并真的导入一次、Word 或 WPS、Excel 或 WPS 表格（只查注册表，不启动程序）、PATH 上的 soffice、读图纸文字用的 ezdxf 和 ODA File Converter（可选，只找不运行）、UTF-8 模式；缺必需项时退出码 1，给出装到当前 Python 的命令和影响，可选项只提示；探测失败或控制台编码不对时不崩 |
| `docx_font_profiles.py` | 0、6 | 格式的唯一来源：读取 `templates/format-presets.json`；正文与一至三级标题分设字体和字号（四、五级跟三级），西文字体可选，行距支持倍数、固定值、最小值；中文字号名换算为磅；非法值直接拒绝；每个字段记录出处；按维度筛选预设 |
| `build_response_docx.py` | 6 | 把 Markdown 生成最终施组 DOCX。项目里只按确认锁定的格式出稿；只含图片的段落用单倍行距，防止固定值行距把图裁成窄条；关闭标题分页时文件之间不强制分页；暗标模式不生成页眉页脚；标题只靠样式定格式，Word 更新目录时条目不带标题字体；不带作者等文档属性并打开"保存时删除个人信息"，图片名称改成"图片N"（门禁 B5）；构建报告记下每个来源文件出稿时的 sha256，供阶段 6 核对 |
| `docx_effective_format.py` | 6、7 | 逐段核对实际生效的格式：按段落角色分级核对字体（中文槽、西文槽）、字号、加粗（双向）、斜体、行距；固定值行距下会被裁切的嵌入图；段落角色按样式名识别，经中文版 Word 另存后样式 ID 变成数字也能认 |
| `validate_docx_format.py` | 6、7（门禁 B3） | 校验施组 DOCX 与项目锁定的格式逐项一致：样式、页面、标题分页与编号、目录、页眉页脚页码、暗标、Markdown 残留；`--final` 拦截待补材料和目录、页码占位；项目格式未确认或待确认时判不通过 |
| `format_state.py` | 0、2 | 项目格式的状态层：读写 `project-state.json`（被短暂占用时稍等重试）；读取 `analysis/tender-format.json`；按 D7 把招标文件规定叠加到用户自己的选择上，出"所选 / 招标文件要求 / 最终采用"三列差异；"要求"不得偏离，"建议"须有用户同意记录才能偏离；招标文件的扣分句（`penalty`）列进差异、带进偏离的出处，规则卡评审注释写了扣分而格式规定漏登的报出来；暗标自动关闭页码；用户确认后锁定 `document_format` |
| `prepare_project.py` | 0 | 建项目目录、登记开工四问（含用户声明的图纸 `--drawing`）、把来源登记进 `sources`、按 `templates/公司资料/` 建 `公司资料/` 和四个子目录的说明并自动登记（相对路径），另给的公司资源路径登记进 `resources`（原地登记，不复制）、按所选格式出样张并登记为待确认；格式值非法时不建任何目录 |
| `extract_text.py` | 1 | 提取 PDF、DOCX、XLSX（标准库解析，单元格内换行压成空格）、TXT、MD 文本；老式 XLS 在临时副本上经 Excel / WPS 表格（其次 LibreOffice）另存为 xlsx 再提取；老式 DOC、XLS 两路都转不了时，报告里的失败原因附上 Office 那一路的报错（只留开头 300 字）；路径太长时写明原因；`--project` 按 `sources` 整批提取；DWG、DXF 图纸经 `dwg_text.py` 读文字；用户声明的图纸提取不到文字记为 `drawing`，原因写明缺什么，不触发 R9；报告记每个来源的 sha256 |
| `dwg_text.py` | 1 | 读 DWG、DXF 图纸上的文字（单行、多行、图框属性、引线、标注和表格），按模型空间、布局、块分段，没用上的块和属性模板不读。DXF 用 ezdxf 直接读；DWG 先复制到临时目录用 ODA File Converter 转成 DXF，读完就删。转换程序按环境变量 `QINGTIAN_ODA_CONVERTER`、PATH、默认安装位置找。缺工具或转换失败时抛出写明原因的异常，由 `extract_text.py` 按图纸放行 |
| `project_cards.py` | 2～4 | 卡片层：规则卡逐字段校验（项目名称与开工登记一字不差、只差连接号时点明，依据、出处、核对、青天启用情况和规则依据范围、工程类别取值、轨道规则（评标办法不在合肥四种之内的不硬停，判 T-AI、T-暗标 须有条款原文，决策 2A）、初步评审表、强制条款及其去处、招标指定条款的关键词须出自原文、答疑补遗更正候选须核对完、格式指针；带 `ref` 的字段交给 `rule_card_fields.py`）、生成 `rule-card.md` 和 `mandatory-checklist.md` 视图（工程类别一行写明哪几张类别知识卡尚未交付、哪些类别没有卡，评标办法不在四种之内时写明没有导则依据）；`scoped_clauses()` 按去处分出施组的和提交前清单的强制条款（决策 4c-4A），去商务文件、报价文件的现在并入提交前清单（`SCOPE_ROUTES`，临时方案，第 5 步替换）；各张卡共用的确认锁：确认时记下卡片 sha256、每行的内容指纹和依赖（`row_locks.py`），以及它依赖的输入指纹（提取文本、规则卡、事实卡、资源卡的逐行指纹，公司资源文件）；上游只有被依赖的行变了才失效，原因里写涉及哪几行；确认规则卡时存 `analysis/rule-card.confirmed.json`，返回和上一次确认相比的逐行差异；各张卡的文件路径常量；`find_project_dir()` 从成品等文件往上找项目目录 |
| `rule_card_rows.py` | 2～8 | 规则卡的行键和逐行比较（决策 D9）：列表行用现有编号，投标文件格式的小节另占一行，评审内容用序号（`review_items.3`），单值字段用字段名；只比内容，不比 `ref`、`source`、`candidates`、`hints` 和字段、行这一层的 `checked`，勾选框 `options` 里的 `checked` 是原文勾没勾，算内容；列出新旧值；核对下游行的 `cites`（没写算依赖全部，`[]` 才是不依赖，决策 D9-1A）。不导入卡片层，由 `project_cards.py` 导入 |
| `row_locks.py` | 3～5 | 按行失效（决策 D9）：矩阵行、事实行、资源行各依赖上游哪几行；上游只比内容，不比出处和 `cites`；上游变了挑出受影响的行；没写 `cites` 的行算依赖全部（决策 D9-1A）。只导入 `rule_card_rows.py`，由 `project_cards.py`、`writing_gate.py` 导入 |
| `fact_resource_cards.py` | 3 | 事实卡与资源卡：逐条校验（编号、类别、依据、出处、工程量、核对）；资源卡键白名单和长串数字拦截，不收姓名、证书编号（决策 3b-1A）；管理岗位、机械、劳动力必须指回编目文件，物资数量引用清单事实（决策 3b-2A）；某节为空须写缺口；生成 `project-facts.md`、`company-resources.md` 视图；两张卡每行可写 `cites`，按当前规则卡（资源行还有事实卡）核对；确认锁（事实卡依赖规则卡的行，资源卡依赖规则卡和事实卡的行，加公司资料）和阶段 3 完成条件 |
| `scaffold_rule_card.py` | 2 | 从提取文本出规则卡候选：建议值和原文片段都带"文件 第 N 页（提取文本第 M 行）"出处，全部 `checked: false`；项目名称按"项目名称："标签取（招标文件优先，各处写法列进候选，没有标签才退回封面标题）；青天启用情况按 AI 条款和评标办法给建议，规则依据范围按建设地点和资质给候选（决策 D11）；四种以外的评标办法按"评标办法采用××法"取，不给轨道建议（决策 2A）；工程类别只列线索（资质、招标范围原文，清单工作表名，清单编码对上各张已交付卡的行数），不填主类别（决策 5-2A）；强制条款候选含前附表 3.7.1 和第七章点名的重点难点、危大清单（整条摘出），答疑补遗的"原内容……现澄清更正为……"逐处摘进 `addenda_changes`；入围规则候选含中标候选人推荐规则；摘要单列评审注释的扣分句；已有规则卡时候选另存，不覆盖 |
| `tender_text.py` | 2、3 | 提取文本的索引：原始行、每行页码、去掉页眉页脚和页码的连续文本（只把页首、页尾的数字行当页码，正文里单独成行的数字留着）；`find_all()` 搜索，`ref_at()`、`ref_hit()` 生成 `{file, page, line, keyword}` 定位。只用标准库 |
| `rule_card_fields.py` | 2 | 规则卡里出处逐行写 `ref` 的字段（资格条款、勾选框、关键日期、表外致命项、定标规则、最高投标限价）：字段规则和逐行校验，`ref` 回到提取文本按行号查关键词，查不到就报错（决策 3A，老字段还是 `source`，v2.1 迁移）；`rule-card.md` 第六节的表。被 `project_cards.py` 导入，不能反过来 |
| `scaffold_rule_fields.py` | 2 | 上述字段的候选：读前附表勾选框（一组一行，投标文件格式一章里投标人填的不读）、四个关键日期（相对时限按投标截止倒推）、最高投标限价（按勾选框判）、项目画像给建议行；资格条款、表外致命项、定标规则只列候选，带现成的 `ref`；全部 `checked: false`。由 `scaffold_rule_card.py` 调用 |
| `material_list.py` | 2 | 规则卡确认后出 `analysis/资料清单.md`（`--confirm rule-card` 时自动出，也可单独运行）：向公司要什么、校验什么，每行写来自规则卡哪一行；报价文件的表合成一行。不含金额和个人信息，条款里的金额换成指向规则卡的记号。只读规则卡，不读公司资料 |
| `project_profile.py` | 2 | 项目画像（八项，每项一行）的校验，按规则卡算触发表，写 `rule-card.md` 第八节。只列命中和判不清的项，做法在对应步骤落地；政府采购、专门面向中小企业、节能产品、竞争性磋商命中时要有用户原话才能往下走。澄清窗口按当前时间算，视图每次生成都重算 |
| `scan_bid_forms.py` | 2 | 按标题找投标文件格式一章，不认第几章；按封面分商务、技术、报价文件，读目录、正文的节和小节，比出三种差异（正文多一节、目录多一节、编号不同）；草稿行 `kind` 留空，类型、字段名、附件只放 `hints`；保函里的条款、编号接不上的不算节。由 `scaffold_rule_card.py` 调用，也能单独跑（只读）；只有两份真实招标文件核对过 |
| `bid_forms_fields.py` | 2 | 上面两个字段的校验和 `rule-card.md` 第七节：找不到这一章、节从表里消失（重扫比对）、差异没有用户决定，都过不了；`字段值`要列字段，`无需提供`要写依据。被 `project_cards.py` 导入 |
| `scaffold_facts.py` | 3 | 从招标文件、读得出字的图纸和 xlsx / xls 工程量清单出事实卡候选：标签取值按连续文本取到下一条条款，跳过"见……"和合同空白处，不复制工期、质量标准、安全目标；清单分项每张类别知识卡保底 8 条（决策 5-5A），总数最多 150 条，对不上卡的行也在内，按 6 位编码轮流取、同组工程量大的在前，同名只取一次；规则卡还没定工程类别时不取；没进候选的和带编码却认不出单位的行列在 `analysis/清单未进候选.md`；工程量后面的单价、合价不读；补遗、答疑里含禁止类词（严禁、不允许、不具备、禁止）或现场条件词（紧邻、夜间、深基坑、二次搬运、围挡等）的整句作场地与周边候选（最多 20 条）；全部 `checked: false`；清单分项预填 `cites: []`；已有事实卡时候选另存，不覆盖 |
| `index_materials.py` | 3 | 编目项目登记的公司资源资料（相对路径按项目目录解析，编目路径重复时报错）：按编目路径分四类（文件名以"证"结尾的不看目录，一律按人员类），记 sha256；非人员类文件提取文字供核对，人员类不落盘，`--show` 临时查看；没有资源卡时出骨架并按缺类别预填缺口。不按文件数判资料空壳，资源卡逐条指回编目文件 |
| `category_cards.py` | 2～5 | 类别知识卡（`references/category-cards/`）：13 张卡的名录（导则 9 类作主类别，另有 3 个专业、1 个场景，决策 5-3A）；逐张校验卡片结构、"推断"标注和规范的核验标注（决策 5-6A）；规则卡 `project_category` 的取值校验（主类别和涉及专业不限名录，决策 D11）；按规则卡选卡，没交付的卡列为尚未交付，名录外的类别 `no_card_names()` 列出；按评审内容标题对应评审方面，标题含重点、难点的一项不给卡片要点；矩阵控制点预填和 W9 比对（每项最多一条提示，决策 5-4A；只比矩阵里还留着的要点，第 6b 步改）；清单行按编码前缀和名称关键词归卡（字母前缀、`01B001` 补充项只比数字）；`--write` 重出 Markdown 视图。只用标准库，供 `project_cards` 导入 |
| `scaffold_matrix.py` | 4 | 从确认过的规则卡和资源卡出响应矩阵骨架：一项评审内容一行，标题照抄原文；按标题关键词预填资源、按条款关键词预填★落点（只预填去处为施组的条款；招标指定的落在标题含重点、难点的那一项）、预填实施进度组织的落点；按规则卡选的类别知识卡预填控制点（标题含重点、难点的不预填，决策 5-4A；与事实卡现场限制矛盾的改写为"现场不设……，写明场外解决方式"，卡片原文附后，输出 `site_limits`，第 6b 步）；每行预填 `cites`（评审内容这一行和落在本项的条款）；按示范文本默认页数的比例在篇幅上限内分页数（示范文本以外的标题按 3 页计权，0.5 页为单位，每项至少 0.5 页，零头按最大余数分，不全堆给一项）；评审内容未规定（T-合格）时硬停；已有矩阵时候选另存，不覆盖 |
| `response_matrix.py` | 4（命名和篇幅估算供 5、7 用） | 响应矩阵：与规则卡评审内容逐项对应（原文、顺序、项数）、要点必填、引用的事实资源条款必须存在、事实少于 2 条须写原因（W1）、去处为施组的★全部有落点且去处为提交前清单的不得写成落点（R5、决策 4c-4A）、页数 0.5 页为单位且合计不超上限、实施进度组织落点与分布依据（R13）、`cites` 只收规则卡的行键；生成 `response-matrix.md` 大纲视图（第五节列每项的类别知识卡必备要点和参考、未交付的卡）；确认时锁定每行依赖的规则行、事实和资源；阶段 4 完成条件；中间稿命名 `实施方案/NN-<评审内容原文>.md` 和一级标题；按锁定格式估算一页字数【推断】；写作闸和稿件门禁共用的输入 `writing_inputs()`、`matrix_items()` |
| `writing_gate.py` | 5 | 逐项写作闸：资源卡有缺口时整个阶段 5 不能开始、不能确认（R8）；按顺序一项一确认，后面的项不得提前写（R12）；结构自查（文件、一级标题原文、只有一个一级标题）附字数和预算字数，再跑本项的稿件门禁，阻断项挡确认；确认时锁定中间稿和本项在矩阵里那一行及其依赖的规则行、事实和资源（决策 3c-2A、D9）；阶段 5 开始和完成条件 |
| `check_qingtian_gates.py` | 5、7（第 4a 步） | 稿件门禁编排：对一项或全稿跑内容门禁，B 级阻断、W 级只提示到阶段 7（决策 4a-2A），B5 暗标阻断、其他轨道提示；W9 按规则卡选的类别知识卡比对必备要点（每项最多一条）；W10 按事实卡的现场限制比对（第 6b 步）；命中编号为门禁、项号、命中内容的哈希；B4、B5、B7、B13 的误报和 W 的不改理由须用户说明后用 `--dismiss` 记进 `review/gate-notes.json`，锁定当时中间稿的 sha256，不存命中原文（决策 4a-1A）；`--check-item` 和 `--confirm-item` 经 `writing_gate.py` 调它；整份检查 `full_run()` 和理由文件的读写由阶段 7 共用 |
| `text_gates.py` | 5、7（第 4a 步） | 正文层门禁：B5 正文部分（用户提供的身份词清单，电话、长串数字、邮箱，"岗位＋姓名"；决策 4a-3A）、B7（卡片里没有的地名、项目名、单位名，本公司名称归 B5）、B8（条款号、写作过程用语、Markdown/HTML 残留，残留判定用 `build_response_docx.detect_markdown_leaks`）、B13（报价用语和金额，表格也查；形式评审"未出现投标报价"）、W2、W3、W4（只在本机比对）、W7、W10（正文要设现场限制禁止的设施，同一句没写不设或场外解决；第 6b 步）；成品可见文字和正文段落的抽取 |
| `site_limits.py` | 4、5、7 | 现场限制：从确认过的事实卡认出禁止设的现场设施（材料堆场、加工区、办公区、生活区、室外堆放点；禁止词须在同一分句、设施叫法之前，"办公区由发包人提供，严禁吸烟"不算），判断一句话是否照写了这些设施却没写不设、场外、租用；矩阵骨架（改写控制点）和 W10（比对正文）共用这一张表。设施和叫法是【推断】，只覆盖两个真实项目补疑、答疑禁止过的，新招标文件禁止别的就加一行。只用标准库 |
| `consistency_gates.py` | 5、7（第 4a 步） | 比对层门禁：B1（逐项标题和全稿齐全、顺序、多余文件）、B4（工期、开工竣工日期、资源卡人数台数和物资数量；有卡片参照值时照卡，没有才各项互比；表格不比）、B9（落在本项的★条款写出原文的值、登记的关键词逐个写到，招标指定的只查关键词；整份去处为施组的每条都有落点；无值也无关键词的列为人工核对）、B10（资源卡以外的岗位、机械、工种带数字）、B11、W1；同一处文字只归一个门禁 |
| `check_content_quality.py` | 5、7（第 4a 步，W6） | 文风门禁：碎片清单、引导词堆砌、括号编号连续起段、单段多重括号，另加正文表格化（只许机械、劳动力、物资计划表等）；去掉命令行 |
| `project_status.py` | 1～8 | 阶段状态闸：阶段 0 只能由格式确认完成；不许跳阶段；阶段 1～8 按完成条件核对（阶段 6、7 的条件在 `final_gate.py`，阶段 8 的在 `submission_checklist.py`），阶段 5 另有开始条件（R8）；`--add-source` 登记补遗并重开阶段 1 起已完成的阶段；`--add-resource` 补登公司资源并重开阶段 3 起已完成的阶段；`--check`、`--confirm` 规则卡、事实卡、资源卡、响应矩阵；`--check-item`（结构加稿件门禁，列出提示、已说明的理由、人工核对项和 `--dismiss` 命令）、`--confirm-item` 逐项中间稿；`--confirm-b12` 逐行确认初步评审对照；`--tick` 勾选提交前清单一条，`--not-applicable` 配 `--reason` 记不适用；概览显示成品门禁、初步评审对照、提交前清单的进度和模拟自评的一行，以及登记处现有的资料文件数，一个都没有且阶段 3 未完成时提醒往 `公司资料/` 里放 |
| `office_bridge.py` | 0、1、7 | Word/WPS 自动化：把格式样张导出 PDF；按 COM 注册表找到实际启动的程序并去重（本机 `Word.Application` 启动的可能是 WPS）；在临时副本上读总页数和各一级标题所在页与行位置，只读不存；副本导出 PDF 兜底；在临时副本上用 Excel / WPS 表格把老式 xls 另存为 xlsx（禁用宏，不更新外部链接） |
| `report_page_numbers.py` | 7（门禁 B2、W5） | 成品计页：Word 和 WPS 都在时两边都计，按较大页数判 B2 并记下差异（决策 4b-1A）；篇幅上限"要求"和"建议"超了都阻断，招标文件没规定上限时不适用；各项页数按标题位置算，精确到行，只能按整页时 W5 放宽 1 页；自动计页失败后才收 `--pdf` 或 `--manual-pages`；结果写 `review/page-count.json`，锁定成品 sha256，不存标题原文；`record_gate()` 按存下的计页重判，阶段 7 复用同一份成品的计页 |
| `check_qingtian_final.py` | 7（第 4b-2 步） | 阶段 7 门禁编排（决策 A）：一次跑完整份中间稿门禁、B3（当前成品上的 `--final` 校验）、成品一级标题的 B1、B2/W5（同一份成品已有的计页直接复用，人工和 PDF 页数不会被覆盖）、成品扫描 B6/B5/W8、`output/` 下遗留的清属性备份、B12（与施组有关、未确认的每行一条）；成品上的误报和不改理由 `--dismiss` 记进 `review/final-gate-notes.json`，锁定成品 sha256，与中间稿的理由分开存；写 `review/gate-report.json/.md`，只记门禁、编号、位置和状态，不存命中原文 |
| `rehearsal.py` | 5、7（第 1c 步） | 类人评审预演的记录和状态：校验并存 `review/rehearsal/NN.json`、`final.json`（拒绝分数和档次判断、超过 200 字的条目、多余字段），锁定稿件 sha256，稿件一改显示要重做；给 `--check-item` 和 `check_qingtian_final.py` 提供一行状态。不是门禁，不影响确认、退出码、`ready` 和任何阶段的完成条件。预演本身按 `references/rehearsal.md` 做 |
| `self_score.py` | 7 之后（可选） | 模拟青天的自评（2026-11-09 用户定 1A、2A、3A、4A）：`--init-standard` 按规则卡的档次原文和招标文件出 `review/自评/评分标准.json` 候选（示范文本结构：施工组织设计一个评审因素整体打分；不覆盖已有的），`--check-standard` 校验分值、档次（区间连续、从 0 连到分值）或固定分值、分值和评分标准的 ref 回查、每项评审内容只归一个评审因素；`--packet` 只在阶段 7 完成、门禁报告就是当前成品时出评审材料（评分标准原文加成品按一级标题分节的正文）和空评分表；`--record` 核对独立评审人（新会话或子代理）填的评分表：每项都评、档次和分数对得上、60% 及以下或 90% 及以上（固定分值是满分和 0 分）写充足理由、未提供的 0 分、出处逐字摘自本项章节、没给满分写失分点和怎么改、不预测入围中标、不收多余字段，总分由脚本算，存 `自评记录.json` 和 `自评报告.md`，锁定成品和评分标准的 sha256；成品、评分标准一改或阶段 7 重开，分数作废。给进度摘要一行。不是门禁，不进任何阶段的完成条件。做法见 `references/self-score.md` |
| `final_gate.py` | 6、7（第 4b-2 步） | 阶段 6、7 的状态层：阶段 6 要求成品在固定路径、由确认过的那版中间稿按矩阵顺序和锁定格式出稿、版式校验无阻断；阶段 7 要求当前成品没有未放行的阻断和未处理的提示、B12 每行已确认、门禁报告是这次放行的结果；`confirm_b12()` 锁定成品的 sha256 和初步评审表这一行（决策 D9），B3、B4、B9 有阻断时拒绝（决策 4b-3A）；概览一行；`stage7_issues()`、`report_issues()` 供阶段 8 复核 |
| `submission_checklist.py` | 8（第 4c-1 步） | 提交前清单的状态层：按 `templates/submission-checklist.json`、规则卡（初步评审表中与施组无关的行、去处为提交前清单的强制条款、工期质量标准和入围规则原文）和轨道现算清单，不存可手改的清单（决策 4c-1A）；勾选锁定条目内容，S01/S02 另锁成品 sha256 且要求门禁报告是当前成品放行后的结果（决策 4c-2A）；只有按需触发的条目可记不适用，理由是用户原话（决策 4c-3A）；自动核对 `output/` 下只许一份施组，多出的文件名只显示不落盘；阶段 8 完成条件（阶段 7 仍成立）；写 `review/submission-checklist.md` 视图，有未处理条目时退出码为 1 |
| `scan_docx_hygiene.py` | 7（门禁 B6、B5、W8） | 成品扫描：B6 隐藏、同底色、极小或压扁的文字，批注、修订、文档变量，嵌入和外部内容、拉取外部内容的域，面向评审系统的指令性文字（含图片替代文字），不能说明理由放行；B5 查成品上中间稿管不到的地方（文档属性、作者域、封面目录、文本框、脚注尾注、页眉页脚、图片名称和替代文字、超链接、图表数据、文件名），暗标时页眉页脚归 B3；W8 按成品各处文字实际生效的字体查评审端可能没有的字体；`--clean-properties` 先备份，只改 docProps |
| `render_format_sample.py` | 0、2 | 列出和筛选格式预设；生成一页格式样张（DOCX，可导出 PDF）和格式确认卡；`--project` 时在项目里出样并登记待确认变更，`--tender-format` 按招标文件覆盖（规则卡评审注释写了扣分而格式规定没登记 `penalty` 的拒绝），`--confirm` 在用户明确同意后锁定 |

## 常用命令

```powershell
# 开工前的环境自检（只读），缺必需项时退出码为 1
python -X utf8 "<skill目录>/scripts/check_env.py"

# 列出预设，可按字段筛选（字段名可写英文键或中文名）
python -X utf8 "<skill目录>/scripts/render_format_sample.py" --list-presets --filter 行距方式=固定值

# 按预设生成样张，可改个别字段；不装 Word/WPS 时加 --no-pdf
python -X utf8 "<skill目录>/scripts/render_format_sample.py" --output-dir <目录> --preset F2 --set 西文和数字字体="Times New Roman"

# 一次生成全部预设的样张
python -X utf8 "<skill目录>/scripts/render_format_sample.py" --output-dir <目录> --all-presets

# 阶段 0：建项目并出开工格式样张（细则见 references/stage-0-init.md）
python -X utf8 "<skill目录>/scripts/prepare_project.py" --root <工作区> --project-name "<项目名称>" --tender <招标文件> --format-preset F2

# 用户明确同意样张后锁定格式
python -X utf8 "<skill目录>/scripts/render_format_sample.py" --project <项目目录> --confirm

# 阶段 2：按招标文件覆盖格式，出三列差异和新样张（细则见 references/stage-6-assembly.md）
python -X utf8 "<skill目录>/scripts/render_format_sample.py" --project <项目目录> --tender-format <项目目录>/analysis/tender-format.json

# 阶段 1：提取（细则见 references/stage-1-extract.md）；每个阶段开始时都可先 --start <N> 记为进行中（前面的阶段须已完成）
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --start 1
python -X utf8 "<skill目录>/scripts/extract_text.py" --project <项目目录>
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --complete 1
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --add-source <补遗> [--kind tender|drawing|sample]

# 阶段 2：规则卡候选、校验、用户同意后确认（细则见 references/stage-2-analysis.md）
python -X utf8 "<skill目录>/scripts/scaffold_rule_card.py" <项目目录>
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --check rule-card
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --confirm rule-card
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --complete 2

# 阶段 3：事实卡候选、公司资源编目、两张卡校验与确认（细则见 references/stage-3-facts-resources.md）
python -X utf8 "<skill目录>/scripts/scaffold_facts.py" <项目目录>
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --check fact-card
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --confirm fact-card
python -X utf8 "<skill目录>/scripts/index_materials.py" --project <项目目录> [--show "<编目路径>"]
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --check resource-card
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --confirm resource-card
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --add-resource <补充的公司资料>
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --complete 3

# 阶段 4：响应矩阵骨架、校验、用户同意后确认大纲（细则见 references/stage-4-matrix.md）
python -X utf8 "<skill目录>/scripts/scaffold_matrix.py" <项目目录>
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --check response-matrix
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --confirm response-matrix
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --complete 4

# 阶段 5：逐项撰写，一项一自查一确认（细则见 references/stage-5-writing.md）
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --start 5
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --check-item <N>
python -X utf8 "<skill目录>/scripts/rehearsal.py" <项目目录> --item <N> --record <记录.json>
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --confirm-item <N>
python -X utf8 "<skill目录>/scripts/check_qingtian_gates.py" <项目目录> [--item <N>]
python -X utf8 "<skill目录>/scripts/check_qingtian_gates.py" <项目目录> --item <N> --dismiss <编号> --reason "<用户说明的理由>"
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --complete 5

# 阶段 6：出稿与校验；Word 更新目录和页码后加 --final 复验
python -X utf8 "<skill目录>/scripts/build_response_docx.py" --manifest <项目目录>/output/manifest.json --output <项目目录>/output/施工组织设计.docx
python -X utf8 "<skill目录>/scripts/validate_docx_format.py" <项目目录>/output/施工组织设计.docx [--final]

python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --complete 6

# 阶段 7：Word 保存 → 清属性 → 门禁（细则见 references/stage-7-gates.md）
python -X utf8 "<skill目录>/scripts/scan_docx_hygiene.py" <项目目录>/output/施工组织设计.docx --clean-properties
python -X utf8 "<skill目录>/scripts/check_qingtian_final.py" <项目目录> [--office auto|word|wps]
python -X utf8 "<skill目录>/scripts/check_qingtian_final.py" <项目目录> --dismiss <编号> --reason "<用户说明的理由>"
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --confirm-b12 <行号>
python -X utf8 "<skill目录>/scripts/rehearsal.py" <项目目录> --final --record <记录.json>
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --complete 7

# 阶段 8：提交前清单（细则见 references/stage-8-submission.md）
python -X utf8 "<skill目录>/scripts/submission_checklist.py" <项目目录>
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --tick <编号>
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --not-applicable <编号> --reason "<用户说明的理由>"
python -X utf8 "<skill目录>/scripts/project_status.py" <项目目录> --complete 8

# 阶段 7 之后（可选）：模拟自评，模拟，不是青天的评分（细则见 references/self-score.md）
python -X utf8 "<skill目录>/scripts/self_score.py" <项目目录> --init-standard
python -X utf8 "<skill目录>/scripts/self_score.py" <项目目录> --check-standard
python -X utf8 "<skill目录>/scripts/self_score.py" <项目目录> --packet
python -X utf8 "<skill目录>/scripts/self_score.py" <项目目录> --record <评分表.json>
python -X utf8 "<skill目录>/scripts/self_score.py" <项目目录>

# 类别知识卡：改 JSON 后校验并重出视图（说明见 references/category-cards/DIRECTORY.md）
python -X utf8 "<skill目录>/scripts/category_cards.py" --write

# 单独查看成品扫描或计页
python -X utf8 "<skill目录>/scripts/scan_docx_hygiene.py" <项目目录>/output/施工组织设计.docx
python -X utf8 "<skill目录>/scripts/report_page_numbers.py" --probe
python -X utf8 "<skill目录>/scripts/report_page_numbers.py" <项目目录>/output/施工组织设计.docx [--office auto|word|wps]
python -X utf8 "<skill目录>/scripts/report_page_numbers.py" <成品> --pdf <PDF> | --manual-pages <页数> --reason "<怎么数的>"
```

## 测试

回归测试不随 Skill 分发，在开发仓库的 `tests/` 下：`tests/test_qingtian_format.py`（格式层与生成器）、`tests/test_qingtian_validate.py`（格式校验）、`tests/test_qingtian_kickoff.py`（开工、确认锁定、招标文件覆盖）、`tests/test_qingtian_analysis.py`（提取、规则卡、阶段状态闸）、`tests/test_qingtian_cards.py`（事实卡、资源编目、资源卡、阶段 3）、`tests/test_qingtian_matrix.py`（响应矩阵、大纲确认、逐项写作闸、阶段 4/5）、`tests/test_qingtian_gates.py`（稿件门禁）、`tests/test_qingtian_final.py`（成品扫描与计页；真机计页设 `QINGTIAN_OFFICE_TESTS=1` 才跑）、`tests/test_qingtian_stage7.py`（阶段 6/7 完成条件、阶段 7 门禁编排、B12、门禁报告）、`tests/test_qingtian_submission.py`（提交前清单、阶段 8）、`tests/test_qingtian_category.py`（类别知识卡）、`tests/test_qingtian_smoke.py`（命令行端到端冒烟：各说明文档里的命令与脚本参数一致，一个虚构项目只用文档里的命令从阶段 0 走到阶段 8）。测试经 `tests/qingtian_loader.py` 加载本目录。
