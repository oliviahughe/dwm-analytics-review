#!/usr/bin/env python3
"""
build_daily_snapshot.py
Build a daily snapshot JSON from daily CSV types with explicit coverage tracking.

Required CSV types (strict mode checks these):
  1. 基础数据其二                         -> core
  2. spin数据总览                         -> spin + top_machines
  3. 内购数据_分点位_分付费用户标签         -> iap
  4. 推广数据监控                         -> promo
  5. 基础数据(其1)                        -> basic1
  6. 付费用户总结数据_按生命周期分组         -> paying_users
  7. 付费用户资源监控                      -> resource (period compare)
  8. 大R用户明细                          -> big_r

Optional CSV types (parsed when present):
  9. 广告大盘数据                          -> ads (by point + ad type)
"""

import argparse
import csv
import glob
import json
import os
import re
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    raise SystemExit("pandas is required: pip install pandas")


DEFAULT_KEYWORDS = {
    "basic_data_1": "基础数据(其1)",
    "basic_data_2": "基础数据其二",
    "slot_spin_overview": "spin数据总览",
    "paying_user_summary": "付费用户总结数据_按生命周期分组",
    "paying_user_resource": "付费用户资源监控",
    "recharge_price_summary": "内购数据_分点位",
    "promotion_data": "推广数据监控",
    "big_r_detail": "大R用户明细",
    "ad_board_data": "广告大盘数据",
}

REQUIRED_KEYS = [
    "basic_data_1",
    "basic_data_2",
    "slot_spin_overview",
    "paying_user_summary",
    "paying_user_resource",
    "recharge_price_summary",
    "promotion_data",
    "big_r_detail",
]

OPTIONAL_KEYS = [
    "ad_board_data",
]

ALL_KEYS = REQUIRED_KEYS + OPTIONAL_KEYS


def load_csv_keywords(mapping_path):
    """Load CSV filename keywords from csv_mapping.json."""
    if not mapping_path or not Path(mapping_path).exists():
        return dict(DEFAULT_KEYWORDS)

    with open(mapping_path, encoding="utf-8") as f:
        cfg = json.load(f)

    result = {}
    for product_cfg in cfg.get("products", {}).values():
        if not isinstance(product_cfg, dict) or "csv_files" not in product_cfg:
            continue
        for key, val in product_cfg["csv_files"].items():
            if isinstance(val, dict) and "filename" in val:
                result[key] = val["filename"]

    for k, v in DEFAULT_KEYWORDS.items():
        result.setdefault(k, v)
    return result


def find_csv(data_dir, keyword):
    """Find CSV by keyword in filename, return most recently modified match."""
    pattern = os.path.join(str(data_dir), f"*{keyword}*.csv")
    matches = glob.glob(pattern)
    if not matches:
        return None
    return sorted(matches, key=os.path.getmtime, reverse=True)[0]


def safe_float(val):
    """Convert to float, handling commas, $, %, etc."""
    if val is None:
        return None
    s = str(val).strip().replace(",", "").replace("$", "").replace("%", "")
    if s in ("", "-", "—", "null", "N/A"):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def pct(a, b):
    """Percentage change: (a - b) / b. Returns None if not computable."""
    if a is None or b is None or b == 0:
        return None
    return round((a - b) / b, 6)


def build_comparison(current_val, d1_val, d7_val, avg7_val):
    """Build standard 3-window comparison dict for a single metric."""
    return {
        "current": current_val,
        "d1": d1_val,
        "d7": d7_val,
        "avg7": avg7_val,
        "chg_d1": pct(current_val, d1_val),
        "chg_d7": pct(current_val, d7_val),
        "chg_avg7": pct(current_val, avg7_val),
    }


def clean_date_str(s):
    """Strip parenthetical weekday suffix: '2026-01-01(四)' -> '2026-01-01'."""
    s = str(s).strip()
    for bracket in ["(", "（"]:
        if bracket in s:
            s = s[: s.index(bracket)]
    return s.strip()


def parse_date_col(df, col):
    """Clean and parse a date column in a DataFrame."""
    df[col] = df[col].apply(clean_date_str)
    df[col] = pd.to_datetime(df[col], errors="coerce").dt.normalize()
    return df


def row_val(df, date_col, day, col):
    """Get value from a single-row-per-date DataFrame."""
    r = df.loc[df[date_col] == day, col]
    if r.empty:
        return None
    v = r.iloc[-1]
    return round(float(v), 2) if pd.notna(v) else None


def date_str(dt):
    return dt.strftime("%Y-%m-%d")


def metric_from_df(df, date_col, target, column):
    """Build D vs D-1 / D-7 / avg7 for a column in a daily dataframe."""
    d = pd.to_datetime(target).normalize()
    return metric_from_anchor(df, date_col, d, column)


def metric_from_anchor(df, date_col, anchor_day, column):
    """Build comparison using an explicit anchor day."""
    d = pd.to_datetime(anchor_day).normalize()
    d1 = d - pd.Timedelta(days=1)
    d7 = d - pd.Timedelta(days=7)
    window = df[(df[date_col] >= d - pd.Timedelta(days=7)) & (df[date_col] < d)]

    cur = row_val(df, date_col, d, column)
    v_d1 = row_val(df, date_col, d1, column)
    v_d7 = row_val(df, date_col, d7, column)
    avg7 = round(float(window[column].mean()), 2) if not window.empty and window[column].notna().any() else None
    return build_comparison(cur, v_d1, v_d7, avg7)


CORE_METRICS = {
    "revenue": "总收入($)",
    "dau": "DAU",
    "pay_rate": "付费率(%)",
    "arppu": "内购ARPPU($)",
}


def parse_core(csv_path, target):
    """Parse 基础数据其二 for core dashboard metrics."""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    date_col = "日期" if "日期" in df.columns else ("时间" if "时间" in df.columns else None)
    if not date_col:
        raise ValueError("date column not found in basic_data_2")

    df = parse_date_col(df, date_col)
    df = df.dropna(subset=[date_col]).sort_values(date_col)

    for col in CORE_METRICS.values():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    result = {}
    for mk, col in CORE_METRICS.items():
        if col in df.columns:
            result[mk] = metric_from_df(df, date_col, target, col)

    return result


