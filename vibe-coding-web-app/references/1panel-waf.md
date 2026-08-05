# 1Panel WAF 商业版 GUI 锁与配置文件点火法

个人项目部署到 1Panel 管理的 VPS(OpenResty 容器反代)时,关于 WAF 的实战排查经验。来自核云(154.217.249.57)真实排查:WAF 配置全开却 0 拦截,最终定位为商业版 GUI 锁导致总开关 off,手动改配置点火成功。

## 背景:1Panel WAF 是商业版功能

- 1Panel(开源版)的 **WAF 是商业版(xpack)功能**,GUI 里"网站 → WAF"入口被锁定,提示仅商业版可用。
- 但 **WAF 运行时引擎随 openresty 应用包完整安装**:lua 引擎(`/usr/local/openresty/1pwaf/*.lua`)、规则库(`data/rules/`,漏洞规则 10000+ 条)、`waf.conf` 全部就位。
- 商业授权记录在 `/opt/1panel/db/xpack.db` 的 `licenses` 表(空 = 未授权)。
- 引擎代码里**没有授权校验**(strings 检查所有 lua,无 license/expire/trial 逻辑;唯一的 "expire" 是 acme 证书续期白名单)。GUI 锁的是入口,不是引擎。

## 症状:WAF 配置全开却完全不拦截

排查时发现(验证方法可复用):

```bash
# 1. 全站日志只有 1 条 403,而 404 有 4 万+ 条(攻击扫描)
# 2. 攻击请求(.env 扫描 8600+ 条)全部返回 404 而非 403
# 3. WAF 监控库全部为空(0 记录)
#    /opt/1panel/apps/openresty/openresty/1pwaf/data/db/monitor/*/site_req_logs.db
# 4. 实测验证(关键!):
curl -sk -o /dev/null -w 'HTTP %{http_code}\n' \
  --resolve api.example.com:443:127.0.0.1 -H 'Host: api.example.com' \
  'https://api.example.com/?id=1%20and%201=1'   # SQLi -> 200 放行 = WAF 失效
```

注意:`curl -k https://127.0.0.1` 直接打会被 default server 的 `ssl_reject_handshake on` 拒绝(exit 35),必须 `--resolve 域名:443:127.0.0.1` 带 SNI。

## 根因:global.json 总开关 off

1Panel WAF 有两层开关:

| 文件 | 作用 |
|---|---|
| `data/conf/global.json` | **全局总闸** `waf.state`(GUI 锁死后永远是 off) |
| `data/sites/<域名>/config.json` | 站点级开关(显示 on 也没用,总闸关着全白搭) |

`waf.lua` 里 `is_global_state_on` 检查的就是 global.json,总闸 off → 整个 WAF 直接放行,不拦不记。

## 点火方法(绕过 GUI,免费启用)

```bash
# 1. 备份(必须!)
cp global.json global.json.bak-$(date +%Y%m%d%H%M%S)
cp monitor.json monitor.json.bak-$(date +%Y%m%d%H%M%S)

# 2. 改 global.json: waf.state -> "on"
#    顺带建议开启(默认都是 off):
#    - notFoundCount.state: "on"  (404 风暴:30次/10秒 -> 封IP 600秒)
#    - cc.state: "on"             (CC 防护:100次/10秒 -> 封IP)
#    - attackCount.state: "on"    (攻击频率:10次/60秒 -> 封IP 3000秒)
#    - vuln.state: "on"           (漏洞规则库 10000+ 条)

# 3. 改 monitor.json: state -> "on"  (流量/攻击监控入库)

# 4. reload openresty(配置在容器里,nginx.conf include 了 waf.conf)
docker exec 1Panel-openresty-tAPf nginx -t
docker exec 1Panel-openresty-tAPf nginx -s reload
```

用 Python 改 JSON 而非 sed(嵌套结构安全)。

## 验证

点火后实测矩阵(正常首页 200,攻击全 403):

```bash
R='--resolve api.example.com:443:127.0.0.1'; H='Host: api.example.com'
curl -sk -o /dev/null -w '%{http_code}\n' $R -H "$H" https://api.example.com/            # 200 正常
curl -sk -o /dev/null -w '%{http_code}\n' $R -H "$H" 'https://api.example.com/?id=1%20and%201=1'  # 403
curl -sk -o /dev/null -w '%{http_code}\n' $R -H "$H" 'https://api.example.com/?id=sleep(5)'        # 403
curl -sk -o /dev/null -w '%{http_code}\n' $R -H "$H" 'https://api.example.com/?q=%3Cscript%3Ealert(1)%3C/script%3E'  # 403
curl -sk -o /dev/null -w '%{http_code}\n' $R -H "$H" https://api.example.com/.env         # 403
```

监控库开始增长(`site_req_logs` 表有记录)即引擎确认生效。`error.log` 无 lua 报错。

## 已知限制与坑

1. **GUI 仍显示未授权**:在面板做网站/WAF 操作时,1Panel 可能把配置同步回 off(面板是权威源)。WAF 又失效时,重改 global.json 的 state 再 reload 即可。
2. **规则覆盖度有限**:如 `union select` 裸词不拦(规则只匹配 `select(`、`sleep(` 等带括号形式)。补规则需手改 `data/rules/` 下的 json,裸词进黑名单误伤大,不建议。
3. **日志格式注意**:openresty 的 access_log 带 `$http_x_forwarded_for`,若站点走 CDN,按 `$remote_addr` 封禁会误封 CDN 节点。当前直连流量按 remote_addr 没问题。
4. **站点独立日志**:1Panel 每个站点有独立 access_log(如 `/www/sites/<域名>/log/access.log`),全局 `/var/log/nginx/access.log` 只记录 default server 的裸流量。
5. **fail2ban 兜底**:若 WAF 拦截效果不足(如扫描仍刷屏),可给 fail2ban 加 nginx jail(404 风暴 + 攻击特征正则),与 WAF 功能重叠但双保险。完整配置见 [`fail2ban-nginx-jail.md`](fail2ban-nginx-jail.md)。
6. **默认 server 加固**:`ssl_reject_handshake on` + 站点敏感文件 location 正则(挡 .env/.git/.svn 等)是 1Panel 自带的,与 WAF 无关,保留。

## 路径速查(1Panel openresty 应用)

- 容器:`1Panel-openresty-tAPf`(host 网络,宿主看不到 `/usr/local/openresty`,要 docker exec)
- 宿主配置根:`/opt/1panel/apps/openresty/openresty/`
- WAF 数据:`.../1pwaf/data/`(挂载到容器 `/usr/local/openresty/1pwaf/data`)
- 关键文件:`conf/global.json`(总闸)、`conf/monitor.json`(监控)、`conf/sites.json`(站点列表)、`conf/siteConfig.json`(默认站点配置)
- 站点规则:`data/sites/<域名>/rules/*.json`(可覆盖全局)、`data/rules/*.json`(全局)
- 监控库:`data/db/monitor/<域名>/site_req_logs.db`
- 授权库:`/opt/1panel/db/xpack.db` 的 `licenses` 表
