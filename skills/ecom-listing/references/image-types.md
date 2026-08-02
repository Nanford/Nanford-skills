# 图型体系与出图工单规范

## 为什么底图和文字要分开

图像模型渲染图片内文字时会出现拼写错误、断词错误、字重不统一，德语复合词和日语混排尤其明显。更现实的问题是成本：文字烧进图里，出十个语言版本就要出十次图。

分层之后，底图出一次，文字层按语言重排即可。文字用真实字体渲染，零拼写错误，用户还能直接改。所以所有底图提示词都必须显式声明不要文字、不要 logo、不要水印。

## 八种图型

**main 合规主图** — 纯白底，产品居中，占画面 85% 以上，无任何文字。不走创意生成，只做抠图加白底合成。这是唯一有硬性合规红线的图型。

**scene 场景图** — 产品置于真实使用环境中，建立使用想象。文字通常不加或只加一句场景短语。

**feature 功能卖点图** — 主推卖点的图解，产品占一侧，另一侧留出文字区。这是文字层最重要的图型，通常放一个大标题加一句支撑说明。

**detail 细节特写图** — 材质、工艺、接口、缝线的近距离展示，配短标签文字。

**size 尺寸标注图** — 产品配尺寸线与数值，或与常见参照物对比。数值必须来自已确认属性，待确认的尺寸不能上图。

**comparison 对比图** — 使用前后或与传统方案对比。注意避免贬低竞品或暗示不可验证的性能提升，Temu 和 Amazon 对这类图审核都较敏感。

**package 包装配件图** — 开箱内容物平铺展示，配件逐一标注。

**model 模特使用图** — 人物使用或穿戴场景，服饰类目必备。涉及真人形象时提醒用户注意肖像与合规风险。

## 默认套图组合

| 类目 | 默认组合 |
|------|---------|
| 3c-accessory | main, feature×2, detail, size, package, scene |
| apparel | main, model×2, detail×2, size, scene |
| home | main, scene×2, size, detail, package, feature |
| kitchen | main, scene, feature×2, detail, size, package |
| outdoor | main, scene×2, feature, detail, size, package |
| 其他 | main, scene, feature×2, detail, size, package |

用户可自定义每种图型的数量。总张数按站点上限约束，Amazon 通常 7 到 9 张，eBay 可以更多。

## 文字图层规范

每个 text_layer 包含以下字段：

`text` 实际文案，来自 listing.json 的卖点短标题，已按目标语言本地化。

`role` 取值 headline（主标题）、subline（支撑说明）、tag（细节标签）、spec（规格数值）。不同 role 对应不同字号区间。

`anchor` 取值 top-left、top-center、top-right、bottom-left、bottom-center、bottom-right、left-center、right-center。决定文字块的定位基准。

`max_width_ratio` 文字块最大宽度占画面比例，超出自动换行。德语法语建议给到 0.5 以上，中文日文 0.4 即可。

`font_size_range` 字号上下限，合成脚本在区间内自动缩放以适配文本长度。这是多语言复用同一模板的关键机制。

`color` 十六进制色值。需要与底图对应区域有足够对比度，合成脚本会做对比度校验。

## 安全区

文字不得进入画面边缘 5% 的范围，避免平台裁切时被切掉。文字块不得覆盖产品主体，合成脚本通过产品透明通道判断主体区域并做避让。
