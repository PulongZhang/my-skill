#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
提取本地 Claude Code 对话记录，作为日报的事实素材。

脚本只读取 Claude Code 已保存的 JSONL 转录，不调用远程模型。它主要保留用户消息和助手文字，
同时跳过系统提醒、思考内容、完整工具结果、工具参数和未知输入。

用法:
    uv run --project ~/.claude/skills/daily-work-summary python \
        ~/.claude/skills/daily-work-summary/scripts/daily_claude_conversations.py
    uv run --project ~/.claude/skills/daily-work-summary python \
        ~/.claude/skills/daily-work-summary/scripts/daily_claude_conversations.py \
        --date 2026-08-04 --json
    uv run --project ~/.claude/skills/daily-work-summary python \
        ~/.claude/skills/daily-work-summary/scripts/daily_claude_conversations.py \
        --since 2026-08-01 --until 2026-08-04 --project my-skill \
        --roots D:\\CETWorkSpace
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple


def _configure_stdio() -> None:
    """在 Windows 控制台中保持中文帮助和报告可读。"""
    for stream in (sys.stdout, sys.stderr):
        if getattr(stream, "encoding", "").lower() != "utf-8" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


_configure_stdio()


DEFAULT_MAX_CHARS_PER_MESSAGE = 2000
# 与 daily_git_commits.py 的默认扫描根目录保持一致。
DEFAULT_PROJECT_ROOTS = [r"D:\CETWorkSpace"]
SOURCE_NAME = "local_claude_jsonl"

_TIMESTAMP_RE = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')
_META_TAGS = (
    "system-reminder",
    "task-notification",
    "local-command-caveat",
    "command-name",
    "command-args",
    "local-command-stdout",
)
_META_BLOCK_RE = re.compile(
    r"<(?P<tag>system-reminder|task-notification|local-command-caveat|"
    r"command-name|command-args|local-command-stdout)\b[^>]*>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_PEM_RE = re.compile(
    r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", re.IGNORECASE | re.DOTALL
)
_BEARER_RE = re.compile(
    r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+"
)
_SENSITIVE_KEYS = (
    r"password|passwd|passphrase|secret|token|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|client[_-]?secret|authorization|cookie"
)
_SENSITIVE_QUOTED_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:" + _SENSITIVE_KEYS + r")\b(\s*[:=]\s*)([\"'])(.*?)\2"
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:" + _SENSITIVE_KEYS + r")\b"
    r"(\s*[:=]\s*)([^\"'\s,;&}\]]+)"
)
_SENSITIVE_ENV_RE = re.compile(
    r"(?i)\b[A-Z0-9_]*(?:PASSWORD|PASSWD|PASSPHRASE|SECRET|TOKEN|"
    r"API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|CLIENT[_-]?SECRET|"
    r"AUTHORIZATION|COOKIE)[A-Z0-9_]*\b(\s*=\s*)([\"'])(.*?)\2"
)
_SENSITIVE_ENV_UNQUOTED_RE = re.compile(
    r"(?i)\b[A-Z0-9_]*(?:PASSWORD|PASSWD|PASSPHRASE|SECRET|TOKEN|"
    r"API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|CLIENT[_-]?SECRET|"
    r"AUTHORIZATION|COOKIE)[A-Z0-9_]*\b(\s*=\s*)([^\"'\s,;&}\]]+)"
)
_SENSITIVE_FLAG_RE = re.compile(
    r"(?i)(--(?:" + _SENSITIVE_KEYS + r"))(\s+)([\"'])(.*?)\3"
)
_SENSITIVE_FLAG_UNQUOTED_RE = re.compile(
    r"(?i)(--(?:" + _SENSITIVE_KEYS + r"))(\s+)([^\"'\s,;&}\]]+)"
)
_KNOWN_TOKEN_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{10,}|gh[pousr]_[A-Za-z0-9_]{16,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})\b"
)
_URL_CREDENTIAL_RE = re.compile(
    r"(?i)(https?://[^\s/:]+):[^\s@]+@"
)

Event = Dict[str, Any]
Stats = Dict[str, Any]


def _new_stats() -> Stats:
    return {
        "files_scanned": 0,
        "files_read": 0,
        "files_failed": 0,
        "lines_seen": 0,
        "malformed_lines": 0,
        "records_skipped": 0,
        "events_emitted": 0,
        "events_after_dedup": 0,
    }


