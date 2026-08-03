# GitHub Actions 镜像构建与 ghcr.io 发布

个人项目部署到 VPS（Docker Compose + 隧道）时，镜像发布的经验总结。来自 TuneBox 项目的实际踩坑。

## 核心原则

1. **不要每次 push 自动构建镜像**。自动构建会让 ghcr 版本无限堆积（每个 push 一个版本）。改用 `workflow_dispatch` 手动触发，需要发版时点一次。
2. **版本号单一来源**。版本号从代码里读取（如 FastAPI 的 `version="x.y.z"` 字段），构建时提取为 `v<版本号>` tag，避免在 CI 里手工填版本导致对不上。
3. **`latest` 作为可滚动指针**。每次构建同时推 `latest` + `:v<版本号>`，latest 自动指向最新版，部署方永远拉 latest。
4. **自动清理旧版本**。构建后用 `actions/delete-package-versions` 保留最近 N 个版本，防止 ghcr 版本堆积。

## 完整工作流示例

```yaml
name: Build Docker image

on:
  # 仅手动触发；版本号从代码中自动读取
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v5

      - name: Set up Buildx
        uses: docker/setup-buildx-action@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Read version from code
        id: ver
        run: |
          VERSION=$(grep -oP 'version="\K[0-9.]+' backend/app/__init__.py)
          echo "tag=v$VERSION" >> "$GITHUB_OUTPUT"

      - name: Build and push
        uses: docker/build-push-action@v7
        with:
          context: .
          push: true
          tags: |
            ghcr.io/<user>/<app>:latest
            ghcr.io/<user>/<app>:${{ steps.ver.outputs.tag }}

      - name: Prune old versions
        uses: actions/delete-package-versions@v5
        with:
          package-name: <app>
          package-type: container
          min-versions-to-keep: 3
```

## 踩坑记录

1. **`delete-package-versions` 的引用写法**：它是 GitHub 上的普通 Actions 仓库，必须写 `uses: actions/delete-package-versions@v5`。写成 `ghcr.io/actions/delete-package-versions@v5` 会报 `Unable to resolve action ghcr.io/actions, repository not found`。
2. **ghcr.io 镜像名必须全小写**（含用户名），如 `ghcr.io/pulongzhang/tunebox`。
3. **鉴权**：workflow 内用 `GITHUB_TOKEN` + `packages: write` 权限即可推镜像和删版本，无需额外配置 token。
4. **镜像管理入口**：`https://github.com/users/<user>/packages/container/package/<name>`。每个构建是一个版本；UI 可逐版本删除，批量删除用 GitHub API + PAT（`packages: Read/Write` 权限）。
5. **手动删除所有镜像不影响已拉取镜像的服务器**，但删完后 `docker compose pull` 会失败，直到下次手动构建。

## 部署联动：compose 环境变量注入

镜像代码读环境变量时，注意 **1Panel 生成的 docker-compose.yml 可能没有 `env_file: .env`**（只有 image/container_name/ports/restart），导致容器内环境变量为空、应用启动失败崩溃循环（反向代理表现为 502）。

排查步骤：

```bash
# 容器实际生效的环境变量（看是否注入）
docker inspect <container> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep KEY

# 服务端 compose 是否引用了 .env
cat docker-compose.yml    # 检查是否有 env_file: .env
docker compose config     # 查看解析后的完整配置
```

修复：在 compose 的 service 下补 `env_file: .env` 后 `docker compose up -d` 重建容器（`restart` 不会重新读取 env_file，必须重建）。

## 敏感信息边界

- 真实 API 地址、密钥只放 `.env`（必须 gitignore），`.env.example` 和 README 用占位符；
- 注释里也不要写真实域名（`grep` 会漏网）；提交前检查 `git grep -i <域名>`；
- VPS 部署时 `.env` 在服务器上单独维护，不进仓库。
