---
name: azure-devops-rest-api
description: 当需要用 REST API 操作 on-prem Azure DevOps Server（TFS）的 Git 仓库与 Pull Request 时使用——批量收口评论、PR 数据拉取、按 commit 取文件做 diff、code review 自动化等。统一用 PAT 认证（不依赖浏览器登录态），涵盖 PR 评论线程（threads）、迭代与文件变更（iterations/changes）、取文件（items/blobs）等接口与本地 PAT 配置方案。
---

# Azure DevOps Server REST API（on-prem / TFS）

通过 PAT 认证调用 Azure DevOps Server（本地部署 TFS）的 Git REST API，操作仓库、Pull Request、评论与文件，用于 PR 数据拉取、批量评论/收口、按 commit 取文件做 diff 分析、code review 自动化等。

## 适用场景

- 读取/操作 PR 评论线程（发评论、批量关闭、删除）
- 拉 PR 的文件变更、提交、审阅者、状态
- 按 commit / blob 取文件内容做 diff
- 写自动化脚本（CI / 机器人）批量处理 PR

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

### 创建普通评论

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
python scripts/azdo_client.py add-comment 36391 --file "/path/File.java" --line 31 --change-tracking-id 3 --content "建议..."

# 删除评论
python scripts/azdo_client.py del-comment 36391 205707 1

# 按 commit 取文件内容
python scripts/azdo_client.py file-content --path "/path/File.java" --commit 7e78dfe4

# 列出 PR 迭代
python scripts/azdo_client.py iterations 36391
```

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

## 安全实践

- PAT 等同于账号密码，**绝不**贴进聊天 / 截图 / 提交 / 日志
- PAT 只存本地 `~/.config/azdo/config.json`，权限限当前用户（600）
- 暴露过的 PAT 立即撤销（Revoke）并重新生成
- Scopes 最小化（Code Read&write），设合理有效期，定期轮换
- `.gitignore` 排除真实 `config.json`，只提交 `config.example.json`
