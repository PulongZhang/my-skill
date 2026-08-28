import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import daily_codex_conversations as codex  # noqa: E402


def record(timestamp, record_type, payload):
    return json.dumps(
        {"timestamp": timestamp, "type": record_type, "payload": payload},
        ensure_ascii=False,
    )


class DailyCodexConversationsTests(unittest.TestCase):
    def make_session(self, directory: Path) -> Path:
        path = directory / "rollout-test.jsonl"
        rows = [
            record(
                "2026-08-28T01:00:00Z",
                "session_meta",
                {"id": "session-1", "cwd": r"D:\WorkSpace\demo"},
            ),
            record(
                "2026-08-28T01:01:00Z",
                "response_item",
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "内部指令"}],
                },
            ),
            record(
                "2026-08-28T01:02:00Z",
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "<environment_context>内部环境</environment_context>"},
                        {"type": "input_text", "text": "# AGENTS.md instructions for D:\\WorkSpace\\demo\n内部规则"},
                        {"type": "input_text", "text": "<codex_internal_context source=\"goal\">内部目标</codex_internal_context>"},
                        {"type": "input_text", "text": "排查接口返回异常，token=secret-value"},
                    ],
                },
            ),
            record(
                "2026-08-28T01:03:00Z",
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "已定位字段映射差异"}],
                },
            ),
            record(
                "2026-08-28T01:04:00Z",
                "response_item",
                {"type": "reasoning", "summary": [{"type": "summary_text", "text": "思考内容"}]},
            ),
            record(
                "2026-08-28T01:05:00Z",
                "response_item",
                {"type": "custom_tool_call_output", "output": "完整工具结果"},
            ),
        ]
        path.write_text("\n".join(rows), encoding="utf-8")
        return path

    def test_extracts_only_user_and_assistant_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session = self.make_session(root)
            stats = codex._new_stats()
            events = list(
                codex.scan_file(
                    session,
                    root,
                    date(2026, 8, 28),
                    date(2026, 8, 28),
                    project_roots=[r"D:\WorkSpace"],
                    stats=stats,
                )
            )
        self.assertEqual([event["record_type"] for event in events], ["user_message", "assistant_message"])
        self.assertIn("[已脱敏信息]", events[0]["text"])
        combined = "\n".join(event["text"] for event in events)
        self.assertNotIn("内部环境", combined)
        self.assertNotIn("内部规则", combined)
        self.assertNotIn("内部目标", combined)
        self.assertNotIn("内部指令", combined)
        self.assertNotIn("思考内容", combined)
        self.assertNotIn("完整工具结果", combined)

    def test_date_and_project_filters(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session = self.make_session(root)
            matching = list(
                codex.scan_file(
                    session,
                    root,
                    date(2026, 8, 28),
                    date(2026, 8, 28),
                    project_filter="demo",
                    project_roots=[r"D:\WorkSpace"],
                )
            )
            wrong_project = list(
                codex.scan_file(
                    session,
                    root,
                    date(2026, 8, 28),
                    date(2026, 8, 28),
                    project_filter="other",
                    project_roots=[r"D:\WorkSpace"],
                )
            )
            wrong_date = list(
                codex.scan_file(
                    session,
                    root,
                    date(2026, 8, 27),
                    date(2026, 8, 27),
                    project_roots=[r"D:\WorkSpace"],
                )
            )
        self.assertEqual(len(matching), 2)
        self.assertEqual(wrong_project, [])
        self.assertEqual(wrong_date, [])

    def test_resolves_active_and_archived_dirs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = codex.resolve_history_dirs(environ={"CODEX_HOME": str(root)})
        self.assertEqual(paths, [(root / "sessions").resolve(), (root / "archived_sessions").resolve()])


if __name__ == "__main__":
    unittest.main()
