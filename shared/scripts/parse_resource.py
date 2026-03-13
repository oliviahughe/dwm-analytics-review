"""
parse_resource.py
聚合「付费用户资源监控」CSV，输出钻石消耗/发放各场景汇总 + 环比。

支持两种 CSV 格式（自动检测）：

1. 日期对比格式（iOS，文件名含 "_日期对比"）：
   列 [0] = 原因（场景名）
   列 [1] = 原始时间（YYYY-MM-DD，即当期日期）
   列 [2..N] = 当期指标（消耗钻石总和, 消耗钻石人数, 发放钻石总和, 消耗钻石中位数...）
   列 [对比时间1] = 分隔符（区分当期/对比期）
   列 [对比时间1+1..end] = 对比期指标（与当期同名列）
   可选 --start-date/--end-date 过滤 原始时间；不传则汇总 CSV 全部行。

2. 全量宽表格式（安卓，列头含 YYYY-MM-DD）：
   列 [0] = 原因（场景名）
   列 [1] = 总付费金额（R 层级，如 0~100 / 100~500 / 500~+∞）
   列 [2] = 分析指标（消耗钻石总和 / 消耗钻石人数 / 发放钻石总和...）
   列 [3] = 阶段汇总（全量合计，忽略）
   列 [4+] = 每日数值（2026-02-07, 2026-02-08, ...）
   必须配合 --start-date/--end-date（当期）使用，
   --prev-start-date/--prev-end-date 为可选对比期。

用法：
    # iOS（日期对比，日期可不传）
    python parse_resource.py --file <csv路径> [--start-date YYYY-MM-DD --end-date YYYY-MM-DD]

    # Android（宽表，必须传日期）
    python parse_resource.py --file <csv路径> \\
        --start-date 2026-03-01 --end-date 2026-03-07 \\
        --prev-start-date 2026-02-22 --prev-end-date 2026-02-28
"""
import csv, json, argparse, re, sys
from collections import defaultdict


def log(msg):
    """INFO/WARN 日志输出到 stderr，保持 stdout 只含 JSON"""
    print(msg, file=sys.stderr)


# ─────────────────────────── 工具函数 ───────────────────────────

def parse_num(s):
    s = str(s).strip().replace(',', '')
    if s in ('-', '', '—'):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def pct_change(cur, prev):
    if prev is None or prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100, 1)


def find_col_index(headers, keyword, start=0):
    """从 start 位置开始找含 keyword 的列索引列表"""
    return [i for i, h in enumerate(headers) if i >= start and keyword in h]


def is_wide_format(headers):
    """检测是否为宽表格式：列头中存在 YYYY-MM-DD 格式的日期列"""
    date_re = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    return any(date_re.match(h.strip()) for h in headers)


# ─────────────────────────── 结果构建 ───────────────────────────

def build_result(consume_by_scene, distribute_by_scene):
    """将 (scene→tier→metrics) 结构转换为标准输出 JSON"""

    def make_consume_entry(tiers):
        total_cur  = sum(t['cur']  for t in tiers.values())
        total_prev = sum(t['prev'] for t in tiers.values())
        u_cur  = sum(t.get('users_cur',  0) for t in tiers.values())
        u_prev = sum(t.get('users_prev', 0) for t in tiers.values())
        mc_sum = sum(t.get('median_cur',  0) for t in tiers.values())
        mc_cnt = sum(t.get('median_count', 0) for t in tiers.values())
        mp_sum = sum(t.get('median_prev', 0) for t in tiers.values())
        mp_cnt = sum(t.get('median_count_prev', 0) for t in tiers.values())
        median_cur  = round(mc_sum / mc_cnt, 1) if mc_cnt > 0 else 0
        median_prev = round(mp_sum / mp_cnt, 1) if mp_cnt > 0 else 0

        entry = {
            'consume':      int(total_cur),
            'prev_consume': int(total_prev),
            'consume_chg':  pct_change(total_cur, total_prev),
            'users':        int(u_cur),
            'prev_users':   int(u_prev),
            'users_chg':    pct_change(u_cur, u_prev),
            'median':       median_cur,
            'prev_median':  median_prev,
            'median_chg':   pct_change(median_cur, median_prev) if median_cur and median_prev else None,
        }
        by_tier = {}
        for tier_name, t in sorted(tiers.items()):
            t_mc = round(t.get('median_cur', 0) / t['median_count'], 1) if t.get('median_count', 0) > 0 else 0
            t_mp = round(t.get('median_prev', 0) / t.get('median_count_prev', 1), 1) if t.get('median_count_prev', 0) > 0 else 0
            by_tier[tier_name] = {
                'consume':      int(t['cur']),
                'prev_consume': int(t['prev']),
                'consume_chg':  pct_change(t['cur'], t['prev']),
                'users':        int(t.get('users_cur', 0)),
                'prev_users':   int(t.get('users_prev', 0)),
                'median':       t_mc,
                'prev_median':  t_mp,
            }
        entry['by_tier'] = by_tier
        return entry

    consume_result = {
        scene: make_consume_entry(tiers)
        for scene, tiers in consume_by_scene.items()
    }

    distribute_result = {}
    for scene, tiers in distribute_by_scene.items():
        total_cur  = sum(t['cur']  for t in tiers.values())
        total_prev = sum(t['prev'] for t in tiers.values())
        entry = {
            'distribute':      int(total_cur),
            'prev_distribute': int(total_prev),
            'distribute_chg':  pct_change(total_cur, total_prev),
        }
        by_tier = {}
        for tier_name, t in sorted(tiers.items()):
            by_tier[tier_name] = {
                'distribute':      int(t['cur']),
                'prev_distribute': int(t['prev']),
                'distribute_chg':  pct_change(t['cur'], t['prev']),
            }
        entry['by_tier'] = by_tier
        distribute_result[scene] = entry

    tc_cur  = sum(v['consume']  for v in consume_result.values())
    tc_prev = sum(v['prev_consume'] for v in consume_result.values())
    td_cur  = sum(v['distribute']  for v in distribute_result.values())
    td_prev = sum(v['prev_distribute'] for v in distribute_result.values())

    return {
        'consume': {
            'total':      tc_cur,
            'prev_total': tc_prev,
            'total_chg':  pct_change(tc_cur, tc_prev),
            'by_scene':   dict(sorted(consume_result.items(),   key=lambda x: -x[1]['consume'])),
        },
        'distribute': {
            'total':      td_cur,
            'prev_total': td_prev,
            'total_chg':  pct_change(td_cur, td_prev),
            'by_channel': dict(sorted(distribute_result.items(), key=lambda x: -x[1]['distribute'])),
        },
        'net_consume':      tc_cur  - td_cur,
        'prev_net_consume': tc_prev - td_prev,
        'net_consume_chg':  pct_change(tc_cur - td_cur, tc_prev - td_prev),
    }