def parse_spin(csv_path, target):
    """Parse spin数据总览 for spin metrics + top machines."""
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    def day_agg(date_val):
        total_spin = total_gold = 0.0
        for r in rows:
            if clean_date_str(r.get("时间", "")) != date_val:
                continue
            total_spin += safe_float(r.get("spin次数")) or 0
            total_gold += safe_float(r.get("消耗金币")) or 0
        return total_spin, total_gold

    def avg_window(start_dt, end_dt_exclusive):
        dates = pd.date_range(start_dt, end_dt_exclusive - pd.Timedelta(days=1))
        spins, golds = [], []
        for dt in dates:
            s, g = day_agg(date_str(dt))
            if s > 0:
                spins.append(s)
                golds.append(g)
        if not spins:
            return None, None
        return (
            round(sum(spins) / len(spins), 2),
            round(sum(golds) / len(golds), 2),
        )

    d = pd.to_datetime(target).normalize()
    d_s = date_str(d)
    d1_s = date_str(d - pd.Timedelta(days=1))
    d7_s = date_str(d - pd.Timedelta(days=7))

    cur_s, cur_g = day_agg(d_s)
    d1_s_v, d1_g = day_agg(d1_s)
    d7_s_v, d7_g = day_agg(d7_s)
    avg7_s, avg7_g = avg_window(d - pd.Timedelta(days=7), d)

    spin_metrics = {
        "spin_times": build_comparison(cur_s, d1_s_v, d7_s_v, avg7_s),
        # spin人数按机台分组存在重复，不可跨机台累加作为总人数指标
        "spin_users": build_comparison(None, None, None, None),
        "spin_users_note": "spin_users is grouped by machine and may contain duplicated users; do not aggregate as global total",
        "gold_sink": build_comparison(cur_g, d1_g, d7_g, avg7_g),
    }

    def machine_agg(day):
        out = {}
        for r in rows:
            if clean_date_str(r.get("时间", "")) != day:
                continue
            name = r.get("机台名称", "").strip()
            if not name:
                continue
            spin_val = int(safe_float(r.get("spin次数")) or 0)
            users_val = int(safe_float(r.get("spin人数")) or 0)
            gold_val = int(safe_float(r.get("消耗金币")) or 0)
            if name not in out:
                out[name] = {"机台名称": name, "spin次数": 0, "spin人数": 0, "消耗金币": 0}
            out[name]["spin次数"] += spin_val
            out[name]["spin人数"] += users_val
            out[name]["消耗金币"] += gold_val
        return out

    d1_s = date_str(d - pd.Timedelta(days=1))
    cur_machine = machine_agg(d_s)
    prev_machine = machine_agg(d1_s)
    top_machines = sorted(cur_machine.values(), key=lambda x: -x["spin次数"])[:5]
    top_machines_d1 = sorted(prev_machine.values(), key=lambda x: -x["spin次数"])[:5]

    rank_d1 = {m["机台名称"]: i + 1 for i, m in enumerate(top_machines_d1)}
    machine_changes = []
    for i, m in enumerate(top_machines, 1):
        name = m["机台名称"]
        prev = prev_machine.get(name, {"spin次数": 0, "spin人数": 0, "消耗金币": 0})
        prev_rank = rank_d1.get(name)
        machine_changes.append(
            {
                "机台名称": name,
                "rank_current": i,
                "rank_d1": prev_rank,
                "rank_shift": (prev_rank - i) if prev_rank else None,
                "spin_current": m["spin次数"],
                "spin_d1": prev["spin次数"],
                "spin_chg_d1": pct(m["spin次数"], prev["spin次数"]) if prev["spin次数"] else None,
                "users_current": m["spin人数"],
                "users_d1": prev["spin人数"],
                "users_chg_d1": pct(m["spin人数"], prev["spin人数"]) if prev["spin人数"] else None,
            }
        )

    return spin_metrics, top_machines, top_machines_d1, machine_changes


def parse_iap_daily(csv_path, target):
    """Parse 内购数据_分点位 for IAP metrics."""
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    def day_agg(date_val):
        rev = users = 0.0
        for r in rows:
            if clean_date_str(r.get("时间", "")) != date_val:
                continue
            loc = r.get("项目位置", "").strip()
            if loc in ("false", "", "null"):
                continue
            rev += safe_float(r.get("付费总金额")) or 0
            users += safe_float(r.get("付费总用户数")) or 0
        arppu = round(rev / users, 2) if users > 0 else 0
        return rev, users, arppu

    d = pd.to_datetime(target).normalize()
    d_s = date_str(d)
    d1_s = date_str(d - pd.Timedelta(days=1))
    d7_s = date_str(d - pd.Timedelta(days=7))

    cur_r, cur_u, cur_a = day_agg(d_s)
    d1_r, d1_u, d1_a = day_agg(d1_s)
    d7_r, d7_u, d7_a = day_agg(d7_s)

    dates = pd.date_range(d - pd.Timedelta(days=7), d - pd.Timedelta(days=1))
    revs, usrs, arppus = [], [], []
    for dt in dates:
        r, u, a = day_agg(date_str(dt))
        if r > 0:
            revs.append(r)
            usrs.append(u)
            arppus.append(a)

    avg7_r = round(sum(revs) / len(revs), 2) if revs else None
    avg7_u = round(sum(usrs) / len(usrs), 2) if usrs else None
    avg7_a = round(sum(arppus) / len(arppus), 2) if arppus else None

    metrics = {
        "iap_revenue": build_comparison(cur_r, d1_r, d7_r, avg7_r),
        "iap_users": build_comparison(cur_u, d1_u, d7_u, avg7_u),
        "iap_arppu": build_comparison(cur_a, d1_a, d7_a, avg7_a),
    }
    def day_loc_agg(date_val):
        out = {}
        for r in rows:
            if clean_date_str(r.get("时间", "")) != date_val:
                continue
            loc = r.get("项目位置", "").strip()
            if loc in ("false", "", "null"):
                continue
            if loc not in out:
                out[loc] = {"rev": 0.0, "users": 0.0}
            out[loc]["rev"] += safe_float(r.get("付费总金额")) or 0
            out[loc]["users"] += safe_float(r.get("付费总用户数")) or 0
        return out

    cur_loc = day_loc_agg(d_s)
    d1_loc = day_loc_agg(d1_s)
    d7_loc = day_loc_agg(d7_s)
    top_current = sorted(cur_loc.items(), key=lambda x: -x[1]["rev"])[:8]
    top_points = []
    for loc, info in top_current:
        cur_rev = round(info["rev"], 2)
        cur_users = round(info["users"], 2)
        cur_arppu = round(cur_rev / cur_users, 2) if cur_users > 0 else 0
        d1_rev = round(d1_loc.get(loc, {}).get("rev", 0.0), 2)
        d7_rev = round(d7_loc.get(loc, {}).get("rev", 0.0), 2)
        top_points.append(
            {
                "location": loc,
                "rev": cur_rev,
                "users": cur_users,
                "arppu": cur_arppu,
                "d1_rev": d1_rev,
                "d7_rev": d7_rev,
                "chg_d1": pct(cur_rev, d1_rev) if d1_rev else None,
                "chg_d7": pct(cur_rev, d7_rev) if d7_rev else None,
            }
        )

    delta_vs_d1 = []
    all_locs = set(cur_loc.keys()) | set(d1_loc.keys())
    for loc in all_locs:
        cur_rev = cur_loc.get(loc, {}).get("rev", 0.0)
        prev_rev = d1_loc.get(loc, {}).get("rev", 0.0)
        delta_vs_d1.append({"location": loc, "delta_rev": round(cur_rev - prev_rev, 2)})
    top_risers = sorted(delta_vs_d1, key=lambda x: -x["delta_rev"])[:5]
    top_fallers = sorted(delta_vs_d1, key=lambda x: x["delta_rev"])[:5]

    iap_points = {
        "top_points_current": top_points,
        "top_risers_vs_d1": top_risers,
        "top_fallers_vs_d1": top_fallers,
        "anchor_date": d_s,
    }
    return metrics, iap_points


