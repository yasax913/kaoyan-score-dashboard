# -*- coding: utf-8 -*-
"""
data_generator.py — 生成考研复试分数线数据集(模拟数据)

用途
----
把"院校 / 专业 / 年份 / 复试线"整理成可分析的表格数据。

关于数据真实性(重要,也是面试会问的点)
--------------------------------------
本脚本生成的**不是真实录取数据**,而是按公开的分数区间规律合成的模拟数据,
用于把数据管道和可视化跑通。合成公式完全公开在下面 SUBJECT / UNI / TREND
三张表里,任何人重跑脚本都能得到逐字节相同的结果(固定随机种子)。

如果要换成真数据,只需要:
  1. 从院校研究生院官网/研招网人工摘录,或写爬虫抓取;
  2. 保持 CSV 的列名不变,替换 data/admission_scores.csv 的内容;
  3. 重新运行 build_dashboard.py。

输出
----
data/admission_scores.csv
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

# Windows 控制台默认 GBK,不强制 UTF-8 会把中文输出打成乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------- 路径配置
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUT_CSV = DATA_DIR / "admission_scores.csv"

YEARS = [2021, 2022, 2023, 2024, 2025]
PREDICT_YEAR = YEARS[-1] + 1  # 看板里做趋势外推的目标年份

# ------------------------------------------------- 专业:基础分与单科线系数
# base        = 该专业在"普通院校"上的典型复试总分
# s1 / s2     = 单科线(满分100 / 满分>100 科目)的换算系数
SUBJECTS = [
    {"code": "085400", "name": "电子信息(专硕)", "base": 277, "s1": 0.140, "s2": 0.213, "national_key": "工学"},
    {"code": "081200", "name": "计算机科学与技术", "base": 276, "s1": 0.137, "s2": 0.210, "national_key": "工学"},
    {"code": "025100", "name": "金融(专硕)", "base": 350, "s1": 0.155, "s2": 0.233, "national_key": "经济学"},
]

# ----------------------------------------------------------- 院校主数据
# 字段说明:
#   name         学校名
#   region       所在省份
#   tier         院校层次
#   adj          分数加成(反映报考热度)
#   app_base     年均报考人数的基准值
#   admit_base   年均录取人数的基准值
#   trend        5 年整体涨跌趋势(正=逐年变热)
#   osc          年度波动幅度(偶数年偏难/偏易造成的小波动)
#   self_marked  是否 34 所自划线院校(自划线院校不适用国家线)
UNI = [
    {"name": "清华大学",       "region": "北京", "tier": "985", "adj": 55, "app_base": 1400, "admit_base": 48,  "trend": +6, "osc": 6, "self_marked": True},
    {"name": "北京大学",       "region": "北京", "tier": "985", "adj": 50, "app_base": 1300, "admit_base": 45,  "trend": +5, "osc": 6, "self_marked": True},
    {"name": "浙江大学",       "region": "浙江", "tier": "985", "adj": 45, "app_base": 1600, "admit_base": 72,  "trend": +7, "osc": 5, "self_marked": True},
    {"name": "上海交通大学",   "region": "上海", "tier": "985", "adj": 46, "app_base": 1550, "admit_base": 80,  "trend": +7, "osc": 5, "self_marked": True},
    {"name": "华中科技大学",   "region": "湖北", "tier": "985", "adj": 32, "app_base": 1900, "admit_base": 150, "trend": +3, "osc": 4, "self_marked": True},
    {"name": "哈尔滨工业大学", "region": "黑龙江", "tier": "985", "adj": 24, "app_base": 1500, "admit_base": 180, "trend": -1, "osc": 3, "self_marked": True},
    {"name": "西安电子科技大学", "region": "陕西", "tier": "211", "adj": 18, "app_base": 2100, "admit_base": 220, "trend": +6, "osc": 4, "self_marked": False},
    {"name": "北京邮电大学",   "region": "北京", "tier": "211", "adj": 22, "app_base": 2000, "admit_base": 200, "trend": +5, "osc": 4, "self_marked": False},
    {"name": "南京航空航天大学", "region": "江苏", "tier": "211", "adj": 14, "app_base": 1500, "admit_base": 190, "trend": +3, "osc": 3, "self_marked": False},
    {"name": "深圳大学",       "region": "广东", "tier": "双非", "adj": 8,  "app_base": 1300, "admit_base": 160, "trend": +8, "osc": 4, "self_marked": False},
    {"name": "杭州电子科技大学", "region": "浙江", "tier": "双非", "adj": 4,  "app_base": 1100, "admit_base": 150, "trend": +9, "osc": 3, "self_marked": False},
    {"name": "重庆邮电大学",   "region": "重庆", "tier": "双非", "adj": 0,  "app_base": 900,  "admit_base": 140, "trend": +2, "osc": 3, "self_marked": False},
]

TIER_CFG = {
    "985":   {"delta": 38, "apps_per_seat": 22.0},
    "211":   {"delta": 18, "apps_per_seat": 15.0},
    "双非":  {"delta": 0,  "apps_per_seat": 8.5},
}

# 国家线(A 区总分),公开信息,按"学科门类"和年份给出
NATIONAL_LINE = {
    "工学":   {2021: 263, 2022: 273, 2023: 273, 2024: 265, 2025: 263},
    "经济学": {2021: 348, 2022: 360, 2023: 346, 2024: 338, 2025: 335},
}

# --------------------------------------------------------- 人工规则(特例)
# 让数据里出现"真实公告里会出现的情况",这样看板才有故事可讲
STOP_ENROLL = {           # 某校某专业某年起停招
    ("重庆邮电大学", "081200"): [2024, 2025],
}
OVERRIDE = {              # 强行指定复试线,用来制造异常点
    ("浙江大学", "085400", 2023): 402,
    ("深圳大学", "085400", 2024): 341,
    ("哈尔滨工业大学", "081200", 2022): 320,
}


def jitter(seed: str, amp: int) -> int:
    """基于字符串种子的确定性抖动:同一个 seed 永远得到同一个值。

    注意 seed 里必须带年份,否则同一学校同一专业每年得到相同的抖动,
    会产生"连续两年涨 0 分"这种一眼假的数据。
    """
    return random.Random(f"{seed}|{amp}").randint(-amp, amp)


def build_rows() -> list[dict]:
    rows: list[dict] = []
    for uni in UNI:
        tier_cfg = TIER_CFG[uni["tier"]]
        for sub in SUBJECTS:
            for idx, year in enumerate(YEARS):
                if year in STOP_ENROLL.get((uni["name"], sub["code"]), []):
                    continue

                # ------ 1) 分数合成:基础分 + 院校加成 + 年份趋势 + 奇偶年波动 + 确定性抖动
                score = sub["base"] + tier_cfg["delta"] + uni["adj"]
                score += uni["trend"] * idx                      # 线性趋势
                if year % 2 == 1:
                    score += uni["osc"]                          # 奇数年普遍偏易
                score += jitter(f"{uni['name']}-{sub['code']}-{year}", 5)

                # ------ 2) 特例覆盖
                if (uni["name"], sub["code"], year) in OVERRIDE:
                    score = OVERRIDE[(uni["name"], sub["code"], year)]

                # ------ 3) 业务约束:非自划线院校的复试线不得低于国家线
                national = NATIONAL_LINE[sub["national_key"]][year]
                note_parts: list[str] = []
                if not uni["self_marked"] and score < national:
                    score = national
                    note_parts.append("按国家线执行")

                s1 = round(score * sub["s1"] / 2) * 2
                s2 = round(score * sub["s2"] / 2) * 2

                # ------ 4) 报考/录取人数:报录比受热度影响,再用确定性抖动打散
                seats = max(
                    6,
                    round(uni["admit_base"] / len(SUBJECTS) * (1 + 0.04 * idx)),
                )
                ratio = tier_cfg["apps_per_seat"] * (1 + 0.05 * idx) * (1 + uni["adj"] / 120)
                applicants = max(
                    seats + 3,
                    round(seats * ratio + jitter(f"app-{uni['name']}-{sub['code']}-{year}", 40)),
                )

                if idx > 0:
                    prev = next(
                        (r for r in rows
                         if r["school"] == uni["name"] and r["subject_code"] == sub["code"]
                         and r["year"] == YEARS[idx - 1]),
                        None,
                    )
                    if prev:
                        delta = score - prev["retest_line"]
                        note_parts.append(f"较上年{'涨' if delta >= 0 else '降'}{abs(delta)}分")

                rows.append({
                    "year": year,
                    "school": uni["name"],
                    "region": uni["region"],
                    "tier": uni["tier"],
                    "subject_code": sub["code"],
                    "subject_name": sub["name"],
                    "is_self_marked": "是" if uni["self_marked"] else "否",
                    "national_line": national,
                    "retest_line": score,
                    "single_subject_100": s1,
                    "single_subject_150": s2,
                    "applicants": applicants,
                    "admitted": seats,
                    "ratio": round(applicants / seats, 1),
                    "note": "; ".join(note_parts),
                })
    return rows


def quality_check(rows: list[dict]) -> list[str]:
    """数据自检:这是简历里容易被追问、也最容易体现工程意识的一环。"""
    problems: list[str] = []

    keys = [(r["year"], r["school"], r["subject_code"]) for r in rows]
    if len(keys) != len(set(keys)):
        problems.append("存在重复的 (年份, 学校, 专业) 主键")
    if any(not str(r["school"]).strip() for r in rows):
        problems.append("存在学校名为空的记录")
    if any(r["retest_line"] <= 0 or r["retest_line"] > 500 for r in rows):
        problems.append("存在超出 [0,500] 的复试线")
    bad_national = [r for r in rows
                    if r["is_self_marked"] == "否" and r["retest_line"] < r["national_line"]]
    if bad_national:
        problems.append(f"{len(bad_national)} 条非自划线记录低于国家线")
    if any(r["admitted"] <= 0 or r["applicants"] < r["admitted"] for r in rows):
        problems.append("存在报考人数小于录取人数的记录")

    # 相邻年份跳变检查(>25 分视为可疑)
    by_key: dict[tuple, list[dict]] = {}
    for r in rows:
        by_key.setdefault((r["school"], r["subject_code"]), []).append(r)
    for key, group in by_key.items():
        group.sort(key=lambda x: x["year"])
        for prev, cur in zip(group, group[1:]):
            if cur["year"] - prev["year"] == 1 and abs(cur["retest_line"] - prev["retest_line"]) > 25:
                problems.append(
                    f"{key[0]} {key[1]} {prev['year']}->{cur['year']} "
                    f"跳变 {cur['retest_line'] - prev['retest_line']:+d} 分"
                )
    return problems


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_rows()

    fields = ["year", "school", "region", "tier", "subject_code", "subject_name",
              "is_self_marked", "national_line", "retest_line", "single_subject_100",
              "single_subject_150", "applicants", "admitted", "ratio", "note"]

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    schools = len({r["school"] for r in rows})
    print(f"[OK] 写出 {len(rows)} 行 -> {OUT_CSV}")
    print(f"     院校 {schools} 所 / 专业 {len(SUBJECTS)} 个 / 年份 {YEARS[0]}-{YEARS[-1]}")
    print(f"     预测目标年份: {PREDICT_YEAR}")

    problems = quality_check(rows)
    if problems:
        print(f"[WARN] 数据自检发现 {len(problems)} 个问题:")
        for p in problems:
            print(f"       - {p}")
    else:
        print("[OK] 数据自检全部通过(主键唯一/分数区间/国家线下限/报录一致性)")


if __name__ == "__main__":
    main()
