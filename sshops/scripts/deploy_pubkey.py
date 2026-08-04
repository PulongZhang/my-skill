#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deploy a validated OpenSSH public key using password authentication."""

import argparse
import base64
import binascii
import os
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_script_dir, 'lib'))
from security import audit_command


def _validate_public_key(value):
    key = value.strip()
    if any(char in key for char in ('\r', '\n', '\x00')):
        raise ValueError('公钥必须是单行内容')
    parts = key.split()
    if len(parts) < 2 or not parts[0].startswith(('ssh-', 'ecdsa-', 'sk-')):
        raise ValueError('无效的 OpenSSH 公钥格式')
    try:
        base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError('公钥 Base64 内容无效') from exc
    return key


def deploy_pubkey(alias, pubkey_content, key_name, confirmed=False):
    """Deploy one validated key without interpolating key material into shell code."""
    if not confirmed:
        audit_command(alias, 'deploy-public-key', execution='deploy-key', confirmed=False,
                      outcome='confirmation_required')
        print('错误: 部署公钥会修改远程 authorized_keys；请显式添加 --confirm')
        return False
    from config_v3 import SSHConfigLoaderV3
    from paramiko_client import ParamikoClient

    try:
        key = _validate_public_key(pubkey_content)
        encoded_key = base64.b64encode(key.encode('utf-8')).decode('ascii')
        params = SSHConfigLoaderV3().get_connection_params(alias)
        if not params.get('password'):
            print(f"错误: {alias} 没有配置密码，无法使用密码认证部署公钥")
            return False

        client = ParamikoClient(
            host=params['hostname'], user=params['user'], port=params['port'],
            password=params['password'], timeout=30,
        )
        print(f"正在连接到 {alias}...")
        if not client.execute("echo 'Connection OK'").success:
            print(f"错误: 无法连接到 {alias}")
            return False
        if not client.execute("mkdir -p ~/.ssh && chmod 700 ~/.ssh").success:
            print("错误: 无法创建 .ssh 目录")
            return False

        # Base64 is an ASCII token and key content never enters the command grammar.
        decode = f"printf '%s' {encoded_key} | base64 -d"
        exists = client.execute(f"grep -Fx -- \"$({decode})\" ~/.ssh/authorized_keys 2>/dev/null")
        if exists.success and exists.stdout.strip():
            print(f"公钥已存在于 {alias}，无需重复添加")
            return True
        result = client.execute(f"{decode} >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys")
        if not result.success:
            print("错误: 无法写入公钥到 authorized_keys")
            print(f"错误信息: {result.stderr}")
            return False
        print(f"✓ 公钥已成功部署到 {alias}")
        return True
    except Exception as exc:
        print(f"错误: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(description='部署公钥到远程服务器')
    parser.add_argument('alias', help='服务器别名')
    parser.add_argument('--pubkey-file', required=True, help='公钥文件路径')
    parser.add_argument('--key-name', required=True, help='密钥名称（仅用于显示）')
    parser.add_argument('--confirm', action='store_true',
                        help='确认修改远程 authorized_keys')
    args = parser.parse_args()
    pubkey_file = os.path.expanduser(args.pubkey_file)
    if not os.path.exists(pubkey_file):
        print(f"错误: 公钥文件不存在: {pubkey_file}")
        sys.exit(1)
    with open(pubkey_file, 'r', encoding='utf-8') as handle:
        pubkey_content = handle.read()
    success = deploy_pubkey(args.alias, pubkey_content, args.key_name, args.confirm)
    audit_command(args.alias, 'deploy-public-key', execution='deploy-key',
                  confirmed=args.confirm, outcome={'success': success})
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