PROMO_METRIC_MAP = {
    "promo_rev": "总收入",
    "promo_cost": "推广成本",
    "promo_roi": "ROI",
    "installs": "安装次数",
    "cpi": "CPI",
}


def parse_promo_daily(csv_path, target, anchor_offset_days=0):
    """Parse 推广数据监控 (transposed: rows=metrics, cols=dates)."""
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    def get_val(metric_keyword, date_col_name):
        for r in rows:
            name = r.get("分析指标", "").strip()
            if metric_keyword in name:
                return safe_float(r.get(date_col_name))
        return None

    d = pd.to_datetime(target).normalize() - pd.Timedelta(days=anchor_offset_days)
    d_s = date_str(d)
    d1_s = date_str(d - pd.Timedelta(days=1))
    d7_s = date_str(d - pd.Timedelta(days=7))

    result = {}
    for mk, keyword in PROMO_METRIC_MAP.items():
        cur = get_val(keyword, d_s)
        v_d1 = get_val(keyword, d1_s)
        v_d7 = get_val(keyword, d7_s)

        dates = pd.date_range(d - pd.Timedelta(days=7), d - pd.Timedelta(days=1))
        vals = []
        for dt in dates:
            v = get_val(keyword, date_str(dt))
            if v is not None:
                vals.append(v)
        avg7 = round(sum(vals) / len(vals), 2) if vals else None

        result[mk] = build_comparison(cur, v_d1, v_d7, avg7)

    return result, d_s


DATE_COL_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_IN_TEXT_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


def extract_header_date_map(headers):
    """Map raw header -> canonical YYYY-MM-DD when the header contains a date."""
    out = {}
    for h in headers:
        if not h:
            continue
        hs = str(h).strip()
        if DATE_COL_PATTERN.match(hs):
            out[h] = hs
            continue
        m = DATE_IN_TEXT_PATTERN.search(hs)
        if m:
            out[h] = m.group(1)
    return out


def infer_ad_type(point_name):
    s = (point_name or "").strip().lower()
    if not s:
        return "other"
    if "_inter" in s or "interstitial" in s or s.startswith("inter_"):
        return "interstitial"
    if "_reward" in s or "reward_" in s or "rewarded" in s or s.endswith("_rv"):
        return "rewarded"
    if "banner" in s:
        return "banner"
    if "native" in s:
        return "native"
    if "open" in s or "splash" in s:
        return "open"
    if "offer" in s:
        return "offerwall"
    reward_like = [
        "reward",
        "collect",
        "bonus",
        "free",
        "mission",
        "quest",
        "login",
        "inbox",
        "wheel",
        "levelup",
        "jackpot",
        "respin",
    ]
    if any(k in s for k in reward_like):
        return "rewarded"
    return "other"


