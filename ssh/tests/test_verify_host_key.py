import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / 'lib'))

from verify_host_key import (_lines_matching, entry_name, known_hosts_path,
                             parse_keyscan_output, record, sha256_fingerprint)

# Golden vector captured from real ssh-keygen -lf on the same key.
GOLDEN_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILPfo9Xfy6wvrvf/MqmLqRsRN1RWdyuLk/Qmtr0GQrhU golden-test"
GOLDEN_FINGERPRINT = "SHA256:CM+S9DI/jrjgBwAMcfoVq9ZMalbWAgNOAI7bzcaPjSo"


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_matches_ssh_keygen(self):
        blob = GOLDEN_KEY.split()[1]
        self.assertEqual(sha256_fingerprint(blob), GOLDEN_FINGERPRINT)

    def test_parse_keyscan_output(self):
        text = (
            f"192.0.2.1 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ== comment\n"
            f"[192.0.2.1]:2222 {GOLDEN_KEY}\n"
            f"# keyscan error line\n"
        )
        self.assertEqual(parse_keyscan_output(text),
                         [("ssh-rsa", "AAAAB3NzaC1yc2EAAAADAQABAAABAQ=="),
                          ("ssh-ed25519", GOLDEN_KEY.split()[1])])

    def test_parse_keyscan_empty(self):
        self.assertEqual(parse_keyscan_output(""), [])


class KnownHostsTests(unittest.TestCase):
    def test_entry_name_port_22_is_plain(self):
        self.assertEqual(entry_name("192.0.2.1", 22), "192.0.2.1")

    def test_entry_name_non_22_uses_brackets(self):
        self.assertEqual(entry_name("192.0.2.1", 2222), "[192.0.2.1]:2222")

    def test_lines_matching_matches_both_forms(self):
        lines = [
            "192.0.2.1 ssh-ed25519 AAAA\n",
            "[192.0.2.1]:2222 ssh-rsa BBBB\n",
            "other-host ssh-rsa CCCC\n",
            "# comment line\n",
            "\n",
        ]
        self.assertEqual(_lines_matching("192.0.2.1", 22, lines), lines[:1])
        self.assertEqual(_lines_matching("192.0.2.1", 2222, lines), lines[1:2])

    @mock.patch('verify_host_key.scan',
                return_value=(0, f"192.0.2.1 {GOLDEN_KEY}\n"))
    def test_record_without_confirm_does_not_write(self, _mock_scan):
        with tempfile.TemporaryDirectory() as directory:
            fake_known_hosts = os.path.join(directory, 'known_hosts')
            with mock.patch('verify_host_key.known_hosts_path',
                            return_value=fake_known_hosts):
                self.assertFalse(record("192.0.2.1", 22, confirmed=False))
                self.assertFalse(os.path.exists(fake_known_hosts))

    @mock.patch('verify_host_key.scan',
                return_value=(0, f"192.0.2.1 {GOLDEN_KEY}\n"))
    def test_record_with_confirm_writes_and_dedupes(self, _mock_scan):
        with tempfile.TemporaryDirectory() as directory:
            fake_known_hosts = os.path.join(directory, 'known_hosts')
            with mock.patch('verify_host_key.known_hosts_path',
                            return_value=fake_known_hosts):
                self.assertTrue(record("192.0.2.1", 22, confirmed=True))
                with open(fake_known_hosts, 'r', encoding='utf-8') as f:
                    content = f.read()
                # known_hosts 行格式：<name> <keytype> <blob>（不含注释字段）
                keytype, blob = GOLDEN_KEY.split()[:2]
                self.assertIn(f"192.0.2.1 {keytype} {blob}", content)
                # 第二次记录应去重，不重复追加
                self.assertTrue(record("192.0.2.1", 22, confirmed=True))
                with open(fake_known_hosts, 'r', encoding='utf-8') as f:
                    self.assertEqual(content, f.read())


if __name__ == '__main__':
    unittest.main()
