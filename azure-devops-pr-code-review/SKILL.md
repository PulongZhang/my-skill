---
name: azure-devops-pr-code-review
description: 当需要对 on-prem Azure DevOps Server（TFS）Pull Request 做静态代码评审、拉取 PR 元数据/变更、创建 PR、更新 PR 标题/描述、用本地 git diff 阅读改动、生成中文 PR 描述或评审结论，并在用户明确要求时只通过 REST API 发布【必改】行内评论时使用。默认只做静态评审：不运行测试、不启动服务、不改代码；REST API 是评审评论与 PR 数据操作的工具支撑，不是本 skill 的唯一目标。
---

# Azure DevOps PR 静态代码评审（on-prem / TFS）

用于对 Azure DevOps Server Pull Request 做静态代码评审：拉 PR 信息、读取 diff 与上下文、产出中文评审结论，并在用户明确要求时只发布 `【必改】` 行内评论。REST API/PAT 脚本是支撑 PR 数据拉取和评论发布的工具。

## 适用场景

- 用户说“代码评审下”“review 这个 PR”“静态评审”“作出评论/发到 PR”等，且目标是 Azure DevOps/TFS PR
- 拉 PR 详情、提交、变更文件、`changeTrackingId`、审阅者、评论线程
- 优先用本地 git diff 做静态评审；仓库不在本地时再用 REST `items`/`blobs` 取文件
- 在用户明确要求发布时，只向 PR 发 `【必改】` 行内评论；不发总结评论
- 批量收口、删除、回复 PR 评论线程

## 静态代码评审工作流（默认）

1. 解析 PR URL/ID，拉取 PR 详情、提交、变更文件和 `changeTrackingId`。
2. 若本地仓库可用，`git fetch` 后用三点 diff 阅读真实改动：`origin/<target>...origin/<source>`。
3. 只做静态审查：读 diff 和必要上下文，判断正确性、安全、兼容性、i18n、边界条件、回归风险。
4. 先形成中文评审结论；用户只说“评审/看看”时，先把结论发给用户，不直接发布到 PR。
5. 用户明确说“发评论/作出评论/评论到 PR”时，再发布：**只发布每个 `【必改】` 具体问题的行内评论**（必须钉到具体 `file:line`）；**永远不发布总结评论**。`【建议】`/`【确认】`/`【提示】`/已核对无问题项只在对话结论里给用户看，不发到 PR。若没有 `【必改】`，不调用评论接口，并告知用户“无必改，不发布 PR 评论”。

**默认禁止**：不要运行测试、构建、启动服务、修改业务代码或格式化文件；除非用户明确要求验证、修复或执行测试。

## API 基础信息

根路径结构：

```
{server}/{collection}/{project}/_apis/git/repositories/{repo}/...
```

| 段 | 示例 | 说明 |
|---|---|---|
| server | `https://cetsoft-svr1` | TFS 服务器地址 |
| collection | `Solutions` | 集合（Collection）名 |
| project | `BIZ-数据中心` 或 GUID | 项目名或项目 ID |
| repo | `dcom` 或 GUID | 仓库名或仓库 ID |
| api-version | `api-version=5.0` | API 版本（实测 5.0 可用）|

**名称 vs GUID**：`project`、`repo` 既可用名称也可用 GUID，二者等价。脚本用名称直观，用 GUID 更稳定（项目/仓库改名不受影响）。

> URL 含中文（如 `BIZ-数据中心`）需做百分号编码：`BIZ-%E6%95%B0%E6%8D%AE%E4%B8%AD%E5%BF%83`。

## 认证：PAT（个人访问令牌）

统一用 PAT 做 HTTP Basic Auth，用户名留空、密码为 PAT：

```
Authorization: Basic base64(":<PAT>")
```

curl 用 `-u ":<PAT>"`：

```bash
curl -u ":<PAT>" "https://cetsoft-svr1/Solutions/BIZ-%E6%95%B0%E6%8D%AE%E4%B8%AD%E5%BF%83/_apis/git/repositories/dcom/pullRequests/36391/threads?api-version=5.0"
```

