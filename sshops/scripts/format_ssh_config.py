#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 ~/.ssh/config 规范化到标准格式

格式定义只在本脚本依赖的 lib/ssh_config_format.py，改动管理脚本与手工编辑
产生的格式漂移都可以用本脚本收敛回去。幂等：已规范的配置不会产生任何改动。

用法：
    # 查看将要发生的改动（默认 dry-run，不写文件）
    uv run --project ~/.claude/skills/sshops python ~/.claude/skills/sshops/scripts/format_ssh_config.py

    # 实际写入
    uv run --project ~/.claude/skills/sshops python ~/.claude/skills/sshops/scripts/format_ssh_config.py --write

    # 只检查是否符合规范（CI / 提交前门禁）：不符合则退出码 1
    uv run --project ~/.claude/skills/sshops python ~/.claude/skills/sshops/scripts/format_ssh_config.py --check
"""

import argparse
import difflib
import json
import os
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_script_dir, 'lib'))

from ssh_config_format import format_config_file, format_config_text


def main():
    parser = argparse.ArgumentParser(description='规范化 SSH config 格式（幂等）')
    parser.add_argument('--config', default=None, help='SSH config 路径（默认 ~/.ssh/config）')
    parser.add_argument('--write', action='store_true', help='写入文件（默认只显示 diff）')
    parser.add_argument('--check', action='store_true', help='只检查：不符合规范时以退出码 1 结束')
    args = parser.parse_args()

    config_path = args.config or os.path.expanduser('~/.ssh/config')
    if not os.path.exists(config_path):
        print(json.dumps({'success': False, 'error': f'配置文件不存在: {config_path}'},
                         ensure_ascii=False))
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8', newline='') as handle:
        original = handle.read()

    if args.check:
        changed = format_config_file(config_path, dry_run=True)
        print(json.dumps({'success': not changed, 'path': config_path, 'changed': changed},
                         ensure_ascii=False, indent=2))
        sys.exit(1 if changed else 0)

    if args.write:
        changed = format_config_file(config_path)
        formatted = original
        diff_lines = []
        if changed:
            with open(config_path, 'r', encoding='utf-8', newline='') as handle:
                formatted = handle.read()
            diff_lines = list(difflib.unified_diff(
                original.splitlines(), formatted.splitlines(),
                fromfile=config_path, tofile=config_path + ' (formatted)', lineterm=''))
    else:
        formatted = format_config_text(original)
        changed = formatted != original
        diff_lines = list(difflib.unified_diff(
            original.splitlines(), formatted.splitlines(),
            fromfile=config_path, tofile=config_path + ' (formatted)', lineterm=''))

    if changed:
        print('\n'.join(diff_lines))
    print(json.dumps({
        'success': True,
        'path': config_path,
        'changed': changed,
        'written': bool(args.write and changed),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