def resolve_history_dir(
    explicit_dir: Optional[str] = None,
    environ: Optional[Dict[str, str]] = None,
    home: Optional[Path] = None,
) -> Path:
    """按显式目录、CLAUDE_CONFIG_DIR 和用户目录的顺序定位 projects 目录。"""
    env = os.environ if environ is None else environ
    home_path = Path.home() if home is None else Path(home)

    if explicit_dir:
        candidate = Path(os.path.expandvars(os.path.expanduser(explicit_dir))).resolve()
        return _as_projects_dir(candidate)

    config_dir = env.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        candidate = Path(os.path.expandvars(os.path.expanduser(config_dir))).resolve()
        return _as_projects_dir(candidate, prefer_child=True)

    return (home_path / ".claude" / "projects").resolve()


def _as_projects_dir(candidate: Path, prefer_child: bool = False) -> Path:
    """兼容 --dir 传入 ~/.claude 或 ~/.claude/projects 两种形式。"""
    if candidate.name.lower() == "projects":
        return candidate
    projects_child = candidate / "projects"
    if projects_child.is_dir() or prefer_child or not candidate.exists():
        return projects_child
    try:
        if any(candidate.rglob("*.jsonl")):
            return candidate
    except OSError:
        pass
    return projects_child


def walk_jsonl(root: Path) -> Iterator[Path]:
    """递归发现 JSONL 转录文件，不跟随目录软链接。"""
    root = Path(root)
    if root.is_file():
        if root.suffix.lower() == ".jsonl":
            yield root
        return
    if not root.is_dir():
        return

    for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
        dirnames.sort()
        for filename in sorted(filenames):
            if filename.lower().endswith(".jsonl"):
                yield Path(dirpath) / filename


def parse_local_timestamp(value: Any) -> Optional[datetime]:
    """解析转录时间戳并转换到本机时区，日期比较因此兼容夏令时。"""
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed.astimezone()


def parse_date(value: str, argument_name: str = "日期") -> date:
    """解析 YYYY-MM-DD，提供适合命令行显示的错误信息。"""
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{argument_name}必须使用 YYYY-MM-DD 格式: {value}")
    return parsed


def resolve_date_range(
    date_arg: Optional[str] = None,
    since_arg: Optional[str] = None,
    until_arg: Optional[str] = None,
    today: Optional[date] = None,
) -> Tuple[date, date]:
    """解析日期参数；未提供参数时只读取本地今天。"""
    if date_arg and (since_arg or until_arg):
        raise ValueError("--date 不能与 --since 或 --until 同时使用")

    today_value = date.today() if today is None else today
    if date_arg:
        selected = parse_date(date_arg, "--date")
        return selected, selected

    if since_arg:
        start = parse_date(since_arg, "--since")
    elif until_arg:
        # 只给结束日期时按单日查询处理，避免意外扫描全部历史。
        start = parse_date(until_arg, "--until")
    else:
        start = today_value

    end = parse_date(until_arg, "--until") if until_arg else today_value
    if start > end:
        raise ValueError("--since 不能晚于 --until")
    return start, end


def extract_message_text(message: Any) -> str:
    """只提取消息中的 text block，不读取 thinking 或 tool_result 内容。"""
    content = message
    if isinstance(message, dict):
        content = message.get("content", "")

    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if content.get("type") == "text":
            return str(content.get("text", ""))
        return ""
    if not isinstance(content, list):
        return ""

    text_parts: List[str] = []
    for block in content:
        if isinstance(block, str):
            text_parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(str(block.get("text", "")))
    return "\n".join(part for part in text_parts if part)


def redact_sensitive(text: str) -> str:
    """脱敏常见密钥、令牌、授权头和带认证信息的 URL。"""
    text = _PEM_RE.sub("[已脱敏密钥]", text)
    text = _BEARER_RE.sub("[已脱敏授权信息]", text)
    text = _SENSITIVE_ENV_RE.sub(r"\1[已脱敏信息]", text)
    text = _SENSITIVE_ENV_UNQUOTED_RE.sub(r"\1[已脱敏信息]", text)
    text = _SENSITIVE_QUOTED_ASSIGNMENT_RE.sub(r"\1[已脱敏信息]", text)
    text = _SENSITIVE_ASSIGNMENT_RE.sub(r"\1[已脱敏信息]", text)
    text = _SENSITIVE_FLAG_RE.sub(r"\1\2[已脱敏信息]", text)
    text = _SENSITIVE_FLAG_UNQUOTED_RE.sub(r"\1\2[已脱敏信息]", text)
    text = _KNOWN_TOKEN_RE.sub("[已脱敏令牌]", text)
    text = _URL_CREDENTIAL_RE.sub(r"\1[已脱敏信息]@", text)
    return text


