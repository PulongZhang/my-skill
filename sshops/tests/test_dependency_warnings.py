import subprocess
import sys
import unittest


class ParamikoWarningTests(unittest.TestCase):
    def test_paramiko_import_emits_no_warnings(self):
        result = subprocess.run(
            [sys.executable, '-W', 'error', '-c', 'import paramiko'],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f'Paramiko import emitted a warning or failed:\n{result.stderr}',
        )


if __name__ == '__main__':
    unittest.main()
