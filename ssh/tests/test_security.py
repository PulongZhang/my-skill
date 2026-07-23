import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / 'lib'))

from deploy_pubkey import _validate_public_key
from security import (is_dangerous_command, quote_posix_shell_arg,
                      validate_ssh_config_value)
from sftp_transfer import SFTPTransfer


class SecurityHelperTests(unittest.TestCase):
    def test_shell_quote_keeps_single_argument(self):
        quoted = quote_posix_shell_arg("a'; touch /tmp/pwned; #")
        self.assertEqual(quoted, "'a'\"'\"'; touch /tmp/pwned; #'")

    def test_config_rejects_newline_injection(self):
        with self.assertRaises(ValueError):
            validate_ssh_config_value("host\n    ProxyCommand id", "hostname")

    def test_dangerous_command_needs_confirmation(self):
        self.assertTrue(is_dangerous_command("sudo systemctl restart nginx"))
        self.assertTrue(is_dangerous_command("rm -rf /var/tmp/cache"))
        self.assertFalse(is_dangerous_command("df -h"))

    def test_public_key_rejects_multiline_and_invalid_base64(self):
        with self.assertRaises(ValueError):
            _validate_public_key("ssh-ed25519 aGVsbG8= comment\nrm -rf /")
        with self.assertRaises(ValueError):
            _validate_public_key("ssh-ed25519 not-base64!")


class Entry:
    def __init__(self, filename, mode):
        self.filename = filename
        self.st_mode = mode


class FakeSftp:
    def listdir_attr(self, _):
        return [Entry('../escape', 0o100644), Entry('safe.txt', 0o100644)]


class SftpContainmentTests(unittest.TestCase):
    def test_recursive_download_rejects_escape_name(self):
        with tempfile.TemporaryDirectory() as directory:
            transfer = SFTPTransfer(FakeSftp())
            transfer._download_root = os.path.realpath(directory)
            # Avoid a real transfer for the valid fake file.
            transfer.download_file = lambda *_args, **_kwargs: type(
                'Result', (), {'bytes_transferred': 0, 'files_transferred': 0,
                               'files_failed': 0, 'details': [], 'errors': []}
            )()
            result = type('Result', (), {'bytes_transferred': 0, 'files_transferred': 0,
                                         'files_failed': 0, 'details': [], 'errors': []})()
            transfer._download_dir_recursive('/remote', directory, False, result)
            self.assertEqual(result.files_failed, 1)
            self.assertTrue(any('不安全' in error for error in result.errors))


if __name__ == '__main__':
    unittest.main()
