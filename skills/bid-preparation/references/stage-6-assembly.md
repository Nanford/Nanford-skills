# 阶段6细则：生成导航表并组装成品DOCX

> 配套阅读：`references/response-file-format.md`（组装顺序与三张导航表规范）、`references/document-checklist.md`（文件清单）。
> 范围裁剪：仅技术部分（technical-only）时跳过 6.1 三张导航表（用户要求时可单出评标导航表的技术评分行），6.2 组装顺序简化为 `封面 → 目录 → 技术文件`，其余生成与校验步骤不变。
>
> **P1 递交方式**：
> - `paper`：标准组装 DOCX + 装订密封检查  
> - `electronic`：仍可组装内容 DOCX 供审阅；**递交以平台加密包为准**，必须完成 `e-bid-delivery-checklist.md`；模块化上传时按平台模块拆文件，勿假设只有一个 docx  
> - `hybrid`：内容一致前提下同时满足纸质与平台清单  
> - `simplified`：通常**不强制三张导航表**，以 format-clone 官方短目录为准
>
> **🚩 P3 定标方式（`award_mode`）——组装阶段最易静默做错的一项**：
> - `standard`：按下述流程组装**一本** `投标响应文件.docx`
> - `evaluation_separated`（**评定分离**）：**必须组装两本**，见 6.0

## 6.0 评定分离：双分册组装（`award_mode = evaluation_separated`）

招标文件原文口径：投标文件**由评标部分及定标部分组成，各部分应分别编制**；
定标部分在评标阶段**加密、不对评标委员会公开**，上传时**不得传入评标部分文件夹**。

因此本阶段产出**两份独立成品**，各自有独立封面、独立目录、独立页码：

| # | 成品 | 内容来源 | 平台上传位置 |
|---|---|---|---|
| 1 | `投标文件（评标部分）.docx` | 资格/形式/响应性材料、技术标、报价 | 评标部分文件夹 |
| 2 | `投标文件（定标部分）.docx` | 资信因素、团队因素、方案因素资料 | **定标部分文件夹** |

操作方式：**分别准备两份清单（manifest），各跑一次 `build_response_docx.py`**，
再各跑一次 `validate_docx_format.py` 与 `report_page_numbers.py`。命名必须含
「评标部分」「定标部分」字样——`check_p0_gates.py` 依此判定是否漏做（缺一即 blocker）。

组装后逐项核对 `analysis/award-separation-plan.md` 第二节：两本互不串内容、
上传文件夹对应正确、备用光盘按招标文件分张刻录密封。细则见
`references/award-separation-defense.md`。

## 6.1 生成三张导航表（放在成品最前面）

用 `templates/` 下模板生成，这是评标专家友好设计，也是最终自查工具：

- **资格审查导航表**：序号 / 投标人资格要求（原文照抄）/ 须提供的资料 / 投标文件对应页码
- **符合性审查导航表**：序号 / 审核内容（原文照抄）/ 须查验的资料 / 投标文件对应页码
- **评标导航表**：评标项目 / 评标分项 / 分值 / 编列内容（评分标准原文照抄）/ 自查情况 / 投标文件对应页码，表尾注明"请与第三章评标办法详细评审表保持一致"

**页码回填规则**：Markdown 阶段页码列填占位符 `P__`，同时标注章节位置（如"一、商务文件（十）"）。最终 DOCX 定稿分页后按 6.5 的对照表回填——交付前必做项。

## 6.2 组装顺序

```
封面（项目名称、招标编号、标包号、投标人名称、日期）
→ 资格审查导航表 → 符合性审查导航表 → 评标导航表
→ 目录（Word/WPS TOC域，定稿后更新域生成页码）
→ 一、商务文件（十二件套顺序）
→ 二、技术文件（技术描述 + 各服务/技术方案）
```

页眉：`<项目全称>投标文件`；页脚居中页码域，全文连续。

## 6.3 排版标记（写入 Markdown，组装时生效）

| 标记 | 位置 | 作用 |
|---|---|---|
| `<!-- cover -->` | 封面文件首行 | 整页居中排版，信息行三号，"投标文件"四字小初加粗 |
| `<!-- toc -->` | 目录文件 | 插入"目　录"标题 + TOC 域（Word/WPS 更新后生成页码） |
| `<!-- notoc -->` | 导航表标题前一行 | 标题居中加粗但不进目录（三张导航表用） |
| `<!-- break-all-headings -->` | 商务文件首行 | 该文件每一章节/小节独立起页（紧跟父标题的除外） |
| `<!-- pagebreak -->` | 任意位置 | 强制下一个内容块另起一页 |

