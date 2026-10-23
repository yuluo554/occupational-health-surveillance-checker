#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""脱敏门禁（M6-1，plan/RELEASE-M6.md 留档）。

四步扫描，任何一步命中即 exit 1：

  step1 tree     工作树全部已跟踪文件扫描（git ls-files -z；**无目录级豁免**）。
                 plan/ 是入仓公开内容，逐文件扫描（迭代 D-1；RELEASE-M6 §六）。
  step2 history  git 全量历史扫描（git rev-list --all 逐提交 grep；**无目录级豁免**）。
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
    py -3.12 -X utf8 tools/audit_sensitive.py               # 四步全跑
    py -3.12 -X utf8 tools/audit_sensitive.py --only tree   # 单步
    py -3.12 -X utf8 tools/audit_sensitive.py --dist-dir <目录>   # step3 指定产物目录
    py -3.12 -X utf8 tools/audit_sensitive.py --json
    py -3.12 -X utf8 tools/audit_sensitive.py --selftest    # 阳性对照（必须能报出）
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

# 中性占位豁免：只放行留档里约定的"环境坑示例"写法，且**只对命中点落在占位式路径内**生效。
# 不做任何目录前缀豁免（plan/ 整目录豁免已撤销，迭代 D-1）。
#   <workdir>/_m5_scratch.py        → 角括号占位符
#   D:/.../\_m1_scratch、D:/Users/.../project → 带 "..." 省略段的示例路径
_PLACEHOLDER_RES = (
    re.compile(r"<[A-Za-z][A-Za-z0-9_-]*>"),
    re.compile(r"[A-Za-z]:[\\/][^\s`'\"()（）]*\.\.\.[^\s`'\"()（）]*"),
)
# 机器工程路径段名，运行时拼接（不写词面：扫描器自身不得含本机标识，L-3 教训）
_PD_SEGMENT = "".join(["program", "data"])  # 既定 token 口径（HANDOFF-M6 §五）

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

# 通用服务/构建账号名：CI runner 上的 getpass 返回这些名字，**不是个人标识**，
# 当 token 只会误伤英文单词（实测 "runner" → 24 处假命中）。名单写死、命中即跳过并留痕。
_GENERIC_USERNAMES = frozenset({
    "runner", "root", "admin", "administrator", "user", "ubuntu", "docker",
    "jenkins", "travis", "circleci", "vsts", "azure", "build", "ci", "ec2-user",
    "system", "default", "github", "actions",
})


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

def _repo_drive(root=None):
    """仓库所在盘符（Windows 形如 `D:`）；非 Windows（Linux/macOS runner）回落 `"C:"`。

    跨平台要求（迭代 D-1 的 CI 接入实测）：CI 在 ubuntu-latest 上跑本门禁，
    路径无盘符 → 旧写法 `re.search(r"[A-Za-z]:", root).group(0)` 抛 AttributeError。
    回落值沿用 `users_home` 模式的默认盘符，Windows 形态泄漏在 Linux 上照扫。
    """
    parts = [p for p in os.path.abspath(root or _repo_root()).replace("/", os.sep).split(os.sep) if p]
    if parts and re.fullmatch(r"[A-Za-z]:", parts[0]):
        return parts[0]
    return "C:"


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

    # 2) 本机用户名（getpass）；词边界，避免误伤包含它的厂商串。
    #    CI（GitHub Actions ubuntu/windows runner）上 getpass 返回的是**构建账号名**而非个人标识
    #    （如 "runner"），拿它当 token 只会把文档里的英文单词判成命中（迭代 D-1 实测：24 处误报）。
    #    故对**通用服务/构建账号名**显式跳过，并在 provenance 里**记名留痕**（不静默）。
    user = getpass.getuser()
    if user and user.lower() in _GENERIC_USERNAMES:
        provenance["username"] = user
        provenance["username_skipped"] = "通用服务/构建账号名（非个人标识，不做 token）"
    elif user and len(user) >= 2:
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
    drive = _repo_drive(root)
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

def _placeholder_spans(line):
    """返回中性占位式写法在行内的字符区间（用于窄豁免，不做行级/目录级豁免）。"""
    spans = []
    for regex in _PLACEHOLDER_RES:
        for m in regex.finditer(line):
            spans.append((m.start(), m.end()))
    return spans