- 生成位置：右上角用户图标 → User settings → **Personal access tokens**
- Scopes：至少勾 `Code → Read & write`（读代码 + PR 评论 + 提交都在此范围）
- Expiration：建议设长（90 天 / 1 年），到期前续期
- on-prem TFS 直接 Basic 即可，不需要 Bearer
- 自签名证书环境 curl 加 `-k` 跳过校验

## 本地 PAT 配置文件方案（推荐）

**不要**把 PAT 硬编码进脚本、写进环境变量散落各处、或贴进聊天/提交。统一放本地配置文件，并限制权限。

### 配置文件路径

跨平台统一用 `~/.config/azdo/config.json`（脚本里自动适配）：

| 平台 | 实际路径 |
|---|---|
| Windows | `C:\Users\<用户名>\.config\azdo\config.json` |
| Linux / macOS | `~/.config/azdo/config.json` |

### 配置文件内容（`config/config.example.json`）

```json
{
  "baseUrl": "https://cetsoft-svr1",
  "collection": "Solutions",
  "defaultProject": "BIZ-数据中心",
  "defaultRepo": "dcom",
  "pat": ""
}
```

`pat` 留空，由用户本地填真实 PAT。**模板文件可提交，真实 PAT 永远只在本地 `config.json`。**

### 权限设置（仅当前用户可读）

```bash
# Linux / macOS
chmod 600 ~/.config/azdo/config.json

# Windows（PowerShell）
icacls "$env:USERPROFILE\.config\azdo\config.json" /inheritance:r /grant:r "$env:USERNAME:R"
```

### 防止误提交

真实 `config.json` 只在本地。若纳入项目，`.gitignore` 加：

```
.config/azdo/config.json
**/config.json
!**/config.example.json
```

### 读取脚本

见 `scripts/azdo_client.py`——自动从 `~/.config/azdo/config.json` 读 PAT 与 baseUrl，封装常用接口，代码与命令行里都不出现明文 PAT。

## 一、PR 评论线程（threads）

最常用的一组接口——发评论、回复、改状态、删除。同 URL 按 method 区分：

```
.../pullRequests/{prId}/threads
```

| Method | URL | 用途 |
|---|---|---|
| GET | `.../pullRequests/{prId}/threads` | 列出所有评论线程 |
| POST | `.../pullRequests/{prId}/threads` | 创建一个线程（普通 / 行内评论）|
| GET | `.../pullRequests/{prId}/threads/{threadId}` | 取单个线程 |
| PATCH | `.../pullRequests/{prId}/threads/{threadId}` | 改线程状态（active/resolved/won't-fix/closed）|
| POST | `.../pullRequests/{prId}/threads/{threadId}/comments` | 在已有线程下追加评论 |
| DELETE | `.../pullRequests/{prId}/threads/{threadId}/comments/{commentId}` | 删除某条评论（软删除）|

### 创建普通评论（接口说明；代码评审发布禁用）

代码评审场景不要用普通评论发布总结；本接口只作为 Azure DevOps threads 能力说明。

```bash
curl -u ":<PAT>" -H "Content-Type: application/json" -X POST \
  ".../pullRequests/36391/threads?api-version=5.0" \
  -d '{"comments":[{"commentType":1,"content":"评论内容"}],"status":1}'
```

### 创建行内代码评论（钉到某文件某行）

```json
{
  "comments": [{"commentType": 1, "content": "评论内容"}],
  "status": 1,
  "threadContext": {
    "filePath": "/path/to/File.java",
    "rightFileStart": {"line": 31, "offset": 1},
    "rightFileEnd": {"line": 31, "offset": 73}
  },
  "pullRequestThreadContext": {
    "changeTrackingId": 3,
    "iterationContext": {"firstComparingIteration": 1, "secondComparingIteration": 1}
  }
}
```

### 字段说明

| 字段 | 说明 |
|---|---|
| `comments[].commentType` | `1`=Text，`2`=CodeChange，`3`=System |
| `comments[].content` | 评论正文 |
| `status` | `1`=Active，`2`=Resolved，`3`=Won't Fix，`4`=Closed，`5`=As Designed |
| `threadContext.filePath` | 行内定位文件（不带即普通评论）|
| `threadContext.rightFileStart/End` | 定位到右侧（新版本）的行/列 |
| `pullRequestThreadContext.changeTrackingId` | 关联 changes 接口返回的文件变更序号 |
| `iterationContext.first/secondComparingIteration` | 基于哪两次迭代对比 |
| `properties.UniqueID` | 可省略，服务端自动生成 |