默认分页规则：每个源文件另起一页；一/二级标题自动独立起页；紧跟父级标题的子标题与父级同页（样本："一、商务文件"+"（一）投标函"同页）。技术方案正文（三/四级以下）连排不分页。

## 6.4 DOCX 版式规则（构建脚本自动执行，校验脚本把关）

- A4 纵向；全文宋体；正文小四、黑色、1.5倍行距、首行缩进2字符
- 一级标题为宋体四号加粗黑色；二至五级标题为宋体小四加粗黑色；标题均顶格、1.5倍行距、段前13磅、段后8磅
- **说明性/待补文字自动渲染为五号红色斜体**：整行的"（此处附：XXX）"、"【图片待补充：…】"、"【说明：…】"等占位说明，交付前必须逐条替换或确认留空
- **标题编号直接写在标题文本里**（一、 / （一） / 1. / 1.1），不叠加 Word/WPS 自动编号（会出现"1. （一）投标函"式重复编号）；目录由 TOC 域按标题样式生成
- 深于五级的小节题（如 1.3.1.1.1）用整行加粗 `**1.3.1.1.1 标题**`，不占标题层级
- 图片（证照扫描件）用 `![说明](路径)` 插入，自动居中缩放；文件缺失时输出【图片待补充】占位并记入构建报告 warnings
- 编辑 `.docx` 前先备份或另存新版本；遇 `~$` 锁文件或 `PermissionError` 时另存副本
- 中文字体需同时设置 `run.font.name` 和 `w:eastAsia`；删除表格填充需移除 `w:shd` 节点
- **兼容 WPS Office**：成稿为标准 DOCX，WPS 文字可直接打开；页码脚本优先 COM（`--office wps` 可强制仅用 WPS）；目录在 WPS 中右键「更新域」或 Ctrl+A 后 F9
- 未经 Word/WPS/LibreOffice 真实打开或导出检查，不得声称"版式已验证"

## 6.5 生成与校验

先在 `output/assembly-manifest.json` 写组装清单（相对路径基于清单所在目录）：

```json
{
  "header": "<项目全称>投标文件",
  "files": ["00-封面.md", "商务文件/00-资格审查导航表.md", "……按组装顺序列全"]
}
```

```powershell
# Windows PowerShell
python -X utf8 <scripts>\build_response_docx.py `
  --output "bid-projects\<项目>\output\投标响应文件.docx" `
  --manifest "bid-projects\<项目>\output\assembly-manifest.json"

python -X utf8 <scripts>\validate_docx_format.py `
  "bid-projects\<项目>\output\投标响应文件.docx"
```

```bash
# macOS / Linux
python3 -X utf8 <scripts>/build_response_docx.py \
  --output "bid-projects/<项目>/output/投标响应文件.docx" \
  --manifest "bid-projects/<项目>/output/assembly-manifest.json"

python3 -X utf8 <scripts>/validate_docx_format.py \
  "bid-projects/<项目>/output/投标响应文件.docx"
```

（也可不用清单，直接按顺序列出 Markdown 文件并加 `--header`。）

构建结果（源文件清单 + 图片待补等警告）自动写入 `投标响应文件.build-report.json`，阶段7门禁会把警告汇总进"人工核查清单"。分析笔记、缺口清单、写作过程说明**不得**进入最终 DOCX。**格式校验失败是阻断项。**

## 6.6 页码对照表（导航表页码回填半自动化）

DOCX 内容定稿后运行：

```powershell
python -X utf8 <scripts>\report_page_numbers.py "bid-projects\<项目>\output\投标响应文件.docx"
# 仅安装了 WPS 时建议：
python -X utf8 <scripts>\report_page_numbers.py "bid-projects\<项目>\output\投标响应文件.docx" --office wps
# 探测本机 Word/WPS COM 是否可用：
python -X utf8 <scripts>\report_page_numbers.py --probe
```

本机有 **Microsoft Word 或 WPS 文字** 时：自动更新目录域并保存（原文件留 `.bak` 备份），逐个读取标题真实页码，输出 `投标响应文件.page-map.md`。按对照表回填三张导航表的 `P__`，回填后在 **Word 或 WPS** 中抽查 3-5 条。

WPS 操作提示：打开 DOCX → 点击目录区域 → 右键「更新域」→ 全页更新；页脚页码域同理。导出 PDF：文件 → 输出为 PDF。

没有 Word/WPS 时降级为 LibreOffice 或 `--pdf` 手动导出 + 文本匹配（精度略低，必须逐条抽查）。

## 完成标志

成品 DOCX 生成、格式校验通过、页码对照表已出。更新状态：

```powershell
python -X utf8 <scripts>\project_status.py "bid-projects\<项目>" --complete 6
```
