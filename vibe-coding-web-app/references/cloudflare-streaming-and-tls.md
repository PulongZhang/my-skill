# Cloudflare 灰云(DNS-only)与流式 API 反代

LLM 网关、SSE/WebSocket 类 API 部署到 Cloudflare + OpenResty 后的实战排查经验。来自 Sub2API(LLM 网关)部署与 Cloudflare 524 真实排查。

## 灰云(DNS-only)的证书坑

- **Cloudflare Origin CA 证书只在"橙云(已代理)"时有效**。把域名切到"仅 DNS(灰云)"后,客户端直连源站会报 `unable to get local issuer certificate` / `SSL certificate verification failed`。
- 规则:**每个 DNS-only 的 API 域名必须装公开受信证书(Let's Encrypt)**,不要用 `-k` / `NODE_TLS_REJECT_UNAUTHORIZED=0` 绕过。
- 推荐拓扑:流式/长连接 API 用独立 DNS-only 子域(如 `direct-api.example.com`)给 API 客户端,原域名保持橙云给网页流量。

## 524 不是 Cloudflare 宕机

524 = Cloudflare 在默认 120 秒 Proxy Read Timeout 内没收到源站完整响应。这是**源站慢或代理缓冲问题**,不是 DNS/网络故障。

诊断步骤:

1. 记下报错页的 **CF-Ray 和时间戳**;
2. 关联源站 Nginx access/error log、应用容器日志、CPU/内存占用、队列时间;
3. 直连对比:`curl --resolve 域名:443:<源站IP> https://域名/...`;
4. 应用声称 TTFB 很低但仍 524:确认指标是**外部客户端**测的——应用可能已经发出早期分块,但 Nginx 缓冲着没吐给 Cloudflare。

P95 总延迟接近 120 秒就很危险,即使 P95 TTFB 很低;检查 P99/max 和超过 110 秒的请求。

## 流式/WebSocket 反代(OpenResty/Nginx)

合并进现有 proxy location(或所在 server 块),**不要在 1Panel 生成的站点里新增重复的 `location /`**:

```nginx
proxy_http_version 1.1;
proxy_buffering off;
proxy_request_buffering off;
proxy_cache off;
gzip off;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
send_timeout 3600s;
```

WebSocket(实时推送、终端、协作类):

```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

标准头仍然保留:

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

- 以上只解决源站侧缓冲与本地超时,**不能提高 Cloudflare 的 120 秒上限** → 可能超过 120 秒的任务走灰云直连域名。
- 应用需要带下划线的请求头(如 `session_id`)时,在 nginx `http {}` 块加 `underscores_in_headers on;`,否则头会被丢弃,粘性会话等逻辑失效。
- 1Panel 的 OpenResty 若以容器运行且非 host 网络,容器内的 `127.0.0.1` 不是宿主机,先确认到应用容器的路由(host gateway 或共享 Docker 网络)再填反代目标。

## 验证

```bash
# TLS 链与主机名校验,期望 Verify return code: 0 (ok)
openssl s_client -connect direct-api.example.com:443 \
  -servername direct-api.example.com \
  -verify_return_error -verify_hostname direct-api.example.com </dev/null

# 返回 200/401/403 都算 TLS 校验通过
curl -sS -o /dev/null -w '%{http_code}\n' https://direct-api.example.com/v1/models
```
