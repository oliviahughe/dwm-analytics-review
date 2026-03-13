"""
parse_paying_users.py
聚合「付费用户总结数据_按生命周期分组」CSV，输出各生命周期分层的月均活跃值 + 环比。

字段：事件与注册相差天数, 分析指标, 阶段汇总, 2026-01-01, 2026-01-02, ...
- 行 = 某生命周期段 + 某指标的每日数据
- 关键指标：spin.用户均次数, bet中位数, 钻石消耗人均, 付费用户活跃数

用法：
    python parse_paying_users.py --file <csv路径> --month 2026-02 [--prev-month 2026-01]
"""
import csv, json, argparse
from datetime import datetime
from collections import defaultdict

def parse_num(s):
    try: return float(str(s).strip().replace(',', ''))
    except: return None

def month_dates(rows_header, month):
    """从表头中找出属于指定月份的列名"""
    dates = []
    for col in rows_header:
        try:
            d = datetime.strptime(col.strip(), '%Y-%m-%d')
            if d.strftime('%Y-%m') == month:
                dates.append(col)
        except:
            pass
    return dates

def range_dates(rows_header, start_date=None, end_date=None, month=None):
    """从表头找出属于指定范围或月份的日期列"""
    from datetime import date as date_cls
    sd = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
    ed = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
    dates = []
    for col in rows_header:
        try:
            d = datetime.strptime(col.strip(), '%Y-%m-%d').date()
            if sd and ed:
                if sd <= d <= ed:
                    dates.append(col)
            elif month:
                if d.strftime('%Y-%m') == month:
                    dates.append(col)
        except:
            pass
    return dates

def avg_of_dates(row, date_cols):
    """对指定日期列求均值，忽略空值"""
    vals = [parse_num(row.get(c)) for c in date_cols if parse_num(row.get(c)) is not None]
    return round(sum(vals) / len(vals), 2) if vals else None

def pct_change(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100, 1)

# 生命周期段的排序顺序
TIER_ORDER = ['0~7', '7~30', '30~60', '60~90', '90~120', '120~150',
              '150~180', '180~210', '210~240', '240~270', '270~300', '300+', '300~∞']

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True)
    parser.add_argument('--month')
    parser.add_argument('--prev-month')
    parser.add_argument('--start-date', help='起始日期 YYYY-MM-DD（周报模式）')
    parser.add_argument('--end-date', help='结束日期 YYYY-MM-DD（周报模式）')
    parser.add_argument('--prev-start-date', help='上周起始日期 YYYY-MM-DD')
    parser.add_argument('--prev-end-date', help='上周结束日期 YYYY-MM-DD')
    parser.add_argument('--output')
    args = parser.parse_args()

    with open(args.file, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames or list(rows[0].keys()) if rows else []

    cur_dates = range_dates(headers, args.start_date, args.end_date, args.month)
    prev_dates = range_dates(headers, args.prev_start_date, args.prev_end_date, args.prev_month) if (args.prev_month or args.prev_start_date) else []

    # 按 (生命周期段, 指标) 聚合
    cur_data = defaultdict(dict)
    prev_data = defaultdict(dict)

    for r in rows:
        tier = r.get('事件与注册相差天数', '').strip()
        metric = r.get('分析指标', '').strip()
        if not tier or not metric:
            continue

        if cur_dates:
            cur_data[tier][metric] = avg_of_dates(r, cur_dates)
        if prev_dates:
            prev_data[tier][metric] = avg_of_dates(r, prev_dates)

    # 生成对比结果
    result = {'month': args.month, 'by_tier': {}}
    all_tiers = sorted(set(list(cur_data.keys()) + list(prev_data.keys())),
                       key=lambda x: TIER_ORDER.index(x) if x in TIER_ORDER else 99)

    for tier in all_tiers:
        c = cur_data.get(tier, {})
        p = prev_data.get(tier, {})
        tier_result = {}
        all_metrics = set(list(c.keys()) + list(p.keys()))
        for metric in all_metrics:
            cv = c.get(metric)
            pv = p.get(metric)
            tier_result[metric] = {
                'current': cv,
                'previous': pv,
                'change': pct_change(cv, pv)
            }
        result['by_tier'][tier] = tier_result

    # 生命周期对齐视角：比较 Feb[X] vs Jan[X的前一段]
    # 即同一批用户，月份推进后桶位上移
    if args.prev_month and cur_data and prev_data:
        aligned = {}
        for i, tier in enumerate(all_tiers[1:], 1):  # 从第二个桶开始
            prev_tier = all_tiers[i-1]  # 上月对应的桶（低一档）
            c = cur_data.get(tier, {})
            p = prev_data.get(prev_tier, {})
            aligned[f'{tier}(对齐前段:{prev_tier})'] = {}
            for metric in set(list(c.keys()) + list(p.keys())):
                cv = c.get(metric)
                pv = p.get(metric)
                aligned[f'{tier}(对齐前段:{prev_tier})'][metric] = {
                    'current_tier': tier, 'prev_tier': prev_tier,
                    'current': cv, 'previous': pv,
                    'change': pct_change(cv, pv)
                }
        result['lifecycle_aligned'] = aligned

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f'已输出到 {args.output}')
    else:
        print(out)

if __name__ == '__main__':
    main()
