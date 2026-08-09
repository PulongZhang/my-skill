---
name: ppt-master-workflow
description: "用于基于 ppt-master 仓库（hugohe3/ppt-master）Quick Generate 路线，从会议纪要/分享素材 + 品牌 PPTX 模板生成内容详细、自由布局的参会分享 PPT。凡是用户要求：把多份智能纪要/分享笔记做成参会分享 PPT、保留模板品牌视觉但不要被模板槽位限制内容、每页要写详细内容、备注要写原素材对应内容（而非口语提示词）、或提到 ppt-master 时，都应使用本 Skill。产出为原生 PPTX（SVG 手绘→导出），可嵌入逐页演讲备注。"
compatibility: "需要 git clone 权限访问 GitHub；LibreOffice（soffice）用于渲染 QA；python3-venv 用于 ppt-master 依赖。"
---

# ppt-master 参会分享 PPT 生成

把「多份分享素材（智能纪要/笔记 MD）+ 一份品牌 PPTX 模板」变成「内容详细、布局自由、保留品牌视觉」的参会分享 PPT。

核心思路：**不套模板槽位**（模板填充会把内容压成短句），而是从模板提取品牌素材（背景图/主色），用 ppt-master Quick Generate 路线手写 SVG 页面，内容放开写，最后导出原生 PPTX 并嵌入「原素材对应内容」的演讲备注。

## 触发条件

- 用户给出多份纪要/笔记 + 一份模板 PPTX，要求做参会分享/汇报 PPT
- 用户强调「内容要多、详细」「不要太依赖模板样式」「备注写原 PPT 对应内容」「金句不要反复出现」
- 用户直接提到 ppt-master

## 前置环境

```bash
# 1. clone ppt-master（含 routing、quick-generate 规范与导出脚本）
git clone --depth 1 --filter=blob:none https://github.com/hugohe3/ppt-master /tmp/ppt-master

# 2. 依赖 venv（python-pptx 等）
python3 -m venv /tmp/pptx-venv
/tmp/pptx-venv/bin/pip install -r /tmp/ppt-master/requirements.txt
# 若 requirements 未列出 python-pptx，补装：python-pptx defusedxml

# 3. 渲染 QA 工具
which soffice pdftoppm   # LibreOffice + poppler-utils；缺则安装
```

注意：ppt-master 是第三方仓库，**先跑 `skills/ppt-master/scripts/attribution_guard.py`**（许可证检查，exit 0 才继续），并阅读 `skills/ppt-master/workflows/routing.md` 与 `quick-generate.md` 后再动手。

## 固定素材

`assets/CET PPT模板.pptx` — CET 中电技术品牌模板（14 页原生 PPTX），本 Skill 的默认品牌来源（封面城市实景、等轴纹理、绿白配色均提取自它）。用户提供其他模板时以用户为准。

## 工作流程

### 1. 建项目 + 导入素材

```bash
P=projects/<title>_ppt169_YYYYMMDD
/tmp/pptx-venv/bin/python skills/ppt-master/scripts/project_manager.py init "<title>" --format ppt169 --quick-generate
# 素材（纪要 MD）导入 sources/：
/tmp/pptx-venv/bin/python skills/ppt-master/scripts/project_manager.py import-sources "$P" /path/to/notes/*.md
```

### 2. 提取模板品牌素材

默认用本 Skill 自带 `assets/CET PPT模板.pptx`；用户另有模板时用它。解压出 `ppt/media/`：

```bash
mkdir -p /tmp/tpl-media && cd /tmp/tpl-media
/tmp/pptx-venv/bin/python -c "import zipfile; zipfile.ZipFile('<本skill>/assets/CET PPT模板.pptx').extractall('x')"
cp x/ppt/media/*.jpeg x/ppt/media/*.png .   # 或选择性拷贝
```

用 `vision_analyze` 逐张确认：哪些是封面主图（建筑/风景实景）、哪些是背景装饰纹理（浅灰等轴/点状）、哪些是 logo。把选中的拷进 `$P/images/`。

### 3. 拉图标池（可选但推荐）

```bash
/tmp/pptx-venv/bin/python skills/ppt-master/scripts/icon_sync.py "$P" \
  tabler-outline/calendar tabler-outline/map-pin tabler-outline/user \
  tabler-outline/cpu tabler-outline/gauge tabler-outline/brain \
  tabler-outline/robot tabler-outline/shield-check tabler-outline/database \
  tabler-outline/settings tabler-outline/git-branch tabler-outline/stack \
  tabler-outline/users tabler-outline/bolt tabler-outline/chart-bar \
  tabler-outline/target tabler-outline/refresh
```

SVG 中引用：`<use data-icon="tabler-outline/xxx" x=".." y=".." width=".." height=".." fill="#RRGGBB"/>`

### 4. 写 SVG 生成脚本

手写 12 页级 SVG 太重，**用 Python 脚本批量生成**（脚本决定内容与布局，产出 `svg_output/NN_name.svg`）。公共 helper 见 `scripts/svg_deck_helpers.py`（CET 绿白配色、header/footer、card、bullet、icon_circle、宽度估算），直接 import 复用：

