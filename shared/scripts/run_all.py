"""
run_all.py
月报数据一键聚合入口。自动找到 CSV 目录，依次调用各 parser，
将所有结果合并输出到 extracted_data.json。

用法：
    python run_all.py --data-dir <ZIP解压后的CSV目录> --month 2026-02 [--prev-month 2026-01] [--output <输出路径>]

示例：
    python run_all.py \
      --data-dir "D:/claudecode/monthly_report/data/WOOHOO_CASINO_iOS_26年3月/月报_20260302" \
      --month 2026-02 \
      --prev-month 2026-01 \
      --output "D:/claudecode/monthly_report/skill/extracted_data.json"
"""
import os, sys, json, argparse, glob, subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def find_csv(data_dir, keyword):
    """按关键字模糊匹配 CSV 文件名"""
    pattern = os.path.join(data_dir, f'*{keyword}*.csv')
    matches = glob.glob(pattern)
    if not matches:
        return None
    # 取最新的
    return sorted(matches, key=os.path.getmtime, reverse=True)[0]

def run_parser(script, args_list):
    """运行子脚本并返回 JSON 结果"""
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, script)] + args_list
    # 问题4修复：打印实际调用命令，方便调试
    short_args = ' '.join(args_list[:4]) + ('...' if len(args_list) > 4 else '')
    print(f'  → cmd: {script} {short_args}')
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        # 问题4修复：输出完整 stderr（原来截断到 200 字符，关键错误信息会丢失）
        print(f'[ERROR] {script} 执行失败 (exit={result.returncode}):')
        print(result.stderr)
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # 可能有多余的 print，尝试找最后一个完整 JSON
        lines = result.stdout.strip().split('\n')
        for line in reversed(lines):
            try: return json.loads(line)
            except: pass
        print(f'[WARN] {script} 输出无法解析为 JSON')
        if result.stdout:
            print(f'  stdout 前 300 字符: {result.stdout[:300]}')
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', required=True, help='ZIP 解压后的 CSV 目录')
    parser.add_argument('--month', help='本月 YYYY-MM，如 2026-02')
    parser.add_argument('--prev-month', help='上月 YYYY-MM，如 2026-01')
    parser.add_argument('--start-date',      help='本周起始日期 YYYY-MM-DD')
    parser.add_argument('--end-date',        help='本周结束日期 YYYY-MM-DD')
    parser.add_argument('--prev-start-date', help='上周起始日期 YYYY-MM-DD')
    parser.add_argument('--prev-end-date',   help='上周结束日期 YYYY-MM-DD')
    parser.add_argument('--output', default=os.path.join(SCRIPT_DIR, '..', 'extracted_data.json'))
    args = parser.parse_args()

    if not args.month and not (args.start_date and args.end_date):
        parser.error('必须提供 --month 或 --start-date + --end-date')

    data_dir = args.data_dir
    month = args.month
    prev = args.prev_month

    # 构建日期范围透传参数
    date_args = []
    if args.start_date:
        date_args.extend([f'--start-date={args.start_date}', f'--end-date={args.end_date}'])
    if args.prev_start_date:
        date_args.extend([f'--prev-start-date={args.prev_start_date}', f'--prev-end-date={args.prev_end_date}'])

    print(f'数据目录: {data_dir}')
    print(f'本月: {month}，上月: {prev}')
    print()

    extracted = {'month': month, 'prev_month': prev, 'data_dir': data_dir}
    if args.start_date:
        extracted['start_date'] = args.start_date
        extracted['end_date']   = args.end_date
        extracted['prev_start_date'] = args.prev_start_date
        extracted['prev_end_date']   = args.prev_end_date

    total_steps = 8

    # 1. 基础大盘（其二 + 其一补充）
    f = find_csv(data_dir, '基础数据其二')
    f2 = find_csv(data_dir, '基础数据(其1)')
    if not f2:
        f2 = find_csv(data_dir, '基础数据其1')
    if f:
        print(f'[1/{total_steps}] 基础大盘: {os.path.basename(f)}' + (f' + {os.path.basename(f2)}' if f2 else ''))
        a = [f'--file={f}']
        if month: a.append(f'--month={month}')
        if prev: a.append(f'--prev-month={prev}')
        if f2: a.append(f'--file2={f2}')
        a.extend(date_args)
        extracted['基础大盘'] = run_parser('parse_basic.py', a)
    else:
        print(f'[1/{total_steps}] 基础大盘: 未找到文件（基础数据其二）')

    # 2. 付费礼包
    f = find_csv(data_dir, '内购数据_分点位')
    if f:
        print(f'[2/{total_steps}] 付费礼包: {os.path.basename(f)}')
        a = [f'--file={f}']
        if month: a.append(f'--month={month}')
        if prev: a.append(f'--prev-month={prev}')
        a.extend(date_args)
        extracted['付费礼包'] = run_parser('parse_iap.py', a)
    else:
        print(f'[2/{total_steps}] 付费礼包: 未找到文件（内购数据_分点位）')

    # 3. 机台 spin
    f = find_csv(data_dir, 'spin数据总览')
    if f:
        print(f'[3/{total_steps}] 机台 spin: {os.path.basename(f)}')
        a = [f'--file={f}', '--top=15']
        if month: a.append(f'--month={month}')
        if prev: a.append(f'--prev-month={prev}')
        a.extend(date_args)
        extracted['机台spin'] = run_parser('parse_spin.py', a)
    else:
        print(f'[3/{total_steps}] 机台 spin: 未找到文件（spin数据总览）')

    # 4. 钻石资源
    # 问题1修复：parse_resource.py 现在支持宽表格式（安卓），需透传日期参数
    f = find_csv(data_dir, '付费用户资源监控')
    if f:
        print(f'[4/{total_steps}] 钻石资源: {os.path.basename(f)}')
        resource_args = [f'--file={f}']
        resource_args.extend(date_args)   # 透传 start/end/prev-start/prev-end
        extracted['钻石资源'] = run_parser('parse_resource.py', resource_args)
    else:
        print(f'[4/{total_steps}] 钻石资源: 未找到文件（付费用户资源监控）')

    # 5. 付费用户生命周期
    f = find_csv(data_dir, '付费用户总结数据')
    if f:
        print(f'[5/{total_steps}] 付费用户: {os.path.basename(f)}')
        a = [f'--file={f}']
        if month: a.append(f'--month={month}')
        if prev: a.append(f'--prev-month={prev}')
        a.extend(date_args)
        extracted['付费用户'] = run_parser('parse_paying_users.py', a)
    else:
        print(f'[5/{total_steps}] 付费用户: 未找到文件（付费用户总结数据）')

    # 6. 推广数据
    f = find_csv(data_dir, '推广数据监控')
    if f:
        print(f'[6/{total_steps}] 推广数据: {os.path.basename(f)}')
        a = [f'--file={f}']
        if month: a.append(f'--month={month}')
        if prev: a.append(f'--prev-month={prev}')
        a.extend(date_args)
        extracted['推广数据'] = run_parser('parse_promotion.py', a)
    else:
        print(f'[6/{total_steps}] 推广数据: 未找到文件（推广数据监控）')

    # 7. 大R用户明细
    # 问题2修复：parse_big_r.py 只接受 --start-date/--end-date，
    # 不接受 --prev-start-date/--prev-end-date（date_args 里含后者会触发 argparse 报错）
    f = find_csv(data_dir, '大R用户明细')
    if f:
        print(f'[7/{total_steps}] 大R明细: {os.path.basename(f)}')
        a = [f'--file={f}', '--top=10']
        if month: a.append(f'--month={month}')
        # 单独构建 big_r 专用日期参数（只含 start/end，不含 prev-*）
        if args.start_date:
            a.extend([f'--start-date={args.start_date}', f'--end-date={args.end_date}'])
        extracted['大R明细'] = run_parser('parse_big_r.py', a)
    else:
        print(f'[7/{total_steps}] 大R明细: 未找到文件（大R用户明细）')

    # 8. 基础数据其一（独立输出，已在步骤1中作为supplement整合）
    if f2 and not extracted.get('基础大盘', {}).get('supplement'):
        print(f'[8/{total_steps}] 基础其一: 已在步骤1中整合' if f2 else f'[8/{total_steps}] 基础其一: 未找到文件')
    else:
        print(f'[8/{total_steps}] 基础其一: {"已整合到基础大盘" if f2 else "未找到文件"}')

    # 输出
    output_path = os.path.abspath(args.output)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)

    print(f'\n完成！已输出到: {output_path}')

    # 简要摘要
    print('\n=== 摘要 ===')
    if extracted.get('基础大盘') and extracted['基础大盘'].get('current'):
        c = extracted['基础大盘']['current']
        chg = extracted['基础大盘'].get('change', {})
        print(f"DAU: {c.get('DAU')} ({chg.get('DAU', 'N/A'):+.1f}%)" if isinstance(chg.get('DAU'), float) else f"DAU: {c.get('DAU')}")
        print(f"月度盈利: ${c.get('趣运利润')} ({chg.get('趣运利润', 'N/A'):+.1f}%)" if isinstance(chg.get('趣运利润'), float) else f"月度盈利: ${c.get('趣运利润')}")
    if extracted.get('付费礼包'):
        r = extracted['付费礼包']
        print(f"总收入: ${r.get('current', {}).get('total_rev')} 环比: {r.get('total_rev_chg', 'N/A')}%")

if __name__ == '__main__':
    main()
