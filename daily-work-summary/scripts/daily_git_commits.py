#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
每日 Git 提交报告提取工具
========================
扫描指定目录下所有 Git 仓库，提取指定用户的提交记录，按日期分组输出。

用法:
    python daily_git_commits.py                          # 默认今天
    python daily_git_commits.py --date 2026-04-13        # 指定日期
    python daily_git_commits.py --since 2026-04-01       # 指定起始日期到今天
    python daily_git_commits.py --since 2026-04-01 --until 2026-04-13  # 指定日期范围
    python daily_git_commits.py --output report.md       # 输出到文件
"""

import subprocess
import os
import sys
import io
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

# 解决 Windows 控制台 GBK 编码问题
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ==================== 配置区域 ====================

# Git 用户名（author）
GIT_AUTHOR = "zhangpulong"

# 要扫描的根目录列表，脚本会递归查找其中所有 Git 仓库
SCAN_ROOTS = [
    r"D:\WorkSpace",
    r"D:\CETWorkSpace",
    # 如需添加更多目录，在此处追加即可
]

# 最大递归深度（避免扫描过深）
MAX_DEPTH = 4

# ==================== 配置区域结束 ====================


def find_git_repos(roots, max_depth=MAX_DEPTH):
    """递归扫描目录，找到所有包含 .git 的仓库路径"""
    repos = []
    for root in roots:
        if not os.path.isdir(root):
            print(f"  ⚠ 目录不存在，跳过: {root}")
            continue
        for dirpath, dirnames, _ in os.walk(root):
            # 计算当前深度
            depth = dirpath.replace(root, "").count(os.sep)
            if depth >= max_depth:
                dirnames.clear()
                continue
            if ".git" in dirnames:
                repos.append(dirpath)
                # 不再往该仓库子目录继续搜索（子模块除外）
                dirnames.clear()
    return sorted(set(repos))


# commit 之间的分隔标记
COMMIT_SEPARATOR = "<<==COMMIT_BOUNDARY==>>"
FIELD_SEPARATOR = "<<==FIELD==>>"


def _run_git_log(repo_path, author, since_date, until_date):
    """执行一次 git log 命令，返回原始输出（包含完整 commit body）"""
    # 使用特殊分隔符区分各字段和各 commit，支持多行 body
    log_format = FIELD_SEPARATOR.join(["%H", "%an", "%ai", "%s", "%b"]) + COMMIT_SEPARATOR

    cmd = [
        "git", "log",
        f"--author={author}",
        f"--after={since_date}",
        f"--before={until_date}",
        f"--pretty=format:{log_format}",
        "--all",  # 搜索所有分支
        "--no-merges",  # 排除 merge commit（通常无实际意义）
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode != 0:
            return ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""

    return result.stdout


def get_git_log(repo_path, author, since_date, until_date):
    """
    获取指定仓库中某作者在日期范围内的所有提交记录。
    返回 list[dict]，每个 dict 包含提交的详细信息（含完整 commit body）。
    会同时尝试 author 和 "author"（带双引号）两种形式，防止 git config
    中 user.name 含引号导致匹配失败。
    """
    # 同时搜索带引号和不带引号的用户名，然后合并去重
    variants = [author]
    stripped = author.strip('"')
    quoted = f'"{stripped}"'
    if quoted != author:
        variants.append(quoted)
    if stripped != author:
        variants.append(stripped)

    raw_output = ""
    for variant in variants:
        output = _run_git_log(repo_path, variant, since_date, until_date)
        if output.strip():
            raw_output += output

    if not raw_output.strip():
        return []

    # 按 commit 分隔符拆分
    commit_blocks = raw_output.split(COMMIT_SEPARATOR)

    seen_hashes = set()
    commits = []
    for block in commit_blocks:
        block = block.strip()
        if not block:
            continue
        parts = block.split(FIELD_SEPARATOR, 4)
        if len(parts) >= 4:
            commit_hash = parts[0].strip()
            author_name = parts[1].strip()
            date_str = parts[2].strip()
            subject = parts[3].strip()
            body = parts[4].strip() if len(parts) > 4 else ""

            if commit_hash in seen_hashes:
                continue
            seen_hashes.add(commit_hash)

            # 组合完整消息：标题 + 换行 + body
            full_message = subject
            if body:
                full_message = subject + "\n\n" + body

            commits.append({
                "hash": commit_hash[:8],
                "full_hash": commit_hash,
                "author": author_name.strip('"'),
                "datetime": date_str,
                "date": date_str[:10],  # YYYY-MM-DD
                "time": date_str[11:19],  # HH:MM:SS
                "subject": subject,  # 仅标题行
                "body": body,  # 详细描述
                "message": full_message,  # 完整信息
                "repo": os.path.basename(repo_path),
                "repo_path": repo_path,
            })
    return commits


def get_changed_files(repo_path, commit_hash):
    """获取某次提交修改的文件列表（带状态：A/M/D）"""
    cmd = [
        "git", "diff-tree", "--no-commit-id", "-r", "--name-status", commit_hash
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []

    files = []
    status_map = {"A": "新增", "M": "修改", "D": "删除", "R": "重命名"}
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            status, filename = parts
            # 处理重命名等带数字的状态，如 R100
            status_char = status[0]
            files.append({
                "status": status_map.get(status_char, status_char),
                "file": filename,
            })
    return files


def get_diff_stat(repo_path, commit_hash):
    """获取某次提交的增删行统计"""
    cmd = [
        "git", "diff-tree", "--no-commit-id", "--stat", "-r", commit_hash
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode != 0:
            return ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""

    lines = result.stdout.strip().splitlines()
    # 最后一行通常是统计摘要
    if lines:
        return lines[-1].strip()
    return ""


def format_report(commits_by_date, show_files=True, author=GIT_AUTHOR):
    """将按日期分组的提交记录格式化为 Markdown 报告"""
    lines = []
    lines.append("# 📋 每日 Git 提交报告")
    lines.append(f"**用户**: `{author}`")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    if not commits_by_date:
        lines.append("> 🔍 在指定日期范围内未找到任何提交记录。")
        return "\n".join(lines)

    total_commits = sum(len(c) for c in commits_by_date.values())
    total_days = len(commits_by_date)
    lines.append(f"**统计**: 共 **{total_days}** 天，**{total_commits}** 次提交")
    lines.append("")
    lines.append("---")
    lines.append("")

    for date in sorted(commits_by_date.keys(), reverse=True):
        commits = commits_by_date[date]
        # 按时间排序
        commits.sort(key=lambda c: c["time"])

        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        dt = datetime.strptime(date, "%Y-%m-%d")
        weekday = weekday_names[dt.weekday()]

        lines.append(f"## 📅 {date} ({weekday})  —  {len(commits)} 次提交")
        lines.append("")

        # 按仓库分组
        repo_commits = defaultdict(list)
        for c in commits:
            repo_commits[c["repo"]].append(c)

        for repo, rcommits in sorted(repo_commits.items()):
            lines.append(f"### 📁 {repo}")
            lines.append("")

            for c in rcommits:
                # 每个 commit 作为独立块展示
                lines.append(f"#### 🔖 `{c['hash']}` — `{c['time']}`")
                lines.append("")
                lines.append(f"**{c['subject']}**")
                lines.append("")

                # 显示详细的 commit body
                if c.get("body"):
                    for body_line in c["body"].splitlines():
                        lines.append(body_line)
                    lines.append("")

                # 显示修改的文件
                if show_files:
                    files = get_changed_files(c["repo_path"], c["full_hash"])
                    stat = get_diff_stat(c["repo_path"], c["full_hash"])
                    if files:
                        lines.append(f"📂 变更文件 ({len(files)} 个):")
                        lines.append("")
                        for f in files:
                            icon = {"新增": "🟢", "修改": "🟡", "删除": "🔴", "重命名": "🔵"}.get(
                                f["status"], "⚪"
                            )
                            lines.append(f"- {icon} **{f['status']}** `{f['file']}`")
                        if stat:
                            lines.append(f"\n📊 {stat}")
                        lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="提取指定用户每日 Git 提交记录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--author", default=GIT_AUTHOR, help=f"Git 用户名 (默认: {GIT_AUTHOR})"
    )
    parser.add_argument(
        "--date", default=None, help="指定日期，格式 YYYY-MM-DD (默认: 今天)"
    )
    parser.add_argument(
        "--since", default=None, help="起始日期，格式 YYYY-MM-DD"
    )
    parser.add_argument(
        "--until", default=None, help="结束日期，格式 YYYY-MM-DD (默认: 今天)"
    )
    parser.add_argument(
        "--output", "-o", default=None, help="输出文件路径 (默认: 打印到控制台)"
    )
    parser.add_argument(
        "--no-files", action="store_true", help="不显示每个 commit 的文件变更详情"
    )
    parser.add_argument(
        "--roots", nargs="+", default=None, help="要扫描的根目录列表 (覆盖默认配置)"
    )

    args = parser.parse_args()

    author = args.author

    # 确定日期范围
    # 注意：git --after/--before 是「严格不含边界」的，所以需要：
    #   after_date = 目标起始日期的前一天
    #   before_date = 目标结束日期的后一天
    today = datetime.now().strftime("%Y-%m-%d")
    if args.date:
        display_since = args.date
        display_until = args.date
        after_dt = datetime.strptime(args.date, "%Y-%m-%d") - timedelta(days=1)
        after_date = after_dt.strftime("%Y-%m-%d")
        before_dt = datetime.strptime(args.date, "%Y-%m-%d") + timedelta(days=1)
        before_date = before_dt.strftime("%Y-%m-%d")
    elif args.since:
        display_since = args.since
        after_dt = datetime.strptime(args.since, "%Y-%m-%d") - timedelta(days=1)
        after_date = after_dt.strftime("%Y-%m-%d")
        if args.until:
            display_until = args.until
            before_dt = datetime.strptime(args.until, "%Y-%m-%d") + timedelta(days=1)
            before_date = before_dt.strftime("%Y-%m-%d")
        else:
            display_until = today
            before_dt = datetime.now() + timedelta(days=1)
            before_date = before_dt.strftime("%Y-%m-%d")
    else:
        # 默认：今天
        display_since = today
        display_until = today
        after_dt = datetime.now() - timedelta(days=1)
        after_date = after_dt.strftime("%Y-%m-%d")
        before_dt = datetime.now() + timedelta(days=1)
        before_date = before_dt.strftime("%Y-%m-%d")

    scan_roots = args.roots if args.roots else SCAN_ROOTS

    print(f"🔍 扫描目录: {', '.join(scan_roots)}")
    print(f"👤 用户: {author}")
    print(f"📅 日期范围: {display_since} ~ {display_until}")
    print()

    # 1. 扫描所有 Git 仓库
    print("📂 正在扫描 Git 仓库...")
    repos = find_git_repos(scan_roots)
    print(f"   找到 {len(repos)} 个仓库")
    print()

    # 2. 提取提交记录
    print("📥 正在提取提交记录...")
    commits_by_date = defaultdict(list)
    total_found = 0

    for repo in repos:
        repo_name = os.path.basename(repo)
        commits = get_git_log(repo, author, after_date, before_date)
        filtered_commits = [c for c in commits if display_since <= c["date"] <= display_until]
        if filtered_commits:
            print(f"   ✅ {repo_name}: {len(filtered_commits)} 次提交")
            total_found += len(filtered_commits)
            for c in filtered_commits:
                commits_by_date[c["date"]].append(c)

    print(f"\n📊 共找到 {total_found} 次提交")
    print()

    # 3. 生成报告
    report = format_report(commits_by_date, show_files=not args.no_files, author=author)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"✅ 报告已保存到: {args.output}")
    else:
        print("=" * 60)
        print(report)


if __name__ == "__main__":
    main()