def normalize_text(text: Any, max_chars: int = DEFAULT_MAX_CHARS_PER_MESSAGE) -> str:
    """清理内部提醒、规范空白、脱敏并限制单条素材长度。"""
    if not isinstance(text, str):
        return ""
    if max_chars < 1:
        raise ValueError("max_chars 必须大于 0")

    cleaned = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    for tag in _META_TAGS:
        if f"<{tag}" in cleaned.lower():
            cleaned = _META_BLOCK_RE.sub("", cleaned)
            break
    # 未闭合的内部提醒无法安全截取，直接丢弃该条文字。
    lowered = cleaned.lower()
    if any(f"<{tag}" in lowered or f"</{tag}" in lowered for tag in _META_TAGS):
        return ""

    cleaned = redact_sensitive(cleaned)
    cleaned = "\n".join(line.rstrip() for line in cleaned.splitlines())
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1].rstrip() + "…"
    return cleaned


def _project_key(file: Path, root: Path) -> str:
    try:
        relative_parent = file.parent.resolve().relative_to(root.resolve())
        if relative_parent.parts:
            return "/".join(relative_parent.parts)
    except ValueError:
        pass
    return file.stem


def _relative_session_file(file: Path, root: Path) -> str:
    try:
        return file.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return file.name


def _session_id(record: Dict[str, Any], file: Path) -> str:
    for key in ("sessionId", "session_id"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    message = record.get("message")
    if isinstance(message, dict):
        for key in ("sessionId", "session_id"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return file.stem


def _event_base(
    timestamp: datetime,
    project_key: str,
    session_id: str,
    session_file: str,
    record_type: str,
    content_type: str,
    text: str,
    record: Dict[str, Any],
) -> Event:
    return {
        "timestamp": timestamp.isoformat(),
        "date": timestamp.date().isoformat(),
        "project_key": project_key,
        "session_id": session_id,
        "session_file": session_file,
        "record_type": record_type,
        "content_type": content_type,
        "text": text,
        "source": SOURCE_NAME,
        "is_sidechain": bool(record.get("isSidechain", False)),
    }


def _path_is_under(path_value: str, root_value: str) -> bool:
    try:
        path_name = os.path.normcase(os.path.abspath(os.path.expanduser(path_value)))
        root_name = os.path.normcase(os.path.abspath(os.path.expanduser(root_value)))
        return os.path.commonpath([path_name, root_name]) == root_name
    except (OSError, ValueError):
        return False


def _project_matches(
    project_filter: Optional[str],
    project_key: str,
    session_file: str,
    record: Dict[str, Any],
    project_roots: Optional[Sequence[str]] = None,
) -> bool:
    cwd = record.get("cwd")
    if project_roots:
        if not isinstance(cwd, str) or not any(
            _path_is_under(cwd, root) for root in project_roots
        ):
            return False

    if not project_filter:
        return True
    needle = project_filter.casefold()
    candidates = [project_key, session_file]
    if isinstance(cwd, str):
        candidates.append(cwd)
    return any(needle in candidate.casefold() for candidate in candidates)


def _events_from_record(
    record: Dict[str, Any],
    timestamp: datetime,
    project_key: str,
    session_id: str,
    session_file: str,
    max_chars_per_message: int,
) -> List[Event]:
    if record.get("isMeta"):
        return []

    record_kind = record.get("type")
    if record_kind not in {"user", "assistant"}:
        return []

    if record.get("toolUseResult") is not None:
        return []

    events: List[Event] = []
    if record_kind == "user":
        text = normalize_text(
            extract_message_text(record.get("message")), max_chars_per_message
        )
        if text:
            events.append(
                _event_base(
                    timestamp,
                    project_key,
                    session_id,
                    session_file,
                    "user_message",
                    "user_text",
                    text,
                    record,
                )
            )
        return events

    message = record.get("message")
    assistant_content = message.get("content", "") if isinstance(message, dict) else message
    blocks: Iterable[Any]
    if isinstance(assistant_content, list):
        blocks = assistant_content
    else:
        blocks = [assistant_content]

    for block in blocks:
        if isinstance(block, str):
            raw_text = block
        elif isinstance(block, dict) and block.get("type") == "text":
            raw_text = block.get("text", "")
        else:
            continue

        text = normalize_text(raw_text, max_chars_per_message)
        if text:
            events.append(
                _event_base(
                    timestamp,
                    project_key,
                    session_id,
                    session_file,
                    "assistant_message",
                    "assistant_text",
                    text,
                    record,
                )
            )
    return events


def scan_file(
    file: Path,
    root: Path,
    start_date: date,
    end_date: date,
    project_filter: Optional[str] = None,
    project_roots: Optional[Sequence[str]] = None,
    max_chars_per_message: int = DEFAULT_MAX_CHARS_PER_MESSAGE,
    stats: Optional[Stats] = None,
) -> Iterator[Event]:
    """逐行扫描单个 JSONL 文件；损坏行和不相关记录不会中断扫描。"""
    current_stats = stats if stats is not None else _new_stats()
    current_stats["files_scanned"] += 1
    file = Path(file)
    root = Path(root)
    project_key = _project_key(file, root)
    session_file = _relative_session_file(file, root)

    try:
        handle = file.open("r", encoding="utf-8", errors="replace")
    except OSError:
        current_stats["files_failed"] += 1
        return

    current_stats["files_read"] += 1
    with handle:
        for line_number, line in enumerate(handle, start=1):
            current_stats["lines_seen"] += 1
            if not line.strip():
                continue

            if not _TIMESTAMP_RE.search(line):
                current_stats["records_skipped"] += 1
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                current_stats["malformed_lines"] += 1
                continue
            if not isinstance(record, dict):
                current_stats["records_skipped"] += 1
                continue

            record_timestamp = parse_local_timestamp(record.get("timestamp"))
            if record_timestamp is None or not (
                start_date <= record_timestamp.date() <= end_date
            ):
                current_stats["records_skipped"] += 1
                continue
            if not _project_matches(
                project_filter, project_key, session_file, record, project_roots
            ):
                continue

            events = _events_from_record(
                record,
                record_timestamp,
                project_key,
                _session_id(record, file),
                session_file,
                max_chars_per_message,
            )
            if not events:
                current_stats["records_skipped"] += 1
                continue
            current_stats["events_emitted"] += len(events)
            for event in events:
                event["line_number"] = line_number
                yield event


def deduplicate_events(events: Iterable[Event]) -> List[Event]:
    """按会话、时间、类型和内容去除重复素材，保留原始顺序中的第一条。"""
    seen: Set[Tuple[Any, ...]] = set()
    result: List[Event] = []
    for event in events:
        key = (
            event.get("session_file", ""),
            event.get("timestamp", ""),
            event.get("record_type", ""),
            event.get("content_type", ""),
            event.get("text", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(event)

    def sort_key(item: Event) -> Tuple[Any, ...]:
        parsed_timestamp = parse_local_timestamp(item.get("timestamp"))
        instant = parsed_timestamp.timestamp() if parsed_timestamp else float("inf")
        return (
            instant,
            item.get("project_key", ""),
            item.get("session_id", ""),
            item.get("line_number", 0),
        )

    result.sort(key=sort_key)
    return result


def _event_label(event: Event) -> str:
    if event.get("record_type") == "user_message":
        return "用户"
    return "助手"


def format_report(
    events: Sequence[Event],
    start_date: date,
    end_date: date,
    stats: Optional[Stats] = None,
    project_filter: Optional[str] = None,
) -> str:
    """将结构化素材格式化为便于人工查看的 Markdown。"""
    lines = [
        "# 本地 Claude 对话工作素材",
        f"**日期范围**: {start_date.isoformat()} ~ {end_date.isoformat()}",
    ]
    if project_filter:
        lines.append(f"**项目筛选**: {project_filter}")
    lines.append("")

    if not events:
        lines.append("> 在指定日期范围内未找到可用的本地 Claude 对话记录。")
    else:
        groups: Dict[Tuple[str, str], List[Event]] = {}
        for event in events:
            key = (str(event.get("project_key", "未知项目")), str(event.get("session_id", "未知会话")))
            groups.setdefault(key, []).append(event)

        for (project_key, session_id), group in sorted(groups.items()):
            lines.append(f"## {project_key}")
            lines.append(f"会话: {session_id[:12]}")
            lines.append("")
            for event in group:
                timestamp = str(event.get("timestamp", ""))
                time_text = timestamp[11:19] if len(timestamp) >= 19 else timestamp
                label = _event_label(event)
                text = event.get("text", "")
                indented = str(text).replace("\n", "\n  ")
                lines.append(f"- [{time_text}][{label}] {indented}")
            lines.append("")

    if stats:
        warnings = []
        if stats.get("malformed_lines", 0):
            warnings.append(f"跳过损坏记录 {stats['malformed_lines']} 行")
        if stats.get("files_failed", 0):
            warnings.append(f"无法读取文件 {stats['files_failed']} 个")
        if warnings:
            lines.append("> " + "；".join(warnings) + "。")
    return "\n".join(lines).rstrip() + "\n"


def build_payload(
    events: Sequence[Event],
    start_date: date,
    end_date: date,
    stats: Stats,
    project_filter: Optional[str] = None,
    project_roots: Optional[Sequence[str]] = None,
    history_dir_found: bool = True,
) -> Dict[str, Any]:
    return {
        "date_range": {"since": start_date.isoformat(), "until": end_date.isoformat()},
        "project_filter": project_filter or "",
        "project_roots": list(project_roots or []),
        "history_dir_found": history_dir_found,
        "stats": stats,
        "events": list(events),
        "source": SOURCE_NAME,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="提取本地 Claude Code JSONL 对话中的日报事实素材",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument("--date", help="指定单日，格式 YYYY-MM-DD（默认: 今天）")
    date_group.add_argument("--since", help="起始日期，格式 YYYY-MM-DD")
    parser.add_argument(
        "--until",
        default=None,
        help="结束日期，格式 YYYY-MM-DD；只传 --until 时按单日查询",
    )
    parser.add_argument(
        "--dir",
        dest="history_dir",
        default=None,
        help="Claude projects 目录或其上级配置目录",
    )
    parser.add_argument("--project", default=None, help="项目关键词，匹配项目目录、会话文件或工作目录")
    parser.add_argument(
        "--roots",
        nargs="+",
        default=None,
        help="项目扫描根目录，默认与 Git 提取器一致",
    )
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    parser.add_argument("--output", "-o", default=None, help="输出文件路径（默认: 打印到控制台）")
    parser.add_argument(
        "--max-chars-per-message",
        type=int,
        default=DEFAULT_MAX_CHARS_PER_MESSAGE,
        help=f"单条文字素材最大字符数（默认: {DEFAULT_MAX_CHARS_PER_MESSAGE}）",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_chars_per_message < 1:
        parser.error("--max-chars-per-message 必须大于 0")

    try:
        start_date, end_date = resolve_date_range(args.date, args.since, args.until)
    except ValueError as exc:
        parser.error(str(exc))

    history_dir = resolve_history_dir(args.history_dir)
    project_roots = args.roots if args.roots else DEFAULT_PROJECT_ROOTS
    stats = _new_stats()
    events: List[Event] = []
    history_dir_found = history_dir.is_dir() or history_dir.is_file()
    if not history_dir_found:
        print(f"警告：本地 Claude 历史目录不存在，跳过对话记录: {history_dir}", file=sys.stderr)
    else:
        for file in walk_jsonl(history_dir):
            events.extend(
                scan_file(
                    file,
                    history_dir,
                    start_date,
                    end_date,
                    project_filter=args.project,
                    project_roots=project_roots,
                    max_chars_per_message=args.max_chars_per_message,
                    stats=stats,
                )
            )

    events = deduplicate_events(events)
    stats["events_after_dedup"] = len(events)
    if args.json:
        rendered = json.dumps(
            build_payload(
                events,
                start_date,
                end_date,
                stats,
                project_filter=args.project,
                project_roots=project_roots,
                history_dir_found=history_dir_found,
            ),
            ensure_ascii=False,
            indent=2,
        )
    else:
        rendered = format_report(events, start_date, end_date, stats, args.project)

    if args.output:
        output_path = Path(os.path.expandvars(os.path.expanduser(args.output)))
        try:
            output_path.write_text(rendered + ("\n" if args.json else ""), encoding="utf-8")
        except OSError as exc:
            print(f"无法写入输出文件: {exc}", file=sys.stderr)
            return 1
        print(f"报告已保存到: {output_path}", file=sys.stderr)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
