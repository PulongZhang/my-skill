# Vibe Coding 全栈开发框架

## 1. 目标

本框架面向个人项目、内部管理系统和中小型 Web 应用，重点是：

- 适合使用 AI 辅助开发；
- 前后端类型和接口边界清晰；
- 本地开发与生产部署一致；
- 技术栈简单、成熟、容易维护；
- 不提前引入微服务、Kubernetes 等复杂基础设施；
- 使用 Git 管理代码、需求文档和部署配置。

---

## 2. 最终技术栈

### 2.1 前端

- Vue 3
- TypeScript
- Vite
- Vue Router
- Pinia
- Axios
- Element Plus
- Tailwind CSS
- pnpm

> Vue 3 使用 Element Plus，不使用旧版 Element UI。

### 2.2 后端

- Python 3.13
- FastAPI
- Pydantic
- SQLAlchemy 2
- Alembic
- PostgreSQL
- psycopg 3
- uv
- Uvicorn
- Ruff
- Pytest

### 2.3 部署

- Docker
- Docker Compose
- 1Panel
- OpenResty
- Cloudflare

Cloudflare 和 OpenResty 均只承担反向代理职责：

- Cloudflare：公网入口和边缘反向代理；
- OpenResty：源站反向代理及路径路由；
- 不使用 Cloudflare Pages、Workers 或 R2；
- 不在 OpenResty 中编写 Lua 业务逻辑；
- Vue 静态文件由独立 Web 容器提供。

### 2.4 版本管理

- Git
- GitHub、GitLab 或 Gitea 私有仓库

---

## 3. 总体架构

建议前后端共用一个域名，减少跨域和 Cookie 配置问题：

```text
https://app.example.com
```

请求链路：

```text
浏览器
  │
  ▼
Cloudflare
仅作为公网反向代理
  │
  ▼
OpenResty
仅进行源站反向代理和路径路由
  │
  ├── /api/* ──────► FastAPI 容器
  │                       │
  │                       ▼
  │                  PostgreSQL
  │
  └── /* ──────────► Web 容器
                      Nginx 提供 Vue 静态文件
```

接口统一使用 `/api/v1` 前缀：

```text
GET    /api/v1/users
POST   /api/v1/users
GET    /api/v1/users/{id}
PUT    /api/v1/users/{id}
DELETE /api/v1/users/{id}
```

---

## 4. 推荐目录结构

整个项目使用一个 Git 仓库管理：

```text
vibe-app/
├── apps/
│   ├── web/
│   │   ├── src/
│   │   │   ├── api/
│   │   │   ├── assets/
│   │   │   ├── components/
│   │   │   ├── layouts/
│   │   │   ├── router/
│   │   │   ├── stores/
│   │   │   ├── styles/
│   │   │   ├── types/
│   │   │   ├── views/
│   │   │   ├── App.vue
│   │   │   └── main.ts
│   │   ├── public/
│   │   ├── Dockerfile
│   │   ├── nginx.conf
│   │   ├── package.json
│   │   ├── pnpm-lock.yaml
│   │   ├── tsconfig.json
│   │   └── vite.config.ts
│   │
│   └── api/
│       ├── app/
│       │   ├── api/
│       │   │   └── v1/
│       │   ├── core/
│       │   │   ├── config.py
│       │   │   ├── database.py
│       │   │   └── security.py
│       │   ├── models/
│       │   ├── schemas/
│       │   ├── services/
│       │   ├── repositories/
│       │   └── main.py
│       ├── migrations/
│       ├── tests/
│       ├── Dockerfile
│       ├── alembic.ini
│       ├── pyproject.toml
│       └── uv.lock
│
├── deploy/
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   └── openresty.conf
│
├── docs/
│   ├── requirements.md
│   ├── architecture.md
│   ├── database.md
│   └── api-conventions.md
│
├── .env.example
├── .gitignore
├── CLAUDE.md
├── README.md
└── Makefile
```

第一版保持单体架构，不提前拆分微服务或多个 Git 仓库。

---

## 5. 前端规范

### Element Plus 负责

- 表单；
- 表格；
- 对话框；
- 日期选择器；
- 分页；
- 树形控件；
- 上传组件；
- 消息和通知。

### Tailwind CSS 负责