def parse_ads_daily(csv_path, target):
    """Parse 广告大盘数据 (rows=point/metric, cols=dates), grouped by point and ad type."""
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError("ad_board_data csv empty")

    headers = list(rows[0].keys())
    date_cols = sorted([c for c in headers if c and DATE_COL_PATTERN.match(c)])
    if not date_cols:
        raise ValueError("no date columns found in ad_board_data")

    metrics = {}
    for r in rows:
        m = (r.get("分析指标", "") or "").strip()
        if not m:
            continue
        metrics[m] = metrics.get(m, 0) + 1
    if not metrics:
        raise ValueError("no metric rows found in ad_board_data")

    primary_metric = "adView.总次数" if "adView.总次数" in metrics else sorted(metrics.items(), key=lambda x: -x[1])[0][0]

    target_dt = pd.to_datetime(target).normalize()
    available_dt = sorted(pd.to_datetime(date_cols).normalize())
    candidate = [d for d in available_dt if d <= target_dt]
    anchor_dt = candidate[-1] if candidate else available_dt[-1]
    anchor_date = date_str(anchor_dt)
    d1_date = date_str(anchor_dt - pd.Timedelta(days=1))
    d7_date = date_str(anchor_dt - pd.Timedelta(days=7))

    def getv(row, day):
        return safe_float(row.get(day))

    by_point = {}
    by_type_raw = {}
    for r in rows:
        metric_name = (r.get("分析指标", "") or "").strip()
        if metric_name != primary_metric:
            continue
        point = (r.get("adpos_name_adpos_adpos", "") or "").strip()
        if not point or point in ("阶段汇总", "total"):
            continue
        raw_type = (r.get("adtype", "") or "").strip().lower()
        if raw_type in ("rewardedvideo", "rewarded", "rv"):
            ad_type = "rewarded"
        elif raw_type in ("interstitial", "inter"):
            ad_type = "interstitial"
        elif raw_type in ("banner",):
            ad_type = "banner"
        elif raw_type in ("native",):
            ad_type = "native"
        elif raw_type in ("open", "appopen", "splash"):
            ad_type = "open"
        elif raw_type:
            ad_type = raw_type
        else:
            ad_type = infer_ad_type(point)

        cur = getv(r, anchor_date) or 0.0
        d1 = getv(r, d1_date) or 0.0
        d7 = getv(r, d7_date) or 0.0
        vals = []
        for dt in pd.date_range(anchor_dt - pd.Timedelta(days=7), anchor_dt - pd.Timedelta(days=1)):
            v = getv(r, date_str(dt))
            if v is not None:
                vals.append(v)
        avg7 = sum(vals) / len(vals) if vals else None
        if point not in by_point:
            by_point[point] = {
                "point": point,
                "ad_type": ad_type,
                "ad_types": set(),
                "current": 0.0,
                "d1": 0.0,
                "d7": 0.0,
                "avg7_sum": 0.0,
                "avg7_cnt": 0,
            }
        by_point[point]["ad_types"].add(ad_type)
        by_point[point]["current"] += cur
        by_point[point]["d1"] += d1
        by_point[point]["d7"] += d7
        if avg7 is not None:
            by_point[point]["avg7_sum"] += avg7
            by_point[point]["avg7_cnt"] += 1

        if ad_type not in by_type_raw:
            by_type_raw[ad_type] = {"current": 0.0, "d1": 0.0, "d7": 0.0, "avg7_sum": 0.0, "avg7_cnt": 0}
        by_type_raw[ad_type]["current"] += cur
        by_type_raw[ad_type]["d1"] += d1
        by_type_raw[ad_type]["d7"] += d7
        if avg7 is not None:
            by_type_raw[ad_type]["avg7_sum"] += avg7
            by_type_raw[ad_type]["avg7_cnt"] += 1

    if not by_point:
        raise ValueError(f"no rows for metric={primary_metric}")

    normalized_points = []
    for v in by_point.values():
        avg7 = round(v["avg7_sum"], 2) if v["avg7_cnt"] > 0 else None
        if len(v["ad_types"]) == 1:
            ad_type = list(v["ad_types"])[0]
        elif len(v["ad_types"]) > 1:
            ad_type = "mixed"
        else:
            ad_type = v["ad_type"]
        normalized_points.append(
            {
                "point": v["point"],
                "ad_type": ad_type,
                "current": round(v["current"], 2),
                "d1": round(v["d1"], 2),
                "d7": round(v["d7"], 2),
                "avg7": avg7,
                "chg_d1": pct(v["current"], v["d1"]) if v["d1"] else None,
                "chg_d7": pct(v["current"], v["d7"]) if v["d7"] else None,
                "chg_avg7": pct(v["current"], avg7),
            }
        )

    total_cur = round(sum(v["current"] for v in normalized_points), 2)
    total_d1 = round(sum(v["d1"] for v in normalized_points), 2)
    total_d7 = round(sum(v["d7"] for v in normalized_points), 2)
    avg7_components = [v["avg7"] for v in normalized_points if v["avg7"] is not None]
    total_avg7 = round(sum(avg7_components), 2) if avg7_components else None

    point_rank = sorted(normalized_points, key=lambda x: -x["current"])
    by_point_top = []
    for item in point_rank[:12]:
        it = dict(item)
        it["share"] = round(it["current"] / total_cur, 4) if total_cur else None
        by_point_top.append(it)

    by_type = []
    for t, acc in by_type_raw.items():
        cur = round(acc["current"], 2)
        d1 = round(acc["d1"], 2)
        d7 = round(acc["d7"], 2)
        avg7 = round(acc["avg7_sum"], 2) if acc["avg7_cnt"] > 0 else None
        by_type.append(
            {
                "ad_type": t,
                "current": cur,
                "d1": d1,
                "d7": d7,
                "avg7": avg7,
                "share": round(cur / total_cur, 4) if total_cur else None,
                "chg_d1": pct(cur, d1) if d1 else None,
                "chg_d7": pct(cur, d7) if d7 else None,
                "chg_avg7": pct(cur, avg7),
            }
        )
    by_type = sorted(by_type, key=lambda x: -x["current"])

    delta = []
    for p in normalized_points:
        delta.append(
            {
                "point": p["point"],
                "ad_type": p["ad_type"],
                "delta_vs_d1": round(p["current"] - p["d1"], 2),
            }
        )

    return {
        "metric": primary_metric,
        "anchor_date": anchor_date,
        "target_date": date_str(target_dt),
        "total": build_comparison(total_cur, total_d1, total_d7, total_avg7),
        "by_point_top": by_point_top,
        "by_type": by_type,
        "top_risers_vs_d1": sorted(delta, key=lambda x: -x["delta_vs_d1"])[:8],
        "top_fallers_vs_d1": sorted(delta, key=lambda x: x["delta_vs_d1"])[:8],
        "note": "ad board grouped by point; ad type grouped by adtype column when available",
    }


BASIC1_METRICS = {
    "net_revenue": "净收入",
    "total_installs": "总安装数",
    "dnu_month_avg": "DNU月均值",
    "next_day_retention": "次留",
    "day7_retention": "7留",
    "active_payers": "活跃付费用户",
}


def parse_basic1(csv_path, target):
    """Parse 基础数据(其1) for supplemental daily metrics."""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    date_col = "时间" if "时间" in df.columns else ("日期" if "日期" in df.columns else None)
    if not date_col:
        raise ValueError("date column not found in basic_data_1")

    df = parse_date_col(df, date_col)
    df = df.dropna(subset=[date_col]).sort_values(date_col)

    for col in BASIC1_METRICS.values():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace("%", "", regex=False), errors="coerce")

    result = {}
    d = pd.to_datetime(target).normalize()
    for mk, col in BASIC1_METRICS.items():
        if col in df.columns:
            if mk == "next_day_retention":
                anchor = d - pd.Timedelta(days=1)
                result[mk] = metric_from_anchor(df, date_col, anchor, col)
                result["next_day_retention_meta"] = {
                    "anchor_date": date_str(anchor),
                    "rule": "retention uses T-1 to avoid incomplete same-day value",
                }
            else:
                result[mk] = metric_from_df(df, date_col, target, col)

    return result


