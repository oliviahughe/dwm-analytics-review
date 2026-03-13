"""
parse_promotion.py
聚合「推广数据监控」CSV，输出月度推广指标汇总 + 环比。

CSV 结构：行=指标名（分析指标列），列=日期（YYYY-MM-DD）。
关键指标：总收入(AF)、推广成本(AF)、ROI、安装次数、CPI、广告展示/点击/eCPM/CTR 等。

用法：
    python parse_promotion.py --file <csv路径> --month 2026-02 [--prev-month 2026-01]
"""
import csv, json, argparse
from datetime import datetime

def parse_num(s):
    try: return float(str(s).strip().replace(',', ''))
    except: return None

def month_cols(headers, month):
    """从表头中筛出属于指定月份的日期列"""
    cols = []
    for h in headers:
        try:
            d = datetime.strptime(h.strip(), '%Y-%m-%d')
            if d.strftime('%Y-%m') == month:
                cols.append(h)
        except:
            pass
    return cols

def range_cols(headers, start_date=None, end_date=None, month=None):
    """从表头找出属于指定范围或月份的日期列"""
    from datetime import date as date_cls
    sd = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
    ed = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
    cols = []
    for h in headers:
        try:
            d = datetime.strptime(h.strip(), '%Y-%m-%d').date()
            if sd and ed:
                if sd <= d <= ed:
                    cols.append(h)
            elif month:
                if d.strftime('%Y-%m') == month:
                    cols.append(h)
        except:
            pass
    return cols

def aggregate(rows, headers, month=None, start_date=None, end_date=None):
    """对每个指标，按月/周汇总（求和或求均值视指标而定）"""
    cols = range_cols(headers, start_date, end_date, month)
    if not cols:
        return None

    # 需要求和的指标关键词
    SUM_KEYWORDS = ['总收入', '推广成本', '安装次数', '广告展示次数', '广告点击次数',
                    '观看广告次数', '观看广告用户数', '付费用户数', '付费次数']
    # 其余指标求均值（ROI, CPI, eCPM, CTR, CPC）

    result = {}
    for r in rows:
        metric = r.get('分析指标', '').strip()
        if not metric:
            continue
        vals = [parse_num(r.get(c)) for c in cols if parse_num(r.get(c)) is not None]
        if not vals:
            result[metric] = None
            continue

        is_sum = any(kw in metric for kw in SUM_KEYWORDS)
        if is_sum:
            result[metric] = round(sum(vals), 2)
        else:
            result[metric] = round(sum(vals) / len(vals), 4)

    return {'days': len(cols), 'metrics': result}

def pct_change(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100, 1)

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

    sd, ed = args.start_date, args.end_date
    psd, ped = args.prev_start_date, args.prev_end_date

    with open(args.file, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        rows = list(reader)

    cur = aggregate(rows, headers, month=args.month, start_date=sd, end_date=ed)
    result = {'month': args.month, 'current': cur}

    if args.prev_month or psd:
        prev = aggregate(rows, headers, month=args.prev_month, start_date=psd, end_date=ped)
        result['prev_month'] = args.prev_month
        result['previous'] = prev
        if cur and prev and cur.get('metrics') and prev.get('metrics'):
            change = {}
            for metric in cur['metrics']:
                cv = cur['metrics'].get(metric)
                pv = prev['metrics'].get(metric)
                change[metric] = pct_change(cv, pv)
            result['change'] = change

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f'已输出到 {args.output}')
    else:
        print(out)

if __name__ == '__main__':
    main()
