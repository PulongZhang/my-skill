# 回环绑定服务的远程访问(VLESS/Reality 隧道)

框架约定所有容器宿主机端口只绑 `127.0.0.1`(见 SKILL.md 部署配置第 2 点)。回环绑定后,服务不再暴露公网,但自用服务(如 CLIProxyAPI :8317、管理后台)仍需要远程访问时,**不要重新开放公网端口**,用已有的 sing-box VLESS/Reality 节点当私有隧道。

## 拓扑

```
本地应用 → 本地 sing-box(mixed/socks inbound)
         → VLESS/Reality outbound(连服务器 :55555)
         → 服务器 sing-box 按端口规则重写目标 → 127.0.0.1:8317
```

## 服务端:端口重写规则(关键)

只改 `/etc/sing-box/config.json` 的 `route` 段,不动 inbound:

```json
{
  "route": {
    "rules": [
      {
        "port": [8317],
        "action": "route-options",
        "override_address": "127.0.0.1",
        "override_port": 8317
      }
    ]
  }
}
```

这样客户端无论拨服务器公网 IP:8317 还是 127.0.0.1:8317 都落到本地服务,客户端配置**无需区分**。

**sing-box 1.13 语法坑**(实测 2026-08,1.13.16):
- `direct` 出站上的 `override_address` / `override_port` 字段已**移除**(1.11 弃用,1.13 删除),报错 `destination override fields in direct outbound are deprecated ... removed in sing-box 1.13.0, use route options instead`;
- 规则 `action` 是**字符串**(`"route-options"`),不是对象——`{"type": "redirect"}` 会报 `cannot unmarshal object into Go struct field _RuleAction.action of type string`;
- 改完必须 `sing-box check -c /etc/sing-box/config.json -C /etc/sing-box/conf` 通过再 `systemctl restart sing-box`。

## 客户端

本地 sing-box 配置:socks/mixed inbound + VLESS outbound(Reality),route 规则把目标端口 8317 的流量送进隧道,其余直连:

```json
{
  "route": {
    "rules": [
      { "port": [8317], "outbound": "vless-out" }
    ],
    "final": "direct"
  }
}
```

注意:多数客户端默认绕过回环地址,规则必须显式按 `port` 匹配,否则应用直连本地端口,隧道根本没被用到。

客户端 `public_key` 用**不带 `=` 填充**的 base64url(X25519 公钥,可从服务端私钥推导),带填充会报 `illegal base64 data`。

## 端到端验证

服务器上起一个客户端实例指向 `127.0.0.1:55555`(公钥从服务端 private_key 推导),然后分别经隧道拨公网 IP 和回环地址,两个都必须是 HTTP 200:

```bash
curl -s -o /dev/null -w '%{http_code}\n' --socks5-hostname 127.0.0.1:10808 http://<公网IP>:8317/
curl -s -o /dev/null -w '%{http_code}\n' --socks5-hostname 127.0.0.1:10808 http://127.0.0.1:8317/
```

## 为什么不是其他方案

- **重新绑 0.0.0.0 / 开防火墙端口**:回到公网裸奔,与框架约定冲突;
- **仅依赖客户端拨 127.0.0.1**:可行,但已有客户端配置都拨公网 IP 时会全部失效;服务端重写规则对两种拨法都兼容,是兼容性最强的落点;
- **SSH 隧道**:临时可行,但没有走已有的 Reality 加密隧道,多一套凭据和会话管理。

## 安全边界

- 重写规则只作用于**隧道内**到目标端口的流量,公网直连依然被回环绑定拒绝;
- 服务仍只监听 127.0.0.1,docker 端口映射不公开;
- 隧道本身有 Reality 认证(uuid),未授权客户端无法进入。
