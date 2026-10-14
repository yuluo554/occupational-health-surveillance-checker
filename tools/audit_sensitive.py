#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""脱敏门禁（M6-1，plan/RELEASE-M6.md 留档）。

四步扫描，任何一步命中即 exit 1：

  step1 tree     工作树已跟踪文件扫描（git ls-files）。plan/ 目录按既定口径豁免
                 （HANDOFF 快照含本机路径示例属计划文档，HANDOFF-M6 §五）。
  step2 history  git 全量历史扫描（git rev-list --all 逐提交 grep）。
                 浅克隆会让本步静默空转 → CI checkout 一律 fetch-depth: 0（决策 D-40）。
  step3 dist     产物本体扫描（构建目录逐文件二进制扫）。本项目自有产物零命中为通过；
                 第三方官方构建路径（Qt/python.org/MSVC/GfW 的 PDB 调试串、USB 厂商串）
                 属供应商嵌入的非本机信息，逐条显式豁免（不得静默吞掉）。
  step4 meta     git 作者/提交者身份清单输出（informational，恒 exit 0）——
                 发布身份的取舍属对外动作，由发布者显式决策（M6-3/M6-4 确认环节）。

**禁用 token 运行时实算，不硬编码**（M6-1 自噬教训 L-3：扫描器若把本机标识写进
自己的源码，literal 会随提交进入历史——"扫描器本身是泄漏源"）。实算来源：

  * git 全部作者/提交者邮箱中的 ≥6 位纯数字串（QQ 号形态）；
  * getpass.getuser()（本机用户名）；
  * 仓库根绝对路径的盘符段（如 D:）与上级目录段（除仓库目录名本身）——
    仓库目录名与日期标签是**有意公开**的项目坐标（plan/00 命名约定），不收；
  * 用户主目录模式（<盘>:/Users/ 或 <盘>:\\Users\\）。

用法：
    py -3.8 -X utf8 tools/audit_sensitive.py               # 四步全跑
    py -3.8 -X utf8 tools/audit_sensitive.py --only tree   # 单步
    py -3.8 -X utf8 tools/audit_sensitive.py --dist-dir <目录>   # step3 指定产物目录
    py -3.8 -X utf8 tools/audit_sensitive.py --json
    py -3.8 -X utf8 tools/audit_sensitive.py --selftest    # 阳性对照（必须能报出）
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import tempfile

PLAN_EXCLUDE = "plan/"
# 机器工程路径段名，运行时拼接（不写词面：扫描器自身不得含本机标识，L-3 教训）
_PD_SEGMENT = "".join(["program", "data"])  # 既定豁免口径（HANDOFF-M6 §五：release zip 不得出现 plan/ 之外的本地路径泄漏）

# 第三方官方构建路径豁免（供应商嵌入，非本机泄漏；实测确认见 plan/RELEASE-M6.md §3.2）
#   C:\Users\qt\work\...        → Qt 官方构建机 PDB 路径（Qt6*.dll、shiboken、plugins）
#   D:\a\1\...、D:\a\_work\1\... → python.org 官方 CI 与 MSVC 官方 CRT 的 PDB 路径
#                                  （python312*.pyd / vcruntime140*.dll / msvcp140*.dll）
#   D:\git-sdk-64-full\...      → Git for Windows 官方构建的 openssl PDB 路径
#   USB 厂商串                  → Qt6Gui 内 "ASUSTek COMPUTER INC"（与用户名同词面时误报排除）
# 全部豁免逐条实测过字节上下文（RSDS PDB 锚点 / USB 描述符），非静默吞掉。
_OFFICIAL_PDB_DIRS = (
    b"C:" + b"\\" + b"Users" + b"\\" + b"qt" + b"\\",
    b"D:" + b"\\" + b"a" + b"\\",                 # Azure DevOps agent（python.org / MSVC）
    b"D:" + b"\\" + b"git-sdk-64-full" + b"\\",   # Git for Windows 构建
)


