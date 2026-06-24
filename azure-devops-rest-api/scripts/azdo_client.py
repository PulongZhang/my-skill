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


def cmd_add_comment(args):
    body = {
        "comments": [{"commentType": 1, "content": args.content}],
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
            "iterationContext": {"firstComparingIteration": 1, "secondComparingIteration": 1},
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
    sp.add_argument("--content", required=True, help="评论内容")
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
