#!/usr/bin/env python3
"""Azure DevOps Server (on-prem TFS) REST API 客户端。

从本地配置文件 ~/.config/azdo/config.json 读取 baseUrl / collection / PAT，
封装常用 PR 接口。代码与命令行都不出现明文 PAT。

配置文件模板见 ../config/config.example.json，复制到
~/.config/azdo/config.json（Windows: %USERPROFILE%\\.config\\azdo\\config.json）
后填入 pat 字段即可。

依赖：pip install requests
"""
import argparse
import base64
import json
import os
import sys
from urllib.parse import quote

try:
    import requests
except ImportError:
    sys.exit("需要 requests 库：pip install requests")

# on-prem 常用自签名证书，默认不校验；如需校验改 verify=True
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Windows 控制台默认 GBK，强制 stdout 用 UTF-8，避免中文输出乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

CONFIG_PATH = os.path.expanduser("~/.config/azdo/config.json")
API_VERSION = "5.0"


def load_config():
    if not os.path.exists(CONFIG_PATH):
        sys.exit(
            f"找不到配置文件 {CONFIG_PATH}\n"
            "请按 config/config.example.json 创建并填入 pat。"
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("pat"):
        sys.exit(f"{CONFIG_PATH} 中 pat 为空，请先填入个人访问令牌。")
    return cfg


def make_session(cfg):
    session = requests.Session()
    token = base64.b64encode(f":{cfg['pat']}".encode()).decode()
    session.headers.update({
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
    })
    session.verify = False
    return session


def repo_base(cfg, repo, project=None):
    project = project or cfg.get("defaultProject", "")
    return f"{cfg['baseUrl']}/{cfg['collection']}/{quote(project)}/_apis/git/repositories/{quote(repo)}"


# ---- 命令实现 ----

def cmd_pr_threads(args):
    url = f"{repo_base(args.cfg, args.repo)}/pullRequests/{args.pr_id}/threads?api-version={API_VERSION}"
    r = args.session.get(url)
    r.raise_for_status()
    for t in r.json().get("value", []):
        c = t["comments"][0] if t.get("comments") else {}
        content = (c.get("content") or "")[:60]
        print(f"[{t['id']}] status={t.get('status')} type={c.get('commentType')} "
              f"deleted={t.get('isDeleted')} | {content}")


def _read_content(args, content_attr="content", file_attr="content_file"):
    """文本内容来源：--<file> > --<content> -（stdin）> --<content> 字面值。
    长内容（含 markdown 反引号/$/换行）优先用 stdin 或文件，避免命令行转义。
    content_attr/file_attr 用于复用到 update-pr 的 --description/--description-file。"""
    file_val = getattr(args, file_attr, None)
    if file_val:
        with open(file_val, "r", encoding="utf-8") as f:
            return f.read()
    content_val = getattr(args, content_attr, None)
    if content_val == "-":
        return sys.stdin.read()
    return content_val


def cmd_add_comment(args):
    if args.content is None and not getattr(args, "content_file", None):
        sys.exit("需要评论内容：用 --content、--content -（stdin）或 --content-file 之一")
    body = {
        "comments": [{"commentType": 1, "content": _read_content(args)}],
        "status": 1,
    }
    if args.file:
        body["threadContext"] = {
            "filePath": args.file,
            "rightFileStart": {"line": args.line, "offset": 1},
            "rightFileEnd": {"line": args.line, "offset": args.offset},
        }
        if args.change_tracking_id is None:
            sys.exit("行内评论需要 --change-tracking-id（来自 iterations/{id}/changes）")
        body["pullRequestThreadContext"] = {
            "changeTrackingId": args.change_tracking_id,
            "iterationContext": {
                "firstComparingIteration": args.iteration_from,
                "secondComparingIteration": args.iteration_to,
            },
        }
    url = f"{repo_base(args.cfg, args.repo)}/pullRequests/{args.pr_id}/threads?api-version={API_VERSION}"
    r = args.session.post(url, json=body)
    r.raise_for_status()
    print(f"已创建 thread {r.json()['id']}")


def cmd_del_comment(args):
    url = (f"{repo_base(args.cfg, args.repo)}/pullRequests/{args.pr_id}"
           f"/threads/{args.thread_id}/comments/{args.comment_id}?api-version={API_VERSION}")
    r = args.session.delete(url)
    r.raise_for_status()
    print(f"已删除 thread {args.thread_id} comment {args.comment_id}")


def cmd_file_content(args):
    url = (f"{repo_base(args.cfg, args.repo)}/items?path={quote(args.path)}"
           f"&versionDescriptor.version={args.commit}&versionDescriptor.versionType=commit"
           f"&api-version={API_VERSION}")
    r = args.session.get(url)
    r.raise_for_status()
    print(r.text)


def cmd_iterations(args):
    url = f"{repo_base(args.cfg, args.repo)}/pullRequests/{args.pr_id}/iterations?api-version={API_VERSION}"
    r = args.session.get(url)
    r.raise_for_status()
    for it in r.json().get("value", []):
        src = it["sourceRefCommit"]["commitId"][:10]
        tgt = it["targetRefCommit"]["commitId"][:10]
        print(f"iteration {it['id']}: source={src} target={tgt}")


def cmd_pr_detail(args):
    url = f"{repo_base(args.cfg, args.repo)}/pullRequests/{args.pr_id}?api-version={API_VERSION}"
    r = args.session.get(url)
    r.raise_for_status()
    pr = r.json()
    print(f"title       : {pr.get('title')}")
    print(f"status      : {pr.get('status')}")
    print(f"createdBy   : {(pr.get('createdBy') or {}).get('displayName')}")
    print(f"sourceRef   : {pr.get('sourceRefName')}")
    print(f"targetRef   : {pr.get('targetRefName')}")
    print(f"mergeStatus : {pr.get('mergeStatus')}")
    print(f"sourceCommit: {(pr.get('lastMergeSourceCommit') or {}).get('commitId')}")
    print(f"targetCommit: {(pr.get('lastMergeTargetCommit') or {}).get('commitId')}")


def cmd_pr_commits(args):
    url = f"{repo_base(args.cfg, args.repo)}/pullRequests/{args.pr_id}/commits?api-version={API_VERSION}"
    r = args.session.get(url)
    r.raise_for_status()
    for c in r.json().get("value", []):
        cid = (c.get("commitId") or "")[:10]
        author = (c.get("author") or {}).get("name")
        raw = (c.get("comment") or "").strip()
        comment = raw.splitlines()[0] if raw else ""
        print(f"{cid} {author}: {comment[:80]}")


def _latest_iteration_id(args):
    url = f"{repo_base(args.cfg, args.repo)}/pullRequests/{args.pr_id}/iterations?api-version={API_VERSION}"
    r = args.session.get(url)
    r.raise_for_status()
    its = r.json().get("value", [])
    if not its:
        sys.exit("该 PR 没有迭代数据")
    return its[-1]["id"]


def cmd_pr_changes(args):
    iteration_id = args.iteration if args.iteration is not None else _latest_iteration_id(args)
    url = (f"{repo_base(args.cfg, args.repo)}/pullRequests/{args.pr_id}"
           f"/iterations/{iteration_id}/changes?api-version={API_VERSION}")
    r = args.session.get(url)
    r.raise_for_status()
    for e in r.json().get("changeEntries", []):
        item = e.get("item", {})
        print(f"[{e.get('changeTrackingId')}] {e.get('changeType')} {item.get('path')}")


def cmd_reviewers(args):
    url = f"{repo_base(args.cfg, args.repo)}/pullRequests/{args.pr_id}/reviewers?api-version={API_VERSION}"
    r = args.session.get(url)
    r.raise_for_status()
    for rv in r.json().get("value", []):
        print(f"{rv.get('displayName')} vote={rv.get('vote')}")


def cmd_update_pr(args):
    has_desc = args.description is not None or args.description_file is not None
    body = {}
    if has_desc:
        body["description"] = _read_content(args, "description", "description_file")
    if args.title is not None:
        body["title"] = args.title
    if not body:
        sys.exit("需要至少一个更新字段：--description（或 --description-file）或 --title")
    url = f"{repo_base(args.cfg, args.repo)}/pullrequests/{args.pr_id}?api-version={API_VERSION}"
    r = args.session.patch(url, json=body)
    r.raise_for_status()
    pr = r.json()
    print(f"已更新 PR {args.pr_id}")
    if "title" in body:
        print(f"title       : {pr.get('title')}")
    if "description" in body:
        print(f"description : {len(pr.get('description') or '')} 字符")


def build_parser():
    parser = argparse.ArgumentParser(description="Azure DevOps Server REST API 客户端（PAT 从本地配置读取）")
    parser.add_argument("--repo", default=None, help="仓库名（默认用配置里的 defaultRepo）")
    parser.add_argument("--project", default=None, help="项目名（默认用配置里的 defaultProject）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("pr-threads", help="列出 PR 评论线程")
    sp.add_argument("pr_id")
    sp.set_defaults(func=cmd_pr_threads)

    sp = sub.add_parser("add-comment", help="创建评论（普通或行内）")
    sp.add_argument("pr_id")
    sp.add_argument("--file", help="行内评论的文件路径（不填则普通评论）")
    sp.add_argument("--line", type=int, help="行内评论定位的行号")
    sp.add_argument("--offset", type=int, default=73, help="rightFileEnd.offset，默认 73")
    sp.add_argument("--change-tracking-id", type=int, help="行内评论的 changeTrackingId")
    sp.add_argument("--iteration-from", type=int, default=1,
                    help="iterationContext.firstComparingIteration，默认 1（多迭代 PR 行内评论定位偏移时按 iterations 输出调整）")
    sp.add_argument("--iteration-to", type=int, default=1,
                    help="iterationContext.secondComparingIteration，默认 1")
    sp.add_argument("--content", help="评论内容；传 - 从 stdin 读（推荐用于长 markdown，配合 <<'EOF' heredoc）")
    sp.add_argument("--content-file", help="评论内容文件路径（与 --content 二选一，适合长 markdown）")
    sp.set_defaults(func=cmd_add_comment)

    sp = sub.add_parser("del-comment", help="删除评论（软删除）")
    sp.add_argument("pr_id")
    sp.add_argument("thread_id")
    sp.add_argument("comment_id")
    sp.set_defaults(func=cmd_del_comment)

    sp = sub.add_parser("file-content", help="按 commit 取文件内容")
    sp.add_argument("--path", required=True)
    sp.add_argument("--commit", required=True)
    sp.set_defaults(func=cmd_file_content)

    sp = sub.add_parser("iterations", help="列出 PR 迭代")
    sp.add_argument("pr_id")
    sp.set_defaults(func=cmd_iterations)

    sp = sub.add_parser("pr-detail", help="PR 详情（标题/状态/分支/merge commit）")
    sp.add_argument("pr_id")
    sp.set_defaults(func=cmd_pr_detail)

    sp = sub.add_parser("pr-commits", help="PR 提交记录")
    sp.add_argument("pr_id")
    sp.set_defaults(func=cmd_pr_commits)

    sp = sub.add_parser("pr-changes", help="PR 文件变更清单（含 changeTrackingId，默认最新迭代）")
    sp.add_argument("pr_id")
    sp.add_argument("--iteration", type=int, default=None, help="指定迭代号，缺省取最新")
    sp.set_defaults(func=cmd_pr_changes)

    sp = sub.add_parser("reviewers", help="PR 审阅者及投票")
    sp.add_argument("pr_id")
    sp.set_defaults(func=cmd_reviewers)

    sp = sub.add_parser("update-pr", help="更新 PR（描述 / 标题）")
    sp.add_argument("pr_id")
    sp.add_argument("--description", help="新的 PR 描述；传 - 从 stdin 读（长 markdown 推荐，配合 <<'EOF' heredoc）")
    sp.add_argument("--description-file", help="从文件读 PR 描述（与 --description 二选一，适合长 markdown）")
    sp.add_argument("--title", help="新的 PR 标题")
    sp.set_defaults(func=cmd_update_pr)

    return parser


def main():
    args = build_parser().parse_args()
    args.cfg = load_config()
    args.repo = args.repo or args.cfg.get("defaultRepo")
    if not args.repo:
        sys.exit("未指定仓库：用 --repo 或在配置里设 defaultRepo")
    args.session = make_session(args.cfg)
    args.func(args)


if __name__ == "__main__":
    main()
