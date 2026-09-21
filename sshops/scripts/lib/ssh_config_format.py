"""
SSH config 规范格式模块

~/.ssh/config 的唯一权威格式定义：解析、规范化与渲染。
ssh_config_manager_v3.py、format_ssh_config.py 必须复用本模块，
不要在别处再实现一套字段顺序。

规范格式：

    # ===== <alias> =====
    # description: ...
    # environment: ...
    # tags: tag1,tag2
    # location: ...
    # password: ...
    # created_at: YYYY-MM-DD HH:MM:SS
    # updated_at: YYYY-MM-DD HH:MM:SS
    Host <alias>
        HostName <主机>
        User <用户>
        [Port <非 22 端口>]
        [IdentityFile ~/.ssh/<密钥>]
        [ProxyJump <别名>]

规则：
- 元数据字段顺序固定，空值省略；tags 用逗号分隔。
- 块间恰好一个空行，文件首行直接是块头，文件尾单个换行；行尾风格沿用原文件。
- Host 内指令顺序固定（hostname/user/port/identityfile/proxyjump/forwardagent）；
  22 端口省略 Port 行；IdentityFile 一律归一为 ~/.ssh/<文件名>；
  未识别指令按原顺序、原拼写保留。
- 非通配 Host 块中无法识别的注释行原样保留在块头之后。
- 通配块（Host *）与不含任何元数据的块整体原样保留，不做改写。
"""

import os
import re

METADATA_KEYS = ('description', 'environment', 'tags', 'location',
                 'password', 'created_at', 'updated_at')

DIRECTIVE_ORDER = ('hostname', 'user', 'port', 'identityfile', 'proxyjump',
                   'forwardagent')

DIRECTIVE_SPELLING = {
    'hostname': 'HostName',
    'user': 'User',
    'port': 'Port',
    'identityfile': 'IdentityFile',
    'proxyjump': 'ProxyJump',
    'forwardagent': 'ForwardAgent',
}


def detect_newline(text):
    """检测行尾风格：出现 CRLF 即按 CRLF 渲染，否则 LF。"""
    return '\r\n' if '\r\n' in text else '\n'


def normalize_identity_path(key_path):
    """把密钥路径归一为 ~/.ssh/<文件名> 形式（已是该形式则原样返回）。"""
    if not key_path:
        return key_path
    normalized = str(key_path).replace('\\', '/')
    if '/.ssh/' in normalized:
        return '~/.ssh/' + normalized.split('/.ssh/', 1)[1]
    return key_path


def _parse_metadata_line(line):
    """解析一行注释，返回 (key, value)；不是元数据行时返回 None。"""
    stripped = line.strip()
    if not stripped.startswith('#'):
        return None
    stripped = stripped[1:].strip()
    if not stripped or stripped.startswith('====='):
        return None
    if ':' not in stripped:
        return None
    key, value = stripped.split(':', 1)
    key = key.strip()
    if key not in METADATA_KEYS:
        return None
    return key, value.strip()


def parse_metadata_comments(comment_lines):
    """
    解析元数据注释。

    Returns:
        (metadata, extras)：metadata 为已知字段字典（tags 为列表）；
        extras 为无法识别的注释行（原样保留用，已剔除空行）。
    """
    metadata = {}
    extras = []
    for line in comment_lines:
        parsed = _parse_metadata_line(line)
        if parsed is None:
            if line.strip() and not line.strip().startswith('# ====='):
                extras.append(line.strip())
            continue
        key, value = parsed
        if key == 'tags':
            metadata['tags'] = [t.strip() for t in value.split(',') if t.strip()]
        else:
            metadata[key] = value
    return metadata, extras


def _has_metadata(comment_lines):
    return any(_parse_metadata_line(line) is not None for line in comment_lines)


def render_metadata_lines(alias, metadata, extras, newline='\n'):
    """渲染规范元数据块（含块头分隔行），返回行列表。"""
    lines = ['# ===== {} ====='.format(alias)]
    lines.extend(extras)
    for key in METADATA_KEYS:
        value = metadata.get(key)
        if key == 'tags':
            if value:
                lines.append('# tags: {}'.format(','.join(value)))
            continue
        if value:
            lines.append('# {}: {}'.format(key, value))
    return [line + newline for line in lines]


