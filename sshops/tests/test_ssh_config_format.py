import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / 'lib'))

from ssh_config_format import (format_config_file, format_config_text,
                               normalize_identity_path)

CANONICAL = (
    "# ===== prod-web-01 =====\n"
    "# description: 生产环境 Web 服务器\n"
    "# environment: production\n"
    "# tags: web,nginx\n"
    "# location: 北京\n"
    "# password: s3cret\n"
    "# created_at: 2026-03-01 12:00:00\n"
    "# updated_at: 2026-03-01 12:00:00\n"
    "Host prod-web-01\n"
    "    HostName 192.168.1.100\n"
    "    User root\n"
    "    IdentityFile ~/.ssh/id_ed25519\n"
)


def block(alias, comments, directives):
    return '\n'.join(comments + ['Host ' + alias] + directives) + '\n'


class NormalizeIdentityPathTests(unittest.TestCase):
    def test_windows_path(self):
        self.assertEqual(normalize_identity_path('C:/Users/dell/.ssh/id_ed25519'),
                         '~/.ssh/id_ed25519')
        self.assertEqual(normalize_identity_path(r'C:\Users\dell\.ssh\id_rsa'),
                         '~/.ssh/id_rsa')

    def test_existing_forms_kept(self):
        self.assertEqual(normalize_identity_path('~/.ssh/id_ed25519'),
                         '~/.ssh/id_ed25519')
        self.assertEqual(normalize_identity_path('/opt/keys/id_rsa'),
                         '/opt/keys/id_rsa')


class FormatTextTests(unittest.TestCase):
    def test_idempotent_on_canonical(self):
        self.assertEqual(format_config_text(CANONICAL), CANONICAL)

    def test_reorders_metadata_directives_and_adds_block_separator(self):
        messy = (
            "\n# tags: web,nginx\n"
            "# description: 生产环境 Web 服务器\n"
            "# environment: production\n"
            "# location: 北京\n"
            "# password: s3cret\n"
            "# updated_at: 2026-03-01 12:00:00\n"
            "# created_at: 2026-03-01 12:00:00\n"
            "Host prod-web-01\n"
            "    IdentityFile C:/Users/dell/.ssh/id_ed25519\n"
            "    User root\n"
            "    Port 22\n"
            "    HostName 192.168.1.100\n"
        )
        self.assertEqual(format_config_text(messy), CANONICAL)

    def test_drops_redundant_port_22_but_keeps_others(self):
        text = block('h', ['# ===== h =====', '# description: x'],
                     ['    HostName 1.2.3.4', '    User root', '    Port 22'])
        formatted = format_config_text(text)
        self.assertNotIn('Port 22', formatted)
        text = text.replace('    Port 22', '    Port 2222')
        self.assertIn('    Port 2222', format_config_text(text))

    def test_block_without_metadata_is_untouched(self):
        raw = ("ServerAliveInterval 60\n"
               "Host legacy\n"
               "    HostName 5.6.7.8\n"
               "    User root\n"
               "    Port 22\n"
               "    IdentityFile C:/Users/dell/.ssh/id_rsa\n")
        self.assertEqual(format_config_text(raw), raw)

    def test_wildcard_block_is_untouched(self):
        raw = "Host *\n    ServerAliveInterval 60\n"
        self.assertEqual(format_config_text(raw), raw)

    def test_unknown_directive_kept_in_place_with_spelling(self):
        text = block('h', ['# ===== h =====', '# description: x'],
                     ['    HostName 1.2.3.4', '    ForwardX11 yes',
                      '    User root', '    ProxyCommand nc %h %p'])
        formatted = format_config_text(text)
        self.assertIn('    ProxyCommand nc %h %p\n', formatted)
        # 已知字段前移，未识别指令保持相对顺序且排在后面
        self.assertLess(formatted.index('User root'), formatted.index('ForwardX11 yes'))
        self.assertLess(formatted.index('ForwardX11 yes'), formatted.index('ProxyCommand'))

    def test_unknown_comment_inside_block_is_kept(self):
        text = block('h', ['# ===== h =====', '# description: x', '# 块前备注'],
                     ['    HostName 1.2.3.4', '    User root'])
        formatted = format_config_text(text)
        self.assertIn('# 块前备注\n', formatted)
        self.assertLess(formatted.index('# 块前备注'), formatted.index('Host h'))

    def test_blank_field_lines_are_dropped(self):
        text = block('h', ['# ===== h =====', '# description: x', '# location:'],
                     ['    HostName 1.2.3.4', '    User root'])
        self.assertNotIn('# location:', format_config_text(text))

    def test_preserves_crlf(self):
        formatted = format_config_text(CANONICAL.replace('\n', '\r\n'))
        self.assertIn('\r\n', formatted)
        self.assertNotIn('\n\r', formatted)
        self.assertEqual(formatted.replace('\r\n', '\n'), CANONICAL)

    def test_multiple_blocks_separated_by_one_blank_line(self):
        text = CANONICAL + CANONICAL.replace('prod-web-01', 'prod-web-02')
        formatted = format_config_text(text)
        self.assertIn('\n\n# ===== prod-web-02 =====\n', formatted)
        self.assertEqual(formatted, format_config_text(formatted))


class FormatFileTests(unittest.TestCase):
    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'config')
            messy = CANONICAL.replace('    User root\n', '    User root\n    Port 22\n')
            with open(path, 'w', encoding='utf-8', newline='') as handle:
                handle.write(messy)
            changed = format_config_file(path, dry_run=True)
            self.assertTrue(changed)
            with open(path, 'r', encoding='utf-8', newline='') as handle:
                self.assertEqual(handle.read(), messy)

    def test_write_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'config')
            with open(path, 'w', encoding='utf-8', newline='') as handle:
                handle.write(CANONICAL.replace('    User root\n', '    User root\n    Port 22\n'))
            changed = format_config_file(path)
            self.assertTrue(changed)
            changed_again = format_config_file(path)
            self.assertFalse(changed_again)


if __name__ == '__main__':
    unittest.main()
