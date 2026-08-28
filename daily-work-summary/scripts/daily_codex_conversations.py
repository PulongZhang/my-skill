#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""提取本地 Codex 对话记录，作为日报事实素材。"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from daily_claude_conversations import (
    DEFAULT_MAX_CHARS_PER_MESSAGE,
    _configure_stdio,
    _new_stats,
    _path_is_under,
    deduplicate_events,
    normalize_text,
    normalize_win_path,
    parse_local_timestamp,
    resolve_date_range,
)
from daily_source_scope import DEFAULT_PROJECT_ROOTS


_configure_stdio()

SOURCE_NAME = "local_codex_jsonl"
_TIMESTAMP_RE = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')
_SYNTHETIC_USER_BLOCK_RE = re.compile(
    r"^\s*<(?:recommended_plugins|environment_context|app-context|"
    r"permissions instructions|skills_instructions|apps_instructions|"
    r"plugins_instructions|collaboration_mode|multi_agent_mode|"
    r"codex_internal_context)(?:\s|>)",
    re.IGNORECASE,
)
_SYNTHETIC_AGENTS_RE = re.compile(
    r"^\s*#\s*AGENTS\.md instructions for\s+", re.IGNORECASE
)

Event = Dict[str, Any]
Stats = Dict[str, Any]


def resolve_history_dirs(
    explicit_dir: Optional[str] = None,
    environ: Optional[Dict[str, str]] = None,
    home: Optional[Path] = None,
) -> List[Path]:
    """定位 Codex 活跃及归档会话目录；显式传入会话文件或目录时只读取该目标。"""
    env = os.environ if environ is None else environ
    home_path = Path.home() if home is None else Path(home)
    if explicit_dir:
        value = normalize_win_path(explicit_dir)
        candidate = Path(os.path.expandvars(os.path.expanduser(value))).resolve()
        if candidate.name.lower() in {"sessions", "archived_sessions"} or candidate.is_file():
            return [candidate]
        children = [candidate / "sessions", candidate / "archived_sessions"]
        if any(child.exists() for child in children):
            return children
        return [candidate]

    config_dir = env.get("CODEX_HOME")
    root = Path(os.path.expandvars(os.path.expanduser(config_dir))).resolve() if config_dir else home_path / ".codex"
    return [(root / "sessions").resolve(), (root / "archived_sessions").resolve()]


def walk_jsonl(root: Path) -> Iterator[Path]:
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


def extract_content_text(content: Any, allowed_types: Sequence[str]) -> List[str]:
    """只读取消息文字块，不读取思考、工具调用或工具结果。"""
    blocks = content if isinstance(content, list) else [content]
    result: List[str] = []
    for block in blocks:
        if isinstance(block, str):
            result.append(block)
        elif isinstance(block, dict) and block.get("type") in allowed_types:
            value = block.get("text")
            if isinstance(value, str):
                result.append(value)
    return result


def _session_metadata(file: Path, stats: Stats) -> Dict[str, str]:
    """从文件头读取会话标识及工作目录。"""
    metadata = {"session_id": file.stem, "cwd": ""}
    try:
        with file.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(40):
                line = handle.readline()
                if not line:
                    break
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict) or record.get("type") != "session_meta":
                    continue
                payload = record.get("payload")
                if isinstance(payload, dict):
                    session_id = payload.get("id") or payload.get("session_id")
                    cwd = payload.get("cwd")
                    if isinstance(session_id, str) and session_id.strip():
                        metadata["session_id"] = session_id.strip()
                    if isinstance(cwd, str):
                        metadata["cwd"] = cwd
                break
    except OSError:
        stats["files_failed"] += 1
    return metadata


def _project_matches(cwd: str, project_filter: Optional[str], roots: Sequence[str]) -> bool:
    if roots and (not cwd or not any(_path_is_under(cwd, root) for root in roots)):
        return False
    if not project_filter:
        return True
    return project_filter.casefold() in cwd.casefold()


def _project_key(cwd: str, file: Path) -> str:
    if cwd:
        name = Path(cwd).name
        return name or normalize_win_path(cwd)
    return file.stem