def parse_directives(config_lines):
    """
    解析 Host 块内的指令行。

    Returns:
        (directives, comments)：
        directives 为 (key_lower, raw_key, value) 列表（保持原顺序）；
        comments 为块内注释行（原样保留用）。
    """
    directives = []
    comments = []
    for line in config_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('#'):
            comments.append(stripped)
            continue
        parts = stripped.split(None, 1)
        key = parts[0].lower()
        value = parts[1].strip() if len(parts) > 1 else ''
        directives.append((key, parts[0], value))
    return directives, comments


def _format_directive(key, value):
    """渲染单条指令行（不含缩进换行）；Port 22 返回 None 表示省略。"""
    if key == 'port':
        try:
            if int(value) == 22:
                return None
        except ValueError:
            pass
    if key == 'identityfile':
        value = normalize_identity_path(value)
    return '    {} {}'.format(DIRECTIVE_SPELLING.get(key, key), value)


def render_directive_lines(directives, comments=(), newline='\n', extra=None):
    """
    渲染规范指令块。

    Args:
        directives: parse_directives 的输出
        comments: 块内注释行
        extra: 覆盖或追加的指令 {key_lower: value}，覆盖时替换原值
    """
    values_by_key = {}
    order = []
    spelling = {}
    for key, raw_key, value in directives:
        if key not in values_by_key:
            values_by_key[key] = []
            order.append(key)
        values_by_key[key].append(value)
        spelling.setdefault(key, raw_key)
    for key, value in (extra or {}).items():
        values = [value] if isinstance(value, str) else list(value)
        if key not in values_by_key:
            order.append(key)
        values_by_key[key] = values

    rendered = []
    emitted = set()
    # 已知字段先按固定顺序输出（覆盖未识别指令的原始位置）
    for key in DIRECTIVE_ORDER:
        if key not in values_by_key:
            continue
        emitted.add(key)
        for value in values_by_key[key]:
            line = _format_directive(key, value)
            if line:
                rendered.append(line)
    # 未识别指令保持原顺序、原拼写
    for key in order:
        if key in emitted:
            continue
        for value in values_by_key[key]:
            rendered.append('    {} {}'.format(spelling.get(key, key), value))

    rendered.extend(comments)
    return [line + newline for line in rendered]


def _is_managed_block(alias, comment_lines):
    """带元数据或块头的非通配块才做规范化，其余原样保留。"""
    if not alias:
        return False
    if any(line.strip().startswith('# =====') for line in comment_lines):
        return True
    return _has_metadata(comment_lines)


def format_config_text(text):
    """
    把 SSH config 文本规范化为标准格式。

    幂等：format(format(x)) == format(x)。行尾风格沿用输入。
    """
    newline = detect_newline(text)
    lines = text.splitlines()
    out = []
    pending = []
    i = 0
    total = len(lines)

    def flush_verbatim():
        for item in pending:
            out.append(item + newline)
        del pending[:]

    while i < total:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith('Host ') and not stripped.startswith('Host *'):
            alias = stripped[len('Host '):].strip()
            comments = pending
            pending = []
            config_lines = []
            i += 1
            while i < total:
                nxt = lines[i]
                if not nxt.strip() or not nxt[:1].isspace():
                    break
                config_lines.append(nxt)
                i += 1

            if not _is_managed_block(alias, comments):
                for comment in comments:
                    out.append(comment + newline)
                out.append(line + newline)
                for config_line in config_lines:
                    out.append(config_line + newline)
                continue

            if out:
                out.append(newline)
            metadata, extras = parse_metadata_comments(comments)
            out.extend(render_metadata_lines(alias, metadata, extras, newline))
            out.append('Host {}'.format(alias) + newline)
            directives, block_comments = parse_directives(config_lines)
            out.extend(render_directive_lines(directives, block_comments, newline))
            continue

        if stripped.startswith('#') or not stripped:
            pending.append(line)
            i += 1
            continue

        flush_verbatim()
        out.append(line + newline)
        i += 1

    flush_verbatim()
    while out and out[-1] == newline:
        out.pop()
    return ''.join(out)


def format_config_file(path, dry_run=False):
    """就地规范化 SSH config 文件（保持文件权限不变）。"""
    with open(path, 'r', encoding='utf-8', newline='') as handle:
        original = handle.read()
    formatted = format_config_text(original)
    changed = formatted != original
    if changed and not dry_run:
        with open(path, 'w', encoding='utf-8', newline='') as handle:
            handle.write(formatted)
    return changed
