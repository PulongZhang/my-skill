import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import daily_claude_conversations as claude  # noqa: E402
import daily_codex_conversations as codex  # noqa: E402
import daily_git_commits as git  # noqa: E402
from daily_source_scope import DEFAULT_PROJECT_ROOTS, normalize_project_roots  # noqa: E402


class DailySourceScopeTests(unittest.TestCase):
    def test_all_extractors_share_default_project_roots(self):
        self.assertEqual(git.SCAN_ROOTS, DEFAULT_PROJECT_ROOTS)
        self.assertEqual(claude.DEFAULT_PROJECT_ROOTS, DEFAULT_PROJECT_ROOTS)
        self.assertEqual(codex.DEFAULT_PROJECT_ROOTS, DEFAULT_PROJECT_ROOTS)

    def test_all_extractors_normalize_the_same_override_roots(self):
        roots = [r"D:\WorkSpace", r"D:/CETWorkSpace", "/srv/work"]
        expected = normalize_project_roots(roots)
        self.assertEqual(git.normalize_paths(roots), expected)
        self.assertEqual([claude.normalize_win_path(path) for path in roots], expected)
        self.assertEqual([codex.normalize_win_path(path) for path in roots], expected)


if __name__ == "__main__":
    unittest.main()
