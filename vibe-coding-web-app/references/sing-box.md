# sing-box(VLESS/Reality 隧道、路由与回环服务访问)

sing-box 相关的完整运维参考:部署布局、VLESS+Reality inbound、路由规则、端口重写(远程访问回环绑定服务)、密钥管理、排障速查。凡涉及 sing-box 配置、路由、隧道访问一律先读本文件。

## 部署布局(systemd + 目录合并)

```
/etc/sing-box/
├── config.json              # 基础配置:log / dns / outbounds / route
├── conf/                    # inbound 分片(可多个),-C 加载
│   └── VLESS-REALITY-55555.json
├── bin/
│   ├── sing-box             # 二进制(官方 release,下载两次比对 sha256)
│   ├── tls.cer / tls.key    # 233boy 遗留,无实际用途
└── sh/                      # 233boy 安装脚本残留,可留可清
```

systemd 启动方式(关键,决定了配置怎么合并):

```
ExecStart=/etc/sing-box/bin/sing-box run -c /etc/sing-box/config.json -C /etc/sing-box/conf
```

- `-c` 基础配置 + `-C` 目录下所有 .json 分片按文件名顺序**深合并**;`outbounds`/`route` 放 config.json,inbound 分片放 conf/,互不冲突;
- 日志:`/var/log/sing-box/access.log`(建议 level `warn`,info 会无限膨胀)。

## VLESS+Reality inbound(conf/ 分片模板)

```json
{
  "inbounds": [
    {
      "tag": "VLESS-REALITY-55555",
      "type": "vless",
      "listen": "::",
      "listen_port": 55555,
      "users": [
        { "flow": "xtls-rprx-vision", "uuid": "<uuid>" }
      ],
      "tls": {
        "enabled": true,
        "server_name": "<sni>",
        "reality": {
          "enabled": true,
          "handshake": { "server": "<sni>", "server_port": 443 },
          "private_key": "<priv_b64>",
          "short_id": ["<8hex>"]
        }
      }
    }
  ]
}
```

要点:
- `flow: xtls-rprx-vision` 客户端必须一致;
- `short_id` 用 `openssl rand -hex 4`(8 位 hex),**绝不能留空数组**——空 short_id 是一键脚本指纹,且客户端 URL 必须带 `sid=` 才能连;
- SNI 选择见 my-skill 本地 skill `proxy-deployment`(TLS1.3+X25519+h2 实测预检,拒绝烂大街 apple/cloudflare 系,因地制宜匹配机房归属)。

## Route 规则(config.json)

```json
{
  "route": {
    "rules": [
      { "port": [8317], "action": "route-options", "override_address": "127.0.0.1", "override_port": 8317 },
      { "ip_cidr": ["10.0.0.0/8"], "outbound": "direct" }
    ]
  }
}
```

- 匹配字段:`port` / `port_range`、`ip_cidr` / `source_ip_cidr`、`domain` / `domain_suffix` / `domain_keyword` / `domain_regex`、`network`、`inbound`、`protocol` 等;
- 命中后两个去向:经典 `outbound`(转发到指定出站),或 `action`(见下);
- 无匹配 → 走默认出站(未指定 final 时取第一个 outbound,通常 `direct`);
- **sing-box ≥1.13 语法**:
  - 规则 `action` 是**字符串**,不是对象:`"action": "route-options"` ✓;`{"type": "redirect"}` ✗ 报 `cannot unmarshal object into Go struct field _RuleAction.action of type string`;
  - `direct` 出站上的 `override_address` / `override_port` 字段已在 1.13 **移除**(1.11 弃用),报错 `destination override fields in direct outbound are deprecated in sing-box 1.11.0 and removed in sing-box 1.13.0, use route options instead`——端口重写一律用 `route-options` action;
  - action 类型:`route`(默认,转发到 outbound)、`route-options`(非终结,改参数后继续路由:override_address/override_port)、`sniff`、`resolve`、`reject`、`hijack-dns`、`bypass`(1.13,auto_redirect 专用)。

## 端口重写:远程访问回环绑定服务

框架约定容器宿主机端口只绑 `127.0.0.1`(见 SKILL.md 部署配置第 2 点)。自用服务(CLIProxyAPI :8317、管理后台)回环绑定后仍需远程访问时,用 sing-box 节点当私有隧道,**不要重新暴露公网端口**。