def _placeholder_at(line, pos, spans=None):
    """命中点是否落在中性占位式路径内部（只有这种情况才豁免）。"""
    for start, end in (spans if spans is not None else _placeholder_spans(line)):
        if start <= pos < end:
            return True
    return False


def scan_text_file(path, patterns):
    """文本文件逐行扫描，返回命中列表（中性占位式路径内的命中不计）。"""
    hits = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return hits
    for lineno, line in enumerate(lines, start=1):
        spans = _placeholder_spans(line)
        for label, regex in patterns:
            for m in regex.finditer(line):
                if _placeholder_at(line, m.start(), spans):
                    continue
                hits.append(
                    {"file": path, "line": lineno, "token": label,
                     "text": line.strip()[:120], "col": m.start()}
                )
    return hits


def _git_grep_escape(regex):
    """把 Python 正则降级为 git grep -E 可用的近似串（本项目 token 集都是字面量或简单词界）。"""
    return regex.pattern.replace("\\b", r"\b")


def _select_tree_files(files):
    """工作树扫描范围：**不设任何目录级豁免**（plan/ 整目录豁免已撤销，迭代 D-1）。

    保留为独立函数，--selftest 用它断言 plan/ 路径确实进入扫描范围。
    """
    return [f for f in files if f.strip()]


def _tracked_files(root):
    """已跟踪文件清单（`-z` 关闭 core.quotepath 引号转义）。

    默认 `git ls-files` 会给非 ASCII 路径加引号转义（如 `"plan/00-README\\346..."`），
    按引号串打开只会静默失败 → 文件被计入"已扫描"却从未读入（迭代实测：8 份）。
    """
    out = _run_git(["ls-files", "-z"], root)
    return [f for f in out.split("\0") if f.strip()]


def step1_tree(root, patterns):
    """工作树已跟踪文件扫描（无目录级豁免：plan/ 逐文件扫描）。"""
    files = _select_tree_files(_tracked_files(root))
    hits = []
    unreadable = []
    scanned = 0
    for rel in files:
        path = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.isfile(path):
            unreadable.append(rel)
            continue
        scanned += 1
        hits.extend(scan_text_file(path, patterns))
    return {"scanned": scanned, "unreadable": unreadable, "hits": hits}


