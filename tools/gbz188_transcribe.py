#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GBZ 188—2025 原文解析器（**只读**，供 `tools/gen_rulesets.py` 调用）。

输入：`data/knowledge/raw/GBZ188-2025.layout.txt`（官方 PDF 经 `pdftotext -enc UTF-8 -layout`
的解析快照，139 页 / 75,555 汉字零丢失）。
输出：第 5–9 章的**结构化转写**（危害因素 / 四个检查时点 / 必检项 / 补充项 / 选检项 /
目标疾病 / 检查周期 / 检查对象），每个抽取值都带**原文逐字包含断言**。

为什么用脚本转写而不是手抄（诚实性口径，plan/05 §1.3 C1–C7）：
  * 手抄 97 个因素的数百个项目名，必然引入不可复现的转写漂移，且无法复核；
  * 本脚本对**每一处**抽取值断言"该字符串逐字出现在冻结原文快照中"，
    节号（如 `5.19`）可 `grep` 到——**这就是"逐字比对"的机器化形式**；
  * 产物由 `gen_rulesets.py` 落盘并配 `--check` 位级一致守门，唯一写入者纪律不破。

解析策略 = **条文号索引**：标准正文是一棵 `X.Y` → `X.Y.N`（时点）→ `X.Y.N.M`（要点）
的编号树。按条文号切块后，"目标疾病/检查内容/检查周期"各自落在确定的条文里，
`同 X.Y.Z` 交叉引用也按条文号直接查表——避免行序启发式带来的串块与漏字。