def parse_paying_users(csv_path, target):
    """Parse 付费用户总结数据_按生命周期分组 (transposed by date columns)."""
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
        headers = list(rows[0].keys()) if rows else []

    if not rows:
        raise ValueError("paying_user_summary csv empty")

    date_cols = [c for c in headers if c and c[:4].isdigit() and "-" in c]
    if not date_cols:
        raise ValueError("no date columns found in paying_user_summary")

    metrics_def = {
        "active_users_by_lifecycle": {"names": ["每日付费用户数", "付费用户活跃数"], "agg": "sum"},
        "active_user_ratio_by_lifecycle": {"names": ["每日付费用户数占比"], "agg": "mean"},
        "spin_per_user_by_lifecycle": {"names": ["spin.用户均次数", "spin.用户均次数 - 付费"], "agg": "mean"},
        "bet_median_by_lifecycle": {"names": ["付费bet中位数", "bet中位数"], "agg": "mean"},
        "diamond_per_user_by_lifecycle": {"names": ["付费钻石消耗人均值", "钻石消耗人均"], "agg": "mean"},
    }

    def day_metric(metric_aliases, day):
        vals = []
        for r in rows:
            metric_name = (r.get("分析指标", "") or "").strip()
            if metric_name not in metric_aliases:
                continue
            tier = (r.get("事件与注册相差天数", "") or "").strip()
            if tier in ("", "阶段汇总"):
                continue
            v = safe_float(r.get(day))
            if v is not None:
                vals.append(v)
        return vals

    d = pd.to_datetime(target).normalize()
    d_s = date_str(d)
    d1_s = date_str(d - pd.Timedelta(days=1))
    d7_s = date_str(d - pd.Timedelta(days=7))

    result = {}
    for out_name, cfg in metrics_def.items():
        def agg(day):
            vals = day_metric(cfg["names"], day)
            if not vals:
                return None
            if cfg["agg"] == "sum":
                return round(sum(vals), 2)
            return round(sum(vals) / len(vals), 2)

        cur = agg(d_s)
        v_d1 = agg(d1_s)
        v_d7 = agg(d7_s)

        avg_vals = []
        for dt in pd.date_range(d - pd.Timedelta(days=7), d - pd.Timedelta(days=1)):
            v = agg(date_str(dt))
            if v is not None:
                avg_vals.append(v)
        avg7 = round(sum(avg_vals) / len(avg_vals), 2) if avg_vals else None

        result[out_name] = build_comparison(cur, v_d1, v_d7, avg7)

    tier_vals = []
    tier_vals_d1 = []
    for r in rows:
        metric_name = (r.get("分析指标", "") or "").strip()
        if metric_name not in ("每日付费用户数", "付费用户活跃数"):
            continue
        tier = (r.get("事件与注册相差天数", "") or "").strip()
        if not tier:
            continue
        v = safe_float(r.get(d_s))
        if v is None:
            continue
        tier_vals.append({"tier": tier, "active_users": v})
        v_d1 = safe_float(r.get(d1_s))
        if v_d1 is not None:
            tier_vals_d1.append({"tier": tier, "active_users": v_d1})
    result["top_lifecycle_tiers"] = sorted(tier_vals, key=lambda x: -x["active_users"])[:5]
    result["top_lifecycle_tiers_d1"] = sorted(tier_vals_d1, key=lambda x: -x["active_users"])[:5]
    d1_map = {x["tier"]: x["active_users"] for x in tier_vals_d1}
    shifts = []
    for x in tier_vals:
        tier = x["tier"]
        cur = x["active_users"]
        prev = d1_map.get(tier)
        shifts.append(
            {
                "tier": tier,
                "current": cur,
                "d1": prev,
                "chg_d1": pct(cur, prev) if prev else None,
                "delta_d1": round(cur - prev, 2) if prev is not None else None,
            }
        )
    result["lifecycle_tier_shifts_vs_d1"] = sorted(shifts, key=lambda x: abs(x["delta_d1"] or 0), reverse=True)[:8]

    return result


