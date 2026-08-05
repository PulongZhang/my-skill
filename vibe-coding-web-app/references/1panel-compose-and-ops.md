# 1Panel Compose 项目与日常运维

个人项目部署到 1Panel 管理的 VPS 时,关于 Compose 项目创建方式、密钥管理和日常运维的实战经验。来自 SubBoost / Sub2API / Wallos 等多次实际部署。

## 创建 Compose 项目的正确方式(让 1Panel 接管生命周期)

- **首选:面板 → 容器 → 编排(Compose)→ 创建编排 → 编辑**,把 `docker-compose.yml` 内容粘贴进去创建。这样项目 source 显示为 `1Panel`,面板能启停、重建、看日志。
- 宿主机手动建好目录(`/opt/1panel/docker/compose/<app>/`)再在面板里"选择路径"导入的,source 显示为 `Local`,面板生命周期控制少。想用面板管理就用前者。
- **`.env` 必须在项目首次启动前就放在 Compose 工作目录里**,再创建/启动项目。
- **"拉取镜像(Pull Image)"是创建之后或升级时才用的操作,不能替代保存/创建编排**——编辑界面没保存就离开,草稿会被丢弃。

## .env 单一密钥来源

- 所有密码、密钥只放 `.env`(提交前 `chmod 600 .env`),不写进 1Panel GUI 字段,不写死在 `docker-compose.yml`。
- 派生值在 Compose 里用 `${VAR}` 组合,避免同一密码出现两处。例如:

```yaml
environment:
  DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
```

- **坑:1Panel 生成的 docker-compose.yml 可能没有 `env_file: .env`**(只有 image/container_name/ports/restart),导致容器内环境变量为空、应用启动失败崩溃循环,反代表现为 502。排查:

```bash
# 容器实际生效的环境变量(看是否注入)
docker inspect <container> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep KEY

# 服务端 compose 是否引用了 .env
cat docker-compose.yml
docker compose config        # 查看解析后的完整配置
```

修复:在 service 下补 `env_file: .env` 后 `docker compose up -d` 重建容器(`restart` 不会重新读取 env_file,必须重建)。

- **JWT_SECRET / 加密密钥必须固定并备份**。空值或每次启动都变,应用重启会重新生成密钥 → 会话全部失效、TOTP 失效、加密数据解不开。

## 健康检查与验证

- 每个服务提供可探测的健康端点(FastAPI 用 `GET /api/v1/health`,其他应用按文档),Compose 里配 `healthcheck`,`depends_on` 用 `condition: service_healthy`。
- 部署后不要只看 `docker compose ps` 的 Up,用 curl 打健康端点:

```bash
docker compose up -d
docker compose ps
curl --fail --show-error http://127.0.0.1:<端口>/<health端点>
```

## 升级

```bash
cd /opt/1panel/docker/compose/<app>
docker compose pull
docker compose up -d
curl -fsS http://127.0.0.1:<端口>/<health端点>
```

- 指定版本升级:先改 `.env` 里的镜像 tag,再 pull/up。
- **注意:某些官方安装器/管理命令(如 SubBoost 的 `subboost update`)会重新下载并覆盖 `docker-compose.yml`**,自定义的 `127.0.0.1` 回环绑定等修改会被冲掉,升级后要复查并重新应用。

## 备份

每次升级或定期备份三件套:

1. `docker-compose.yml`(含自定义修改);
2. `.env`(密钥,必须!丢了 ENCRYPTION_KEY/JWT_SECRET 等价于丢数据);
3. 数据:数据库逻辑备份(`pg_dump --format=custom --compress=6`)或数据目录。

```bash
cd /opt/1panel/docker/compose/<app>
ts=$(date +%F-%H%M%S)
docker compose exec db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6 -f /tmp/app.pgdump'
docker compose cp db:/tmp/app.pgdump "./backups/app-$ts.pgdump"
docker compose exec db rm -f /tmp/app.pgdump
cp .env "./backups/app-env-$ts.backup"
```

`docker compose down` 不会删除 bind-mount 数据;只有故意删目录/卷才会。

## 故障排查

- **502**:容器没起来(看日志)、端口映射没绑对(`docker compose ps` 核对)、反代目标用了容器 IP(重建后漂移 → 一律用 `127.0.0.1:端口`)、env_file 缺失导致启动崩溃循环。
- **HTTPS 重定向循环**:Cloudflare 设成了 Flexible → 改 Full (strict)。
- **登录/会话突然失效**:JWT_SECRET 变了(容器重建后重新生成)。
- **2FA/TOTP 失效**:加密密钥没固定。
- **流式/SSE/长连接断流**:反代 buffering 或 Cloudflare 120s 超时 → 见 [`cloudflare-streaming-and-tls.md`](cloudflare-streaming-and-tls.md)。
- **WAF 不拦截、扫描刷屏**:见 [`1panel-waf.md`](1panel-waf.md) 和 [`fail2ban-nginx-jail.md`](fail2ban-nginx-jail.md)。
