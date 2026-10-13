#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""零字面量门禁（决策 D-27）。

扫描面（plan/03 §十，**随交付形态扩张**）：引擎 / 规则层 / 报告层 / CLI / 基准 / GUI。
禁用 token 从**规则包与 manifest 实算**（周期月数、适用性阈值、切口日、生效日期、年度数字），
词边界匹配，**连 docstring 与注释一起扫**。

**诚实处置（决策 D-27）**：M0 期规则包全 pending/null ⇒ token 集**为空**，
门禁此时是**空转**的。故本工具自带 `--selftest` 阳性对照：
程序化合成一组已知 token + 一份含该 token 的临时源文件，断言扫描器能报出。
**任何"0 命中"结论都必须先跑阳性对照。**

用法：
    py -3.8 tools/check_literals.py             # 扫描（命中即 exit 1）
    py -3.8 tools/check_literals.py --selftest  # 阳性对照（必须能报出）
    py -3.8 tools/check_literals.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

# 扫描面（相对仓库根）
SCAN_GLOBS = (
    "src/ohscheck/engine",
    "src/ohscheck/rules",
    "src/ohscheck/report",
    "src/ohscheck/benchmark",
    "src/ohscheck/gui",
    "src/ohscheck/cli.py",
)

# 豁免：**说明性散文**里的数字不属"抄进代码的第二份真相"。
# 判别口径（写死，防门禁刷屏）：行内数字若被**汉字/全角标点**包裹（中文叙述），
# 视为文档说明；若出现在代码标识符、字符串比较、算术或 ASCII 语法里，视为违规。
# 例："2026 年内两版并存（≤07-31 …）" 是说明 → 豁免；
#     `ruleset_id.endswith("2025")` 是判定逻辑 → 报错。
_PROSE_NEIGHBOURS = re.compile(
    r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]"
)


def _is_prose_context(line, start, end):
    """判断命中的数字是否处于中文说明性散文里。"""
    before = line[:start]
    after = line[end:]
    left = bool(_PROSE_NEIGHBOURS.search(before[-1:])) if before else False
    right = bool(_PROSE_NEIGHBOURS.search(after[:1])) if after else False
    # 两侧至少一侧紧邻汉字/全角标点，且该行不是纯代码赋值/比较
    if not (left or right):
        return False
    # 明显是代码语法（比较、赋值、调用参数）则不豁免
    if re.search(r"(?:endswith|startswith|==|!=|<=|>=|\bassert\b|\bif\b.*\d{4}\b)\s*\(?", line):
        if not _PROSE_NEIGHBOURS.search(before[-2:]):
            return False
    return True

# 小于此值的整数视作日历/精度常量，不作禁用 token（豁免口径写死）
MIN_TOKEN_VALUE = 100


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


def collect_tokens(data_dir=None):
    """从规则包与 manifest 实算禁用 token。

    M0 期规则包全 pending/null → 返回**空集**（门禁空转，如实留档）。
    """
    from ohscheck import paths
    from ohscheck.loaders import load_path

    root = paths.find_data_dir(data_dir)
    tokens = {"period_months": [], "thresholds": [], "dates": [], "years": []}
    if root is None:
        return tokens

    manifest_path = os.path.join(root, "rules", "manifest.json")
    if not os.path.isfile(manifest_path):
        return tokens
    try:
        manifest = load_path(manifest_path)
    except Exception:  # noqa: BLE001 - 门禁不应因坏数据崩溃，如实返回空集
        return tokens

    cutover = (manifest.get("cutover") or {}).get("date")
    if cutover:
        tokens["dates"].append(str(cutover))
        tokens["years"].append(str(cutover)[:4])

    rules_dir = os.path.join(root, "rules")
    for name in sorted(os.listdir(rules_dir)):
        if not name.endswith(".json") or name == "manifest.json":
            continue
        try:
            obj = load_path(os.path.join(rules_dir, name))
        except Exception:  # noqa: BLE001
            continue
        basis = obj.get("basis") or {}
        for key in ("effective_from", "published"):
            value = basis.get(key)
            if value:
                tokens["dates"].append(str(value))
                tokens["years"].append(str(value)[:4])
        for factor in obj.get("factors") or []:
            period = factor.get("period") or {}
            if period.get("kind") == "months" and isinstance(period.get("value"), int):
                tokens["period_months"].append(period["value"])
            elig = factor.get("eligibility") or {}
            if elig.get("threshold") is not None:
                tokens["thresholds"].append(str(elig["threshold"]))
    return tokens


