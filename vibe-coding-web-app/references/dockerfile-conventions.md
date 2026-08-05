# Dockerfile 编写规范

与 [`github-actions-image-build.md`](github-actions-image-build.md) 配合使用：本文件规定镜像怎么写，那篇规定怎么发。

## 核心原则

1. **多阶段构建**：依赖安装和构建放在构建阶段，运行阶段只保留产物和最小运行时。
2. **锁定依赖**：前端 `pnpm install --frozen-lockfile`，后端 `uv sync --frozen`，不重新解析锁文件。
3. **缓存友好**：`COPY` 按变化频率从低到高排列——先复制依赖清单和锁文件装依赖，最后复制业务代码，代码改动不破坏依赖层缓存。
4. **运行阶段最小化**：只拷贝构建产物、虚拟环境和应用代码，不包含源码包管理工具。
5. **基础镜像版本固定**：示例用大版本号（如 `node:22-alpine`、`python:3.13-slim`），滚动 tag（`nginx:alpine`、`uv:latest`）在需要可复现构建时固定到具体大版本。
6. **配 `.dockerignore`**：放在各构建上下文目录（`apps/web`、`apps/api`），排除不会进镜像的内容：

```dockerignore
node_modules/
.venv/
dist/
__pycache__/
.git/
.env
```

## 前端 web（Nginx 提供静态文件）

```dockerfile
# 构建阶段
FROM node:22-alpine AS build
WORKDIR /app
RUN npm install -g pnpm@10
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# 运行阶段
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- 容器内监听 80，与 Compose `127.0.0.1:3000:80` 对应；
- nginx 主进程以 root 运行是官方镜像默认（只读静态文件，风险低）；若要求完全非 root，改用 `nginxinc/nginx-unprivileged`，内部端口相应改为 8080。

## 后端 api（uv 管理依赖）

```dockerfile
# 构建阶段：安装生产依赖
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 运行阶段
FROM python:3.13-slim
COPY --from=builder /app/.venv /app/.venv
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser
USER appuser
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- `uv sync --frozen`：严格按 `uv.lock` 安装，`--no-dev` 不装开发依赖，`--no-install-project` 不安装项目自身（业务代码用 `COPY` 进入，依赖层保持缓存）；
- 业务代码（`app/`）最后 `COPY`，且以非 root 用户（uid 10001）运行应用；
- 容器内监听 8000，与 Compose `127.0.0.1:8000:8000` 对应。

## 注意

- 多镜像 monorepo 在 CI 构建时分别指定 `dockerfile` 和 `context`（`apps/web`、`apps/api`），不要把整个仓库作为构建上下文；
- api 镜像可在 Compose 中加 healthcheck 命中 `GET /api/v1/health`，与现有 postgres healthcheck 保持同一风格；
- 修改依赖后必须更新锁文件并提交，镜像构建才能通过 `--frozen-lockfile` / `--frozen` 校验。
