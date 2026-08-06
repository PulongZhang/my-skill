import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import daily_git_commits as git_commits


class PathNormalizeTest(unittest.TestCase):
    def test_normalize_paths_converts_windows_backslash(self):
        result = git_commits.normalize_paths([r"D:\CETWorkSpace", r"D:\WorkSpace"])
        self.assertEqual(result, ["D:/CETWorkSpace", "D:/WorkSpace"])

    def test_normalize_paths_keeps_forward_slash_and_non_drive(self):
        result = git_commits.normalize_paths(["D:/CETWorkSpace", "/home/user/proj"])
        self.assertEqual(result, ["D:/CETWorkSpace", "/home/user/proj"])

    def test_find_git_repos_with_normalized_paths(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "demo-repo" / ".git"
            repo.mkdir(parents=True)
            repos = git_commits.find_git_repos([temp_dir.replace("\\", "/")])
            self.assertEqual(len(repos), 1)


if __name__ == "__main__":
    unittest.main()
