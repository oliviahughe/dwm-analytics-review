# DWM Analytics Assistant

基于 Claude Code 的手游数据分析报告工具，支持月报、周报、日报三种报告类型。通过解析从数据看板导出的 CSV 文件，自动生成结构化的 Markdown 复盘报告。

---

## 报告类型

| 类型 | 触发方式 | 对比维度 | 异常阈值 |
|------|---------|---------|---------|
| 月报 | "生成月报"、"跑月报" | 月环比 | ±30% |
| 周报 | "生成周报"、"跑周报" | 周环比 | ±20% |
| 日报 | "生成日报"、"跑日报" | 日环比 / 7日均值 | ±15% |

---

## 项目结构

```
DWM-Analytics-Assistant/
├── shared/scripts/         # 月报、周报共用的 CSV 解析脚本
│   ├── run_all.py          # 总调度脚本，一键跑完所有解析
│   ├── parse_basic.py      # 基础指标（DAU、收入、留存）
│   ├── parse_iap.py        # 内购数据（按点位拆分）
│   ├── parse_spin.py       # Spin 数据总览
│   ├── parse_resource.py   # 付费用户资源监控
│   ├── parse_paying_users.py # 付费用户生命周期分析
│   ├── parse_promotion.py  # 推广投放数据
│   ├── parse_big_r.py      # 大R用户明细
│   └── validate_daily_report.py # 日报数据校验
├── monthly-report/         # 月报 Skill 配置
├── weekly-report/          # 周报 Skill 配置
└── daily-report/           # 日报 Skill 配置及快照脚本
```

---

## 使用前提

1. 本地已安装 [Claude Code](https://claude.ai/code)
2. 已将本项目的三个 Skill 安装到 Claude Code
3. 数据 CSV 文件已从看板导出并放置到本地数据目录

---

## 快速开始

### 第一步：安装 Skill

在 Claude Code 中分别安装三个 Skill：

```bash
# 月报
/install-skill monthly-report

# 周报
/install-skill weekly-report

# 日报
/install-skill daily-report
```

### 第二步：准备数据

从数据看板导出以下 CSV 文件，放入本地数据目录：

| 文件 | 用途 |
|------|------|
| 基础数据（其一）| DAU、收入、留存等核心指标 |
| 基础数据（其二）| 补充基础指标 |
| spin数据总览 | Spin 次数、消耗等 |
| 内购数据_分点位 | 各付费点位的内购数据 |
| 付费用户资源监控_日期对比 | 付费用户资源消耗对比 |
| 付费用户总结数据_按生命周期分组 | 用户生命周期分布 |
| 推广数据监控 | 投放花费与回收 |
| 大R用户明细 | 历史累计付费 $500+ 用户 |

### 第三步：生成报告

在 Claude Code 中直接说：

```
生成 1 月的月报
```

```
跑一下 2.24-3.2 的周报
```

```
帮我出今天的日报
```

Claude 会自动调用对应 Skill，解析 CSV、汇总数据、生成报告。

---

## 解析脚本说明

所有脚本位于 `shared/scripts/`，由 `run_all.py` 统一调度。

**月报调用方式：**
```bash
python run_all.py --month 2026-01 --prev-month 2025-12
```

**周报调用方式：**
```bash
python run_all.py --start-date 2026-02-24 --end-date 2026-03-02 \
  --prev-start-date 2026-02-17 --prev-end-date 2026-02-23
```

脚本输出 `extracted_data.json`，Claude 读取后生成最终报告。

---

## 注意事项

- 月报和周报各自独立，每份报告对应一个产品 + 一个平台（iOS / Android 分开出）
- CSV 文件通过模糊关键字匹配，文件名格式略有不同也可正常识别
- 如遇解析报错，优先检查 CSV 是否为"全量下载"格式（与单独下载格式略有差异）

