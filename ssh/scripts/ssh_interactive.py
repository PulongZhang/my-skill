#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interactive SSH terminal with strict host-key verification.

The session is intentionally independent from ssh_daemon.py: a local daemon must
never expose a bidirectional terminal channel to other local processes.
"""

import argparse
import os
import select
import signal
import sys
import threading
import time

import paramiko

_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_script_dir, 'lib'))

from config_v3 import SSHConfigLoaderV3
from security import audit_command, configure_host_key_verification


def _terminal_size():
    try:
        return os.get_terminal_size(sys.stdout.fileno())
    except OSError:
        return os.terminal_size((80, 24))


def _connect_client(params, sock=None):
    """Create one strictly verified Paramiko client from parsed config data."""
    client = paramiko.SSHClient()
    configure_host_key_verification(client)
    connect_kwargs = {
        'hostname': params['hostname'], 'port': params['port'],
        'username': params['user'], 'timeout': params.get('timeout', 30),
        'look_for_keys': not bool(params.get('password')),
        'allow_agent': not bool(params.get('password')), 'sock': sock,
    }
    if params.get('password'):
        connect_kwargs['password'] = params['password']
    if params.get('key_file'):
        connect_kwargs['key_filename'] = os.path.expanduser(params['key_file'])
    client.connect(**connect_kwargs)
    return client


def _connect(alias):
    """Connect with the same config source, including one configured ProxyJump."""
    loader = SSHConfigLoaderV3()
    params = loader.get_connection_params(alias)
    proxy_alias = params.get('proxy_jump')
    if not proxy_alias:
        return _connect_client(params), None

    # The skill documents ProxyJump as an alias. A separate interactive session
    # deliberately supports that single explicit hop rather than guessing a shell command.
    proxy_params = loader.get_connection_params(proxy_alias)
    proxy_client = _connect_client(proxy_params)
    channel = proxy_client.get_transport().open_channel(
        'direct-tcpip', (params['hostname'], params['port']), ('', 0)
    )
    return _connect_client(params, sock=channel), proxy_client


def _copy_remote_output(channel, finished):
    """Forward remote bytes directly; terminal content is deliberately not logged."""
    try:
        while not finished.is_set():
            if channel.recv_ready():
                data = channel.recv(32768)
                if not data:
                    break
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            elif channel.closed:
                break
            else:
                time.sleep(0.02)
    finally:
        finished.set()


def _read_local_input(fd):
    """Read currently available local terminal input without persisting it."""
    if os.name == 'nt':
        import msvcrt
        if not msvcrt.kbhit():
            return None
        char = msvcrt.getwch()
        return '\r' if char == '\r' else char

    ready, _, _ = select.select([fd], [], [], 0.1)
    return os.read(fd, 1024) if ready else None


def interactive_session(alias, command=None, timeout=None):
    client = None
    proxy_client = None
    channel = None
    result_code = 1
    finished = threading.Event()
    command_for_audit = command or '<interactive-shell>'
    started = time.monotonic()

    try:
        client, proxy_client = _connect(alias)
        size = _terminal_size()
        channel = client.invoke_shell(term='xterm', width=size.columns, height=size.lines)

        def resize_handler(_signum, _frame):
            if channel and not channel.closed:
                new_size = _terminal_size()
                channel.resize_pty(width=new_size.columns, height=new_size.lines)

        if hasattr(signal, 'SIGWINCH'):
            signal.signal(signal.SIGWINCH, resize_handler)

        reader = threading.Thread(target=_copy_remote_output, args=(channel, finished), daemon=True)
        reader.start()
        if command:
            channel.sendall(command + '\n')

        deadline = time.monotonic() + timeout if timeout else None
        stdin_fd = sys.stdin.fileno()
        terminal_state = None
        if os.name != 'nt' and os.isatty(stdin_fd):
            import termios
            import tty
            terminal_state = termios.tcgetattr(stdin_fd)
            tty.setraw(stdin_fd)

        try:
            while not finished.is_set() and not channel.closed:
                if deadline and time.monotonic() >= deadline:
                    sys.stderr.write('\n[interactive] 会话达到整体超时，正在关闭。\n')
                    break
                data = _read_local_input(stdin_fd)
                if data == b'' or data == '':
                    break
                if data is not None:
                    channel.sendall(data.encode() if isinstance(data, str) else data)
        finally:
            if terminal_state is not None:
                import termios
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, terminal_state)

        result_code = 0
        return result_code
    except KeyboardInterrupt:
        result_code = 130
        return result_code
    except Exception as exc:
        sys.stderr.write(f'交互式 SSH 会话失败: {exc}\n')
        return result_code
    finally:
        finished.set()
        if channel:
            try:
                channel.close()
            except Exception:
                pass
        if client:
            try:
                client.close()
            except Exception:
                pass
        if proxy_client:
            try:
                proxy_client.close()
            except Exception:
                pass
        audit_command(
            alias, command_for_audit, execution='interactive', confirmed=True,
            outcome={'exit_code': result_code,
                     'duration_seconds': round(time.monotonic() - started, 2)},
        )


def main():
    parser = argparse.ArgumentParser(description='安全的交互式 SSH 终端')
    parser.add_argument('alias', help='SSH host alias from ~/.ssh/config')
    parser.add_argument('--command', help='连接后立即执行的初始命令；不会记录原文')
    parser.add_argument('--timeout', type=int,
                        help='整个会话最大秒数；默认无限制，适合持续运行的交互命令')
    parser.add_argument('--confirm', action='store_true',
                        help='确认启动可执行任意命令的交互式远程终端')
    args = parser.parse_args()

    if not args.confirm:
        audit_command(args.alias, args.command or '<interactive-shell>',
                      execution='interactive-rejected', confirmed=False,
                      outcome='confirmation_required')
        parser.error('交互式远程终端可执行任意命令；获得确认后请添加 --confirm')
    if args.timeout is not None and args.timeout <= 0:
        parser.error('--timeout 必须是正整数')

    sys.exit(interactive_session(args.alias, args.command, args.timeout))


if __name__ == '__main__':
    main()
