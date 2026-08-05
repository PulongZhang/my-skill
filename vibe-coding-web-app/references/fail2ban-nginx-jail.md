# fail2ban 防护:SSH jail 现状与 nginx jail 配置

1Panel + OpenResty 部署的 VPS 上,fail2ban 的实战经验。来自核云(154.217.249.57)真实排查:SSH jail 正常运转(累计 741 次封禁),Web 层当时没有任何 jail,扫描攻击量大。

## 现状诊断(命令可直接复用)

```bash
fail2ban-client status                      # 所有 jail
fail2ban-client status sshd                 # 指定 jail 详情(当前/累计封禁、IP 列表)
```

核云当时输出:`Number of jail: 1`(只有 sshd),累计 741 次封禁、当前 6 个 IP 在封。这说明端口 22 对公网开放,被全球扫描器持续爆破。

## 判断 Web 层是否需要 jail

先分析 openresty 访问日志,用数据说话:

```bash
# 状态码分布(404 数量是攻击信号的直接指标)
awk '{print $9}' /opt/1panel/apps/openresty/openresty/log/access.log | grep -E '^[0-9]+$' | sort | uniq -c | sort -rn

# 404 攻击源 Top
grep ' 404 ' <日志> | awk '{print $1}' | sort | uniq -c | sort -rn | head -20

# 攻击特征请求(挖矿 payload、.env 泄露扫描等)
grep -c 'wget.sh\|mining\|xmrig' <日志>
```

核云实例:404 共 42,230 条(正常 200 仅 10,360),其中 25,742 条带攻击特征;43 条挖矿木马下载请求(`91.92.40.118/wget.sh`、`/tmUnblock.cgi`、`/sysinfo.cgi`——典型 IoT 僵尸网络)。结论:Web 层确实需要兜底防护。

## nginx jail 配置

优先让 1Panel WAF(如已点火)接管,它自带 404 风暴检测(30次/10秒→封600秒)和 CC 防护,与 fail2ban 功能重叠。**若 WAF 不可用或拦截不足,再叠加 fail2ban nginx jail 双保险。**

### filter 文件

`/etc/fail2ban/filter.d/nginx-404.conf`:

```ini
[Definition]
failregex = ^<HOST> -.*"(GET|POST|HEAD).*" 404
ignoreregex =
```

`/etc/fail2ban/filter.d/nginx-scan.conf`(攻击特征,按实际日志调整):

```ini
[Definition]
failregex = ^<HOST> -.*"(GET|POST|HEAD) .*(\.env|\.git|\.svn|passwd|wget\.sh|xmrig|wp-admin|/tmUnblock\.cgi|/sysinfo\.cgi|\.php\?).*"
ignoreregex =
```

### jail 配置

`/etc/fail2ban/jail.d/nginx.conf`:

```ini
[nginx-404]
enabled = true
port = http,https
filter = nginx-404
logpath = /opt/1panel/apps/openresty/openresty/log/access.log
maxretry = 20
findtime = 60
bantime = 3600
action = iptables-multiport[name=nginx-404, port="http,https"]

[nginx-scan]
enabled = true
port = http,https
filter = nginx-scan
logpath = /opt/1panel/apps/openresty/openresty/log/access.log
maxretry = 3
findtime = 60
bantime = 86400
action = iptables-multiport[name=nginx-scan, port="http,https"]
```

```bash
systemctl reload fail2ban    # 或 fail2ban-client reload
fail2ban-client status nginx-404
```

## 关键坑

1. **日志路径**:1Panel openresty 的访问日志在 `/opt/1panel/apps/openresty/openresty/log/access.log`(站点独立日志在 `/www/sites/<域名>/log/`),不是标准 `/var/log/nginx/access.log`。
2. **`$http_x_forwarded_for` 与 CDN**:日志格式带 X-Forwarded-For 字段。站点走 CDN 时按 `$remote_addr` 封会误封 CDN 节点,殃及所有用户;需改按 XFF 取真实 IP 的 filter。当前核云流量直连,按 remote_addr 无问题。
3. **404 风暴阈值**:20次/60秒对扫描器足够敏感,正常用户几乎不可能触发(浏览器一次页面加载最多几个请求)。用 `fail2ban-client set <jail> unbanip <IP>` 可手动解封误伤。
4. **与 WAF 的边界**:WAF 按应用层规则拦截(立即、精确);fail2ban 按日志统计封 IP(滞后、粗暴)。两者不冲突,先 WAF 后 fail2ban 的叠加顺序最稳。
5. **jail 数量不多**:fail2ban 一个 jail 绑定一个服务的日志(一个"门卫"守一个"门")。只有公网暴露的服务需要 jail;容器全部绑定 127.0.0.1 的内部服务不用配。