```bash
cp <本skill>/scripts/svg_deck_helpers.py /tmp/ppt-master/
# 在生成脚本里：from svg_deck_helpers import *
```

页面设计要点：

- 画布 `viewBox="0 0 1280 720"`，根元素 `data-pptx-page-role="cover|toc|content|ending"`
- 每页 `header(title, tag, page_no, total, subtitle)` 输出顶部标题条+右下页码+左下单位 footer
- 内容密度大时用卡片分区（`card()`），卡片内多行文本**手动拆行**（SVG text 不自动换行！）
- 颜色大写 `#RRGGBB`；字体 `微软雅黑`；XML 保留字符用 `esc()` 转义
- 图片用 `<image href="images/xxx.png" ... opacity="0.35"/>`

**金句/重复元素**：除非用户明确要，不要每页放「金句」行；如用户反感反复出现，全部删除，最多保留一页集中展示。

### 5. 质量门 + 导出（带备注）

```bash
# 文本溢出预检（本 skill 的脚本，按卡片边界估算宽度）
python3 scripts/check_svg_overflow.py "$P/svg_output"   # 或 venv python

# ppt-master 质量门（0 error 才能导出）
/tmp/pptx-venv/bin/python skills/ppt-master/scripts/svg_quality_checker.py "$P" --quick-generate --stage final --json

# 备注：notes/total.md（标题必须是 # NN_<svgstem> 与 SVG 文件名严格一致！）
# 备注内容 = 原素材对应内容（原文摘录/数据/出处），不是口语化讲解
/tmp/pptx-venv/bin/python skills/ppt-master/scripts/total_md_split.py "$P"

# 导出（Quick 模式必须 --with-notes，否则备注不嵌入）
/tmp/pptx-venv/bin/python skills/ppt-master/scripts/svg_to_pptx.py "$P" --quick-generate --with-notes
```

### 6. 渲染 QA（必须逐页）

```bash
cd "$P" && mkdir -p qa && cp "exports/"*.pptx qa/out.pptx && cd qa
soffice --headless --convert-to pdf out.pptx && pdftoppm -png -r 110 out.pdf slide
```

逐页 `vision_analyze`：文字是否超出卡片/画布、是否截断、是否重叠、金句是否残留、页码是否正确。**每轮修复后重跑 5→6 全链**。

### 7. 交付

成品拷到用户目录（如 `/root/ppt/`），用 `zipfile` 校验 notesSlide 数量 == 页数；清理 qa/ 等临时产物。

## 关键 Pitfalls（都踩过）

1. **SVG `<text>` 里不能用 `<b>`**——`<b>` 不是 SVG 元素，检查器直接报错。加粗用 `<tspan font-weight="bold">`。
2. **中文不自动换行**——超宽就溢出卡片。写文案时按宽度估算预拆行：中文 ≈ 1.0×字号、拉丁/数字 ≈ 0.55×字号、空格 ≈ 0.33×字号；卡片内宽 = 卡片宽 - 2×内边距(约 24-32)。
3. **notes 标题编号必须匹配 SVG 文件名**——`# 10_takeaways 收获` 匹配 `10_takeaways.svg`；写错编号（如 09）split 会静默忽略，导出时 notes Disabled/旧文件残留，看起来成功实际备注是旧的。修完 total.md 后**先删 notes/*.md 旧文件再 split**。
4. **svg_output 残留旧页**——删页后旧 .svg 还在，checker/split 会把旧页当目标（报 Missing notes）。删页后同步删对应 svg。
5. **Quick 导出默认 notes Disabled**——必须 `--with-notes`。
6. **不能从 gateway 会话内重启 gateway**（Hermes 保护）——与本 skill 无关但改配置时注意。
7. **页码总数**：header 的 total 默认值要跟随页数变化，删页后重排 page_no 和 total。
8. 导出文件名带时间戳，`cp exports/*.pptx` 多文件时指定确切文件。
9. `svg_to_pptx.py --quick-generate` 要求先跑 checker（stale 报告会拒绝导出），且**每次改 SVG 后必须重跑 checker**。

## 备注规范（用户偏好，强制）

- 备注 = **原素材（智能纪要/原 PPT）对应的内容**：原文要点、数据、原话、出处标注（如「本页对应《智能纪要：xxx》。原文要点：…」）
- 不是口语化「防忘词」讲稿——用户明确拒绝过口语稿
- 金句内容不单独成段（用户不要金句反复体现）
- 每页 100-1200 字均可，详细优先

## 验证清单

- [ ] attribution_guard 通过
- [ ] svg_quality_checker 0 error
- [ ] total_md_split 无 Missing
- [ ] 导出输出含 `Speaker notes: N page(s)`
- [ ] zipfile 校验 notesSlide == 页数
- [ ] 逐页渲染 QA 无截断/溢出/重叠
- [ ] 临时目录（qa、解压的 media）已清理