def parse_resource(csv_path, target=None):
    """Parse 付费用户资源监控 dual-period compare format with duplicate headers."""
    # Newer format: rows = reasons/metrics, columns = date series.
    with open(csv_path, encoding="utf-8-sig") as f:
        dict_rows = list(csv.DictReader(f))
        headers_dict = list(dict_rows[0].keys()) if dict_rows else []
    header_date_map = extract_header_date_map(headers_dict)
    date_cols = sorted(set(header_date_map.values()))
    if dict_rows and date_cols:
        target_dt = pd.to_datetime(target).normalize() if target else pd.to_datetime(date_cols[-1]).normalize()
        available_dt = sorted(pd.to_datetime(date_cols).normalize())
        candidate = [d for d in available_dt if d <= target_dt]
        cur_dt = candidate[-1] if candidate else available_dt[-1]
        d1_dt = cur_dt - pd.Timedelta(days=1)
        d7_dt = cur_dt - pd.Timedelta(days=7)
        cur_day = date_str(cur_dt)
        d1_day = date_str(d1_dt)
        d7_day = date_str(d7_dt)

        def row_date_value(row, day):
            for raw_h, canon_day in header_date_map.items():
                if canon_day != day:
                    continue
                v = safe_float(row.get(raw_h))
                if v is not None:
                    return v
            return None

        def total_on_day(metric_rows, day):
            return sum((row_date_value(r, day) or 0.0) for r in metric_rows)

        def avg7_before_day(metric_rows):
            vals = []
            for dt in pd.date_range(cur_dt - pd.Timedelta(days=7), cur_dt - pd.Timedelta(days=1)):
                vals.append(total_on_day(metric_rows, date_str(dt)))
            return round(sum(vals) / len(vals), 2) if vals else None

        consume_rows = [r for r in dict_rows if "消耗钻石总和" in str(r.get("分析指标", "") or "")]
        grant_rows = [r for r in dict_rows if "发放钻石总和" in str(r.get("分析指标", "") or "")]

        consume_cur = total_on_day(consume_rows, cur_day)
        consume_d1 = total_on_day(consume_rows, d1_day)
        consume_d7 = total_on_day(consume_rows, d7_day)
        consume_avg7 = avg7_before_day(consume_rows)

        grant_cur = total_on_day(grant_rows, cur_day)
        grant_d1 = total_on_day(grant_rows, d1_day)
        grant_d7 = total_on_day(grant_rows, d7_day)
        grant_avg7 = avg7_before_day(grant_rows)

        net_cur = consume_cur - grant_cur
        net_d1 = consume_d1 - grant_d1
        net_d7 = consume_d7 - grant_d7
        net_avg7 = round((consume_avg7 - grant_avg7), 2) if consume_avg7 is not None and grant_avg7 is not None else None

        consume_cmp = build_comparison(round(consume_cur, 2), round(consume_d1, 2), round(consume_d7, 2), consume_avg7)
        grant_cmp = build_comparison(round(grant_cur, 2), round(grant_d1, 2), round(grant_d7, 2), grant_avg7)
        net_cmp = build_comparison(round(net_cur, 2), round(net_d1, 2), round(net_d7, 2), net_avg7)

        reason_rank = []
        for r in consume_rows:
            reason = str(r.get("原因", "") or "").strip()
            if not reason:
                continue
            cur_v = row_date_value(r, cur_day) or 0.0
            d1_v = row_date_value(r, d1_day) or 0.0
            d7_v = row_date_value(r, d7_day) or 0.0
            if cur_v <= 0 and d1_v <= 0 and d7_v <= 0:
                continue
            reason_rank.append(
                {
                    "reason": reason,
                    "current": round(cur_v, 2),
                    "previous": round(d1_v, 2),
                    "d1": round(d1_v, 2),
                    "d7": round(d7_v, 2),
                    "chg": pct(cur_v, d1_v),
                    "chg_d1": pct(cur_v, d1_v),
                    "chg_d7": pct(cur_v, d7_v),
                }
            )
        reason_rank = sorted(reason_rank, key=lambda x: -x["current"])[:8]

        return {
            "period": {
                "current": cur_day,
                "previous": d1_day,
            },
            "consume_total": {**consume_cmp, "previous": consume_cmp.get("d1"), "chg": consume_cmp.get("chg_d1")},
            "grant_total": {**grant_cmp, "previous": grant_cmp.get("d1"), "chg": grant_cmp.get("chg_d1")},
            "net_consume": {**net_cmp, "previous": net_cmp.get("d1"), "chg": net_cmp.get("chg_d1")},
            "top_consume_reasons": reason_rank,
            "mode": "date_series",
        }

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)

    compare_col = None
    for i, h in enumerate(headers):
        if "对比时间" in str(h):
            compare_col = i
            break
    if compare_col is None:
        # Fallback for single-period format: 原因, 分析指标, <period>
        if len(headers) == 3 and "分析指标" in headers and "原因" in headers:
            period_col = headers[2]
            consume_rows = [r for r in rows if len(r) > 2 and str(r[1]).strip() == "消耗钻石总和"]
            grant_rows = [r for r in rows if len(r) > 2 and str(r[1]).strip() == "发放钻石总和"]
            consume_total = sum(safe_float(r[2]) or 0 for r in consume_rows)
            grant_total = sum(safe_float(r[2]) or 0 for r in grant_rows)
            reason_rank = []
            for r in consume_rows:
                reason = str(r[0]).strip()
                v = safe_float(r[2]) or 0
                if reason and v > 0:
                    reason_rank.append({"reason": reason, "current": round(v, 2), "previous": None, "chg": None})
            reason_rank = sorted(reason_rank, key=lambda x: -x["current"])[:8]
            net = consume_total - grant_total
            return {
                "period": {"current": period_col, "previous": None},
                "consume_total": {"current": round(consume_total, 2), "previous": None, "chg": None},
                "grant_total": {"current": round(grant_total, 2), "previous": None, "chg": None},
                "net_consume": {"current": round(net, 2), "previous": None, "chg": None},
                "top_consume_reasons": reason_rank,
                "mode": "single_period",
            }
        raise ValueError("'对比时间' column not found in paying_user_resource")

    def find_indices(keyword):
        return [i for i, h in enumerate(headers) if keyword in str(h)]

    def split_cur_prev(indices):
        cur = [i for i in indices if i < compare_col]
        prev = [i for i in indices if i > compare_col]
        return (cur[0] if cur else None, prev[0] if prev else None)

    c_total_cur, c_total_prev = split_cur_prev(find_indices("消耗钻石总和"))
    d_total_cur, d_total_prev = split_cur_prev(find_indices("发放钻石总和"))

    if c_total_cur is None or c_total_prev is None or d_total_cur is None or d_total_prev is None:
        raise ValueError("resource key columns not found")

    cur_period = None
    prev_period = None
    consume_by_reason = {}

    total_consume_cur = total_consume_prev = 0.0
    total_grant_cur = total_grant_prev = 0.0

    for r in rows:
        if len(r) <= max(c_total_cur, c_total_prev, d_total_cur, d_total_prev):
            continue
        reason = str(r[0]).strip()
        if not reason:
            continue

        cur_period = cur_period or (str(r[1]).strip() if len(r) > 1 else None)
        prev_period = prev_period or (str(r[compare_col]).strip() if len(r) > compare_col else None)

        c_cur = safe_float(r[c_total_cur]) or 0
        c_prev = safe_float(r[c_total_prev]) or 0
        d_cur = safe_float(r[d_total_cur]) or 0
        d_prev = safe_float(r[d_total_prev]) or 0

        total_consume_cur += c_cur
        total_consume_prev += c_prev
        total_grant_cur += d_cur
        total_grant_prev += d_prev

        if reason not in consume_by_reason:
            consume_by_reason[reason] = {"current": 0.0, "previous": 0.0}
        consume_by_reason[reason]["current"] += c_cur
        consume_by_reason[reason]["previous"] += c_prev

    reason_rank = []
    for reason, v in consume_by_reason.items():
        reason_rank.append(
            {
                "reason": reason,
                "current": round(v["current"], 2),
                "previous": round(v["previous"], 2),
                "chg": pct(v["current"], v["previous"]),
            }
        )
    reason_rank = sorted(reason_rank, key=lambda x: -x["current"])[:8]

    net_cur = total_consume_cur - total_grant_cur
    net_prev = total_consume_prev - total_grant_prev

    return {
        "period": {
            "current": cur_period,
            "previous": prev_period,
        },
        "consume_total": {
            "current": round(total_consume_cur, 2),
            "previous": round(total_consume_prev, 2),
            "chg": pct(total_consume_cur, total_consume_prev),
        },
        "grant_total": {
            "current": round(total_grant_cur, 2),
            "previous": round(total_grant_prev, 2),
            "chg": pct(total_grant_cur, total_grant_prev),
        },
        "net_consume": {
            "current": round(net_cur, 2),
            "previous": round(net_prev, 2),
            "chg": pct(net_cur, net_prev),
        },
        "top_consume_reasons": reason_rank,
    }


