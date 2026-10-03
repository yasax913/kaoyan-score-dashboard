# -*- coding: utf-8 -*-
"""
build_dashboard.py — 把 CSV 数据注入 HTML 模板,产出零依赖单文件看板

为什么要"注入"而不是让页面用 fetch 读 CSV
----------------------------------------
浏览器的 fetch 受同源策略限制:直接双击打开 HTML 时,file:// 协议下 fetch 本地
CSV 会被 CORS 拦截,页面会白屏。对要发给导师/面试官的文件来说这是致命的。

所以这里在构建期就把数据内联进 HTML,产出物是**一个文件**,双击即开、
可以直接当附件发邮件、断网也能跑,代价只是数据变了要重新构建一次。

输入:data/admission_scores.csv + assets/dashboard_template.html
输出:dashboard.html
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
IN_CSV = BASE_DIR / "data" / "admission_scores.csv"
TEMPLATE = BASE_DIR / "assets" / "dashboard_template.html"
OUT_HTML = BASE_DIR / "dashboard.html"

# CSV 列 -> 输出的 JSON 字段与类型
# 显式声明类型是刻意的:CSV 里一切都是字符串,不转换的话
# JS 里 "380" < "1000" 会按字典序比较,排序和筛选会全部出错。
FIELDS: list[tuple[str, str, type]] = [
    ("year", "year", int),
    ("school", "school", str),
    ("region", "region", str),
    ("tier", "tier", str),
    ("subject_code", "subject_code", str),
    ("subject_name", "subject_name", str),
    ("is_self_marked", "is_self_marked", str),
    ("national_line", "national_line", int),
    ("retest_line", "retest_line", int),
    ("single_subject_100", "single_subject_100", int),
    ("single_subject_150", "single_subject_150", int),
    ("applicants", "applicants", int),
    ("admitted", "admitted", int),
    ("ratio", "ratio", float),
    ("note", "note", str),
]

REQUIRED_KEYS = {"year", "school", "subject_code", "retest_line", "national_line"}


def load_rows() -> list[dict]:
    if not IN_CSV.exists():
        raise SystemExit(f"[ERR] 找不到数据文件 {IN_CSV},请先运行 python data_generator.py")

    rows: list[dict] = []
    # utf-8-sig:Excel 存出来的 CSV 常带 BOM,不处理会让第一列列名变成 "\ufeffyear"
    with IN_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED_KEYS - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"[ERR] CSV 缺少必需列: {sorted(missing)}")

        for lineno, raw in enumerate(reader, start=2):
            row: dict = {}
            for src, dst, caster in FIELDS:
                value = raw.get(src)
                if value is None or value == "":
                    if caster is str:
                        row[dst] = ""
                        continue
                    raise SystemExit(f"[ERR] 第 {lineno} 行字段 {src} 为空,无法转换为 {caster.__name__}")
                try:
                    row[dst] = caster(value)
                except ValueError as exc:
                    raise SystemExit(f"[ERR] 第 {lineno} 行字段 {src}={value!r} 转换失败: {exc}") from exc
            rows.append(row)

    if not rows:
        raise SystemExit("[ERR] CSV 里没有任何数据行")
    return rows


def sanity(rows: list[dict]) -> list[str]:
    """构建期自检:宁可构建失败,也不要发布一个数字明显不对的看板。"""
    problems: list[str] = []
    years = sorted({r["year"] for r in rows})

    dup = len(rows) - len({(r["year"], r["school"], r["subject_code"]) for r in rows})
    if dup:
        problems.append(f"{dup} 条重复主键")

    for r in rows:
        if not (0 < r["retest_line"] <= 500):
            problems.append(f"{r['year']} {r['school']} 复试线异常: {r['retest_line']}")
        if r["is_self_marked"] == "否" and r["retest_line"] < r["national_line"]:
            problems.append(f"{r['year']} {r['school']} 非自划线但低于国家线")
        if r["admitted"] <= 0 or r["applicants"] < r["admitted"]:
            problems.append(f"{r['year']} {r['school']} 报录数据不合理")

    # 每个 (学校, 专业) 至少要 3 个年份,否则前端回归外推会直接判为样本不足
    groups: dict[tuple, int] = {}
    for r in rows:
        groups[(r["school"], r["subject_code"])] = groups.get((r["school"], r["subject_code"]), 0) + 1
    thin = [k for k, n in groups.items() if n < 3]
    if thin:
        problems.append(f"{len(thin)} 个 (学校,专业) 组合不足 3 年: {thin[:3]}")

    print(f"[OK] 读入 {len(rows)} 行 / {len({r['school'] for r in rows})} 所院校 / "
          f"{len({r['subject_code'] for r in rows})} 个专业 / {years[0]}-{years[-1]}")
    return problems


def main() -> None:
    rows = load_rows()
    problems = sanity(rows)
    if problems:
        print(f"[WARN] 构建期自检发现 {len(problems)} 个问题:")
        for p in problems:
            print(f"       - {p}")

    if not TEMPLATE.exists():
        raise SystemExit(f"[ERR] 找不到模板 {TEMPLATE}")

    template = TEMPLATE.read_text(encoding="utf-8")
    for marker in ("/*__DATA__*/", "/*__META__*/"):
        if marker not in template:
            raise SystemExit(f"[ERR] 模板缺少占位符 {marker},数据无法注入")

    meta = {
        "built": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": IN_CSV.name,
        "rows": len(rows),
        "warnings": problems,
    }

    # ensure_ascii=False 让中文在源码里可读;把 </ 转义掉,避免数据里出现 </script> 提前闭合标签
    def dump(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    html = (template
            .replace("/*__DATA__*/", dump(rows))
            .replace("/*__META__*/", dump(meta)))

    OUT_HTML.write_text(html, encoding="utf-8")
    size_kb = OUT_HTML.stat().st_size / 1024
    print(f"[OK] 生成 {OUT_HTML}  ({size_kb:.1f} KB,零依赖单文件)")
    print("     直接双击用浏览器打开即可;不需要 pip install,不需要本地服务器。")


if __name__ == "__main__":
    main()
