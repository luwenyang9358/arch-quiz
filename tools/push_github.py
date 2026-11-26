#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本仓库内容推送到 GitHub —— 走 Git Data API，不依赖 git 协议。

适用场景：所在网络连不上 github.com:443（git push 会 CONNECT 502），
但 api.github.com 可访问。

用法：
    export GH_TOKEN=ghp_xxxxxxxx          # 需要 repo 权限的 Personal Access Token
    python3 tools/push_github.py arch-quiz --desc "系统架构设计师刷题工具"

    python3 tools/push_github.py arch-quiz --dry-run   # 只看会传哪些文件

说明：
  * token 只从环境变量读，不接受命令行明文参数（避免写进 shell history）；
  * 会新建仓库（若不存在），并一次性提交为一个 commit（不是逐文件提交）；
  * 遵循 .gitignore：只上传 `git ls-files` 列出的文件。
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


def call(method, path, payload=None, token=None, ok=(200, 201, 204)):
    url = path if path.startswith("http") else API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "arch-quiz-push")
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode() or "{}"
            return r.status, json.loads(body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        if e.code in ok:
            return e.code, {}
        raise SystemExit(f"！{method} {path} → HTTP {e.code}\n{detail}")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", help="仓库名，例如 arch-quiz")
    ap.add_argument("--desc", default="软考高级「系统架构设计师」本地刷题工具：真题 + 模拟题 + 背诵卡")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)

    files = [f for f in git("ls-files").split("\n") if f]
    if not files:
        raise SystemExit("！当前目录没有 git 跟踪的文件，请先 git init && git add .")

    total = sum(os.path.getsize(f) for f in files)
    print(f"待上传 {len(files)} 个文件，共 {total/1024/1024:.2f} MB")
    if args.dry_run:
        for f in files:
            print(f"  {os.path.getsize(f)/1024:8.1f} KB  {f}")
        return
    if not TOKEN:
        raise SystemExit("！请先 export GH_TOKEN=<有 repo 权限的 PAT>")

    status, me = call("GET", "/user", token=TOKEN)
    owner = me["login"]
    print(f"账号：{owner}")

    status, repo = call("GET", f"/repos/{owner}/{args.repo}", token=TOKEN, ok=(200, 404))
    if status == 404:
        print(f"仓库不存在，创建 {owner}/{args.repo} …")
        call("POST", "/user/repos", {
            "name": args.repo,
            "description": args.desc,
            "private": bool(args.private),
            "has_issues": True,
            "has_wiki": False,
            "auto_init": False,
        }, token=TOKEN)
        parent = None
    else:
        print(f"仓库已存在：{repo['html_url']}（默认分支 {repo.get('default_branch')}）")
        args.branch = repo.get("default_branch") or args.branch
        st, ref = call("GET", f"/repos/{owner}/{args.repo}/git/ref/heads/{args.branch}",
                       token=TOKEN, ok=(200, 404, 409))
        parent = ref["object"]["sha"] if st == 200 else None

    if parent:
        st, base = call("GET", f"/repos/{owner}/{args.repo}/git/commits/{parent}", token=TOKEN)
        base_tree = base["tree"]["sha"]
    else:
        base_tree = None

    entries = []
    for i, f in enumerate(files, 1):
        mode = "100755" if os.access(f, os.X_OK) else "100644"
        with open(f, "rb") as fh:
            blob = base64.b64encode(fh.read()).decode()
        st, res = call("POST", f"/repos/{owner}/{args.repo}/git/blobs",
                       {"content": blob, "encoding": "base64"}, token=TOKEN)
        entries.append({"path": f, "mode": mode, "type": "blob", "sha": res["sha"]})
        print(f"  [{i}/{len(files)}] {f}")

    tree_payload = {"tree": entries}
    if base_tree:
        tree_payload["base_tree"] = base_tree
    st, tree = call("POST", f"/repos/{owner}/{args.repo}/git/trees", tree_payload, token=TOKEN)

    msg = git("log", "-1", "--pretty=%B").strip() or "update"
    commit_payload = {"message": msg, "tree": tree["sha"], "parents": [parent] if parent else []}
    st, commit = call("POST", f"/repos/{owner}/{args.repo}/git/commits", commit_payload, token=TOKEN)

    if parent:
        call("PATCH", f"/repos/{owner}/{args.repo}/git/refs/heads/{args.branch}",
             {"sha": commit["sha"], "force": False}, token=TOKEN)
    else:
        call("POST", f"/repos/{owner}/{args.repo}/git/refs",
             {"ref": f"refs/heads/{args.branch}", "sha": commit["sha"]}, token=TOKEN)

    print(f"\n完成：https://github.com/{owner}/{args.repo}  （commit {commit['sha'][:8]}）")


if __name__ == "__main__":
    main()
