# 1Panel WAF 社区版功能边界与配置文件点火法

个人项目部署到 1Panel 管理的 VPS(OpenResty 容器反代)时,关于 WAF 的实战排查经验。来自核云(154.217.249.57)真实排查:WAF 配置全开却 0 拦截,最终定位为总开关 off,手动改配置点火成功。

## 社区版 / 商业版功能边界(重要,先分清)

1Panel 开源版(社区版)**自带 WAF,全局设置与网站设置中的基础防护可用**,不需要商业版。商业版独有:

| 商业版独有功能 | 说明 |
|---|---|
| 拦截地图 | 统计并展示 30 天内拦截的地理位置分布 |
| 日志 / 封锁记录 | 攻击日志与封禁记录的查看界面 |
| 地区访问限制(geoRestrict) | 按地理位置限制访问来源 |
| 自定义规则(ACL) | 自定义拦截规则 |
| 自定义拦截页面 | 请求被拦截后的显示页面 |

**社区版即可用(全局设置/网站设置中):** WAF 总开关、SQL 注入、XSS、CC 防护、404 检测(notFoundCount)、攻击频率(attackCount)、漏洞规则库(vuln)、UA/URL/IP 黑白名单、请求参数(args)、Header/Cookie 检查等。这些在 GUI 的"网站 → WAF → 全局设置/网站设置"中直接可配,不需要手动改文件。

**判断 GUI 里某项是否商业版:** 页面/功能入口若提示"仅商业版可用"或显示升级引导,即为商业版;能正常开关的就是社区版功能。不要因为看到某个商业版入口(如拦截地图)被锁,就误以为整个 WAF 不可用。

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
| `data/conf/global.json` | **全局总闸** `waf.state`(GUI 的"全局设置"里对应 WAF 开关) |
| `data/sites/<域名>/config.json` | 站点级开关(GUI 的"网站设置"里对应,显示 on 但总闸 off 则无效) |

`waf.lua` 里 `is_global_state_on` 检查的就是 global.json,总闸 off → 整个 WAF 直接放行,不拦不记。

## 点火方法(首选 GUI,手动改文件为备用)

**首选:GUI 操作(社区版即可,配置会同步到文件,不会被面板重置)**
- 1Panel 面板 → 网站 → WAF → 全局设置:打开 WAF 总开关,按需开启 404 检测(notFoundCount)、CC 防护、攻击频率(attackCount)、漏洞检测(vuln)等。
- 网站设置:确认各站点 WAF 处于"防护中"(protection)。
- 保存后面板自动写入 global.json 并 reload,无需手动改文件。

**备用:手动改文件(GUI 不可用/需批量时)**

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

用 Python 改 JSON 而非 sed(嵌套结构安全)。手动改文件后,若之后在面板里再保存一次 WAF 设置,面板会以 GUI 状态为准重写文件——因此**手动改与 GUI 开的效果最终一致,但以 GUI 为权威源**。

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

1. **GUI 是权威源**:在面板保存 WAF 设置时,1Panel 会以 GUI 状态重写配置文件。手动改文件后若面板又保存过,以面板为准;WAF 意外失效时,先查 global.json 的 state 再 reload 即可。商业版功能(拦截地图、日志查看、地区限制、ACL、自定义拦截页)在社区版 GUI 中不可用,但不影响社区版基础防护的运行。
2. **规则覆盖度有限**:如 `union select` 裸词不拦(规则只匹配 `select(`、`sleep(` 等带括号形式)。补规则需手改 `data/rules/` 下的 json,裸词进黑名单误伤大,不建议。
3. **日志格式注意**:openresty 的 access_log 带 `$http_x_forwarded_for`,若站点走 CDN,按 `$remote_addr` 封禁会误封 CDN 节点。当前直连流量按 remote_addr 没问题。
4. **站点独立日志**:1Panel 每个站点有独立 access_log(如 `/www/sites/<域名>/log/access.log`),全局 `/var/log/nginx/access.log` 只记录 default server 的裸流量。
5. **fail2ban 兜底**:若 WAF 拦截效果不足(如扫描仍刷屏),可给 fail2ban 加 nginx jail(404 风暴 + 攻击特征正则),与 WAF 功能重叠但双保险。完整配置见 [`fail2ban-nginx-jail.md`](fail2ban-nginx-jail.md)。
6. **默认 server 加固**:`ssl_reject_handshake on` + 站点敏感文件 location 正则(挡 .env/.git/.svn 等)是 1Panel 自带的,与 WAF 无关,保留。