def step2_history(root, patterns):
    """git 全量历史逐提交扫描（无目录级豁免；提交数 0 = 空转失败，D-40）。

    git grep -E 不支持 \\b，词边界场景改用 git grep -w 的全词匹配或在 Python 端复核。
    命中行再按 Python 正则+中性占位区间复核，保证与 step1 同一豁免口径。
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
            # rc 1 = 无命中（git grep 语义），正常
            out = _run_git(args, root, ok_codes=(0, 1))
            for line in out.strip().split("\n"):
                if not line.strip():
                    continue
                # 行格式 <commit>:<path>:<lineno>:<text>；path 可能被引号转义（不影响文本复核）
                body = line.split(":", 1)[1] if ":" in line else line
                text = body.split(":", 2)[2] if body.count(":") >= 2 else body
                if not list(regex.finditer(text)) or not any(
                        not _placeholder_at(text, m.start()) for m in regex.finditer(text)):
                    continue
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

    # 二进制阳性/豁免对照（needle 集可能为空：Linux runner 无盘符 + 通用用户名已跳过 →
    # 此时用被测盘符 needle 兜底，保证"阳性对照必能报出"这条断言仍然可证伪）
    bs = b"\\"
    official_qt = b"x" * 10 + b"C:" + bs + b"Users" + bs + b"qt" + bs + b"work" + bs + b"Qt6Gui.pdb" + b"y" * 10
    official_py = b"D:" + bs + b"a" + bs + b"1" + bs + b"s" + bs + b"Modules" + bs + b"gcmodule.c"
    drive = _repo_drive()
    probe_needles = list(needles) or [drive.encode("utf-8") + bs]
    local_leak = drive.encode() + bs + b"secret" + bs + b"leak.bin\x00"
    # 兜底二（Linux runner 实测）：needle 集**非空**但里面没有盘符串时
    # （ubuntu 上 repo 路径无盘符 → 盘符 needle 不产生；用户名 "runner" 被通用名单跳过；
    #  剩下只有 git 邮箱里的身份数字），上面那个 `or` 分支不会触发，
    # 而 local_leak 是按盘符拼的 → 两者无交集 → 阳性对照恒 0 命中，门禁**假红**。
    # 修法：合成件必须嵌入至少一个真实 needle，保证"本机泄漏必被报出"这条断言可证伪。
    if not any(n in local_leak for n in probe_needles):
        local_leak = b"\x00".join(probe_needles) + b"\x00" + local_leak
    official_hits = _scan_bytes_blob(official_qt + official_py, probe_needles)
    local_hits = _scan_bytes_blob(local_leak, probe_needles)

    # 目录级豁免阳性对照（迭代 D-1）：plan/ 路径必须进入扫描范围，且其中的本机标识必须报出。
    # 若代码里再出现"按目录前缀跳过"，本对照会立刻变红。
    plan_dir = os.path.join(tmp, "plan")
    os.makedirs(plan_dir, exist_ok=True)
    plan_probe = os.path.join(plan_dir, "x.md")
    with open(plan_probe, "w", encoding="utf-8", newline="\n") as fh:
        for label, value in probe_values:
            fh.write("token_probe_%s=%s\n" % (label, value))
    plan_hits = scan_text_file(plan_probe, patterns)
    plan_selected = "plan/x.md" in _select_tree_files(["plan/x.md", "src/x.py"])

    # 中性占位豁免必须是"窄"的：占位式路径内的命中放行，真实路径仍报出。
    # 路径按运行时实算的盘符拼接（扫描器自身不得含本机路径字面量，L-3 教训）。
    placeholder_line = "临时目录示例：" + drive + "/" + "Users" + "/.../project（占位）\n"
    real_line = "真实路径：" + drive + "/" + "Users" + "/realname/project\n"
    place_clean = os.path.join(tmp, "placeholder.txt")
    place_real = os.path.join(tmp, "real.txt")
    with open(place_clean, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(placeholder_line)
    with open(place_real, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(real_line)
    placeholder_hits = scan_text_file(place_clean, patterns)
    real_hits = scan_text_file(place_real, patterns)

    ok = (
        labels_hit == want
        and not clean_hits
        and not official_hits
        and len(local_hits) >= 1
        and plan_selected
        and set(h["token"] for h in plan_hits) == want
        and not placeholder_hits
        and any(h["token"] == "users_home" for h in real_hits)
    )
    print(
        "AUDIT_SELFTEST_OK: 文本 token 全报出（%s），干净对照 0 命中，"
        "二进制官方路径豁免 0 误报、盘符根泄漏报出 %d 处，"
        "plan/ 路径阳性对照报出 %d 处，中性占位豁免 0 命中且真实路径仍报出"
        % (",".join(sorted(labels_hit)), len(local_hits), len(plan_hits))
        if ok
        else "AUDIT_SELFTEST_FAIL: 文本命中=%s（应 %s）干净=%d 官方=%d 本机=%d "
        "plan_selected=%s plan_hits=%s 占位=%d 真实=%d"
        % (sorted(labels_hit), sorted(want), len(clean_hits), len(official_hits),
           len(local_hits), plan_selected, sorted(set(h["token"] for h in plan_hits)),
           len(placeholder_hits), len(real_hits))
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
    tree = report.get("tree", {})
    if tree and tree.get("unreadable"):
        blocking.append({
            "step": "tree",
            "reason": "有 %d 份已跟踪文件无法读取 → 扫描不完整，不得视为通过：%s"
                      % (len(tree["unreadable"]), ", ".join(tree["unreadable"][:5])),
        })
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
            extra = ""
            if tree.get("unreadable"):
                extra = "，无法读取 %d 份（须为 0）" % len(tree["unreadable"])
            print("step1 tree     : 扫描 %s 份已跟踪文件（无目录级豁免，plan/ 逐文件）%s，命中 %d"
                  % (tree.get("scanned", 0), extra, len(tree.get("hits", []))))
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