def _event(
    timestamp: Any,
    project_key: str,
    session_id: str,
    session_file: str,
    role: str,
    text: str,
    line_number: int,
) -> Event:
    return {
        "timestamp": timestamp.isoformat(),
        "date": timestamp.date().isoformat(),
        "project_key": project_key,
        "session_id": session_id,
        "session_file": session_file,
        "record_type": f"{role}_message",
        "content_type": f"{role}_text",
        "text": text,
        "source": SOURCE_NAME,
        "is_sidechain": False,
        "line_number": line_number,
    }


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
    current_stats = stats if stats is not None else _new_stats()
    current_stats["files_scanned"] += 1
    file = Path(file)
    metadata = _session_metadata(file, current_stats)
    cwd = metadata["cwd"]
    roots = list(project_roots or [])
    if not _project_matches(cwd, project_filter, roots):
        return
    try:
        session_file = file.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        session_file = file.name

    try:
        handle = file.open("r", encoding="utf-8", errors="replace")
    except OSError:
        current_stats["files_failed"] += 1
        return

    current_stats["files_read"] += 1
    with handle:
        for line_number, line in enumerate(handle, start=1):
            current_stats["lines_seen"] += 1
            if not line.strip() or not _TIMESTAMP_RE.search(line):
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
            timestamp = parse_local_timestamp(record.get("timestamp"))
            if timestamp is None or not (start_date <= timestamp.date() <= end_date):
                current_stats["records_skipped"] += 1
                continue
            if record.get("type") != "response_item":
                current_stats["records_skipped"] += 1
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict) or payload.get("type") != "message":
                current_stats["records_skipped"] += 1
                continue
            role = payload.get("role")
            if role not in {"user", "assistant"}:
                current_stats["records_skipped"] += 1
                continue
            allowed = ("input_text", "text") if role == "user" else ("output_text", "text")
            emitted = 0
            for raw_text in extract_content_text(payload.get("content"), allowed):
                if role == "user" and (
                    _SYNTHETIC_USER_BLOCK_RE.match(raw_text)
                    or _SYNTHETIC_AGENTS_RE.match(raw_text)
                ):
                    continue
                text = normalize_text(raw_text, max_chars_per_message)
                if not text:
                    continue
                emitted += 1
                yield _event(
                    timestamp,
                    _project_key(cwd, file),
                    metadata["session_id"],
                    session_file,
                    role,
                    text,
                    line_number,
                )
            if emitted:
                current_stats["events_emitted"] += emitted
            else:
                current_stats["records_skipped"] += 1


def format_report(events: Sequence[Event], start_date: date, end_date: date, stats: Stats) -> str:
    lines = [
        "# 本地 Codex 对话工作素材",
        f"**日期范围**: {start_date.isoformat()} ~ {end_date.isoformat()}",
        "",
    ]
    if not events:
        lines.append("> 在指定日期范围内未找到可用的本地 Codex 对话记录。")
    else:
        for event in events:
            label = "用户" if event["record_type"] == "user_message" else "助手"
            time_text = str(event["timestamp"])[11:19]
            text = str(event["text"]).replace("\n", "\n  ")
            lines.append(f"- [{time_text}][{label}] {text}")
    if stats.get("malformed_lines") or stats.get("files_failed"):
        lines.extend(["", "> 部分损坏或不可读记录已跳过。"])
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="提取本地 Codex JSONL 对话中的日报事实素材")
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument("--date", help="指定单日，格式 YYYY-MM-DD（默认: 今天）")
    date_group.add_argument("--since", help="起始日期，格式 YYYY-MM-DD")
    parser.add_argument("--until", help="结束日期，格式 YYYY-MM-DD；只传 --until 时按单日查询")
    parser.add_argument("--dir", dest="history_dir", help="Codex 配置目录、会话目录或单个 JSONL 文件")
    parser.add_argument("--project", dest="project_filter", help="项目关键词，匹配会话工作目录")
    parser.add_argument("--project-filter", dest="project_filter", help="项目关键词，匹配会话工作目录")
    parser.add_argument("--roots", nargs="+", help="项目扫描根目录，默认与 Git 提取器一致")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    parser.add_argument("--only-user", action="store_true", help="只保留用户消息")
    parser.add_argument("--output", "-o", help="输出文件路径（默认: 打印到控制台）")
    parser.add_argument("--max-chars-per-message", type=int, default=DEFAULT_MAX_CHARS_PER_MESSAGE)
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
    roots = [normalize_win_path(p) for p in (args.roots or DEFAULT_PROJECT_ROOTS)]
    history_dirs = resolve_history_dirs(args.history_dir)
    stats = _new_stats()
    events: List[Event] = []
    found = False
    for history_dir in history_dirs:
        if not (history_dir.is_dir() or history_dir.is_file()):
            continue
        found = True
        for file in walk_jsonl(history_dir):
            events.extend(
                scan_file(
                    file,
                    history_dir,
                    start_date,
                    end_date,
                    args.project_filter,
                    roots,
                    args.max_chars_per_message,
                    stats,
                )
            )
    if args.only_user:
        events = [event for event in events if event["record_type"] == "user_message"]
    events = deduplicate_events(events)
    stats["events_after_dedup"] = len(events)
    if args.json:
        rendered = json.dumps(
            {
                "date_range": {"since": start_date.isoformat(), "until": end_date.isoformat()},
                "project_filter": args.project_filter or "",
                "project_roots": roots,
                "history_dir_found": found,
                "stats": stats,
                "events": events,
                "source": SOURCE_NAME,
            },
            ensure_ascii=False,
            indent=2,
        )
    else:
        rendered = format_report(events, start_date, end_date, stats)
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