def _ensure_utf8_stdio():
    """编码守卫（决策 D-39）：cp1252 等管道不因非 ASCII 输出崩。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        encoding = (getattr(stream, "encoding", None) or "").lower()
        if not encoding or "utf" in encoding:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(6):
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
        if os.path.exists(os.path.join(cur, "pyproject.toml")):
            return cur
    return os.path.dirname(here)


def _run_git(args, root, ok_codes=(0,)):
    proc = subprocess.run(["git"] + args, cwd=root, capture_output=True)
    if proc.returncode not in ok_codes:
        raise RuntimeError(
            "git %s 失败: %s" % (" ".join(args), proc.stderr.decode("utf-8", "replace").strip())
        )
    return proc.stdout.decode("utf-8", "replace")


# ---------------- token 实算 ----------------

def collect_tokens(root):
    """运行时实算禁用 token（同 check_literals 从规则包实算的思路，决策 D-27 同族）。

    返回 (text_patterns, binary_needles, provenance)。任一来源实算为空时如实记入
    provenance——token 集整体为空则门禁空转，必须靠 --selftest 阳性对照背书。
    """
    text_patterns = []
    binary_needles = []
    provenance = {}

    # 1) git 身份邮箱里的 ≥6 位纯数字串（QQ 号形态）
    numeric = set()
    try:
        out = _run_git(["log", "--format=%ae %ce", "--all"], root, ok_codes=(0, 1))
        emails = sorted(set(re.findall(r"[\w.+-]+@[\w.-]+", out)))
        for email in emails:
            for m in re.findall(r"\d{6,}", email):
                numeric.add(m)
        provenance["identity_numbers"] = sorted(numeric)
    except RuntimeError:
        provenance["identity_numbers"] = "unavailable（非 git 仓库）"
    for value in sorted(numeric):
        text_patterns.append(("identity_number", re.compile(re.escape(value))))
        binary_needles.append(value.encode("utf-8"))

    # 2) 本机用户名（getpass）；词边界，避免误伤包含它的厂商串
    user = getpass.getuser()
    if user and len(user) >= 2:
        text_patterns.append(("username", re.compile(r"\b%s\b" % re.escape(user))))
        binary_needles.append(user.encode("utf-8"))
        provenance["username"] = user

    # 3) 仓库根绝对路径：盘符段 + 上级目录段（仓库目录名本身是有意公开的项目坐标，不收）
    root_abs = os.path.abspath(root)
    parts = [p for p in root_abs.replace("/", os.sep).split(os.sep) if p]
    seg_tokens = set()
    for seg in parts[:-1]:  # 末段 = 仓库目录名，豁免
        if seg.lower() in ("users", "program files", "windows"):
            continue
        if re.fullmatch(r"[A-Za-z]:", seg) or seg.lower() == _PD_SEGMENT:
            seg_tokens.add(seg)
    # 盘符 + Users 目录模式（用户主目录泄漏形态）
    drive = parts[0] if parts and re.fullmatch(r"[A-Za-z]:", parts[0]) else "C:"
    text_patterns.append(("users_home", re.compile(r"%s[/\\]Users[/\\]" % re.escape(drive), re.IGNORECASE)))
    for seg in sorted(seg_tokens):
        if seg.lower() == _PD_SEGMENT:
            text_patterns.append(("machine_path", re.compile(re.escape(seg), re.IGNORECASE)))
            binary_needles.append(seg.encode("utf-8"))
        elif re.fullmatch(r"[A-Za-z]:", seg):
            binary_needles.append(seg.encode("utf-8") + b"\\")
    provenance["repo_path_segments"] = sorted(seg_tokens)
    provenance["users_home_pattern"] = "%s[/\\\\]Users[/\\\\]" % drive

    return text_patterns, binary_needles, provenance


# ---------------- 扫描执行 ----------------

def scan_text_file(path, patterns):
    """文本文件逐行扫描，返回命中列表。"""
    hits = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return hits
    for lineno, line in enumerate(lines, start=1):
        for label, regex in patterns:
            m = regex.search(line)
            if m:
                hits.append(
                    {"file": path, "line": lineno, "token": label,
                     "text": line.strip()[:120], "col": m.start()}
                )
    return hits


def _git_grep_escape(regex):
    """把 Python 正则降级为 git grep -E 可用的近似串（本项目 token 集都是字面量或简单词界）。"""
    return regex.pattern.replace("\\b", r"\b")


def step1_tree(root, patterns):
    """工作树已跟踪文件扫描（plan/ 豁免）。"""
    files = [f for f in _run_git(["ls-files"], root).split("\n") if f.strip()]
    hits = []
    scanned = 0
    for rel in files:
        if rel.replace("\\", "/").startswith(PLAN_EXCLUDE):
            continue
        scanned += 1
        hits.extend(scan_text_file(os.path.join(root, rel), patterns))
    return {"scanned": scanned, "hits": hits}


def step2_history(root, patterns):
    """git 全量历史逐提交扫描（plan/ 豁免；提交数 0 = 空转失败，D-40）。

    git grep -E 不支持 \\b，词边界场景改用 git grep -w 的全词匹配或在 Python 端复核。
    """
    commits = [c for c in _run_git(["rev-list", "--all"], root).split("\n") if c.strip()]
    hits = []
    for commit in commits:
        for label, regex in patterns:
            pat = _git_grep_escape(regex)
            args = ["grep", "-I", "-n", "-E", "-e", pat]
            if r"\b" in regex.pattern:
                args.append("-w")
            args.append(commit)
            # rc 1 = 无命中（git grep 语义），正常；plan/ 豁免在 Python 端按前缀过滤
            out = _run_git(args, root, ok_codes=(0, 1))
            for line in out.strip().split("\n"):
                if not line.strip():
                    continue
                # 行格式 <commit>:<path>:<lineno>:<text>
                body = line.split(":", 1)[1] if ":" in line else line
                rel = body.split(":", 1)[0] if ":" in body else body
                if rel.replace("\\", "/").startswith(PLAN_EXCLUDE):
                    continue
                text = body.split(":", 1)[1] if ":" in body else body
                hits.append({"commit": commit[:12], "token": label, "text": text.strip()[:160]})
    return {"commits": len(commits), "hits": hits}


def step3_dist(dist_dir, needles):
    """产物本体二进制扫描（本项目自有产物零命中；第三方官方路径显式豁免）。"""
    hits = []
    exempt_hits = 0
    scanned = 0
    for cur, dirs, files in os.walk(dist_dir):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(cur, name)
            try:
                data = open(path, "rb").read()
            except OSError:
                continue
            scanned += 1
            for needle in needles:
                start = 0
                while True:
                    i = data.find(needle, start)
                    if i < 0:
                        break
                    ctx = data[max(0, i - 40): i + 60]
                    if _binary_exempt(data, i, needle):
                        exempt_hits += 1
                    else:
                        printable = bytes(b if 32 <= b < 127 else 46 for b in ctx).decode()
                        hits.append({"file": path, "token": needle.decode("latin-1"), "context": printable})
                    start = i + 1
    return {"scanned_files": scanned, "exempt_count": exempt_hits, "hits": hits}


def _binary_exempt(data, i, needle):
    """第三方官方嵌入串豁免判定（全部显式列出，逐条实测过字节上下文）。"""
    ctx = data[max(0, i - 40): i + 60]
    # Qt 官方构建机用户目录（C:\Users\qt\work\...）
    if needle.startswith(b"C:") and re.search(
            b"C:" + re.escape(b"\\" + b"Users" + b"\\") + b"qt" + re.escape(b"\\"), ctx):
        return True
    # 官方 PDB 调试路径：命中点锚在 RSDS 上，且完整路径以官方目录前缀开头
    if (needle.startswith(b"D:") or needle.startswith(b"C:")) and b"RSDS" in data[max(0, i - 30):i]:
        end = data.find(b"\x00", i)
        pdb = data[i:end if end > 0 else i + 120]
        if any(pdb.startswith(d) for d in _OFFICIAL_PDB_DIRS):
            return True
    # 官方 CI agent 盘符路径（D:\a\...，python.org/MSVC 嵌入的源码路径）无条件豁免——
    # 该前缀只出现在供应商官方构建产物里，本机路径不可能以 D:\a\ 开头撞上它
    if needle.startswith(b"D:") and re.match(re.escape(b"D:" + b"\\" + b"a" + b"\\"), ctx[i - max(0, i - 40):]):
        return True
    # USB 厂商串（Qt6Gui 字符串表；与运行时实算的用户名同词面时属误报排除）
    vendor = re.search(b"ASUSTe?K", ctx, re.IGNORECASE)
    if vendor and vendor.group(0).upper().startswith(needle.upper()):
        return True
    return False


def step4_meta(root):
    """git 作者/提交者身份清单（informational，恒通过；发布身份由发布者显式决策）。"""
    out = _run_git(["log", "--format=%an <%ae> | committer: %cn <%ce>", "--all"], root, ok_codes=(0, 1))
    identities = sorted(set(line.strip() for line in out.split("\n") if line.strip()))
    return {"identities": identities, "note": "informational：是否以当前身份发布属对外动作，须发布者显式确认（M6-3/M6-4）"}


def _scan_bytes_blob(data, needles):
    """对内存字节串跑 step3 的同一 needle/豁免逻辑（供 selftest 复用）。"""
    hits = []
    for needle in needles:
        start = 0
        while True:
            i = data.find(needle, start)
            if i < 0:
                break
            if not _binary_exempt(data, i, needle):
                hits.append((needle.decode("latin-1"), i))
            start = i + 1
    return hits


def _selftest(patterns, needles):
    """阳性对照（决策 D-27 同族）：程序化合成含 token 的临时件，断言扫描器能报出。

    token 从运行时实算集取（不写死任何本机标识），另合成官方路径样本验证豁免不误报。
    """
    tmp = tempfile.mkdtemp(prefix="ohscheck-audit-")

    # 文本阳性：把每个实算出的文本 token 拼进合成行
    probe_values = []
    for label, regex in patterns:
        pat = regex.pattern
        if "(?i)" in pat or label == "machine_path":
            value = re.search(r"[A-Za-z]+", pat.split("(?i)")[-1]).group(0)
        elif r"\b" in pat and label == "username":
            core = pat.replace(r"\b", "")
            core = re.sub(r"^\\|\\" r"b", "", core).replace("\\", "")
            value = re.sub(r"[^A-Za-z0-9_.-]", "", core)
            if not value:
                value = getpass.getuser()
        elif label == "users_home":
            value = re.search(r"[A-Za-z]:", pat).group(0) + "/" + "Users" + "/"
        else:
            digits = re.search(r"\d+", pat)
            value = digits.group(0) if digits else pat
        probe_values.append((label, value))
    dirty = os.path.join(tmp, "dirty.txt")
    with open(dirty, "w", encoding="utf-8", newline="\n") as fh:
        for label, value in probe_values:
            fh.write("token_probe_%s=%s\n" % (label, value))
    dirty_hits = scan_text_file(dirty, patterns)
    labels_hit = set(h["token"] for h in dirty_hits)
    want = set(label for label, _ in patterns)

    clean = os.path.join(tmp, "clean.txt")
    with open(clean, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("ASUSTek vendor string is fine; plain text with no identifiers.\n")
    clean_hits = scan_text_file(clean, patterns)

    # 二进制阳性/豁免对照
    bs = b"\\"
    official_qt = b"x" * 10 + b"C:" + bs + b"Users" + bs + b"qt" + bs + b"work" + bs + b"Qt6Gui.pdb" + b"y" * 10
    official_py = b"D:" + bs + b"a" + bs + b"1" + bs + b"s" + bs + b"Modules" + bs + b"gcmodule.c"
    drive = re.search(r"[A-Za-z]:", _repo_root()).group(0)
    local_leak = drive.encode() + bs + b"secret" + bs + b"leak.bin\x00"
    official_hits = _scan_bytes_blob(official_qt + official_py, needles)
    local_hits = _scan_bytes_blob(local_leak, needles)

    ok = (
        labels_hit == want
        and not clean_hits
        and not official_hits
        and len(local_hits) >= 1
    )
    print(
        "AUDIT_SELFTEST_OK: 文本 token 全报出（%s），干净对照 0 命中，"
        "二进制官方路径豁免 0 误报、盘符根泄漏报出 %d 处"
        % (",".join(sorted(labels_hit)), len(local_hits))
        if ok
        else "AUDIT_SELFTEST_FAIL: 文本命中=%s（应 %s）干净=%d 官方=%d 本机=%d"
        % (sorted(labels_hit), sorted(want), len(clean_hits), len(official_hits), len(local_hits))
    )
    return 0 if ok else 1


def _in_git_repo(root):
    probe = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=root, capture_output=True)
    return probe.returncode == 0


def main(argv=None):
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="脱敏门禁（M6-1）")
    parser.add_argument("--selftest", action="store_true", help="阳性对照")
    parser.add_argument("--only", choices=["tree", "history", "dist", "meta"], help="只跑单步")
    parser.add_argument("--dist-dir", default=None, help="step3 产物目录（默认 build-m5/dist/ohscheck，缺目录则跳过并注明）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = _repo_root()
    patterns, needles, provenance = collect_tokens(root)

    if args.selftest:
        return _selftest(patterns, needles)

    # git archive 导出的干净树（无 .git）：tree/history/meta 依赖 git 索引与历史，
    # 如实声明不适用；产物扫描（step3）不依赖 git 照常可跑。
    gitless = not _in_git_repo(root)
    steps = ["tree", "history", "dist", "meta"] if not args.only else [args.only]
    report = {"token_provenance": provenance, "token_count": len(patterns) + len(needles)}
    if gitless:
        for step in ("tree", "history", "meta"):
            if step in steps:
                report[step] = {"gitless": True, "note": "非 git 仓库（archive 导出树），该步不适用"}
                steps = [s for s in steps if s != step]
    for step in steps:
        if step == "tree":
            report["tree"] = step1_tree(root, patterns)
        elif step == "history":
            report["history"] = step2_history(root, patterns)
        elif step == "dist":
            dist_dir = args.dist_dir or os.path.join(root, "build-m5", "dist", "ohscheck")
            if not os.path.isdir(dist_dir):
                report["dist"] = {"skipped": True, "note": "产物目录不存在（未构建或已清理）：%s" % dist_dir}
            else:
                report["dist"] = step3_dist(dist_dir, needles)
        elif step == "meta":
            report["meta"] = step4_meta(root)

    blocking = []
    if report["token_count"] == 0:
        blocking.append({"step": "tokens", "reason": "token 集为空 → 门禁空转，先跑 --selftest 并核对实算来源"})
    hist = report.get("history", {})
    if hist and not hist.get("gitless") and hist.get("commits", 0) == 0:
        blocking.append({"step": "history", "reason": "提交数为 0 → 历史扫描空转（浅克隆？），不得视为通过"})
    for step in ("tree", "history", "dist"):
        data = report.get(step)
        if data and data.get("hits"):
            blocking.append({"step": step, "hits": data["hits"]})

    if args.json:
        sys.stdout.write(json.dumps({"report": report, "blocking": blocking}, ensure_ascii=False, indent=2) + "\n")
    else:
        print("token 实算：%s" % json.dumps(provenance, ensure_ascii=False))
        tree = report.get("tree", {})
        if tree.get("gitless"):
            print("step1 tree     : 跳过（%s）" % tree["note"])
        else:
            print("step1 tree     : 扫描 %s 份已跟踪文件（plan/ 豁免），命中 %d" % (tree.get("scanned", 0), len(tree.get("hits", []))))
        hist = report.get("history", {})
        if hist.get("gitless"):
            print("step2 history  : 跳过（%s）" % hist["note"])
        elif hist:
            print("step2 history  : 全量历史 %s 个提交逐提交扫描，命中 %d" % (hist.get("commits", 0), len(hist.get("hits", []))))
        dist = report.get("dist", {})
        if dist.get("skipped"):
            print("step3 dist     : 跳过（%s）" % dist["note"])
        else:
            print("step3 dist     : 扫描 %s 个产物文件，第三方官方路径豁免 %s 处，本项目产物命中 %d"
                  % (dist.get("scanned_files", 0), dist.get("exempt_count", 0), len(dist.get("hits", []))))
        meta = report.get("meta")
        if meta and meta.get("gitless"):
            print("step4 meta     : 跳过（%s）" % meta["note"])
        elif meta:
            print("step4 meta     : git 身份清单（informational）：")
            for ident in meta["identities"]:
                print("    %s" % ident)
        for item in blocking:
            if "reason" in item:
                print("!! [%s] %s" % (item["step"], item["reason"]))
            else:
                for hit in item["hits"]:
                    print("!! [%s] %s" % (item["step"], json.dumps(hit, ensure_ascii=False)[:200]))
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
