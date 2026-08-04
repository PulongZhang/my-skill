#!/usr/bin/env python
# -*- coding: utf-8 -*-

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import daily_claude_conversations as conversations


class DailyClaudeConversationsTest(unittest.TestCase):
    def test_scan_extracts_dialogue_and_filters_internal_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_dir = root / "project-a"
            project_dir.mkdir()
            transcript = project_dir / "session-1.jsonl"
            records = [
                {
                    "type": "user",
                    "timestamp": "2026-08-04T09:00:00+00:00",
                    "sessionId": "session-1",
                    "cwd": r"D:\WorkSpace\project-a",
                    "message": {
                        "role": "user",
                        "content": "核对字段映射，password=top-secret",
                    },
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-08-04T09:01:00+00:00",
                    "sessionId": "session-1",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "thinking", "thinking": "内部推理不应输出"},
                            {"type": "text", "text": "已核对字段来源，准备复查空值场景。"},
                            {
                                "type": "tool_use",
                                "name": "Read",
                                "input": {"file_path": r"D:\WorkSpace\project-a\config.py"},
                            },
                            {
                                "type": "tool_use",
                                "name": "Edit",
                                "input": {"file_path": r"D:\WorkSpace\project-a\config.py"},
                            },
                            {
                                "type": "tool_use",
                                "name": "UnknownTool",
                                "input": {"secret": "do-not-include"},
                            },
                        ],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-08-04T09:02:00+00:00",
                    "sessionId": "session-1",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tool-1",
                                "content": "完整文件内容不应输出",
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-08-04T09:03:00+00:00",
                    "sessionId": "session-1",
                    "isMeta": True,
                    "message": {"role": "user", "content": "系统提醒不应输出"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-08-02T12:00:00+00:00",
                    "sessionId": "session-1",
                    "message": {"role": "assistant", "content": "其他日期"},
                },
            ]
            transcript.write_text(
                "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
                + "\n"
                + '{"timestamp":"2026-08-04T09:04:00+00:00",\n'
                + "not-json\n",
                encoding="utf-8",
            )

            stats = conversations._new_stats()
            events = list(
                conversations.scan_file(
                    transcript,
                    root,
                    date(2026, 8, 4),
                    date(2026, 8, 4),
                    stats=stats,
                )
            )

            self.assertEqual(stats["malformed_lines"], 1)
            self.assertEqual(len(events), 2)
            self.assertEqual(
                [event["record_type"] for event in events],
                ["user_message", "assistant_message"],
            )
            self.assertEqual(events[0]["project_key"], "project-a")
            self.assertEqual(events[0]["session_file"], "project-a/session-1.jsonl")
            self.assertEqual(events[0]["session_id"], "session-1")
            self.assertIn("[已脱敏信息]", events[0]["text"])
            self.assertNotIn("top-secret", events[0]["text"])
            self.assertNotIn("D:\\WorkSpace", json.dumps(events, ensure_ascii=False))
            self.assertNotIn("do-not-include", json.dumps(events, ensure_ascii=False))

    def test_plain_assistant_text_and_mixed_user_text_are_kept(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transcript = root / "project" / "session.jsonl"
            transcript.parent.mkdir()
            records = [
                {
                    "type": "assistant",
                    "timestamp": "2026-08-04T10:00:00+00:00",
                    "message": {"role": "assistant", "content": "纯文本回复"},
                },
                {
                    "type": "user",
                    "timestamp": "2026-08-04T10:01:00+00:00",
                    "message": {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "content": "不应保留"},
                            {"type": "text", "text": "保留这段对话"},
                        ],
                    },
                },
            ]
            transcript.write_text(
                "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
                encoding="utf-8",
            )
            events = list(
                conversations.scan_file(
                    transcript,
                    root,
                    date(2026, 8, 4),
                    date(2026, 8, 4),
                )
            )
            self.assertEqual([event["text"] for event in events], ["纯文本回复", "保留这段对话"])

    def test_meta_markers_and_message_length_are_removed(self):
        text = "普通内容\n<system-reminder>内部内容</system-reminder>\n后续内容"
        self.assertEqual(conversations.normalize_text(text), "普通内容\n\n后续内容")
        self.assertEqual(conversations.normalize_text("abcdef", max_chars=4), "abc…")
        self.assertEqual(conversations.normalize_text("<system-reminder>未闭合"), "")
        redacted = conversations.redact_sensitive(
            'ANTHROPIC_API_KEY=secret-value password: "two words" --token cli-secret'
        )
        self.assertNotIn("secret-value", redacted)
        self.assertNotIn("two words", redacted)
        self.assertNotIn("cli-secret", redacted)
        self.assertIn("[已脱敏信息]", redacted)

    def test_date_range_and_history_directory_resolution(self):
        self.assertEqual(
            conversations.resolve_date_range(date_arg="2026-08-04"),
            (date(2026, 8, 4), date(2026, 8, 4)),
        )
        self.assertEqual(
            conversations.resolve_date_range(
                since_arg="2026-08-01", until_arg="2026-08-04"
            ),
            (date(2026, 8, 1), date(2026, 8, 4)),
        )
        with self.assertRaises(ValueError):
            conversations.resolve_date_range(
                date_arg="2026-08-04", since_arg="2026-08-03"
            )
        with self.assertRaises(ValueError):
            conversations.resolve_date_range(
                since_arg="2026-08-05", until_arg="2026-08-04"
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            config_dir = home / ".claude"
            projects_dir = config_dir / "projects"
            projects_dir.mkdir(parents=True)
            self.assertEqual(
                conversations.resolve_history_dir(environ={"CLAUDE_CONFIG_DIR": str(config_dir)}, home=home),
                projects_dir.resolve(),
            )
            self.assertEqual(
                conversations.resolve_history_dir(explicit_dir=str(projects_dir), home=home),
                projects_dir.resolve(),
            )
            broken_config = home / "broken-claude-config"
            broken_config.mkdir()
            self.assertEqual(
                conversations.resolve_history_dir(
                    environ={"CLAUDE_CONFIG_DIR": str(broken_config)}, home=home
                ),
                (broken_config / "projects").resolve(),
            )

    def test_project_roots_filter_by_transcript_cwd(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transcript = root / "project" / "session.jsonl"
            transcript.parent.mkdir()
            project_root = root / "CETWorkSpace"
            records = [
                {
                    "type": "user",
                    "timestamp": "2026-08-04T10:00:00+00:00",
                    "cwd": str(project_root / "app"),
                    "message": {"role": "user", "content": "保留的项目对话"},
                },
                {
                    "type": "user",
                    "timestamp": "2026-08-04T10:01:00+00:00",
                    "cwd": str(root / "OtherWorkspace"),
                    "message": {"role": "user", "content": "排除的项目对话"},
                },
            ]
            transcript.write_text(
                "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
                encoding="utf-8",
            )
            events = list(
                conversations.scan_file(
                    transcript,
                    root,
                    date(2026, 8, 4),
                    date(2026, 8, 4),
                    project_roots=[str(project_root)],
                )
            )
            self.assertEqual([event["text"] for event in events], ["保留的项目对话"])

    def test_deduplication_sorting_and_json_payload(self):
        event = {
            "session_file": "project/session.jsonl",
            "timestamp": "2026-08-04T10:00:00+00:00",
            "project_key": "project",
            "session_id": "session",
            "record_type": "user_message",
            "content_type": "user_text",
            "text": "核对配置",
        }
        duplicate = dict(event)
        earlier = dict(event, timestamp="2026-08-04T09:00:00+00:00", text="读取记录")
        result = conversations.deduplicate_events([event, duplicate, earlier])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["text"], "读取记录")

        payload = conversations.build_payload(
            result,
            date(2026, 8, 4),
            date(2026, 8, 4),
            conversations._new_stats(),
        )
        self.assertEqual(payload["source"], conversations.SOURCE_NAME)
        self.assertEqual(len(payload["events"]), 2)

    def test_json_cli_output_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transcript = root / "project" / "session.jsonl"
            transcript.parent.mkdir()
            transcript.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": "2026-08-04T10:00:00+00:00",
                        "cwd": str(root),
                        "message": {"role": "user", "content": "记录一次核对"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                return_code = conversations.main(
                    [
                        "--date",
                        "2026-08-04",
                        "--dir",
                        str(root),
                        "--roots",
                        str(root),
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(return_code, 0)
            self.assertEqual(payload["date_range"]["since"], "2026-08-04")
            self.assertEqual(len(payload["events"]), 1)


if __name__ == "__main__":
    unittest.main()