def _iter_source_files(root):
    out = []
    for rel in SCAN_GLOBS:
        target = os.path.join(root, rel.replace("/", os.sep))
        if os.path.isfile(target):
            out.append(target)
        elif os.path.isdir(target):
            for cur, dirs, files in os.walk(target):
                dirs.sort()
                for name in sorted(files):
                    if name.endswith(".py"):
                        out.append(os.path.join(cur, name))
    return sorted(set(out))


def _build_patterns(tokens):
    """把 token 编译为词边界正则。

    ≥ MIN_TOKEN_VALUE 的整数才收；日期与长数字串按原样；
    2026 这类年度数字也收（plan/03 §十：年度数字是禁用 token）。
    """
    patterns = []
    for value in tokens.get("period_months", []):
        if isinstance(value, int) and value >= MIN_TOKEN_VALUE:
            patterns.append((r"\b%d\b" % value, "period_months:%d" % value))
    for value in tokens.get("thresholds", []):
        text = str(value)
        patterns.append((r"\b%s\b" % re.escape(text), "threshold:%s" % text))
    for value in tokens.get("dates", []):
        text = str(value)
        if len(text) >= 8:
            patterns.append((r"%s" % re.escape(text), "date:%s" % text))
    for value in tokens.get("years", []):
        text = str(value)
        if len(text) == 4 and text.isdigit():
            patterns.append((r"\b%s\b" % text, "year:%s" % text))
    return patterns


def scan_files(files, patterns):
    """扫描文件列表，返回命中列表。"""
    hits = []
    compiled = [(re.compile(p), label) for p, label in patterns]
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().split("\n")
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            for regex, label in compiled:
                for match in regex.finditer(line):
                    if _is_prose_context(line, match.start(), match.end()):
                        continue  # 中文说明性散文 → 豁免（口径见文件头）
                    hits.append(
                        {"file": path, "line": lineno, "token": label,
                         "text": line.strip()[:120], "col": match.start()}
                    )
    return hits


def _selftest():
    """阳性对照：合成 token + 合成源文件，断言扫描器能报出（决策 D-27）。"""
    tmp = tempfile.mkdtemp(prefix="ohscheck-lit-")
    sample = os.path.join(tmp, "sample_module.py")
    # 程序化合成，避免把真实数值写进本脚本（否则自己也成禁用 token）
    synthetic_token = 1000 + 234  # 1234
    with open(sample, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("PERIOD = %d\n" % synthetic_token)
        fh.write("def f():\n")
        fh.write("    '''docstring mentions %d'''\n" % synthetic_token)
        fh.write("    return 'literal %d'\n" % synthetic_token)

    patterns = [(r"\b%d\b" % synthetic_token, "selftest:%d" % synthetic_token)]
    hits = scan_files([sample], patterns)

    negative = os.path.join(tmp, "clean_module.py")
    with open(negative, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("VALUE = 1\n")
    neg_hits = scan_files([negative], patterns)

    ok = len(hits) >= 3 and len(neg_hits) == 0
    print(
        "LITERALS_SELFTEST_OK: 合成 token 命中 %d 处（≥3），反例命中 %d 处（应 0）"
        % (len(hits), len(neg_hits))
        if ok
        else "LITERALS_SELFTEST_FAIL: 命中 %d 处，反例 %d 处" % (len(hits), len(neg_hits))
    )
    return 0 if ok else 1


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


def main(argv=None):
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="零字面量门禁")
    parser.add_argument("--selftest", action="store_true", help="跑阳性对照")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    root = _repo_root()
    tokens = collect_tokens(args.data_dir)
    patterns = _build_patterns(tokens)
    files = _iter_source_files(root)
    hits = scan_files(files, patterns)

    payload = {
        "scanned_files": len(files),
        "token_count": len(patterns),
        "tokens": tokens,
        "hits": hits,
        "vacuous": len(patterns) == 0,
        "note": (
            "token 集为空 → 门禁空转（M0 期规则包全 pending/null）。"
            "请先跑 --selftest 阳性对照。"
            if not patterns
            else "已按规则包实算 token 扫描源代码。"
        ),
    }
    if args.json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        print("扫描文件 %d 份，禁用 token %d 个" % (len(files), len(patterns)))
        if payload["vacuous"]:
            print("注意：%s" % payload["note"])
        for hit in hits:
            print("  %s:%d [%s] %s" % (hit["file"], hit["line"], hit["token"], hit["text"]))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
