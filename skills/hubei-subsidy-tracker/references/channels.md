# 官方数据源清单（阶段1 采集）

> 均为湖北省/武汉市官方发布渠道，已联网核对 2026 年在持续发文。解析策略利用"发布日期内嵌在 URL"的规律取日期 + 去重。

| 部门 | 级别 | 列表页 / 接口 | 类型 | 解析要点 |
|---|---|---|---|---|
| 经信厅 | 省 | `jxt.hubei.gov.cn/fbjd/zc/qtzdgkwj/gwfb/` | html | 链接含 `t20xxxxxx` 日期 |
| 经信局 | 市 | `jxj.wuhan.gov.cn/xwzx_9/tztg/` | html | 标题含"序号+日期+标题+摘要"，脚本已清洗 |
| 科技厅 | 省 | `kjt.hubei.gov.cn/kjdt/tzgg/` | html | 链接含日期 |
| 科创局 | 市 | `kjj.wuhan.gov.cn/wmfw/tzgg/tzgg_18371/` | html | 链接含日期 |
| 财政厅 | 省 | `czt.hubei.gov.cn/.../qtzdgkwj/qtzd.json` | json(ajax) | 列表页为 JS 渲染，直抓 `qtzd.json`（含标题/链接/PUBDATE），`seed_since` 取 2026-01-01 |
| 财政局 | 市 | `czj.wuhan.gov.cn/BMDT/TZGG/` | html | 链接含日期 |
| 人社厅 | 省 | `rst.hubei.gov.cn/bmdt/dtyw/tzgg/` | html | 链接含日期 |
| 人社局 | 市 | `rsj.wuhan.gov.cn/zwgk_17/zc/qtzdgkwj/zcfg/` | html | 仅"政策法规"入口，偏低频，可补"通知公告" |

## 改版监测
某源连续 2 天命中为 0 或骤降 → 报警 → 检查列表页结构 / URL 规律是否变化，更新 `fetch_subsidies.py` 中 `SOURCES` 或解析逻辑。

## 采集口径
只抓**申报类通知**（政府补贴/扶持/优惠政策的申报、征集、报名），结果公告类（公示/名单/通报/验收/立项等）前期不采集，由 `fetch_subsidies.py` 的 `RESULT_KWS`/`APPLY_KWS` 控制；后续需要结果公告时再放开。

## 可扩展源（用户可选）
东湖高新区、江岸区等区级奖补发布渠道；发改、商务、中小企业服务平台等。新增只需在 `SOURCES` 加一项（html 型直接加 url；json 型加 `type:"json"` 及字段映射）。