# ────────────────────── 日期对比格式解析（iOS） ──────────────────────

def parse_date_compare_format(headers, rows, start_date, end_date):
    """
    解析 iOS 日期对比格式。
    每行 = 一个 (场景, 当期日期) 的指标对，右半部分为对比期指标。
    可选 start_date/end_date 过滤 原始时间 列。
    """
    # 找 对比时间1 列（分隔当期/对比期）
    compare_col = None
    for i, h in enumerate(headers):
        if '对比时间' in h:
            compare_col = i
            break
    if compare_col is None:
        log('[WARN] 未找到"对比时间"列，尝试 fallback（按列数等分）')
        compare_col = len(headers) // 2

    def split_cur_prev(indices):
        cur  = [i for i in indices if i < compare_col]
        prev = [i for i in indices if i > compare_col]
        return (cur[0] if cur else None, prev[0] if prev else None)

    c_total_cur,  c_total_prev  = split_cur_prev(find_col_index(headers, '消耗钻石总和'))
    c_users_cur,  c_users_prev  = split_cur_prev(find_col_index(headers, '消耗钻石人数'))
    d_total_cur,  d_total_prev  = split_cur_prev(find_col_index(headers, '发放钻石总和'))
    c_median_cur, c_median_prev = split_cur_prev(find_col_index(headers, '消耗钻石中位数'))

    # 原始时间列（用于可选日期过滤）
    time_col = next((i for i, h in enumerate(headers) if '原始时间' in h), None)

    consume_by_scene    = defaultdict(lambda: defaultdict(lambda: {
        'cur': 0, 'prev': 0, 'users_cur': 0, 'users_prev': 0,
        'median_cur': 0, 'median_prev': 0, 'median_count': 0, 'median_count_prev': 0
    }))
    distribute_by_scene = defaultdict(lambda: defaultdict(lambda: {'cur': 0, 'prev': 0}))

    for r in rows:
        if len(r) < 3:
            continue
        reason = r[0].strip()
        if not reason:
            continue

        # 可选：按 原始时间 过滤到目标日期区间
        if start_date and time_col is not None and time_col < len(r):
            row_date = r[time_col].strip()
            if not (start_date <= row_date <= end_date):
                continue

        # iOS 日期对比格式无 R 层级，统一用 'all'
        tier = 'all'

        cc = parse_num(r[c_total_cur])  if c_total_cur  is not None and c_total_cur  < len(r) else 0
        cp = parse_num(r[c_total_prev]) if c_total_prev is not None and c_total_prev < len(r) else 0
        uc = parse_num(r[c_users_cur])  if c_users_cur  is not None and c_users_cur  < len(r) else 0
        up = parse_num(r[c_users_prev]) if c_users_prev is not None and c_users_prev < len(r) else 0
        mc = parse_num(r[c_median_cur]) if c_median_cur is not None and c_median_cur < len(r) else 0
        mp = parse_num(r[c_median_prev])if c_median_prev is not None and c_median_prev < len(r) else 0

        if cc > 0 or cp > 0:
            d = consume_by_scene[reason][tier]
            d['cur']  += cc;  d['prev'] += cp
            d['users_cur'] += uc; d['users_prev'] += up
            if mc > 0: d['median_cur'] += mc * uc; d['median_count'] += uc
            if mp > 0: d['median_prev'] += mp * up; d['median_count_prev'] += up

        dc = parse_num(r[d_total_cur])  if d_total_cur  is not None and d_total_cur  < len(r) else 0
        dp = parse_num(r[d_total_prev]) if d_total_prev is not None and d_total_prev < len(r) else 0
        if dc > 0 or dp > 0:
            distribute_by_scene[reason][tier]['cur']  += dc
            distribute_by_scene[reason][tier]['prev'] += dp

    return consume_by_scene, distribute_by_scene