> 创建时 `id`、`publishedDate`、`lastUpdatedDate` 会被服务端忽略/覆盖，POST body 不必填。

### 返回结构要点

GET threads 返回 `value[]`，每条含 `id`、`status`、`isDeleted`、`comments[]`、`threadContext`、`properties`：

- `commentType: "system"` 是审计事件（投票 VoteUpdate、策略状态 PolicyStatusUpdate、自动完成 AutoCompleteUpdate、状态变更 StatusUpdate），**不是**人工评论
- `commentType: "text"` 才是人工评论
- DELETE 是软删除：`isDeleted: true`，`content` 被清空

## 二、PR 迭代与文件变更

```
GET .../pullRequests/{prId}/iterations?api-version=5.0
```

返回所有迭代（每次 push 一个），含 `id`、`sourceRefCommit`、`targetRefCommit`。

```
GET .../pullRequests/{prId}/iterations/{iterationId}/changes?api-version=5.0
```

返回某次迭代的文件变更清单 `changeEntries[]`：

- `changeTrackingId`：变更序号（发行内评论填这个）
- `item.path`：文件路径
- `item.objectId` / `originalObjectId`：新/旧 blob ID
- `changeType`：edit / add / delete

## 取 PR 改动 diff：本地仓库优先用 git

若评审的仓库已在本机检出（Claude Code 在仓库内运行的常见情况），**优先用本地 git 取 diff，不要走 REST 取文件**——更快、行号可直接用于行内评论、可 `--stat` 概览。

### 三点 diff（PR 的真实改动）

PR 改动 = 源分支相对目标分支分叉点以来的变更，用**三个点** `...`（merge-base diff）：

```bash
git fetch origin
git diff origin/<目标分支>...origin/<源分支> --stat          # 概览
git diff origin/<目标分支>...origin/<源分支> -- "<路径>"      # 指定文件
```

> 三个点 `...` 才是 PR 真实改动；两个点 `..` 是直接比较两端，会把目标分支期间的新提交也算进来，结果偏大。

### 行号定位（行内评论用）

直接看 diff 里 `+` 行号，或 `git show origin/<源分支>:<path> | grep -n "xxx"`，即为行内评论的 `--line`，无需 REST changes 推算。`changeTrackingId` 仍用 `pr-changes` 命令取。

### 何时仍走 REST

仓库不在本地、或要取某历史 commit/blob 的精确内容时，才用下文 `items`/`blobs` 接口或 `file-content` 命令。

## 三、获取文件内容

取完整文件（页面 DOM 抓不全时用）：

### 按 path + commit 取文本（推荐）

```
GET .../items?path={filePath}&versionDescriptor.version={commitId}&versionDescriptor.versionType=commit&api-version=5.0
```

返回文件文本。`commitId` 用 iterations 的 `sourceRefCommit`（新）或 `targetRefCommit`（旧）即可做 diff。

### 按 blob objectId 取

```
GET .../blobs/{objectId}?api-version=5.0
```

> 默认 `application/octet-stream`（二进制），工具里可能显示 "Binary data not displayed"。取文本优先用 items API。

## 四、其他常用 PR 接口

| 用途 | Method + 路径 |
|---|---|
| PR 详情 | `GET .../pullRequests/{prId}` |
| PR 提交记录 | `GET .../pullRequests/{prId}/commits` |
| 审阅者 | `GET .../pullRequests/{prId}/reviewers` |
| PR 状态检查 | `GET .../pullRequests/{prId}/statuses` |
| 关联工作项 | `GET .../pullRequests/{prId}/workitems` |
| 更新/合并 PR | `PATCH .../pullrequests/{prId}` |
| 创建 PR | `POST .../pullrequests` |

## 五、通用 Git 接口

| 用途 | 路径 |
|---|---|
| 仓库列表 | `GET .../repositories` |
| 某提交的变更 | `GET .../commits/{commitId}/changes` |
| 文件树 | `GET .../items?scopePath=/&recursionLevel=full` |
| 分支 refs | `GET .../refs` |
| pushes | `GET .../pushes` |

## 自动化脚本