- 页面布局；
- Flex 和 Grid；
- 间距和尺寸；
- 响应式设计；
- 普通容器和文字；
- 业务状态颜色。

避免同时使用 Element Plus 和 Tailwind 深度修改同一个组件的内部样式。

建议根据 FastAPI 的 OpenAPI 文档生成前端 TypeScript 类型，可选择：

- `openapi-typescript`；
- `orval`。

这能减少前后端字段不一致的问题。

---

## 6. 后端规范

后端保持清晰但不过度设计的分层：

```text
Router
  ↓
Service
  ↓
Repository（复杂查询时使用）
  ↓
SQLAlchemy
```

### Router

负责：

- 接收和校验 HTTP 参数；
- 身份认证；
- 调用 Service；
- 返回 HTTP 响应。

### Service

负责：

- 业务规则；
- 状态变化；
- 事务边界；
- 多个数据操作的组合。

### Repository

负责：

- 数据库查询；
- 保存和更新；
- 复杂筛选。

简单业务允许 Service 直接使用 SQLAlchemy，不必为每张表机械地创建 Repository。

### Pydantic Schema

用于：

- 请求参数；
- 响应数据；
- 参数校验；
- OpenAPI 定义。

不要在接口中随意返回未定义结构的字典。

---

## 7. PostgreSQL 选择

PostgreSQL 不像 SQLite 那样属于嵌入式数据库，但对普通 VPS 足够轻量。

建议配置：

- 最低：1 核 2 GB；
- 推荐：2 核 4 GB。

适合直接使用 PostgreSQL 的情况：

- 多用户同时操作；
- 存在频繁写入；
- 需要事务和唯一约束；
- 需要关联查询或统计；
- 项目准备长期维护；
- 未来可能扩展多个 API 实例。

建议开发和生产都使用 PostgreSQL，避免 SQLite 与 PostgreSQL 的行为差异。

---

## 8. Git 管理规范

### 8.1 分支策略

采用简单的主干开发模式：

```text
main
├── feature/user-management
├── feature/login
├── fix/token-refresh
├── docs/deployment-guide
└── chore/add-docker-compose
```

规则：

- `main` 始终保持可部署；
- 每个需求或问题使用独立分支；
- 开发和验证完成后合并回 `main`；
- 不在 `main` 上直接进行大范围开发；
- 多人协作时通过 Pull Request 或 Merge Request 合并。

### 8.2 分支命名

```text
feature/功能名称
fix/问题名称
refactor/重构内容
docs/文档内容
chore/工程任务
```

### 8.3 Commit 规范

使用 Conventional Commits，标题建议使用中文：

```text
feat: 新增用户登录功能
fix: 修复令牌刷新失败问题
refactor: 调整用户查询服务
docs: 补充生产环境部署说明
test: 添加用户接口测试
chore: 增加 Docker Compose 配置
style: 调整登录页面样式
```

一次提交只完成一个相对独立的目标，不将多个无关改动放在同一个提交中。

### 8.4 初始化 Git

```bash
git init
git branch -M main
git add .
git commit -m "chore: 初始化项目"
```

关联远程仓库：

```bash
git remote add origin <仓库地址>
git push -u origin main
```

### 8.5 日常工作流程

```bash
git switch main
git pull

git switch -c feature/user-management

# 开发、测试和检查
git add apps/api
git commit -m "feat: 实现用户管理接口"

git add apps/web
git commit -m "feat: 添加用户管理页面"

git push -u origin feature/user-management
```

随后通过 Pull Request 或 Merge Request 合并到 `main`。

---

## 9. `.gitignore` 示例

```gitignore
# Environment
.env
.env.*
!.env.example

# Python
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.venv/
.coverage
htmlcov/

# Node
node_modules/
dist/
.vite/
coverage/

# IDE
.idea/
.vscode/*
!.vscode/extensions.json
!.vscode/settings.json

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Runtime data
data/
uploads/

# Local Docker overrides
docker-compose.override.yml
```

必须提交 `.env.example`，禁止提交真实 `.env`。

严禁提交：

- 数据库密码；
- JWT 密钥；
- Cloudflare Token；
- 服务器私钥；
- 第三方 API Key；
- 数据库备份；
- 用户上传文件；
- 生产环境配置。