## 症状:API 客户端(Claude Code 等)请求被误拦 —— "API Error: 请求拦截"

与"完全不拦截"相反的问题:WAF 太激进,把合法 API 请求当攻击拦了。2026-08 真实案例(核云 `api.654355.xyz` + 圣何塞 `api.puzzle.de5.net` 同款同修)。

**症状特征(可复用判别点):**
- Claude Code 等 agent 客户端用域名(base_url 走 openresty+Cloudflare)调用 → 报 `API Error: 请求拦截` / 状态栏 `● Please run /login`
- 同一个客户端直连 IP:端口 → 完全正常
- 发 `hello` 等纯文本 → 正常;发复杂对话(带代码/skill 内容)→ 被拦
- 浏览器/curl 访问首页正常

**根因:内容检测规则误判。** agent 请求体是任意代码/文档内容,复杂对话必然带 `select(`、`$(...)`、`<script>`、`../../` 等攻击指纹,命中 1Panel WAF 的:
- `args` 规则组(sqlInject / rce / dirFilter 三个特征类都在它下面)
- `xss` 规则

返回 403 + 拦截页(`data/default/forbidden.html`,标题就是 **"请求拦截"**),客户端把页面文字显示成 API Error。

**确认方法(拦截日志):** 社区版 GUI 没有"日志/封锁记录"查看界面(那是商业版),但底层 SQLite 记录全在:

```bash
docker exec 1Panel-openresty-tAPf sh -c 'ls /usr/local/openresty/1pwaf/data/db/waf/'
# attack_logs.db = 拦截记录(外键关联 ips/rules/rule_types/match_values/req_uris 各库)
# docker cp 拉出后 sqlite 联表查,能看到命中规则名(sqlInject/rce/xss)与具体特征
```

**修复:站点级关闭内容检测,保留限频类防护**(GUI 优先:网站 → 该站点 → WAF → 网站设置 → 关 args/sql/xss;手动改文件备用):

```bash
# data/sites/<域名>/config.json 中 args/sql/xss 的 state 改 "off"(用 python 改 JSON,勿 sed),然后:
docker exec 1Panel-openresty-tAPf nginx -s reload
```

- 只关内容检测(args/sql/xss),**保留** CC / notFoundCount / attackCount / UA / URL / 方法黑白名单 —— API 端点上做内容指纹检测必然误伤,限频和扫描拦截仍有价值
- 纯 API 域名(仅 agent/程序调用、有 key 认证)甚至可以站点级 WAF 全关,API key 就是门禁

**验证矩阵(改完必须实测):**

```bash
for p in 'hello' '<script>alert(1)</script>' 'SELECT * FROM users WHERE id=1 OR 1=1' 'read ../../etc/passwd' 'ls -la | grep passwd; cat /etc/shadow'; do
  curl -s -o /dev/null -w "%{http_code} " -X POST https://<域名>/v1/messages \
    -H 'Content-Type: application/json' -H 'x-api-key: test' -H 'anthropic-version: 2023-06-01' \
    -d "{\"model\":\"claude-sonnet-4-5\",\"max_tokens\":64,\"messages\":[{\"role\":\"user\",\"content\":\"$p\"}]}"
done; echo
# 修复前:403(拦截页);修复后:401(到达上游,API key 校验)或 200
```

**注意:** GUI 仍是权威源,面板保存会重写站点配置;多台服务器同构(核云 `1Panel-openresty-tAPf` / 圣何塞 `1Panel-openresty-z2Pf`)修法一致,可批量。

## 路径速查(1Panel openresty 应用)

- 容器:`1Panel-openresty-tAPf`(host 网络,宿主看不到 `/usr/local/openresty`,要 docker exec)
- 宿主配置根:`/opt/1panel/apps/openresty/openresty/`
- WAF 数据:`.../1pwaf/data/`(挂载到容器 `/usr/local/openresty/1pwaf/data`)
- 关键文件:`conf/global.json`(总闸)、`conf/monitor.json`(监控)、`conf/sites.json`(站点列表)、`conf/siteConfig.json`(默认站点配置)
- 站点规则:`data/sites/<域名>/rules/*.json`(可覆盖全局)、`data/rules/*.json`(全局)
- 监控库:`data/db/monitor/<域名>/site_req_logs.db`
- 拦截日志库:`data/db/waf/attack_logs.db`(拦截记录,联 `ips/rules/rule_types/match_values/req_uris` 等库查详情;社区版 GUI 看不到,只能查库)
- 授权库:`/opt/1panel/db/xpack.db` 的 `licenses` 表
