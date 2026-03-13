"""
parse_big_r.py
解析「大R用户明细」CSV，输出付费排行、活跃状态分布、异动标注。

CSV 结构：
  #account_id, 注册时间, r_level, country, 登录天数, 付费天数,
  总付费, 最大付费, 最后付费点位, 最后付费日期, 最后登录日期, 流失天数

用法：
    python parse_big_r.py --file <csv路径> --month 2026-02 [--top 10] [--output <输出路径>]
"""
import csv, json, argparse
from datetime import datetime, timedelta
from collections import defaultdict


def parse_num(s):
    s = str(s).strip().replace(',', '')
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def parse_date(s):
    s = str(s).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True)
    parser.add_argument('--month', help='YYYY-MM（月报模式）')
    parser.add_argument('--start-date', help='YYYY-MM-DD（周报模式）')
    parser.add_argument('--end-date', help='YYYY-MM-DD（周报模式）')
    parser.add_argument('--top', type=int, default=10)
    parser.add_argument('--output')
    args = parser.parse_args()

    if args.start_date and args.end_date:
        month_start = datetime.strptime(args.start_date, '%Y-%m-%d')
        month_end   = datetime.strptime(args.end_date,   '%Y-%m-%d')
    elif args.month:
        month_start = datetime.strptime(args.month + '-01', '%Y-%m-%d')
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1) - timedelta(days=1)
    else:
        raise ValueError('必须提供 --month 或 --start-date + --end-date')

    with open(args.file, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    users = []
    for r in rows:
        uid = r.get('#account_id', '').strip()
        reg_time = parse_date(r.get('注册时间', ''))
        total_pay = parse_num(r.get('总付费', 0))
        max_pay = parse_num(r.get('最大付费', 0))
        login_days = int(parse_num(r.get('登录天数', 0)))
        pay_days = int(parse_num(r.get('付费天数', 0)))
        last_pay_date = parse_date(r.get('最后付费日期', ''))
        last_login_date = parse_date(r.get('最后登录日期', ''))
        churn_days = int(parse_num(r.get('流失天数', 0)))
        country = r.get('country', '').strip()
        r_level = r.get('r_level', '').strip()
        last_pay_loc = r.get('最后付费点位', '').strip()

        # 注册天数
        reg_days = (month_end - reg_time).days if reg_time else None

        # 本月是否活跃（最后登录在本月内，或流失天数 < 当月天数）
        active_in_month = False
        if last_login_date and last_login_date >= month_start:
            active_in_month = True

        # 本月是否付费（最后付费在本月内）
        paid_in_month = False
        if last_pay_date and last_pay_date >= month_start:
            paid_in_month = True

        users.append({
            'uid': uid,
            'reg_time': reg_time.strftime('%Y-%m-%d') if reg_time else None,
            'reg_days': reg_days,
            'r_level': r_level,
            'country': country,
            'login_days': login_days,
            'pay_days': pay_days,
            'total_pay': total_pay,
            'max_pay': max_pay,
            'last_pay_loc': last_pay_loc,
            'last_pay_date': last_pay_date.strftime('%Y-%m-%d') if last_pay_date else None,
            'last_login_date': last_login_date.strftime('%Y-%m-%d') if last_login_date else None,
            'churn_days': churn_days,
            'active_in_month': active_in_month,
            'paid_in_month': paid_in_month,
        })

    # 排序：总付费降序
    users.sort(key=lambda x: -x['total_pay'])

    # Top N
    top_users = users[:args.top]

    # 统计
    total_users = len(users)
    active_users = [u for u in users if u['active_in_month']]
    paid_users = [u for u in users if u['paid_in_month']]
    churned_users = [u for u in users if not u['active_in_month']]

    # 付费总额分布
    pay_buckets = {'$0-100': 0, '$100-500': 0, '$500-1000': 0, '$1000-5000': 0, '$5000+': 0}
    for u in users:
        p = u['total_pay']
        if p < 100:
            pay_buckets['$0-100'] += 1
        elif p < 500:
            pay_buckets['$100-500'] += 1
        elif p < 1000:
            pay_buckets['$500-1000'] += 1
        elif p < 5000:
            pay_buckets['$1000-5000'] += 1
        else:
            pay_buckets['$5000+'] += 1

    # 注册月份分布
    reg_month_dist = defaultdict(int)
    for u in users:
        if u['reg_time']:
            rm = u['reg_time'][:7]
            reg_month_dist[rm] += 1

    # 异动标注
    alerts = []
    # 大R流失（总付费 > 1000 且本月不活跃）
    for u in users:
        if u['total_pay'] >= 1000 and not u['active_in_month']:
            alerts.append({
                'type': 'big_r_churned',
                'uid': u['uid'],
                'total_pay': u['total_pay'],
                'last_login': u['last_login_date'],
                'reg_time': u['reg_time'],
            })
    # 新注册大R（本月注册且总付费 > 100）
    for u in users:
        reg_in_period = (args.month and u['reg_time'] and u['reg_time'][:7] == args.month) or \
                        (args.start_date and u['reg_time'] and args.start_date <= u['reg_time'] <= args.end_date)
        if reg_in_period and u['total_pay'] >= 100:
            alerts.append({
                'type': 'new_big_r',
                'uid': u['uid'],
                'total_pay': u['total_pay'],
                'reg_time': u['reg_time'],
                'pay_days': u['pay_days'],
            })

    period_label = args.month or f"{args.start_date}~{args.end_date}"
    result = {
        'month': period_label,
        'total_historical_payers': total_users,
        'active_in_month': len(active_users),
        'paid_in_month': len(paid_users),
        'churned': len(churned_users),
        'active_rate': round(len(active_users) / total_users * 100, 1) if total_users > 0 else 0,
        'total_ltv': round(sum(u['total_pay'] for u in users), 2),
        'top_users': [{
            'uid': u['uid'],
            'total_pay': u['total_pay'],
            'max_pay': u['max_pay'],
            'reg_time': u['reg_time'],
            'reg_days': u['reg_days'],
            'login_days': u['login_days'],
            'pay_days': u['pay_days'],
            'last_pay_date': u['last_pay_date'],
            'last_pay_loc': u['last_pay_loc'],
            'active_in_month': u['active_in_month'],
            'paid_in_month': u['paid_in_month'],
            'country': u['country'],
        } for u in top_users],
        'pay_distribution': pay_buckets,
        'reg_month_distribution': dict(sorted(reg_month_dist.items())),
        'alerts': alerts[:20],  # 最多20条
    }

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f'已输出到 {args.output}')
    else:
        print(out)


if __name__ == '__main__':
    main()