**边界如实声明**：本脚本只做**机械转录**，不做医学判断；原文按作业分级/接触水平/
接触年限分支的周期一律转 `input_required`（**绝不替原文猜一个数值**，决策 D-13）。
"""

from __future__ import annotations

import os
import re

# ---- 章节 → 危害因素类别（schema 的 FACTOR_CATEGORIES 需同步扩展）----
CHAPTER_CATEGORY = {
    "5": "chemical",    # 接触有害化学因素
    "6": "dust",        # 粉尘
    "7": "physical",    # 接触有害物理因素
    "8": "biological",  # 接触有害生物因素
    "9": "special",     # 特殊作业人员
}

# 检查时点：原文小标题 → 规则包键
EXAM_LABEL_TO_KEY = {
    "上岗前职业健康检查": "pre_placement",
    "在岗期间职业健康检查": "periodic",
    "离岗时职业健康检查": "post_placement",
    "应急健康检查": "emergency",
}
EXAM_KEYS = ("pre_placement", "periodic", "post_placement", "emergency")
EXAM_KEY_TO_LABEL = {v: k for k, v in EXAM_LABEL_TO_KEY.items()}

SNAPSHOT_REL = os.path.join("data", "knowledge", "raw", "GBZ188-2025.layout.txt")

_CLAUSE_RE = re.compile(r"^\s*(\d+(?:\.\d+)+)\s+(\S.*)$")

# 括号族（用于按"括号深度 0"切分项目列表）
_OPEN = "（(【["
_CLOSE = "）)】]"


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


def snapshot_path():
    return os.path.join(_repo_root(), SNAPSHOT_REL)


def load_raw_lines(path=None):
    """读快照并剔除页眉/页码/换页符，返回行列表（保留缩进）。"""
    path = path or snapshot_path()
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    text = text.replace("\x0c", "")
    out = []
    for line in text.split("\n"):
        stripped = line.strip()
        if re.match(r"^\d{1,3}$", stripped):  # 页码
            continue
        if re.match(r"^GBZ\s*188[\－—–-]\s*2025$", stripped):  # 页眉
            continue
        out.append(line.rstrip())
    return out


def _body_start(lines):
    """正文起点 = 首次出现独立成行的『1 范围』（此前为封面/目次/前言）。"""
    for idx, line in enumerate(lines):
        if re.match(r"^\s*1\s+范围\s*$", line):
            return idx
    raise ValueError("未在快照中找到正文起点『1 范围』")


def _collapse(text):
    """压平空白（换行/缩进是排版折行产物，不是内容）。"""
    return re.sub(r"\s+", "", text)


def clause_index(lines):
    """条文号 → (标题, 正文行列表)。文本含全部下级条文，止于下一个非下级条文。

    这是解析的**唯一结构来源**：避免"行序启发式"把下一小节的字样串进本小节。

    标题行可能折行（如 6.4『其他致尘肺病的无机粉尘[根据职业病分类和目录，系指…云母粉』
    换行续『尘、水泥粉尘…]』）。判据 = 紧跟的下一行**不是空行且不是新条文号**，
    且**未缩进到正文层级**（正文缩进 ≥ 4 空格，标题续行不缩进）→ 并入标题。
    """
    marks = []
    for idx, line in enumerate(lines):
        m = _CLAUSE_RE.match(line)
        if m and "." * 4 not in m.group(2):
            title = m.group(2).strip()
            # 吸收折行续写的标题片段（不缩进、非空、非条文号行）
            j = idx + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    break
                if _CLAUSE_RE.match(nxt):
                    break
                if len(nxt) - len(nxt.lstrip()) >= 4:
                    break
                title += nxt.strip()
                j += 1
            marks.append((idx, m.group(1), title))
    out = {}
    for pos, (idx, num, title) in enumerate(marks):
        end = len(lines)
        for j in range(pos + 1, len(marks)):
            if not marks[j][1].startswith(num + "."):
                end = marks[j][0]
                break
        out[num] = (title, lines[idx + 1 : end])
    return out


def _text_of(index, num):
    entry = index.get(num)
    return "\n".join(entry[1]) if entry else ""


def _title_of(index, num):
    entry = index.get(num)
    return entry[0] if entry else ""


def _full_text(index, num):
    """条文全文 = 标题行剩余文本 + 正文（标准常把内容直接写在编号行上，
    如 `5.19.2.4 健康检查周期：1 年。`——只取正文会漏掉整条内容）。"""
    entry = index.get(num)
    if not entry:
        return ""
    return entry[0] + "\n" + "\n".join(entry[1])


def _children(index, num):
    """直接下级条文号（按数值序）。"""
    prefix = num + "."
    depth = num.count(".")
    out = []
    for key in index:
        if not key.startswith(prefix):
            continue
        if key.count(".") != depth + 1:
            continue
        out.append(key)
    return sorted(out, key=lambda k: [int(x) for x in k.split(".")])


def split_top(text, seps="、"):
    """按**括号深度 0** 的分隔符切分（括号内的顿号不拆，如"（含血嗜酸粒细胞计数）"）。"""
    out = []
    buf = []
    depth = 0
    for ch in text:
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth = max(0, depth - 1)
        if ch in seps and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return [piece.strip() for piece in out if piece.strip()]


# 检验/检查项目名里常见的"测试名词"标记。用于识别"多项共享一个后置名词"的写法
# （如『长骨、大关节X射线摄片检查（…）』——两个部位共享"X射线摄片检查"）。
_TEST_SUFFIXES = (
    "检查", "测试", "常规", "测定", "试验", "摄片", "片", "分析", "计数",
    "功能", "B超", "CT", "MRI", "心电图", "造影", "镜", "培养", "涂片",
)


def _looks_like_bare_modifier(fragment):
    """片段是否"只是修饰语"（不含任何测试名词标记，故本身不构成一个检验项目）。"""
    return not any(suffix in fragment for suffix in _TEST_SUFFIXES)


def _merge_fragments(fragments, source):
    """合并"多项共享后置名词"的枚举片段（**只在原文确实连写时**，无损）。

    原文有『…、脊椎片，长骨、大关节X射线摄片检查（双肩、双髋…）』这类写法：机械按
    顿号切会得到孤立的"长骨"。判据（三条同时成立才算本是一体）：
      ① 前片段 ≤4 字且**不含任何测试名词标记**（只是部位/限定语，自身不是检验项目）；
      ② 后片段**含**测试名词标记（是真正的检验项目名）；
      ③ `前片段、后片段` 逐字出现在原文里。
    合并结果仍是原文子串，不引入原文没有的字。
    """
    out = []
    for frag in fragments:
        if (
            out
            and len(out[-1]) <= 3
            and _looks_like_bare_modifier(out[-1])
            and not _looks_like_bare_modifier(frag)
        ):
            joined = out[-1] + "、" + frag
            if joined in source:
                out[-1] = joined
                continue
        out.append(frag)
    return out


_STOP_LABELS = ("补充检查项目", "选检项目", "复查", "注：", "注:")


def _payload(text, marker):
    """取 marker 后的载荷（截到下一个语义终止标记或句末）。

    注意**不能**在首个 `1)` / `a)` 处截断：项目列表本身可能就是编号列表
    （如 7.4.1.3『必检项目：1) 血常规、…；2) 咽鼓管功能检查；…』）。
    编号只在**其后紧跟**"补充检查项目/选检项目"时才是终止点，故改为截停止标签后
    再把残留的编号前缀剥掉。
    """
    idx = text.find(marker)
    if idx < 0:
        return None
    tail = text[idx + len(marker):]
    tail = re.sub(r"^[：:为]", "", tail)
    cut = len(tail)
    for stop in _STOP_LABELS:
        j = tail.find(stop)
        if j >= 0:
            cut = min(cut, j)
    j = tail.find("。")
    if j >= 0:
        cut = min(cut, j)
    payload = tail[:cut]
    # 剥掉残留的并列编号前缀（如 "…；2) " 里的 "2)" 与末尾分隔符）
    payload = re.sub(r"(?:[；;]\s*)?(?:\d|[a-h])\)\s*$", "", payload)
    return payload


def items_from_payload(payload):
    """把载荷切成项目名列表（保持标准原样的项目粒度）。"""
    if not payload:
        return []
    text = _collapse(payload).strip("；;。、")
    # 形式一：编号列表（1) A、B；2) C；…）——把各组内容并入同一列表
    if re.match(r"^\d\)", text):
        groups = split_top(text, "；;")
        merged = []
        for group in groups:
            group = re.sub(r"^\d\)", "", group).strip()
            if group:
                merged.extend(_merge_fragments(split_top(group, "、，"), text))
        return [g for g in merged if g]
    # 形式二：顿号/逗号枚举
    return [x for x in _merge_fragments(split_top(text, "、，"), text) if x]


def _trim_optional_tail(payload):
    """把『…者可选择 X、Y』这类条件性尾部从必检载荷里摘掉（决策 D-16）。

    标准在必检项句末偶有『某异常者可选择…』的条件表述；补充/选检项另有标记，
    此处只处理**没有标记**的漏网写法——条件性项目不进判定。
    返回 (head, tail)，两者都仍是原文子串（无损）。
    """
    if not payload:
        return payload, ""
    depth = 0
    for i, ch in enumerate(payload):
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth = max(0, depth - 1)
        elif ch == "，" and depth == 0:
            tail = payload[i + 1:]
            if "可选择" in tail or "可选" in tail:
                return payload[:i], tail
    return payload, ""


def parse_diseases(text):
    """抽取"目标疾病 / 职业禁忌证"条目名（**仅记录，不参与判定**，核对清单 C2）。"""
    flat = _collapse(text)
    idx = flat.find("目标疾病")
    if idx < 0:
        idx = flat.find("职业禁忌证")
        if idx < 0:
            return []
    tail = flat[idx:]
    for stop in ("检查内容", "健康检查周期", "复查", "检查对象"):
        j = tail.find(stop)
        if j > 0:
            tail = tail[:j]
    tail = tail.replace("目标疾病为职业禁忌证", "").replace("目标疾病", "")
    tail = tail.replace("职业禁忌证", "")
    tail = re.sub(r"^[：:为]+", "", tail)
    out = []
    # 先按字母编号切，再按顿号/分号切
    for chunk in re.split(r"[a-z]\)|\d\)", tail):
        chunk = chunk.strip().strip("：:。；;")
        chunk = re.sub(r"^(职业病|职业禁忌证)[：:]?", "", chunk).strip()
        if not chunk:
            continue
        out.append(chunk)
    return out


_SIMPLE_PERIOD_START = re.compile(r"^(?:健康检查)?(?:周期)?[：:为]?")


def classify_period(payload):
    """把周期载荷分为 (kind, value, note)。

    只有**单一无条件周期**才落 `months`；原文按作业分级/接触水平/接触年限等分支的
    一律 `input_required`（**绝不替原文挑一个分支值**，决策 D-13）。
    """
    text = _collapse(payload).strip()
    if not text:
        return "input_required", None, ""
    # 去掉标题括注『（按 GBZ/T xxx）』与残留前缀
    head = re.sub(r"^[（(][^）)]*[）)]", "", text)
    head = re.sub(r"^健康检查周期", "", head)
    head = re.sub(r"^健康检查", "", head)
    head = re.sub(r"^[：:为]+", "", head)
    # 分支表述（a) …；b) …）或含"分级"/"及以上"/"＜"的比较 → 不承载单值
    if re.search(r"[a-h]\)", text) or "分级" in text or "及以上" in text or "＜" in text or "≤" in text:
        return "input_required", None, ""
    m = re.match(r"^(\d+)年", head)
    if m:
        return "months", int(m.group(1)) * 12, head[m.end():].strip("，。；;")
    m = re.match(r"^半年", head)
    if m:
        return "months", 6, head[m.end():].strip("，。；;")
    m = re.match(r"^(\d+)个月", head)
    if m:
        return "months", int(m.group(1)), head[m.end():].strip("，。；;")
    return "input_required", None, ""


class Section:
    """一个危害因素节（X.Y）的条文视图。"""

    __slots__ = ("sid", "chapter", "title", "index")

    def __init__(self, sid, title, index):
        self.sid = sid
        self.chapter = sid.split(".")[0]
        self.title = title
        self.index = index

    def exam_clauses(self):
        """时点 → 条文号（如 5.19.2）。"""
        out = {}
        for child in _children(self.index, self.sid):
            title = _title_of(self.index, child)
            if title in EXAM_LABEL_TO_KEY:
                out[EXAM_LABEL_TO_KEY[title]] = child
        return out

    def _descendant_with_title(self, clause, keyword):
        for child in _children(self.index, clause):
            if keyword in _title_of(self.index, child):
                return child
        # 再深一层
        for child in _children(self.index, clause):
            for grand in _children(self.index, child):
                if keyword in _title_of(self.index, grand):
                    return grand
        return None

    def parse(self, resolve_ref):
        """解析本节。resolve_ref(clause) → 别的条文文本（解析『同 X.Y.Z』）。"""
        exams = {}
        clauses = self.exam_clauses()
        for key in EXAM_KEYS:
            if key not in clauses:
                exams[key] = {
                    "required": [], "supplementary": [], "optional": [],
                    "diseases": [], "basis_clause": self.sid, "absent": True,
                    "exposed": "",
                }
                continue
            clause = clauses[key]
            exams[key] = self._parse_exam(clause, resolve_ref)
        period = self._parse_period(clauses.get("periodic"), resolve_ref)
        return {
            "factor_id": self.sid,
            "chapter": self.chapter,
            "category": CHAPTER_CATEGORY[self.chapter],
            "name": self.title,
            "exams": exams,
            "period": period,
        }

    def _resolve_content(self, clause, resolve_ref, _seen=None):
        """解析『检查内容』条文为 (required, supplementary, optional)。

        『同 X.Y.Z』链可多跳（如 7.8.3.2 → 7.8.2.2 → 7.8.1.2），递归解析并防环。
        """
        _seen = _seen or set()
        if clause in _seen:
            return [], [], []
        _seen.add(clause)
        content_num = self._descendant_with_title(clause, "检查内容")
        if not content_num:
            return [], [], []
        text = _collapse(_full_text(self.index, content_num))
        text = re.sub(r"^检查内容[：:]?", "", text)
        ref = re.search(r"同(\d+(?:\.\d+){2,})", text)
        if ref:
            target_clause = ref.group(1).rsplit(".", 1)[0]  # 指向时点条文（去掉末级）
            # 先按完整条文号试（有的写成"同 X.Y.N.M"），再按所在时点条文试
            for candidate in (ref.group(1), target_clause):
                if candidate in self.index and candidate not in _seen:
                    got = self._resolve_content(candidate, resolve_ref, _seen)
                    if any(got):
                        return got
                    # 直接按条文全文抽（目标条文本身即"检查内容"）
                    got2 = _items_from_content(_collapse(_full_text(self.index, candidate)))
                    if any(got2):
                        return got2
            return [], [], []
        return _items_from_content(text)

    def _parse_exam(self, clause, resolve_ref):
        disease_num = self._descendant_with_title(clause, "目标疾病") or self._descendant_with_title(
            clause, "职业禁忌证"
        )
        exposed_num = self._descendant_with_title(clause, "检查对象")
        disease_text = _collapse(_full_text(self.index, disease_num)) if disease_num else ""
        exposed_text = _collapse(_full_text(self.index, exposed_num)) if exposed_num else ""
        disease_text = re.sub(r"^目标疾病[：:]?", "", disease_text)
        disease_text = re.sub(r"^职业禁忌证[：:]?", "", disease_text)
        exposed_text = re.sub(r"^检查对象[：:]?", "", exposed_text)

        # 『目标疾病：同 X.Y.Z』链
        ref_dis = re.search(r"同(\d+(?:\.\d+){2,})", disease_text)
        if ref_dis:
            target = resolve_ref(ref_dis.group(1))
            if target:
                disease_text = _collapse(target)
                disease_text = re.sub(r"^目标疾病[：:]?", "", disease_text)
                disease_text = re.sub(r"^职业禁忌证[：:]?", "", disease_text)

        content_num = self._descendant_with_title(clause, "检查内容")
        required, supplementary, optional = self._resolve_content(clause, resolve_ref)
        return {
            "required": required,
            "supplementary": supplementary,
            "optional": optional,
            "diseases": parse_diseases(disease_text),
            "basis_clause": content_num or clause,
            "absent": False,
            "exposed": exposed_text,
        }

    def _parse_period(self, periodic_clause, resolve_ref):
        result = {"kind": "pending", "value": None, "payload": "", "clause": "", "note": ""}
        if not periodic_clause:
            return result
        period_num = self._descendant_with_title(periodic_clause, "健康检查周期") or self._descendant_with_title(
            periodic_clause, "周期"
        )
        if not period_num:
            return result
        text = _collapse(_full_text(self.index, period_num))
        text = re.sub(r"^健康检查周期[（(][^）)]*[）)]", "", text)
        text = re.sub(r"^健康检查周期", "", text)
        text = re.sub(r"^健康检查", "", text)
        text = re.sub(r"^[：:为]+", "", text)
        kind, value, note = classify_period(text)
        result.update(
            {"kind": kind, "value": value, "payload": text, "clause": period_num, "note": note}
        )
        # 『同 X.Y.Z』式周期引用
        ref = re.search(r"同(\d+(?:\.\d+){2,})", text) if kind == "input_required" else None
        if ref:
            target = resolve_ref(ref.group(1))
            if target:
                kind2, value2, note2 = classify_period(_collapse(target))
                if kind2 != "input_required":
                    result.update(
                        {"kind": kind2, "value": value2, "note": note2,
                         "payload": _collapse(target)}
                    )
        return result


def _items_from_content(content_text):
    """从"检查内容"条文中抽必检 / 补充 / 选检三组项目。"""
    req_payload = _payload(content_text, "必检项目为") or _payload(content_text, "必检项目")
    sup_payload = _payload(content_text, "补充检查项目为") or _payload(content_text, "补充检查项目")
    opt_payload = _payload(content_text, "选检项目为") or _payload(content_text, "选检项目")

    # 无标记但含条件性尾部（『…者可选择 X、Y』）→ 摘到补充项（决策 D-16）
    if req_payload and not sup_payload:
        head, tail = _trim_optional_tail(_collapse(req_payload))
        if tail:
            req_payload = head
            marker = "可选择" if "可选择" in tail else "可选"
            sup_payload = tail.split(marker, 1)[1]  # 条件性项目本体
    return (
        items_from_payload(req_payload),
        items_from_payload(sup_payload),
        items_from_payload(opt_payload),
    )


def iter_sections(lines=None):
    """返回全部危害因素节（第 5–9 章的 X.Y 条）。"""
    lines = lines if lines is not None else load_raw_lines()
    lines = lines[_body_start(lines):]
    index = clause_index(lines)
    out = []
    for num in sorted(index, key=lambda k: [int(x) for x in k.split(".")]):
        if num.count(".") != 1:
            continue
        chapter = num.split(".")[0]
        if chapter not in CHAPTER_CATEGORY:
            continue
        out.append(Section(num, index[num][0], index))
    return out


def transcribe(lines=None):
    """全量转写；返回 {section_id: parsed}（按节号排序，确定）。"""
    lines = lines if lines is not None else load_raw_lines()
    lines = lines[_body_start(lines):]
    index = clause_index(lines)

    def resolve_ref(num):
        return _text_of(index, num)

    out = {}
    for num in sorted(index, key=lambda k: [int(x) for x in k.split(".")]):
        if num.count(".") != 1:
            continue
        if num.split(".")[0] not in CHAPTER_CATEGORY:
            continue
        section = Section(num, index[num][0], index)
        out[num] = section.parse(resolve_ref)
    return out


def assert_verbatim(parsed, raw_lines):
    """逐字核对：每个抽取值必须逐字出现在冻结原文中（否则转写漂移）。

    比对前两侧都**压平空白**：原文的换行/缩进是排版产物，不属内容差异。
    """
    flat = _collapse("\n".join(raw_lines))
    problems = []
    for sid, item in sorted(parsed.items()):
        if not flat.count(sid):
            problems.append("节号 %s 不在原文中" % sid)
        name = _collapse(item["name"])
        if name and name not in flat:
            problems.append("%s 因素名称不在原文：%r" % (sid, item["name"][:60]))
        for key, block in sorted(item["exams"].items()):
            for group in ("required", "supplementary", "optional"):
                for value in block[group]:
                    if _collapse(value) not in flat:
                        problems.append("%s.%s.%s 抽取值不在原文：%r" % (sid, key, group, value))
    return problems


# ---------------- 前言差异条目（核对清单 C8）----------------


def foreword_changes(lines=None):
    """抽取前言『与 GBZ 188—2014 相比…主要技术变化如下』的逐条差异。

    返回 [{"kind": added|removed|changed|others, "text": 原句, "clauses": [本节号…]}]。
    用途：`compare` 通路的期望差异来源（供 FR-C3 基准），以及 2014 版差异导向骨架的
    核对依据（未引述的条目一律保持 pending，决策 D-28）。
    """
    import re as _re

    lines = lines if lines is not None else load_raw_lines()
    # 前言在正文之前；取『主要技术变化如下』到『本标准由国家卫生健康标准委员会』之间
    flat = _collapse("\n".join(lines[: _body_start(lines)]))
    start = flat.find("主要技术变化如下")
    if start < 0:
        return []
    end = flat.find("本标准由国家卫生健康标准委员会", start)
    segment = flat[start:end if end > 0 else len(flat)]
    out = []
    for piece in segment.split("——"):
        piece = piece.strip()
        if not piece:
            continue
        if piece.startswith("删除了"):
            kind = "removed"
        elif piece.startswith("增加了"):
            kind = "added"
        elif piece.startswith("更改了"):
            kind = "changed"
        else:
            kind = "others"
        clauses = _re.findall(r"(\d+\.\d+(?:\.\d+)*)", piece)
        out.append({"kind": kind, "text": piece, "clauses": clauses})
    return out


def _ensure_utf8_stdio():  # pragma: no cover - 仅供脚本直跑
    import sys

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


def main(argv=None):  # pragma: no cover - 诊断入口
    _ensure_utf8_stdio()
    lines = load_raw_lines()
    parsed = transcribe(lines)
    problems = assert_verbatim(parsed, lines)
    print("解析节数：%d" % len(parsed))
    print("逐字核对问题：%d" % len(problems))
    for p in problems[:60]:
        print("  " + p)
    from collections import Counter

    kinds = Counter(v["period"]["kind"] for v in parsed.values())
    print("周期类型分布：%s" % dict(kinds))
    empty = []
    for sid, v in sorted(parsed.items()):
        if v["chapter"] not in ("5", "6", "7"):
            continue
        for key, b in sorted(v["exams"].items()):
            if not b["absent"] and not b["required"]:
                empty.append((sid, key))
    print("ch5-7 存在但必检项为空：%d %s" % (len(empty), empty))
    if len(argv or []) and "--dump" in argv:
        for sid in argv[argv.index("--dump") + 1 :]:
            item = parsed.get(sid)
            if not item:
                continue
            print("---- %s %s" % (sid, item["name"]))
            for key in EXAM_KEYS:
                b = item["exams"][key]
                print("   %-14s absent=%s req=%s" % (key, b["absent"], b["required"]))
            print("   period=%s" % (item["period"],))
    return 0 if not problems else 1


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main(sys.argv[1:]))