def parse_big_r(csv_path):
    """Parse 大R用户明细 snapshot metrics with churn-risk profiling."""
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    def fnum(row, key):
        return safe_float(row.get(key)) or 0.0

    users = []
    for r in rows:
        total_pay = fnum(r, "总付费")
        pay_days = int(fnum(r, "付费天数"))
        users.append(
            {
                "uid": (r.get("#account_id") or "").strip(),
                "total_pay": total_pay,
                "max_pay": fnum(r, "最大付费"),
                "login_days": int(fnum(r, "登录天数")),
                "pay_days": pay_days,
                "churn_days": int(fnum(r, "流失天数")),
                "country": (r.get("country") or "").strip(),
                "r_level": (r.get("r_level") or "").strip(),
                "last_pay_date": (r.get("最后付费日期") or "").strip(),
                "last_login_date": (r.get("最后登录日期") or "").strip(),
                "last_pay_loc": (r.get("最后付费点位") or "").strip(),
                "pay_frequency": round(pay_days / max(total_pay, 1.0), 4),
            }
        )

    users.sort(key=lambda x: -x["total_pay"])
    total = len(users)
    active_7d = len([u for u in users if u["churn_days"] <= 7])
    active_30d = len([u for u in users if u["churn_days"] <= 30])
    churn_risk = len([u for u in users if u["churn_days"] > 30])

    # In this table, everyone is usually within 30-day active set.
    # Real risk should focus on the tail close to 30 days.
    at_risk_users = [u for u in users if 20 <= u["churn_days"] <= 30]
    high_risk_users = [u for u in users if u["churn_days"] >= 27]

    def top_count(items, key, top_n=5, min_share=0.35):
        bucket = {}
        n = len(items)
        if n == 0:
            return [], []
        for it in items:
            v = (it.get(key) or "UNKNOWN").strip() if isinstance(it.get(key), str) else str(it.get(key))
            if v in ("", "None"):
                v = "UNKNOWN"
            bucket[v] = bucket.get(v, 0) + 1
        ranked = sorted(bucket.items(), key=lambda x: -x[1])[:top_n]
        top = [{"value": k, "count": c, "share": round(c / n, 4)} for k, c in ranked]
        concentrated = [x for x in top if x["share"] >= min_share and x["count"] >= 2]
        return top, concentrated

    risk_country, risk_country_hot = top_count(at_risk_users, "country")
    risk_r_level, risk_r_level_hot = top_count(at_risk_users, "r_level")
    risk_pay_loc, risk_pay_loc_hot = top_count(at_risk_users, "last_pay_loc")

    # Pay intensity buckets for risk users
    intensity_bucket = {"pay_days<=30": 0, "pay_days31-90": 0, "pay_days>90": 0}
    for u in at_risk_users:
        pdays = u["pay_days"]
        if pdays <= 30:
            intensity_bucket["pay_days<=30"] += 1
        elif pdays <= 90:
            intensity_bucket["pay_days31-90"] += 1
        else:
            intensity_bucket["pay_days>90"] += 1

    concentrated_features = []
    for grp_name, grp in [
        ("country", risk_country_hot),
        ("r_level", risk_r_level_hot),
        ("last_pay_loc", risk_pay_loc_hot),
    ]:
        for x in grp:
            concentrated_features.append(
                {
                    "feature": grp_name,
                    "value": x["value"],
                    "share": x["share"],
                    "count": x["count"],
                    "note": "risk users show concentration on this feature",
                }
            )

    return {
        "table_scope_note": "big_r table is 30-day-active payer snapshot; focus on churn-tail users (20-30 days).",
        "total_users": total,
        "active_7d": active_7d,
        "active_30d": active_30d,
        "churn_risk_over_30d": churn_risk,
        "active_30d_rate": round(active_30d / total, 4) if total > 0 else None,
        "total_ltv": round(sum(u["total_pay"] for u in users), 2),
        "at_risk_summary": {
            "at_risk_users_20_30d": len(at_risk_users),
            "high_risk_users_27_30d": len(high_risk_users),
            "at_risk_share": round(len(at_risk_users) / total, 4) if total > 0 else None,
            "high_risk_share": round(len(high_risk_users) / total, 4) if total > 0 else None,
        },
        "at_risk_features": {
            "country_top": risk_country,
            "r_level_top": risk_r_level,
            "last_pay_loc_top": risk_pay_loc,
            "pay_intensity_bucket": intensity_bucket,
            "concentrated_features": concentrated_features,
        },
        "at_risk_users_top": sorted(at_risk_users, key=lambda x: (-x["churn_days"], -x["total_pay"]))[:20],
        "top_users": users[:10],
    }


def build_coverage_entry(key, keyword, path, required):
    return {
        "csv_key": key,
        "keyword": keyword,
        "required": required,
        "file": path,
        "status": "found" if path else "missing",
        "section": None,
        "error": None,
    }


def mark_parsed(cov, section):
    cov["status"] = "parsed"
    cov["section"] = section


def mark_error(cov, section, err):
    cov["status"] = "parse_error"
    cov["section"] = section
    cov["error"] = str(err)


