"""
parse_spin.py
聚合「spin数据总览」CSV，输出各机台月度 spin 量/用户数排名 + 环比 + 每日趋势（用于新机台分析）。

字段：时间, 机台名称, spin次数, spin人数, 人均spin次数, 人均下注额, 消耗金币

用法：
    python parse_spin.py --file <csv路径> --month 2026-02 [--prev-month 2026-01] [--top 10] [--daily 机台名称]
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
    try: return float(str(s).strip().replace(',', ''))
    except: return 0.0

def aggregate_by_slot(rows, month=None, start_date=None, end_date=None):
    slot_data = defaultdict(lambda: {'spin': 0.0, 'users': 0.0, 'gold': 0.0, 'bet_sum': 0.0, 'days': 0})
    for r in rows:
        if not date_in_range(r.get('时间', ''), start_date, end_date, month):
            continue
        name = r.get('机台名称', '').strip()
        spin = parse_num(r.get('spin次数', 0))
        users = parse_num(r.get('spin人数', 0))
        gold = parse_num(r.get('消耗金币', 0))
        bet = parse_num(r.get('人均下注额', 0))
        if spin > 0:
            slot_data[name]['days'] += 1
        slot_data[name]['spin'] += spin
        slot_data[name]['users'] += users
        slot_data[name]['gold'] += gold
        if users > 0:
            slot_data[name]['bet_sum'] += bet * users  # 加权求和

    result = {}
    for name, d in slot_data.items():
        if d['spin'] == 0:
            continue
        result[name] = {
            'spin': int(d['spin']),
            'users': int(d['users']),
            'avg_spin_per_user': round(d['spin'] / d['users'], 1) if d['users'] > 0 else 0,
            'gold': int(d['gold']),
            'avg_bet': round(d['bet_sum'] / d['users'], 0) if d['users'] > 0 else 0,
            'active_days': d['days']
        }
    return dict(sorted(result.items(), key=lambda x: -x[1]['spin']))

def get_daily(rows, month=None, slot_name=None, start_date=None, end_date=None):
    """获取指定机台的每日数据，用于新机台爬坡曲线分析"""
    daily = []
    for r in rows:
        if not date_in_range(r.get('时间', ''), start_date, end_date, month):
            continue
        if r.get('机台名称', '').strip() != slot_name:
            continue
        daily.append({
            'date': r.get('时间', '').strip(),
            'spin': int(parse_num(r.get('spin次数', 0))),
            'users': int(parse_num(r.get('spin人数', 0))),
            'avg_bet': round(parse_num(r.get('人均下注额', 0)), 0)
        })
    return sorted(daily, key=lambda x: x['date'])

def pct_change(cur, prev):
    if prev is None or prev == 0:
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
    parser.add_argument('--top', type=int, default=10)
    parser.add_argument('--daily', nargs='*', help='需要输出每日趋势的机台名称列表')
    parser.add_argument('--output')
    args = parser.parse_args()

    sd, ed = args.start_date, args.end_date
    psd, ped = args.prev_start_date, args.prev_end_date

    with open(args.file, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    cur = aggregate_by_slot(rows, month=args.month, start_date=sd, end_date=ed)
    result = {'month': args.month, 'top': args.top}

    # Top N 排名
    cur_top = dict(list(cur.items())[:args.top])
    result['current_top'] = cur_top

    if args.prev_month or psd:
        prev = aggregate_by_slot(rows, month=args.prev_month, start_date=psd, end_date=ped)
        result['prev_month'] = args.prev_month

        # 合并对比
        comparison = {}
        all_slots = set(list(cur.keys())[:args.top*2] + list(prev.keys())[:args.top*2])
        for slot in all_slots:
            c = cur.get(slot, {'spin': 0, 'users': 0})
            p = prev.get(slot, {'spin': 0, 'users': 0})
            if c['spin'] == 0 and p['spin'] == 0:
                continue
            comparison[slot] = {
                'spin': c['spin'], 'prev_spin': p['spin'],
                'spin_chg': pct_change(c['spin'], p['spin']),
                'users': c['users'], 'prev_users': p['users'],
                'users_chg': pct_change(c['users'], p['users'])
            }
        result['comparison'] = dict(sorted(comparison.items(), key=lambda x: -x[1]['spin'])[:args.top*2])

        # 本月新上线（上月无数据）
        result['new_slots'] = [s for s in cur if s not in prev or prev[s]['spin'] == 0]
        # 逆势增长（上月有数据且本月提升>20%）
        result['growing_slots'] = [
            s for s in cur
            if s in prev and prev[s]['spin'] > 0
            and pct_change(cur[s]['spin'], prev[s]['spin']) is not None
            and pct_change(cur[s]['spin'], prev[s]['spin']) > 20
        ]
        # 大幅下滑（下滑>30%）
        result['declining_slots'] = [
            s for s in prev
            if prev[s]['spin'] > 0
            and (s not in cur or pct_change(cur.get(s, {'spin': 0})['spin'], prev[s]['spin']) is not None
                 and pct_change(cur.get(s, {'spin': 0})['spin'], prev[s]['spin']) < -30)
        ]

    # 每日趋势（新机台用）
    if args.daily:
        result['daily_trends'] = {}
        for slot_name in args.daily:
            result['daily_trends'][slot_name] = get_daily(rows, month=args.month, slot_name=slot_name, start_date=sd, end_date=ed)

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f'已输出到 {args.output}')
    else:
        print(out)

if __name__ == '__main__':
    main()
