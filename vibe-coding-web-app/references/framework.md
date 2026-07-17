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

关键安全设置：

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

Web 和 API 端口只绑定到本机回环地址，避免绕过 OpenResty 直接暴露到公网。PostgreSQL 不映射宿主机端口，只允许 Docker 内部访问。

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

---

## 13. Vibe Coding 开发约束

### 13.1 先写最小需求规格

每个功能至少明确：

- 目标；
- 数据字段；
- 业务规则；
- API；
- 页面；
- 权限；
- 验收条件。

不要只给 AI 一个宽泛要求，例如“实现完整的用户管理”。

### 13.2 每次只完成一个可验证任务

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

### 13.3 强制质量检查

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

### 13.4 不提前引入复杂设施

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

## 14. 推荐实施顺序

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

## 15. 最终方案总结

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
