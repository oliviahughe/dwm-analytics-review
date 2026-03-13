"""
parse_iap.py
聚合「内购数据_分点位_分付费用户标签」CSV，输出各点位月度汇总 + 环比。

字段：时间, 项目位置, 总付费金额(层级), 付费总金额, 付费总次数, 付费总用户数, ARPPU

用法：
    python parse_iap.py --file <csv路径> --month 2026-02 [--prev-month 2026-01]
"""
import csv, json, argparse
from datetime import datetime
from collections import defaultdict

def month_of(date_str):
    try: return datetime.strptime(date_str.strip(), '%Y-%m-%d').strftime('%Y-%m')
    except: return None

def date_in_range(date_str, start_date=None, end_date=None, month=None):
    """支持两种模式：date range 或 month 前缀"""
    s = str(date_str).strip()
    if '(' in s: s = s[:s.index('(')]
    if '（' in s: s = s[:s.index('（')]
    try:
        d = datetime.strptime(s.strip(), '%Y-%m-%d').date()
    except:
        return False
    if start_date and end_date:
        sd = datetime.strptime(start_date, '%Y-%m-%d').date()
        ed = datetime.strptime(end_date, '%Y-%m-%d').date()
        return sd <= d <= ed
    if month:
        return s.strip().startswith(month)
    return False

def parse_num(s):
    s = str(s).strip().replace(',', '')
    try: return float(s)
    except: return 0.0

def aggregate_by_location(rows, month):
    """按点位聚合，忽略层级细分（层级数据保留在 by_tier）"""
    loc_data = defaultdict(lambda: {'rev': 0, 'cnt': 0, 'users': set_proxy()})
    tier_data = defaultdict(lambda: {'rev': 0, 'users': 0})
    total = {'rev': 0, 'cnt': 0}

    for r in rows:
        if month_of(r.get('时间', '')) != month:
            continue
        loc = r.get('项目位置', '').strip()
        tier = r.get('总付费金额', '').strip()
        if loc in ('false', '', 'null'):
            continue
        rev = parse_num(r.get('付费总金额', 0))
        cnt = parse_num(r.get('付费总次数', 0))
        users = parse_num(r.get('付费总用户数', 0))

        loc_data[loc]['rev'] += rev
        loc_data[loc]['cnt'] += cnt
        loc_data[loc]['users'] += users

        tier_data[tier]['rev'] += rev
        tier_data[tier]['users'] += users

        total['rev'] += rev
        total['cnt'] += cnt

    # 去重：同一用户在多个层级可能被重复计，取 max 近似
    result_loc = {}
    for loc, d in loc_data.items():
        arppu = round(d['rev'] / d['users'], 2) if d['users'] > 0 else 0
        result_loc[loc] = {
            'rev': round(d['rev'], 2),
            'cnt': int(d['cnt']),
            'users': int(d['users']),
            'arppu': arppu
        }

    result_tier = {}
    for tier, d in tier_data.items():
        arppu = round(d['rev'] / d['users'], 2) if d['users'] > 0 else 0
        result_tier[tier] = {
            'rev': round(d['rev'], 2),
            'users': int(d['users']),
            'arppu': arppu,
            'rev_pct': round(d['rev'] / total['rev'] * 100, 1) if total['rev'] > 0 else 0
        }

    return {
        'total_rev': round(total['rev'], 2),
        'total_cnt': int(total['cnt']),
        'by_location': dict(sorted(result_loc.items(), key=lambda x: -x[1]['rev'])),
        'by_tier': result_tier
    }

def set_proxy():
    """用 float 累加代替 set，因为用户数已是聚合值"""
    return 0.0

