"""临时：把本地 HEAD 强制发布到远端分支（github.com 直连被墙时用 API）。

用法：python scripts/_publish.py <branch> [--force]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from git_push_via_api import GH, get_token, git, ROOT  # noqa: E402


def flatten_remote(gh, sha):
    """远端 tree 展开为 {path: sha}（递归）。"""
    def walk(s, prefix=""):
        out = {}
        for e in gh.req("GET", f"/repos/{gh.repo}/git/trees/{s}")["tree"]:
            if e["type"] == "tree":
                out.update(walk(e["sha"], prefix + e["path"] + "/"))
            else:
                out[prefix + e["path"]] = e["sha"]
        return out
    return walk(sha)


def flatten_local_blobs():
    """本地 HEAD 的所有文件路径（内容用本地文件读取，避免远端取 SHA）。"""
    out = []
    for line in git("ls-tree", "-r", "--name-only", "HEAD").splitlines():
        p = line.strip()
        if p:
            out.append(p)
    return out


def main() -> int:
    branch = sys.argv[1]
    force = "--force" in sys.argv
    local_sha = git("rev-parse", "HEAD")
    gh = GH(get_token())
    old = gh.ref(branch)
    print(f"本地 HEAD      : {local_sha}")
    print(f"远端 {branch:<8} : {old}")

    old_files = flatten_remote(gh, gh.commit(old)["tree"]["sha"]) if old else {}
    local_paths = flatten_local_blobs()
    new_exists = set(local_paths)
    print(f"旧文件数 {len(old_files)} → 新文件数 {len(new_exists)}")

    # 先用本地 git 算出 blob SHA（与 GitHub 算法一致），只上传真正变化的文件
    local_blobs = {}
    for line in git("ls-tree", "-r", "HEAD").splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) >= 3:
            local_blobs[path] = parts[2]

    entries = []
    changed = []
    for p in local_paths:
        blob = local_blobs.get(p, "")
        if old_files.get(p) == blob:
            continue
        changed.append(p)
        data = (ROOT / p).read_bytes()
        sha = gh.create_blob(data)
        entries.append({"path": p, "mode": "100644", "type": "blob", "sha": sha})
    deleted = [p for p in old_files if p not in new_exists]
    for p in deleted:
        entries.append({"path": p, "mode": "100644", "type": "blob", "sha": None})
    print(f"内容有变化 {len(changed)} 个，删除 {len(deleted)} 个")
    for p in changed:
        print(f"   ~ {p}")

    base_tree = gh.commit(old)["tree"]["sha"] if old else None
    tree = gh.create_tree(base_tree, entries)
    print(f"远端新 tree    : {tree}")
    author = {
        "name": git("log", "-1", "--format=%an"),
        "email": git("log", "-1", "--format=%ae"),
        "date": git("log", "-1", "--format=%aI"),
    }
    msg = git("log", "-1", "--format=%B").rstrip("\n")
    new_sha = gh.create_commit(msg, tree, [old] if old else [], author)
    print(f"远端新提交     : {new_sha}")
    gh.update_ref(branch, new_sha, force=force)
    print(f"分支 {branch} 已更新 → {gh.ref(branch)}")
    print("（远端 SHA 与本地可能不同：GitHub 写入自己的 committer 时间戳，内容一致）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
