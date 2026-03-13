"""
parse_basic.py
聚合「基础数据其二」CSV，输出月度汇总指标（iOS 或 安卓通用）。
可选整合「基础数据其一」CSV 中的补充字段（净收入、7留、活跃付费用户等）。

用法：
    python parse_basic.py --file <基础数据其二> --month 2026-02 [--prev-month 2026-01] [--file2 <基础数据其一>]

输出：JSON，包含本月均值/合计 + 环比变化
"""
import csv, json, sys, argparse
from datetime import datetime
from collections import defaultdict

def parse_pct(s):
    s = s.strip().replace('%', '')
    try: return float(s)
    except: return None

def parse_num(s):
    s = s.strip().replace(',', '').replace('$', '')
    try: return float(s)
    except: return None

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

def aggregate(rows, month=None, start_date=None, end_date=None):
    data = [r for r in rows if date_in_range(r.get('日期',''), start_date, end_date, month)]
    if not data:
        return None
    n = len(data)

    def avg(field):
        vals = [parse_num(r.get(field,'')) for r in data if parse_num(r.get(field,'')) is not None]
        return round(sum(vals)/len(vals), 2) if vals else None

    def total(field):
        vals = [parse_num(r.get(field,'')) for r in data if parse_num(r.get(field,'')) is not None]
        return round(sum(vals), 2) if vals else None

    def avg_pct(field):
        vals = [parse_pct(r.get(field,'')) for r in data if parse_pct(r.get(field,'')) is not None]
        return round(sum(vals)/len(vals), 2) if vals else None

    return {
        'days': n,
        'DAU': avg('DAU'),
        'DNU': avg('DNU'),
        'MAU': avg('MAU'),
        '自然安装量': total('自然安装量'),
        '推广安装量': total('推广安装量'),
        '注册转化率': avg_pct('注册转化率(%)'),
        '次留': avg_pct('次留(%)'),
        '总收入': total('总收入($)'),
        '内购收入': total('内购收入($)'),
        '内购ARPU': avg('内购ARPU($)'),
        '内购ARPPU': avg('内购ARPPU($)'),
        '付费用户数': avg('付费用户数'),
        '付费率': avg_pct('付费率(%)'),
        '广告收入': total('广告收入($)'),
        '广告ARPU': avg('广告ARPU($)'),
        '人均广告次数': avg('人均广告次数'),
        '广告渗透率': avg_pct('广告渗透率(%)'),
        '推广成本': total('推广成本($)'),
        '趣运利润': total('趣运利润($)'),
        '破产率': avg_pct('破产率(%)'),
    }

def pct_change(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100, 1)

def month_of_file1(date_str):
    """解析基础数据其一的日期格式，如 '2026-01-01(四)' 或 '2026-01-01'"""
    s = str(date_str).strip()
    # 去掉括号及之后内容
    if '(' in s:
        s = s[:s.index('(')]
    if '（' in s:
        s = s[:s.index('（')]
    return month_of(s.strip())


def aggregate_file1(rows, month=None, start_date=None, end_date=None):
    """聚合基础数据其一的补充字段。
    日期列可能叫「时间」或「日期」，日期格式可能带星期后缀如 '2026-01-01(四)'。
    可能包含：净收入、7留、8-7留、9-7留、活跃付费用户、DNU月均值、DAU月均值 等。
    最后一行可能是"阶段值"汇总行，需要排除。
    """
    # 自动找日期列
    date_col = None
    if rows:
        for col in ['日期', '时间', 'date']:
            if col in rows[0]:
                date_col = col
                break
    if not date_col:
        return {}

    # 过滤：排除非日期行（如"阶段值"）和不匹配月份/范围的行
    data = []
    for r in rows:
        date_val = r.get(date_col, '').strip()
        if not date_val or date_val in ('阶段值', '合计', 'total'):
            continue
        if date_in_range(date_val, start_date, end_date, month):
            data.append(r)

    if not data:
        return {}

    headers = list(data[0].keys())
    result = {}

    # 尝试提取各字段（avg for 率类/均值类，total for 量类/收入类）
    rate_keywords = ['留', '率', '转化']
    total_keywords = ['收入', '净收入', '安装']
    avg_keywords = ['均值', 'ARPU', 'ARPPU', '用户']

    for h in headers:
        if h == date_col:
            continue
        is_rate = any(kw in h for kw in rate_keywords)
        is_total = any(kw in h for kw in total_keywords)

        vals = []
        for r in data:
            v = r.get(h, '').strip().replace('%', '').replace(',', '').replace('$', '')
            try:
                vals.append(float(v))
            except (ValueError, TypeError):
                pass

        if not vals:
            continue

        key = h.strip()
        if is_rate:
            result[key] = round(sum(vals) / len(vals), 2)
        elif is_total:
            result[key] = round(sum(vals), 2)
        else:
            # 默认取均值
            result[key] = round(sum(vals) / len(vals), 2)

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True, help='基础数据其二 CSV')
    parser.add_argument('--file2', help='基础数据其一 CSV（可选，补充净收入/7留等）')
    parser.add_argument('--month', help='本月，格式 YYYY-MM，如 2026-02')
    parser.add_argument('--prev-month', help='上月，格式 YYYY-MM，如 2026-01')
    parser.add_argument('--start-date', help='起始日期 YYYY-MM-DD（周报模式）')
    parser.add_argument('--end-date', help='结束日期 YYYY-MM-DD（周报模式）')
    parser.add_argument('--prev-start-date', help='上周起始日期 YYYY-MM-DD')
    parser.add_argument('--prev-end-date', help='上周结束日期 YYYY-MM-DD')
    parser.add_argument('--output', help='输出 JSON 路径，不指定则打印到 stdout')
    args = parser.parse_args()

    sd, ed = args.start_date, args.end_date
    psd, ped = args.prev_start_date, args.prev_end_date

    with open(args.file, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    cur = aggregate(rows, month=args.month, start_date=sd, end_date=ed)
    prev = aggregate(rows, month=args.prev_month, start_date=psd, end_date=ped) if (args.prev_month or psd) else None

    result = {'month': args.month, 'current': cur}
    if prev:
        result['prev_month'] = args.prev_month
        result['previous'] = prev
        result['change'] = {k: pct_change(cur.get(k), prev.get(k)) for k in cur if isinstance(cur.get(k), (int, float))}

    # 整合基础数据其一的补充字段
    if args.file2:
        try:
            with open(args.file2, encoding='utf-8-sig') as f:
                rows2 = list(csv.DictReader(f))
            supplement_cur = aggregate_file1(rows2, month=args.month, start_date=sd, end_date=ed)
            supplement_prev = aggregate_file1(rows2, month=args.prev_month, start_date=psd, end_date=ped) if (args.prev_month or psd) else {}

            if supplement_cur:
                result['supplement'] = supplement_cur
            if supplement_prev:
                result['supplement_prev'] = supplement_prev
                # 计算补充字段环比
                supplement_change = {}
                for k in supplement_cur:
                    if isinstance(supplement_cur.get(k), (int, float)) and k in supplement_prev:
                        supplement_change[k] = pct_change(supplement_cur[k], supplement_prev.get(k))
                if supplement_change:
                    result['supplement_change'] = supplement_change
        except Exception as e:
            print(f'[WARN] 基础数据其一读取失败: {e}', file=sys.stderr)

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f'已输出到 {args.output}')
    else:
        print(out)

if __name__ == '__main__':
    main()
