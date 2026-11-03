# Teambition 原文件版本 API

本参考用于在已授权的项目/目录中更新既有文件，默认复用 Chrome 登录态直接调用接口。执行授权及浏览器选择见 [SKILL.md](../SKILL.md)，S1867 部署地址见 [项目参考](s1867.md)。不包含新建文件、移动、重命名、修改可见性或成员。

接口依据为 2026-11-03 对 `https://tb.cet-electric.com:4753` 部署前端的只读检查。来源实现是 `flow-engine` 提交 `99d1bf74` 中的 `.agents/skills/bpm-category-onboarding/scripts/publish_bpm_sql.mjs`，已有 15 项离线模拟测试；尚未以真实上传验证这条 API 链路。其他部署或前端升级时先核对契约，不能直接复用历史模块编号。

## 输入与边界

- 来源必须是本次完整已校验文件；读取当前原始字节，记录文件名、MIME 类型、字节数和 SHA-256，不从聊天复制截断内容。
- 部署 origin、项目 ID、目录 ID 和原文件目标来自本次请求或已确认上下文，不预设 BPM 项目的目录或持续上传授权。
- 复用当前聊天已确认的同源 Chrome 页面；没有可用页面时再 `list_pages` 定位。每次脚本先检查 `location.origin` 与 `/login`，无需导航到文件目录的 DOM。
- Cookie/Authorization 由浏览器会话处理，不读取或导出。上传 token、SDK 临时凭证及签名下载地址只在页面函数内使用，不输出聊天、日志、临时文件或回执。
- BPM SQL 交付继续使用该项目的固定 helper 和路径白名单；本参考不替代其业务校验或扩大数据库执行授权。

## 定位原文件与写前检查

| 请求 | 响应及校验 |
|---|---|
| `GET /api/collections/{folderId}` | 对象的 `_id` 和 `_projectId` 必须匹配授权目录、项目 |
| `GET /api/works?_parentId={folderId}&_projectId={projectId}&order=updatedAsc&count=50&page={page}` | 直接返回数组；从 1 开始完整分页，返回不足 50 项才结束；重复 ID、无进展或页数上限到达时停止 |
| `GET {downloadUrl}` | 使用本次元数据的完整地址，只接受已核对的同源下载及最终响应；下载字节数与 `fileSize` 一致后计算原始 SHA-256 |

文件列表是直接数组，不套用要求对象响应的工时 helper，也不添加工时服务专用头。按 `fileName` 精确唯一匹配，要求 `_id` 为有效的 24 位十六进制 ID、`_projectId` 和 `_parentId` 正确、`isArchived=false`。匹配失败、重名、归档或归属变化时停止，不能改成新建文件。

原始字节相同返回 `same_bytes` 并跳过。只有调用方明确采用文本换行等价规则时，才可把仅 CRLF/LF 差异报告为 `line_endings_only` 并跳过，保留双方原始哈希；BOM 或其他文本变化不能算纯换行。真正上传后的验收始终要求原始字节一致。

上传前重新查询和下载原文件，要求其 ID/归属与内容哈希仍与刚才检查一致；若已是目标字节则跳过，若被他人改变则停止。使用 `cache: 'no-store'` 避免旧缓存被误当作本次证据。

## 申请单次上传凭证

```http
POST /api/awos/upload-token
Content-Type: application/json
```

```json
{
  "scope": "work:{原文件ID}/version",
  "category": "work",
  "fileName": "本次完整文件名",
  "fileType": "application/sql",
  "fileSize": 12345
}
```

上例 MIME 类型和大小仅示意，必须替换为实际文件信息。`scope` 使用实时匹配的原文件 ID，不用项目或目录 ID。请求复用 `credentials: 'same-origin'`，写请求采用 `redirect: 'error'`、有限超时且不自动重试，避免认证重定向被误报成功。

前端使用直接返回的 `sdk`、`upload`、`token` 字段：`sdk` 为 S3 临时签名配置，`upload` 包含 `Bucket`、`Key` 等对象参数，`token` 用于后续关联原文件版本。检查这些字段非空且上传 endpoint 与已确认 origin 相同；结构不符、登录失效或跨源时停止，不打印原始响应。申请凭证和上传字节都不代表原文件已更新。

## 上传字节

复用当前页面底层 S3 SDK：通过 `webpackChunkteambition_web` 的 runtime 回调取得模块加载器，加载分块 `68613`、`47310` 后读取模块 `968613`，核对它导出带 `prototype.upload` 的构造器。runtime 只放在本次函数局部变量中，移除临时加入的 chunk 数组项，不在页面全局保留文件或凭证。模块编号只属于上述已检查部署，缺失或契约变化时先只读核对。

构造客户端时使用服务端 `sdk` 配置，并设置 `maxRetries: 0`、`logger: null`、`s3ForcePathStyle: true`；沿用来源实现的 `httpOptions: {timeout: 30000, connectTimeout: 10000}`。若凭证响应有可解析的 `Date` 头，用服务器时间与 `Date.now()` 之差设置 `systemClockOffset`，避免签名时钟偏差。

调用 `client.upload({...upload, Body: 原始字节Blob}, {queueSize: 1, leavePartsOnError: true}).promise()`，Blob 保留原始字节与 MIME 类型。不调用页面上层上传器：该实现包含自动重试及输出 token/上传配置的异常日志。仅捕获并返回固定阶段摘要，不回传 SDK 原始错误对象，不自动删除对象或分片补偿失败。

对象上传后、原文件版本提交前，再次核对原 ID/归属和远端下载哈希。内容已被他人修改则返回 `conflict`，不覆盖；若已变成目标字节则只做独立核验，不重复提交版本。该复查不能消除服务端未提供条件写入时的全部竞态。

## 提交原文件版本并独立核验

```http
POST /api/works/{原文件ID}/versions
Content-Type: application/json
```

```json
{"fileToken": "本次上传返回的token"}
```

只发送本次 token，不调用 `POST /api/works`，不改项目、目录、名称、权限或成员。版本请求只提交一次；HTTP 成功仅表示接口接受，必须重新查询原文件元数据并独立下载，对照原 ID、项目、目录、文件名、字节数及 SHA-256。

正常路径在一次 `evaluate_script` 内完成写前检查、凭证请求、对象上传、版本提交和独立核验；独立核验指重新查询并下载，不要求另一次工具调用。可按来源实现最多三次只读核验，每次间隔约 1 秒，不包含任何写入重试。

| 结果 | 含义与下一步 |
|---|---|
| `same_bytes` | 远端已是目标原始字节，跳过 |
| `line_endings_only` | 仅在明确文本等价规则下跳过，原始哈希不同 |
| `verified` | 原 ID/归属和下载的原始大小、SHA-256 全部一致，无需再重复核验 |
| `conflict` | 写前复查发现并发变化，未提交本次版本 |
| `unknown` 或调用中断 | 先对原 ID 做只读查询和下载核验，不重新申请凭证或整体重发 |

版本提交响应丢失后也先只读核验：已是目标字节才报告完成；无法确认则保留未知。对象上传成功而版本关联失败可能留下未关联对象，不能以删除或再次上传自动补偿。逐文件报告结果和目标目录；不能把“对象已上传”写成“文件版本已更新”。
