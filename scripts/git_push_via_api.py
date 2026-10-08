"""通过 GitHub Git Data API 推送一个已存在的本地提交（用于 github.com 直连被墙时）。

原理：本地 commit 对象已经存在，只要把「新增的 blob → tree → commit」按同样内容
提交到远端，并更新分支 ref，远端就会得到与本地**完全一致的 commit SHA**。

用法：python scripts/git_push_via_api.py <branch> [--dry-run]
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
REPO = "mmdaq/FreeNodeMailer"
API = "https://api.github.com"


def git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {out.stderr.decode('utf-8', 'replace')}")
    return out.stdout.decode("utf-8", "replace").strip()


def get_token() -> str:
    """从 git credential store 读取 token（不落盘、不回显）。"""
    proc = subprocess.run(
        ["git", "credential", "fill"],
        cwd=str(ROOT), input=b"protocol=https\nhost=github.com\n\n",
        capture_output=True,
    )
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("无法从 git 凭据库读取 GitHub token")


class GH:
    def __init__(self, token: str, repo: str = REPO):
        self.repo = repo
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {token}",
            "User-Agent": "FreeNodeMailer-push",
            "Accept": "application/vnd.github+json",
        })

    def req(self, method: str, path: str, **kw) -> Any:
        r = self.s.request(method, f"{API}{path}", timeout=60, **kw)
        if r.status_code >= 300:
            raise RuntimeError(f"{method} {path} → {r.status_code}: {r.text[:400]}")
        return r.json() if r.content else {}

    # ---- 基础对象 ----
    def ref(self, branch: str) -> Optional[str]:
        try:
            return self.req("GET", f"/repos/{self.repo}/git/ref/heads/{branch}")["object"]["sha"]
        except RuntimeError as exc:
            if "404" in str(exc):
                return None
            raise

    def commit(self, sha: str) -> Dict[str, Any]:
        return self.req("GET", f"/repos/{self.repo}/git/commits/{sha}")

    def create_blob(self, content: bytes) -> str:
        return self.req("POST", f"/repos/{self.repo}/git/blobs",
                        json={"content": base64.b64encode(content).decode(), "encoding": "base64"})["sha"]

    def create_tree(self, base_tree: str, entries: List[Dict[str, Any]]) -> str:
        return self.req("POST", f"/repos/{self.repo}/git/trees",
                        json={"base_tree": base_tree, "tree": entries})["sha"]

    def create_commit(self, message: str, tree: str, parents: List[str],
                      author: Dict[str, str]) -> str:
        return self.req("POST", f"/repos/{self.repo}/git/commits", json={
            "message": message, "tree": tree, "parents": parents,
            "author": author, "committer": author,
        })["sha"]

    def update_ref(self, branch: str, sha: str, force: bool = False) -> Any:
        return self.req("PATCH", f"/repos/{self.repo}/git/refs/heads/{branch}",
                        json={"sha": sha, "force": force})


def main() -> int:
    ap = argparse.ArgumentParser("git_push_via_api")
    ap.add_argument("branch")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    local_sha = git("rev-parse", "HEAD")
    branch = args.branch
    token = get_token()
    gh = GH(token)

    remote_sha = gh.ref(branch)
    print(f"本地 HEAD     : {local_sha}")
    print(f"远端 {branch:<8}: {remote_sha}")

    if remote_sha == local_sha:
        print("远端已是最新，无需推送")
        return 0

    # 计算本地相对远端新增的提交链
    if remote_sha:
        try:
            chain = git("rev-list", "--reverse", f"{remote_sha}..{local_sha}").splitlines()
        except RuntimeError:
            chain = []
        if not chain:
            print("远端不是本地祖先，需要 force（请人工确认后再执行）")
            return 1
        base = remote_sha
    else:
        chain = git("rev-list", "--reverse", local_sha).splitlines()
        base = None

    print(f"待推送提交数: {len(chain)}")
    for c in chain:
        print(f"  {c[:8]} {git('log', '-1', '--format=%s', c)}")

    if args.dry_run:
        print("--dry-run：不做任何修改")
        return 0

    # 从基线开始逐个重放提交
    parent = base
    for c in chain:
        files = [f for f in git("show", "--pretty=format:", "--name-only", c).splitlines() if f.strip()]

        # base_tree = 父提交的完整 tree SHA，GitHub 会在此基础上做增量合并
        if parent:
            base_tree = gh.commit(parent)["tree"]["sha"]
        else:
            base_tree = git("rev-parse", f"{c}^{{tree}}")

        entries = []
        for path in files:
            p = ROOT / path
            rel = path.replace("\\", "/")
            if p.exists():
                blob = gh.create_blob(p.read_bytes())
                entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob})
            else:
                entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": None})

        tree = gh.create_tree(base_tree, entries)

        message = git("log", "-1", "--format=%B", c).rstrip("\n")
        author = {
            "name": git("log", "-1", "--format=%an", c),
            "email": git("log", "-1", "--format=%ae", c),
            "date": git("log", "-1", "--format=%aI", c),
        }
        new_sha = gh.create_commit(message, tree, [parent] if parent else [], author)
        flag = "SHA 一致 ✓" if new_sha == c else "SHA 不同"
        print(f"  {c[:8]} → 远端 {new_sha[:8]} ({flag})")
        parent = new_sha

    gh.update_ref(branch, parent, force=False)
    print(f"\n分支 {branch} 已更新 → {parent}")
    if parent != local_sha:
        print(f"[提示] 远端 SHA({parent[:8]}) 与本地 HEAD({local_sha[:8]}) 不同，"
              f"本地需执行 git fetch && git reset --hard origin/{branch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