`scripts/azdo_client.py` 自动读本地配置 + 封装常用接口（PAT 不出现在命令行）：

```bash
# 列出某 PR 评论线程
python scripts/azdo_client.py pr-threads 36391

# 行内评论
python scripts/azdo_client.py add-comment 36391 --file "/path/File.java" --line 31 --change-tracking-id 3 --content "【必改】..."

# 长内容必改行内评论（含 markdown 反引号/$/换行）：优先 stdin（--content -）或 --content-file，
# 避免命令行 --content 被 shell 转义破坏；heredoc 用带引号的 'EOF' 禁用一切展开
python scripts/azdo_client.py add-comment 36391 --file "/path/File.java" --line 31 --change-tracking-id 3 --content - <<'EOF'
【必改】这里会导致空语言覆盖默认值
影响：`LanguageUtil.getLanguage()` 返回空字符串时，下游会把默认语言写成空值，导致 i18n 文案缺失。
建议：写入前先 trim 并过滤空字符串，空值继续使用默认语言。
EOF

# 或从文件读（适合先用编辑器/工具写好长必改行内评论再发）
python scripts/azdo_client.py add-comment 36391 --file "/path/File.java" --line 31 --change-tracking-id 3 --content-file must-fix-comment.md

# 删除评论
python scripts/azdo_client.py del-comment 36391 205707 1

# 按 commit 取文件内容
python scripts/azdo_client.py file-content --path "/path/File.java" --commit 7e78dfe4

# 列出 PR 迭代
python scripts/azdo_client.py iterations 36391

# 创建 PR（源分支 -> 目标分支；分支名自动补 refs/heads/）
# 描述内容按 references/pr-description-template.md 准备；创建 PR 的背景/说明边界见该文件同名章节。
# 默认远端描述使用不含 Context/Description 的裁剪版描述文件，背景/说明在对话里给人工粘贴参考。
python scripts/azdo_client.py create-pr --source feature/x --target main \
  --title "feat(bpm): 新增 xxx" --description-file pr-description.remote.md

# 或从 stdin 读远端描述；EOF 内同样只放远端描述，不放对话参考内容
python scripts/azdo_client.py create-pr --source feature/x --target main \
  --title "feat(bpm): 新增 xxx" --description - <<'EOF'
<按模板填写的远端描述，不包含 Context 背景 / Description 说明>
EOF

# 代码评审：拉 PR 数据（详情 / 提交 / 文件变更含 changeTrackingId / 审阅者）
python scripts/azdo_client.py pr-detail 36391
python scripts/azdo_client.py pr-commits 36391
python scripts/azdo_client.py pr-changes 36391          # changeTrackingId 供行内评论用
python scripts/azdo_client.py reviewers 36391
```

> **长必改行内评论勿走 `--content` 字面值**：含反引号（shell 命令替换）、`$`（变量展开）、单引号（字符串断裂）或超长内容，经命令行 `--content "..."` 传参会被 shell 破坏或触发 ARG_MAX。统一用 `--content -`（stdin + `<<'EOF'`）或 `--content-file`；短评论仍可用 `--content "..."`。

## 代码评审评论格式

向 PR 发评审评论前，先读 [`references/code-review-format.md`](references/code-review-format.md) 并按其模板与原则。核心约定：

- **只有用户明确要求发布时才可能发到 PR**；否则先在对话中给出静态评审结论。
- **发布到 PR 时只发 `【必改】` 行内评论**：每个必改具体问题 1 条行内评论（必须钉到具体 `file:line`）。
- **永远不要发布总结评论**：不要创建普通总结线程；`【建议】`/`【确认】`/`【提示】`/已核对无问题项只在对话结论里给用户看，不发到 PR。
- **没有 `【必改】` 就不发布任何 PR 评论**：即使用户要求“评论到 PR”，也告知“无必改，不发布 PR 评论”。
- 评论按严重程度分级、行首用 `【必改】` / `【建议】` / `【确认】` / `【提示】` 标注；每条给 `file:line` + 原因 + 具体修复；拿不准标 `【确认】` 不标 `【必改】`；主观偏好标 `【提示】` 且不强求。
- **文字风格（深入浅出）**：评审文字中文撰写，能用中文表达的概念不用英文（类名/方法名/字段名等标识符保留原文）；讲清问题与影响用平实的话，不堆大段代码贴片。