# ────────────────────── 宽表格式解析（安卓） ──────────────────────

def parse_wide_format(headers, rows, start_date, end_date, prev_start_date, prev_end_date):
    """
    解析安卓全量宽表格式。
    行 = (场景, R层级, 指标类型)，列 = 每日日期。
    通过 start_date/end_date 汇总当期，prev_* 汇总对比期。
    """
    if not start_date or not end_date:
        log('[ERROR] 宽表格式必须传 --start-date/--end-date，无法汇总当期数据')
        return (defaultdict(lambda: defaultdict(dict)),
                defaultdict(lambda: defaultdict(dict)))

    date_re = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    date_cols = [(i, h.strip()) for i, h in enumerate(headers) if date_re.match(h.strip())]

    cur_cols  = [i for i, d in date_cols if start_date <= d <= end_date]
    prev_cols = ([i for i, d in date_cols if prev_start_date <= d <= prev_end_date]
                 if prev_start_date and prev_end_date else [])

    if not cur_cols:
        log(f'[WARN] 宽表：未在列头找到当期日期范围 {start_date}~{end_date}')
        log(f'  列头日期范围: {date_cols[0][1] if date_cols else "无"} ~ {date_cols[-1][1] if date_cols else "无"}')

    # COL 0=原因, 1=总付费金额(R层), 2=分析指标, 3=阶段汇总, 4+=日期
    consume_by_scene    = defaultdict(lambda: defaultdict(lambda: {
        'cur': 0, 'prev': 0, 'users_cur': 0, 'users_prev': 0,
        'median_cur': 0, 'median_prev': 0, 'median_count': 0, 'median_count_prev': 0
    }))
    distribute_by_scene = defaultdict(lambda: defaultdict(lambda: {'cur': 0, 'prev': 0}))

    for row in rows:
        if len(row) < 4:
            continue
        scene  = row[0].strip()
        tier   = row[1].strip()   # R 层级，如 0~100
        metric = row[2].strip()   # 分析指标名
        if not scene:
            continue

        cur_val  = sum(parse_num(row[i]) for i in cur_cols  if i < len(row))
        prev_val = sum(parse_num(row[i]) for i in prev_cols if i < len(row))

        if '消耗钻石总和' in metric:
            d = consume_by_scene[scene][tier]
            d['cur'] += cur_val; d['prev'] += prev_val
        elif '消耗钻石人数' in metric:
            d = consume_by_scene[scene][tier]
            d['users_cur'] += cur_val; d['users_prev'] += prev_val
        elif '发放钻石总和' in metric:
            distribute_by_scene[scene][tier]['cur']  += cur_val
            distribute_by_scene[scene][tier]['prev'] += prev_val

    return consume_by_scene, distribute_by_scene


# ────────────────────────────── main ──────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file',            required=True,  help='CSV 文件路径')
    parser.add_argument('--output',                          help='输出 JSON 路径（不传则 stdout）')
    parser.add_argument('--start-date',      default=None,   help='当期起始 YYYY-MM-DD')
    parser.add_argument('--end-date',        default=None,   help='当期结束 YYYY-MM-DD')
    parser.add_argument('--prev-start-date', default=None,   help='对比期起始 YYYY-MM-DD')
    parser.add_argument('--prev-end-date',   default=None,   help='对比期结束 YYYY-MM-DD')
    args = parser.parse_args()

    with open(args.file, encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)

    # 格式自动检测
    if is_wide_format(headers):
        log(f'[INFO] 格式=宽表（安卓）  当期={args.start_date}~{args.end_date}'
            f'  对比期={args.prev_start_date}~{args.prev_end_date}')
        consume_by_scene, distribute_by_scene = parse_wide_format(
            headers, rows,
            args.start_date, args.end_date,
            args.prev_start_date, args.prev_end_date,
        )
        fmt = 'wide'
    else:
        log(f'[INFO] 格式=日期对比（iOS）  日期过滤={args.start_date}~{args.end_date}')
        consume_by_scene, distribute_by_scene = parse_date_compare_format(
            headers, rows, args.start_date, args.end_date
        )
        fmt = 'date_compare'

    result = build_result(consume_by_scene, distribute_by_scene)
    result['detected_format'] = fmt

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(out)
        log(f'已输出到 {args.output}')
    else:
        print(out)


if __name__ == '__main__':
    main()
