---
name: dingtalk-doc-markdown
description: 当 AI 需要读取或理解钉钉文档（DingTalk Docs、DingTalk Wiki、钉钉文档）内容——如总结、回答、提取、改写文档内容——时使用。通过在浏览器控制台把页面正文转换为 Markdown 供 AI 阅读，下载 .md 文件只是顺带行为。适用于包含 wiki-doc-iframe、article.body-editor-content、layout_body、data-type 块、表格、卡片、标题的浏览器控制台/书签脚本场景。
---

# 钉钉文档 Markdown 读取

## 概述

使用这个技能，让 AI 能读到钉钉文档的内容。脚本在已加载的文档页面中运行，必要时滚动钉钉文档容器，读取编辑器块，把标题、段落、表格和卡片转换为 Markdown 输出到控制台，供 AI 阅读；下载 `.md` 文件只是顺带行为（供用户留档），不是主要目的。除非用户明确要求其他集成方式，否则保持 DOM 读取方案。

## 快速开始

1. 在已登录的浏览器中打开目标钉钉文档或钉钉 Wiki 页面。
2. 等待正文内容完全加载并可见。
3. 打开浏览器 DevTools Console。
4. 将 `scripts/export-dingtalk-doc-markdown.js` 复制到控制台并运行。
5. 从控制台读取 Markdown 内容（这是 AI 阅读文档的主要途径）；下载的 `.md` 文件只是顺带产物。

如果用户需要书签脚本，将同一份脚本压缩成 `javascript:(()=>{...})()` 形式即可。除非用户明确要求，不要编造远程服务、API 接口、浏览器扩展或登录流程。

## 快速参考

| 需求 | 做法 |
| --- | --- |
| 读取当前钉钉文档内容 | 在 DevTools Console 运行 `scripts/export-dingtalk-doc-markdown.js`，从控制台读取 Markdown |
| 读取 iframe 内容 | 脚本先读取 `#wiki-doc-iframe`，再回退到当前 `document` |
| 定位正文区域 | 优先使用 `article.body-editor-content`，回退到 `#layout_body` |
| 采集虚拟滚动内容 | 滚动 `#layout_body` 并收集每个已渲染切片 |
| 转换块类型 | 支持 `heading-1` 到 `heading-6`、`paragraph`、`table`、`card` |
| 保留表格形状 | 规范化每行列数，并转义单元格中的 `|` |
| 排查缺失内容 | 确认文档已加载、iframe 同源可读、选择器仍匹配、滚动切片已采集 |

## 期望的 Markdown 行为

- 文档标题导出为 `# <标题>`，文件名清理为 `<标题>.md`。
- 钉钉 `data-type="heading-N"` 标题映射为 Markdown 标题层级。
- 编号标题保留原始编号，例如 `1.功能定位`、`3.1页面访问权限`。
- 段落导出为普通文本，并规范化空白字符。
- 以 `●` 或 `•` 开头的段落导出为 Markdown 列表项。
- 表格导出为 GitHub 风格 Markdown 表格。
- 卡片去掉 `[Not supported by viewer]` 后导出为 `text` 代码块。
- 重复文本或重复表格会被跳过，避免嵌套 DOM 造成重复输出。

## 浏览器与安全说明

只在用户信任并有权限访问的钉钉页面上运行脚本。脚本读取当前可见/可滚动文档 DOM，并触发本地下载；不应将文档内容发送到任何网络接口或外部服务。

不要承诺完美保真。钉钉 DOM 结构可能变化，图片、提及、复选框、合并单元格、嵌入文件、评论和不支持的卡片等复杂富文本可能退化为纯文本或被省略。

## 常见错误

- 文档尚未加载完成就运行脚本；应等正文可见后再运行。
- 在错误的 frame 或页面中运行；脚本会先尝试 `#wiki-doc-iframe`，再使用当前文档。
- 把同源 iframe 读取失败误认为 Markdown 转换问题；某些页面会被浏览器安全策略阻止读取 iframe。
- 只根据某一个页面泛化选择器；应明确保留 `wiki-doc-iframe`、`article.body-editor-content`、`#layout_body` 和 `data-type` 检查。
- 只读取当前 DOM 切片；钉钉可能虚拟滚动正文，需要滚动 `#layout_body` 收集所有已渲染切片。
- 将本地下载替换为服务器上传；这会改变隐私模型，需要用户明确同意。

## 可复用脚本

以 `scripts/export-dingtalk-doc-markdown.js` 作为标准脚本。调整脚本时保持以下不变量：

- 规范化隐藏 Unicode 控制字符、不间断空格和重复空白。
- 转义 Markdown 表格单元格中的管道符 `|`。
- 跳过表格内部的嵌套子块，避免表格内容重复输出。
- 滚动 `#layout_body` 时保留编号标题文本，并在结束后恢复原滚动位置。
- 使用 `Blob` 和 `URL.createObjectURL` 触发本地下载。
- 同时输出文件名和 Markdown：控制台输出是让 AI 读到内容的途径，下载 `.md` 文件只是顺带。
