# Change Log — Monthly Report / Daily Report Workflow

记录日/月报工作流的改动与执行记录，按时间倒序。

---

## 2026-03-05（日报流程稳定性修复）

### 一、代码变更（daily-report）

**变更文件**：`C:/Users/69050/.claude/skills/daily-report/scripts/build_daily_snapshot.py`

1. 资源章节从“单周期近似环比”升级为“日级双周期对比”
- `resource.consume_total / grant_total / net_consume` 新增：`d1`、`d7`、`avg7`、`chg_d1`、`chg_d7`、`chg_avg7`
- 保留兼容字段：`previous`、`chg`（映射到 D-1）

2. 资源原因维度新增双周期字段
- `top_consume_reasons` 新增：`d1`、`d7`、`chg_d1`、`chg_d7`

3. 增强日期列识别鲁棒性
- 对“列头包含日期+额外文本”的格式进行日期抽取与归一化，避免只按裸 `YYYY-MM-DD` 匹配导致漏读。

### 二、执行流程变更（运行SOP）

1. 快照阶段强制使用严格模式：
- `--expected-csv-count 8 --strict`
- 任一 required CSV `missing/parse_error` 立即失败，不进入写稿阶段。

2. 写稿阶段改为“手工撰写优先”
- 不使用模板直填，不允许把低质量草稿直接归档为正式报告。

3. 归档前增加人工质量门（当前为流程门禁）
- 必查项：
  - 是否覆盖 9 个章节
  - 生命周期是否包含 `0-30 / 30-120 / 120+` 三档
  - 资源章节是否包含 `D-1` 与 `D-7`
  - 风险清单是否有 Top1/2/3 与明日动作

### 三、本次已完成运行记录

1. 数据：`D:/claudecode/monthly_report/data/WOOHOO_CASINO_2026-03-05`
- 报告：`D:/claudecode/monthly_report/reports_daily/WOOHOO CASINO iOS日常监控 - 2026-03-04.md`

2. 数据：`D:/claudecode/monthly_report/data/WOOHOO_CASINO_ANDROID_2026-03-05`
- 报告：`D:/claudecode/monthly_report/reports_daily/WOOHOO CASINO 安卓日常监控 - 2026-03-04.md`

3. 数据：`D:/claudecode/monthly_report/data/grandriches_日常数据_20260305`
- 报告：`D:/claudecode/monthly_report/reports_daily/grandrichescasino安卓日常监控 - 2026-03-04.md`

### 四、后续待办

1. 把“归档前人工质量门”脚本化（自动校验章节覆盖、双周期字段、风险动作完整性）。
2. 在 `daily-report` skill 中增加“归档禁止条件”，不满足质量门时禁止复制为正式报告。

### 五、本次新增：归档前质量门脚本（可回撤）

- 新增脚本：`D:/claudecode/monthly_report/skill/scripts/validate_daily_report.py`
- 作用：归档前只校验硬指标，不判断文风，避免低质量草稿直接归档。
- 校验项：
  - 9 个固定章节是否齐全
  - 文稿是否包含 `D-1`、`D-7` 标识
  - 生命周期是否具备 `0-30 / 30-120 / 120+` 三档
  - 风险优先级是否含 `Top1/Top2/Top3`
  - 明日动作条数是否 >=3
  - `daily_snapshot.json` required coverage 是否全通过
  - `resource.consume_total/grant_total/net_consume` 是否含 `d1/d7/chg_d1/chg_d7`

### 六、回撤管理

- 变更前快照目录：`D:/claudecode/monthly_report/skill/snapshots/daily_quality_gate_20260305_163647`
- 快照内容：`BUG_LOG.md`、`CHANGE_LOG.md`、`validate_daily_report.py(若存在)`、`SNAPSHOT_MANIFEST.json`
- 回撤方式：将快照内文件覆盖回原路径即可。