---

## 10. Docker Compose 示例

```yaml
services:
  web:
    build:
      context: ../apps/web
    ports:
      - "127.0.0.1:3000:80"
    restart: unless-stopped

  api:
    build:
      context: ../apps/api
    env_file:
      - ../.env
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test:
        - CMD-SHELL
        - pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  postgres_data:
```

**统一网络方案：所有容器只绑回环地址，禁止容器 IP 直连。**

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

- 所有需要宿主机访问的服务（Web、API 等）一律绑定 `127.0.0.1:端口`，反向代理只通过回环地址访问；
- 禁止用容器 IP（如 `172.x.x.x`）作为反代目标：容器重建后 IP 漂移，OpenResty / 1Panel 里的旧 IP 失效，表现为反代 502；
- 1Panel 面板配置反向代理时，目标地址同样填写 `127.0.0.1:端口`，不要从容器列表复制容器 IP；
- 宿主机端口只绑回环地址，避免绕过 OpenResty 直接暴露到公网；
- PostgreSQL 不映射宿主机端口，只允许 Docker 内部访问；若本机管理工具需要直连，同样只绑 `127.0.0.1:5432:5432`，不暴露到 `0.0.0.0`。

**配置与密钥单一来源：**

- 所有密钥只放 `.env`（服务器上 `chmod 600`），不写死在 compose、不进 1Panel GUI 字段；
- 派生连接串在 compose 中用 `${VAR}` 组合（如 `DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}`），避免同一密码出现两处；
- 注意 1Panel 生成的 compose 可能没有 `env_file: .env`（只有 image/ports/restart），容器内环境变量为空会导致应用崩溃循环（反代 502）。用 `docker inspect <容器> --format '{{range .Config.Env}}{{println .}}{{end}}'` 确认注入，补 `env_file: .env` 后必须 `docker compose up -d` 重建（`restart` 不会重新读取 env_file）；
- JWT_SECRET / 加密密钥必须固定并备份：空值或每次启动都变，重启后会话、TOTP、加密数据全部失效。

健康检查、升级与备份等日常运维见 [`1panel-compose-and-ops.md`](1panel-compose-and-ops.md)。

---

## 11. OpenResty 示例

OpenResty 只进行路径转发，不重写 API 路径：

```nginx
server {
    listen 443 ssl http2;
    server_name app.example.com;

    client_max_body_size 20m;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 10s;
        proxy_read_timeout 60s;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

FastAPI 自身保留 `/api/v1` 前缀：

```python
app.include_router(api_router, prefix="/api/v1")
```

请求 `/api/v1/users` 时，FastAPI 仍收到 `/api/v1/users`。

在 1Panel 面板中配置反向代理时，目标地址同样填写 `127.0.0.1:8000` / `127.0.0.1:3000`，不要使用容器 IP：容器重建后 IP 漂移，反代会 502。

**流式 / WebSocket 端点（SSE、LLM 流式输出、实时推送）需要额外配置：**

```nginx
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 流式响应：禁缓冲，长超时
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
        gzip off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        send_timeout 3600s;

        # WebSocket（实时推送、终端、协作类）
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
```

- 这些指令合并进现有 `location` 即可，不要在 1Panel 生成的站点里新增重复的 `location /`；
- 应用需要带下划线的请求头（如 `session_id`）时，在 `http {}` 块加 `underscores_in_headers on;`，否则头会被丢弃；
- 以上只解决源站侧缓冲与本地超时，Cloudflare 有 120 秒代理上限，更长的任务见 [`cloudflare-streaming-and-tls.md`](cloudflare-streaming-and-tls.md) 的灰云方案。

---

## 12. Cloudflare 配置原则

Cloudflare 只作为外层反向代理：

```text
app.example.com → 服务器公网 IP
代理状态：已代理
SSL/TLS：Full (strict)
```

推荐链路：

```text
浏览器 HTTPS
    ↓
Cloudflare
    ↓ HTTPS
OpenResty
    ↓ HTTP（本机回环地址）
