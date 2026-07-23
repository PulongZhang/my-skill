"""Security helpers shared by SSH skill entry points."""

import hashlib
import json
import os
import re
import shlex
import stat
import time
from pathlib import Path

import paramiko


def configure_host_key_verification(client):
    """Use the system and user known_hosts files; reject unknown hosts."""
    client.load_system_host_keys()
    user_known_hosts = os.path.expanduser("~/.ssh/known_hosts")
    if os.path.exists(user_known_hosts):
        client.load_host_keys(user_known_hosts)
    client.set_missing_host_key_policy(paramiko.RejectPolicy())


def quote_posix_shell_arg(value):
    """Return one safe POSIX-shell argument, rejecting impossible path data."""
    value = str(value)
    if "\x00" in value:
        raise ValueError("参数不能包含 NUL 字符")
    return shlex.quote(value)


def validate_ssh_config_value(value, field, *, single_token=False):
    """Reject values that could add directives when written to ssh config."""
    if value is None:
        return value
    value = str(value)
    if any(char in value for char in ("\r", "\n", "\x00")):
        raise ValueError(f"{field} 不能包含换行或 NUL 字符")
    if single_token and (not value or any(char.isspace() for char in value) or "#" in value):
        raise ValueError(f"{field} 必须是单个 SSH 标识符")
    return value


def validate_network_host(host):
    """Accept only host syntax safe for the /dev/tcp connectivity check."""
    host = str(host)
    if not re.fullmatch(r"[A-Za-z0-9._:-]+", host):
        raise ValueError("主机名包含不允许的字符")
    return host


def validate_port(port):
    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError("端口必须是整数") from exc
    if not 1 <= port <= 65535:
        raise ValueError("端口必须在 1 到 65535 之间")
    return port


_DANGEROUS_COMMAND = re.compile(
    r"(?:\brm\s+(?:-[^\s]*[rf]|--recursive)|\b(?:sudo|su)\b|"
    r"\bsystemctl\s+(?:start|stop|restart|reload|disable|enable)|"
    r"\b(?:shutdown|reboot|poweroff|halt)\b|\b(?:dd|mkfs|fdisk|parted)\b|"
    r"\b(?:docker|kubectl)\s+(?:rm|down|delete|apply)|"
    r"\b(?:apt|apt-get|yum|dnf|apk)\s+(?:install|remove|purge|upgrade)|"
    r"(?:curl|wget)[^\n|]*\|\s*(?:ba)?sh\b)",
    re.IGNORECASE,
)


def is_dangerous_command(command):
    return bool(_DANGEROUS_COMMAND.search(command))


def audit_command(alias, command, *, execution, confirmed, outcome=None):
    """Append non-secret command metadata to an owner-readable local audit file."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ssh-skill"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "ssh-skill"
    base.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(base, stat.S_IRWXU)
    path = base / "audit.jsonl"
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "alias": alias,
        "execution": execution,
        "dangerous": is_dangerous_command(command),
        "confirmed": confirmed,
        "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "outcome": outcome,
    }
    with open(path, "a", encoding="utf-8") as handle:
        if os.name != "nt":
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