def main():
    ap = argparse.ArgumentParser(description="Build daily snapshot with coverage (8 required + optional extras)")
    ap.add_argument("--input-dir", required=True, help="Directory containing daily CSV files")
    ap.add_argument("--target-date", required=True, help="Target date YYYY-MM-DD (data date)")
    ap.add_argument("--output", required=True, help="Output JSON path")
    ap.add_argument("--csv-mapping", default=None, help="Path to csv_mapping.json (optional)")
    ap.add_argument("--expected-csv-count", type=int, default=8, help="Expected REQUIRED CSV count for completeness")
    ap.add_argument("--strict", action="store_true", help="Fail if any expected CSV is missing or parse_error")
    args = ap.parse_args()

    input_dir = args.input_dir
    target = args.target_date
    out_path = Path(args.output)

    keywords = load_csv_keywords(args.csv_mapping)

    coverage = {}
    for key in ALL_KEYS:
        kw = keywords.get(key, DEFAULT_KEYWORDS.get(key, key))
        coverage[key] = build_coverage_entry(key, kw, find_csv(input_dir, kw), required=(key in REQUIRED_KEYS))

    result = {
        "date": target,
        "expected_csv_count": args.expected_csv_count,
        "found_csv_count": len([v for v in coverage.values() if v["file"]]),
        "required_csv_count": len(REQUIRED_KEYS),
        "required_found_count": len([k for k in REQUIRED_KEYS if coverage[k]["file"]]),
    }
    warnings = []
    result["_freshness"] = {
        "retention_rule": "use T-1 for next_day_retention",
        "promo_rule": "use T-1 for promo metrics by default",
        "iap_points_rule": "include top iap point changes vs D-1",
        "ads_rule": "use D by default; fallback to nearest available date in ad board table",
    }

    try:
        p = coverage["basic_data_2"]["file"]
        if not p:
            warnings.append("core: basic_data_2 CSV not found")
        else:
            result["core"] = parse_core(p, target)
            mark_parsed(coverage["basic_data_2"], "core")
    except Exception as e:
        warnings.append(f"core: {e}")
        mark_error(coverage["basic_data_2"], "core", e)

    try:
        p = coverage["slot_spin_overview"]["file"]
        if not p:
            warnings.append("spin: slot_spin_overview CSV not found")
        else:
            spin, top_machines, top_machines_d1, machine_changes = parse_spin(p, target)
            result["spin"] = spin
            result["top_machines"] = top_machines
            result["top_machines_d1"] = top_machines_d1
            result["top_machine_changes"] = machine_changes
            mark_parsed(coverage["slot_spin_overview"], "spin")
    except Exception as e:
        warnings.append(f"spin: {e}")
        mark_error(coverage["slot_spin_overview"], "spin", e)

    try:
        p = coverage["recharge_price_summary"]["file"]
        if not p:
            warnings.append("iap: recharge_price_summary CSV not found")
        else:
            iap_metrics, iap_points = parse_iap_daily(p, target)
            result["iap"] = iap_metrics
            result["iap_points"] = iap_points
            mark_parsed(coverage["recharge_price_summary"], "iap")
    except Exception as e:
        warnings.append(f"iap: {e}")
        mark_error(coverage["recharge_price_summary"], "iap", e)

    try:
        p = coverage["promotion_data"]["file"]
        if not p:
            warnings.append("promo: promotion_data CSV not found")
        else:
            promo_t1, anchor_date = parse_promo_daily(p, target, anchor_offset_days=1)
            promo_raw_d, raw_date = parse_promo_daily(p, target, anchor_offset_days=0)
            result["promo"] = promo_t1
            result["promo_raw_d"] = promo_raw_d
            result["_freshness"]["promo_anchor_date"] = anchor_date
            result["_freshness"]["promo_raw_date"] = raw_date
            mark_parsed(coverage["promotion_data"], "promo")
    except Exception as e:
        warnings.append(f"promo: {e}")
        mark_error(coverage["promotion_data"], "promo", e)

    try:
        p = coverage["basic_data_1"]["file"]
        if not p:
            warnings.append("basic1: basic_data_1 CSV not found")
        else:
            result["basic1"] = parse_basic1(p, target)
            mark_parsed(coverage["basic_data_1"], "basic1")
    except Exception as e:
        warnings.append(f"basic1: {e}")
        mark_error(coverage["basic_data_1"], "basic1", e)

    try:
        p = coverage["paying_user_summary"]["file"]
        if not p:
            warnings.append("paying_users: paying_user_summary CSV not found")
        else:
            result["paying_users"] = parse_paying_users(p, target)
            mark_parsed(coverage["paying_user_summary"], "paying_users")
    except Exception as e:
        warnings.append(f"paying_users: {e}")
        mark_error(coverage["paying_user_summary"], "paying_users", e)

    try:
        p = coverage["paying_user_resource"]["file"]
        if not p:
            warnings.append("resource: paying_user_resource CSV not found")
        else:
            result["resource"] = parse_resource(p, target=target)
            mark_parsed(coverage["paying_user_resource"], "resource")
    except Exception as e:
        warnings.append(f"resource: {e}")
        mark_error(coverage["paying_user_resource"], "resource", e)

    try:
        p = coverage["big_r_detail"]["file"]
        if not p:
            warnings.append("big_r: big_r_detail CSV not found")
        else:
            result["big_r"] = parse_big_r(p)
            mark_parsed(coverage["big_r_detail"], "big_r")
    except Exception as e:
        warnings.append(f"big_r: {e}")
        mark_error(coverage["big_r_detail"], "big_r", e)

    try:
        p = coverage["ad_board_data"]["file"]
        if not p:
            warnings.append("ads: ad_board_data CSV not found (optional)")
        else:
            result["ads"] = parse_ads_daily(p, target)
            mark_parsed(coverage["ad_board_data"], "ads")
    except Exception as e:
        warnings.append(f"ads: {e}")
        mark_error(coverage["ad_board_data"], "ads", e)

    coverage_list = [coverage[k] for k in ALL_KEYS]
    result["_coverage"] = coverage_list

    missing_or_error_required = [c for c in coverage_list if c["required"] and c["status"] in ("missing", "parse_error")]

    if warnings:
        result["_warnings"] = warnings

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"daily snapshot written: {out_path}")
    print(
        "coverage: parsed="
        f"{len([c for c in coverage_list if c['status'] == 'parsed'])}, "
        f"required_missing_or_error={len(missing_or_error_required)}"
    )

    if args.strict and missing_or_error_required:
        raise SystemExit("strict mode failed: required CSVs are missing or parse_error")


if __name__ == "__main__":
    main()