Web / API 容器
```

不要使用 Flexible SSL，避免源站明文通信和 HTTPS 重定向循环。

**灰云（仅 DNS）注意事项：**

- 切到"仅 DNS"后，Cloudflare Origin CA 证书对直连客户端无效（报 `unable to get local issuer certificate`），每个灰云域名必须装公开受信证书（Let's Encrypt）；不要用 `-k` / 关闭证书校验绕过；
- 流式/长连接 API 建议用独立灰云子域（如 `direct-api.example.com`）给 API 客户端，网页域名保持橙云；
- 524 是源站 120 秒内未返回完整响应，不是 Cloudflare 故障：记下 CF-Ray 与时间戳，关联源站 Nginx/应用日志，再用 `curl --resolve 域名:443:<源站IP>` 直连对比；应用自称低 TTFB 但 524 时，检查 Nginx 是否缓冲了响应没吐给 Cloudflare。完整诊断见 [`cloudflare-streaming-and-tls.md`](cloudflare-streaming-and-tls.md)。

---

## 13. 1Panel Compose 项目与日常运维

- 想让 1Panel 管理生命周期：面板 → 容器 → 编排 → 创建编排 → 编辑，粘贴 compose 内容创建（项目 source 显示 `1Panel`）；宿主机建目录再"选择路径"导入的显示为 `Local`，面板生命周期控制少；
- `.env` 在首次启动前放在 Compose 工作目录；"拉取镜像"是创建后/升级时才用的操作，不能替代保存/创建编排；
- 健康检查、升级（`docker compose pull && docker compose up -d`）、备份三件套（compose + `.env` + `pg_dump`）与故障排查（502、TLS 循环、会话失效）详见 [`1panel-compose-and-ops.md`](1panel-compose-and-ops.md)。

---

## 14. Vibe Coding 开发约束

### 14.1 先写最小需求规格

每个功能至少明确：

- 目标；
- 数据字段；
- 业务规则；
- API；
- 页面；
- 权限；
- 验收条件。

不要只给 AI 一个宽泛要求，例如“实现完整的用户管理”。

### 14.2 每次只完成一个可验证任务

推荐顺序：

```text
1. 设计数据模型和迁移
2. 实现后端接口
3. 添加后端测试
4. 生成前端类型
5. 实现前端页面
6. 执行端到端验证
7. 提交 Git
```

### 14.3 强制质量检查

前端：

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

后端：

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

数据库迁移：

```bash
uv run alembic revision --autogenerate -m "新增用户表"
uv run alembic upgrade head
```

### 14.4 不提前引入复杂设施

第一版不建议加入：

- Kubernetes；
- 微服务；
- Kafka；
- Elasticsearch；
- GraphQL；
- CQRS；
- 事件溯源；
- 自研权限引擎；
- 多数据库兼容层。

Redis、异步任务、WebSocket 等组件应在出现明确需求后再加入。

---

## 15. 推荐实施顺序

```text
1. 初始化项目目录和 Git 仓库
   验证：完成首个提交

2. 初始化 Vue 3 前端
   验证：开发页面可以打开，生产构建成功

3. 初始化 FastAPI 后端
   验证：GET /api/v1/health 返回成功

4. 加入 PostgreSQL 和 Alembic
   验证：数据库连接正常，迁移可以执行

5. 加入 Docker Compose
   验证：web、api、postgres 均正常运行

6. 配置 OpenResty
   验证：同一域名可以访问页面和 API

7. 配置 Cloudflare
   验证：公网 HTTPS 可以完整访问

8. 建立远程 Git 仓库和合并流程
   验证：功能分支可以通过 PR/MR 合并

9. 开始实现第一个实际业务功能
```

每完成一个阶段，执行对应检查并创建独立 Git 提交。

---

## 16. 最终方案总结

```text
前端：
Vue 3 + TypeScript + Vite
Element Plus + Tailwind CSS
Vue Router + Pinia + Axios
pnpm

后端：
FastAPI + Pydantic
SQLAlchemy 2 + Alembic
PostgreSQL + psycopg 3
uv + Ruff + Pytest

部署：
Docker + Docker Compose
1Panel
Cloudflare + OpenResty（仅反向代理）

管理：
Git + GitHub/GitLab/Gitea
```

核心原则：

> 从模块化单体开始，以类型、测试、文档和 Git 提交约束 AI 生成代码；不提前微服务化，不引入没有明确业务需求的基础设施。
