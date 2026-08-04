#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主机密钥指纹核对工具 — 新环境首次接入前必须执行

所有连接都使用严格 Host Key 校验（RejectPolicy / StrictHostKeyChecking=yes），
未记录指纹的新主机第一次连接必然失败。本工具负责「获取 → 核对 → 记录」这一环：

用法：
    # 获取服务器指纹（只读取，不写入任何文件）
    uv run --project ~/.claude/skills/sshops python ~/.claude/skills/sshops/scripts/verify_host_key.py <IP或主机名> [--port <端口>]

    # 与可信渠道核对指纹一致后，记录到 ~/.ssh/known_hosts
    uv run --project ~/.claude/skills/sshops python ~/.claude/skills/sshops/scripts/verify_host_key.py <IP或主机名> --port <端口> --confirm

    # 从 known_hosts 移除某主机（回滚 / 更换主机时）
    uv run --project ~/.claude/skills/sshops python ~/.claude/skills/sshops/scripts/verify_host_key.py --remove <IP或主机名> [--port <端口>]
"""

import argparse
import base64
import hashlib
import os
import subprocess
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_script_dir, 'lib'))
from security import audit_command, validate_port, validate_ssh_config_value


def known_hosts_path():
    return os.path.expanduser("~/.ssh/known_hosts")


def entry_name(host, port):
    """known_hosts 条目名：非 22 端口使用 [host]:port 形式（paramiko/OpenSSH 通用）"""
    return f"[{host}]:{port}" if port != 22 else host


def parse_keyscan_output(text):
    """
    解析 ssh-keyscan 输出，返回 (keytype, blob) 列表。
    每行格式为 "<host> <keytype> <base64-blob> [comment]"，
    键名由调用方按 entry_name() 生成，不信任 keyscan 输出的主机名前缀。
    """
    keys = []
    for line in text.splitlines():
        parts = line.split()
        for i, field in enumerate(parts):
            if field.startswith(('ssh-', 'ecdsa-', 'sk-')):
                # 类型字段后的第一个字段即 base64 blob
                if i + 1 < len(parts):
                    keys.append((field, parts[i + 1]))
                break
    return keys


def sha256_fingerprint(key_blob):
    """计算 OpenSSH 风格的 SHA256 指纹（与 ssh-keygen -lf 一致）"""
    digest = hashlib.sha256(base64.b64decode(key_blob)).digest()
    return "SHA256:" + base64.b64encode(digest).decode('ascii').rstrip('=')


def _lines_matching(host, port, lines):
    """返回 known_hosts 中匹配该主机的行（明文条目）"""
    names = {entry_name(host, port)}
    if port == 22:
        names.add(host)
    matches = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        first = stripped.split()[0]
        if first in names:
            matches.append(line)
    return matches


def entry_exists(host, port):
    path = known_hosts_path()
    if not os.path.exists(path):
        return False
    with open(path, 'r', encoding='utf-8') as f:
        return bool(_lines_matching(host, port, f.readlines()))


def scan(host, port, timeout=5):
    """执行 ssh-keyscan，返回 (退出码, 原始输出)"""
    result = subprocess.run(
        ['ssh-keyscan', '-T', str(timeout), '-p', str(port), host],
        capture_output=True, text=True
    )
    return result.returncode, result.stdout


def record(host, port, confirmed=False):
    """获取指纹；--confirm 且已核对一致时写入 known_hosts"""
    exit_code, output = scan(host, port)
    keys = parse_keyscan_output(output)
    if not keys:
        print(f"错误: 无法从 {host}:{port} 获取主机密钥（网络不通、端口未开放或返回码 {exit_code}）")
        return False

    fingerprints = sorted(set(sha256_fingerprint(blob) for _, blob in keys))
    print(f"{host}:{port} 的主机指纹：")
    for fp in fingerprints:
        print(f"  {fp}")

    if entry_exists(host, port):
        print(f"已在 known_hosts 中，无需重复添加")
        return True

    if not confirmed:
        print(f"提示: 请与可信渠道（云控制台/运维工单/同事）核对上述指纹；")
        print(f"确认一致后重新执行并追加 --confirm 写入 ~/.ssh/known_hosts")
        return False

    name = entry_name(host, port)
    new_lines = [f"{name} {keytype} {blob}\n" for keytype, blob in keys]
    path = known_hosts_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            existing = f.readlines()
        # 避免重复行
        existing_names = {line.strip().split()[0] for line in existing if line.strip() and not line.strip().startswith('#')}
        if name in existing_names:
            print(f"已在 known_hosts 中，无需重复添加")
            return True
        new_lines = existing + new_lines
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print(f"✓ 指纹已记录到 {path}（{len(keys)} 个密钥条目）")
    return True


def remove(host, port):
    """从 known_hosts 移除该主机的所有明文条目"""
    path = known_hosts_path()
    if not os.path.exists(path):
        print(f"known_hosts 不存在: {path}")
        return True
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    remaining = [line for line in lines if line not in _lines_matching(host, port, lines)]
    removed = len(lines) - len(remaining)
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(remaining)
    print(f"{'✓' if removed else '!'} 已从 known_hosts 移除 {entry_name(host, port)} 的 {removed} 个条目"
          if removed else f"known_hosts 中没有 {entry_name(host, port)} 的条目")
    return True


def main():
    parser = argparse.ArgumentParser(description='主机密钥指纹核对工具（新环境首次接入必用）')
    parser.add_argument('host', nargs='?', help='IP 或主机名')
    parser.add_argument('--port', type=int, default=22, help='端口（默认 22）')
    parser.add_argument('--confirm', action='store_true',
                        help='确认指纹与可信渠道核对一致，写入 ~/.ssh/known_hosts')
    parser.add_argument('--remove', action='store_true',
                        help='从 known_hosts 移除该主机（回滚）')
    args = parser.parse_args()

    if not args.host:
        parser.print_help()
        sys.exit(1)

    host = validate_ssh_config_value(args.host, 'host', single_token=True)
    port = validate_port(args.port)

    if args.remove:
        success = remove(host, port)
    else:
        success = record(host, port, confirmed=args.confirm)
        audit_command(host, 'verify-host-key', execution='known-hosts',
                      confirmed=args.confirm, outcome={'success': success})

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