**拓扑**:本地应用 → 本地 sing-box(socks/mixed inbound)→ VLESS/Reality outbound(连服务器 :55555)→ 服务端 route 重写 → `127.0.0.1:8317`

**为什么必须服务端重写**:客户端通常拨 `服务器公网IP:8317` 进隧道;服务端默认 direct 会直连公网 IP——服务改为只绑回环后这个拨法立即失效(connection refused)。在服务端加 `route-options` 重写,客户端无论拨公网 IP 还是 127.0.0.1 都落到本地服务,**客户端配置完全不用改**。

服务端(config.json):

```json
{
  "route": {
    "rules": [
      { "port": [8317], "action": "route-options", "override_address": "127.0.0.1", "override_port": 8317 }
    ]
  }
}
```

客户端(本地 sing-box):

```json
{
  "inbounds": [ { "type": "socks", "listen": "127.0.0.1", "listen_port": 10808 } ],
  "outbounds": [ { "type": "vless", "server": "<服务器IP>", "server_port": 55555, "uuid": "<uuid>",
    "flow": "xtls-rprx-vision",
    "tls": { "enabled": true, "server_name": "<sni>",
      "utls": { "enabled": true, "fingerprint": "chrome" },
      "reality": { "enabled": true, "public_key": "<pub_b64url>", "short_id": "<8hex>" } } } ],
  "route": { "rules": [ { "port": [8317], "outbound": "vless-out" } ], "final": "direct" }
}
```

客户端坑:
- **多数客户端默认绕过回环地址**,route 规则必须显式按 `port` 匹配,否则应用直连本地端口,隧道根本没被用到;
- `public_key` 用**不带 `=` 填充**的 base64url(X25519 公钥),带填充报 `illegal base64 data`。

## 密钥管理

- 生成新密钥对:`sing-box generate reality-keypair`;
- 从已有 private_key 推导 public_key(python,需 cryptography 库):

```python
import base64
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives import serialization
b = '<priv_b64>'; b += '=' * (-len(b) % 4)
pub = X25519PrivateKey.from_private_bytes(base64.b64decode(b)).public_key() \
    .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
print(base64.b64encode(pub).decode().rstrip('='))
```

- 客户端 pbk 必须与服务端 private_key 配对;升级/优化时**保留 uuid + 密钥对**,只轮换 SNI/short_id,客户端零迁移。

## 端到端验证

改配置后必须验证:

1. `sing-box check -c /etc/sing-box/config.json -C /etc/sing-box/conf` 通过再 `systemctl restart sing-box`;`systemctl is-active sing-box` + `ss -tlnp` 确认监听;
2. **走真实隧道测**(服务器上起一个客户端实例指向 `127.0.0.1:55555`),两条拨法都必须是 HTTP 200:

```bash
curl -s -o /dev/null -w '%{http_code}\n' --socks5-hostname 127.0.0.1:10808 http://<公网IP>:8317/
curl -s -o /dev/null -w '%{http_code}\n' --socks5-hostname 127.0.0.1:10808 http://127.0.0.1:8317/
```

- 服务端日志 `/var/log/sing-box/access.log` 与 `journalctl -u sing-box` 保持干净。

## 排障速查

| 症状 | 原因/修复 |
|------|-----------|
| 改回环绑定后经隧道访问失败 | 服务端缺 `route-options` 端口重写规则(见上),加规则即可 |
| `destination override fields in direct outbound are deprecated ... removed in 1.13.0` | direct 出站 override 字段已删,改用 route 规则的 `route-options` action |
| `cannot unmarshal object into Go struct field _RuleAction.action of type string` | 1.13 的 action 是字符串,不是 `{"type": ...}` 对象 |
| `decode public_key: illegal base64 data` | 客户端 public_key 带了 `=` 填充,去掉 |
| 客户端连不上、服务端无日志 | short_id 不匹配(客户端 URL 缺 `sid=` 或 sid 不同);uuid/flow 不一致 |
| access.log 无限膨胀 | log level 用 `warn`,不用 `info` |

## 安全边界

- 端口重写规则只作用于**隧道内**到目标端口的流量,公网直连依然被回环绑定拒绝;
- 服务只监听 127.0.0.1,docker 端口映射不公开;
- 隧道有 Reality 认证(uuid + 密钥对),未授权客户端无法进入;
- 已有一键脚本痕迹(233boy)的部署,优先改用用户自己的 hardened fork(PulongZhang/sing-box)或手工加固后的配置。