完整行内模板、对话结论模板与分级定义见该参考文件。

## PR 描述模板

帮作者写或补 PR 描述时，先读 [`references/pr-description-template.md`](references/pr-description-template.md) 并按其六段结构填写。核心约定：

- **六段**：Context 背景 / Description 说明 / Changes 变更内容 / Outside Changes 代码库外变更 / Test & Risk 自测与风险 / 代码来源声明。
- **创建 PR 边界**：新建 PR 时必须遵守参考文件的“创建 PR 时的背景/说明边界”；默认仅把 `Context` / `Description` 留在对话参考中，远端描述仍保留其余四段，例外条件以参考文件为准。
- **直接写正文**：填实际内容时不保留 placeholder 提示词（"为什么要改："、"怎么实现："等），标题已说明该写什么。
- **标注来源**：`Changes` 每条行内打 `【AI】` / `【人工】` / `【AI·人工修订】`，末尾"代码来源声明"汇总整体 AI / 人工比例。
- **单一职责**：一个 PR 只围绕一件事；后端不卡文件数硬门槛。
- **文字风格（深入浅出）**：描述中文撰写，能用中文表达的概念不用英文（标识符保留原文）；背景与风险用平实的话讲清，不堆大段代码贴片。

更新已有 PR 描述用 `scripts/azdo_client.py update-pr` 命令（封装了 `PATCH .../pullrequests/{prId}`，用法见该参考文件）；新建 PR 的描述边界以上述参考文件为准。

完整模板、标注规则与填写示例见该参考文件。

## 常用 ID / 路径速查

| 项 | 值 |
|---|---|
| 服务器 | `https://cetsoft-svr1` |
| 集合 | `Solutions` |
| 项目（示例） | `BIZ-数据中心`（编码 `BIZ-%E6%95%B0%E6%8D%AE%E4%B8%AD%E5%BF%83`）|
| 项目 GUID（示例）| `a6d9f6b9-72b8-41da-9c33-83a927b2a8ba` |
| 仓库（示例） | `dcom` |
| 仓库 GUID（示例）| `aafefca6-1425-441e-a5d4-ff5fb9b4c58d` |

> 换项目/仓库时用 `GET .../repositories` 查实际 ID。

## 注意事项

1. `api-version` 实测 `5.0` 可用；on-prem 不同版本上限不同，5.0/6.0 通常都行
2. URL 中文项目名必须百分号编码，否则 404
3. 行内评论的 `changeTrackingId` 必须来自 changes 接口对应文件，填错会定位错文件
4. 删除评论是软删除（isDeleted=true），审计仍可见
5. `system` 类型线程是审计事件，不是人工评论
6. 取完整文件用 items API，不要依赖页面 DOM

## 常见错误

- **PAT 调用 401**：PAT 过期 / 已撤销 / Scopes 没勾 `Code` → 重新生成并勾对 scope
- **中文项目名 404**：URL 没做百分号编码
- **行内评论定位错文件**：`changeTrackingId` 填错 → 先 GET changes 拿正确序号
- **blobs 返回 "Binary data not displayed"**：blob 默认 octet-stream → 改用 items API
- **创建后评论"消失"**：检查 `isDeleted`，可能被自动策略/他人删除
- **自签名证书报错**：curl 加 `-k`，Python requests 设 `verify=False`
- **Windows 脚本输出中文乱码**：控制台默认 GBK，脚本已强制 stdout 为 UTF-8；若环境变量覆盖仍乱码，设 `PYTHONUTF8=1` 或先 `chcp 65001` 再跑
- **长必改行内评论内容被破坏/截断**：含反引号、`$`、单引号的 markdown 经 `--content "..."` 传参被 shell 转义 → 改用 `--content -`（stdin + `<<'EOF'` heredoc）或 `--content-file`

## 安全实践

- PAT 等同于账号密码，**绝不**贴进聊天 / 截图 / 提交 / 日志
- PAT 只存本地 `~/.config/azdo/config.json`，权限限当前用户（600）
- 暴露过的 PAT 立即撤销（Revoke）并重新生成
- Scopes 最小化（Code Read&write），设合理有效期，定期轮换
- `.gitignore` 排除真实 `config.json`，只提交 `config.example.json`