# 修正：直接用累加而非 set
def aggregate_by_location(rows, month=None, start_date=None, end_date=None):
    loc_data = defaultdict(lambda: {'rev': 0.0, 'cnt': 0.0, 'users': 0.0})
    tier_data = defaultdict(lambda: {'rev': 0.0, 'users': 0.0})
    total = {'rev': 0.0, 'cnt': 0.0}

    for r in rows:
        if not date_in_range(r.get('时间', ''), start_date, end_date, month):
            continue
        loc = r.get('项目位置', '').strip()
        tier = r.get('总付费金额', '').strip()
        if loc in ('false', '', 'null'):
            continue
        rev = parse_num(r.get('付费总金额', 0))
        cnt = parse_num(r.get('付费总次数', 0))
        users = parse_num(r.get('付费总用户数', 0))

        loc_data[loc]['rev'] += rev
        loc_data[loc]['cnt'] += cnt
        loc_data[loc]['users'] += users
        tier_data[tier]['rev'] += rev
        tier_data[tier]['users'] += users
        total['rev'] += rev
        total['cnt'] += cnt

    result_loc = {}
    for loc, d in loc_data.items():
        if d['rev'] == 0 and d['users'] == 0:
            continue
        result_loc[loc] = {
            'rev': round(d['rev'], 2),
            'cnt': int(d['cnt']),
            'users': int(d['users']),
            'arppu': round(d['rev'] / d['users'], 2) if d['users'] > 0 else 0
        }

    result_tier = {}
    for tier, d in tier_data.items():
        if d['rev'] == 0:
            continue
        result_tier[tier] = {
            'rev': round(d['rev'], 2),
            'users': int(d['users']),
            'arppu': round(d['rev'] / d['users'], 2) if d['users'] > 0 else 0,
            'rev_pct': round(d['rev'] / total['rev'] * 100, 1) if total['rev'] > 0 else 0
        }

    return {
        'total_rev': round(total['rev'], 2),
        'total_cnt': int(total['cnt']),
        'by_location': dict(sorted(result_loc.items(), key=lambda x: -x[1]['rev'])),
        'by_tier': result_tier
    }

def pct_change(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100, 1)

def compare(cur_loc, prev_loc):
    """为每个点位计算环比"""
    result = {}
    all_locs = set(list(cur_loc.keys()) + list(prev_loc.keys()))
    for loc in all_locs:
        c = cur_loc.get(loc, {'rev': 0, 'cnt': 0, 'users': 0, 'arppu': 0})
        p = prev_loc.get(loc, {'rev': 0, 'cnt': 0, 'users': 0, 'arppu': 0})
        if c['rev'] == 0 and p['rev'] == 0:
            continue
        result[loc] = {
            'rev': c['rev'], 'prev_rev': p['rev'],
            'rev_chg': pct_change(c['rev'], p['rev']),
            'users': c['users'], 'prev_users': p['users'],
            'users_chg': pct_change(c['users'], p['users']),
            'arppu': c['arppu'], 'prev_arppu': p['arppu'],
            'arppu_chg': pct_change(c['arppu'], p['arppu'])
        }
    return dict(sorted(result.items(), key=lambda x: -x[1]['rev']))

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
    parser.add_argument('--top', type=int, default=15, help='输出 Top N 点位')
    args = parser.parse_args()

    sd, ed = args.start_date, args.end_date
    psd, ped = args.prev_start_date, args.prev_end_date

    with open(args.file, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    cur = aggregate_by_location(rows, month=args.month, start_date=sd, end_date=ed)
    result = {'month': args.month, 'current': cur}

    if args.prev_month or psd:
        prev = aggregate_by_location(rows, month=args.prev_month, start_date=psd, end_date=ped)
        result['prev_month'] = args.prev_month
        result['previous'] = prev
        result['comparison'] = compare(cur['by_location'], prev['by_location'])
        result['total_rev_chg'] = pct_change(cur['total_rev'], prev['total_rev'])
        result['total_cnt_chg'] = pct_change(cur['total_cnt'], prev['total_cnt'])

        # 层级环比
        tier_cmp = {}
        for tier in set(list(cur['by_tier'].keys()) + list(prev['by_tier'].keys())):
            c = cur['by_tier'].get(tier, {'rev': 0, 'users': 0, 'arppu': 0})
            p = prev['by_tier'].get(tier, {'rev': 0, 'users': 0, 'arppu': 0})
            tier_cmp[tier] = {
                'rev': c['rev'], 'prev_rev': p['rev'], 'rev_chg': pct_change(c['rev'], p['rev']),
                'users': c['users'], 'prev_users': p['users'], 'users_chg': pct_change(c['users'], p['users']),
                'arppu': c['arppu'], 'prev_arppu': p['arppu'], 'arppu_chg': pct_change(c['arppu'], p['arppu']),
                'rev_pct': c.get('rev_pct', 0)
            }
        result['tier_comparison'] = tier_cmp

    # 截断 top N
    if 'comparison' in result:
        items = list(result['comparison'].items())[:args.top]
        result['comparison_top'] = dict(items)

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f'已输出到 {args.output}')
    else:
        print(out)

if __name__ == '__main__':
    main()
