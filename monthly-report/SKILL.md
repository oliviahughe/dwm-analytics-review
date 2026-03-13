---
name: monthly-report
description: >
  生成手游月度复盘报告的完整工作流。当用户提到"生成月报"、"跑月报"、"月度复盘"、"出月度报告"、"X月的月报"时，必须使用本 skill。

  适用场景：用户有月份信息和对应的 CSV 数据（手动提供或看板下载），需要生成结构化月度复盘 Markdown 报告。
  即使用户只说"跑一下月报"、"帮我出月报"，也要触发本 skill。
version: 1.0.0
---

# 月度复盘报告生成器

本 skill 支持两种数据获取方式：用户已手动提供 CSV，或由 Claude 操作浏览器从看板下载 ZIP。

---

## 参考路径

| 路径 | 说明 |
|------|------|
| `D:/claudecode/monthly_report/reports/` | 历史月报存档目录，命名格式：`<产品名>_<平台>月度复盘 - YY年M月.md`（如 `WOOHOO_CASINO_安卓月度复盘 - 26年2月.md`） |
| `D:/claudecode/monthly_report/skill/section_registry.json` | 章节定义、触发字段、分析要点 |
| `D:/claudecode/monthly_report/skill/csv_mapping.json` | CSV 文件名 → 章节映射配置（看板搭建完成后填入） |
| `D:/claudecode/monthly_report/skill/style_guide.json` | 文风规范、禁止写法、措辞参考 |
| `D:/claudecode/monthly_report/skill/wip_report.md` | 当前月报草稿（逐章追加写入） |

---

## 第零步：初始化

1. 从用户输入中判断三个要素：**产品名**（如 WOOHOO CASINO）、**平台**（iOS / Android / 全平台）、**报告月份**（如 `26年3月`）
2. 根据平台裁剪章节列表：
   - **iOS 报告**：跳过「基础大盘 安卓」「进阶数据 安卓」
   - **Android 报告**：跳过「基础大盘 iOS」「进阶数据 iOS」
   - **全平台报告**：保留所有章节
   - 同时读取 `section_registry.json`，按 `platform` 字段过滤
3. 自动推算上月文件名，用 Read 工具读取上月 md：
   - 优先查找产品专属文件（如 `WOOHOO_CASINO_安卓月度复盘 - <上月>.md`）
   - 若不存在，尝试通用文件（如 `LUCKYME月度复盘 - <上月>.md`）
   - 读取成功后，将全文存入上下文，后续每章生成时作为参考
   - 若文件不存在，告知用户并请其手动粘贴上月对应章节结论
4. 清空或新建 `wip_report.md`，写入报告标题：
   ```
   # <产品名> <平台>月度复盘 - <月份>
   # <月份> 月度复盘（<平台>）
   ```
5. 向用户说明裁剪后的章节顺序，并提示：
   > "上月报告已读取完毕，请按章节顺序提供数据，或告知我需要从看板下载。"

> **重要原则**：每份报告只包含**一个产品的一个渠道**的数据。不同渠道（iOS/Android）视为不同报告。不在报告中引用其他渠道或产品的数据做对比。

---

## 【可选】浏览器自动化下载 ZIP

> 适用于用户尚未下载数据时。需已安装 Claude in Chrome 扩展并连接。
> **每个产品有独立看板，每次只下载当前产品的数据。**

### B-1：导航到看板，确认登录状态

1. 用 `tabs_context_mcp` 获取当前标签 ID
2. 导航到用户提供的看板 URL（或从 `csv_mapping.json` 中读取 `dashboard_url`）
3. 截图确认是否已登录
   - **未登录**：告知用户「看板 Session 已过期，请在浏览器手动登录后告诉我继续」，等待用户回复

### B-2：点击「下载数据」按钮触发全量 ZIP 下载

1. 截图确认当前在目标看板页面
2. **优先使用 JS 点击方案**（鼠标点击容易因菜单关闭而失败）：
   - 先用鼠标点击页面**右上角工具栏**的 `...`（更多）按钮，展开下拉菜单
   - 等待 1 秒菜单渲染完成
   - 用 JS 执行点击：
   ```javascript
   const labels = document.querySelectorAll('.ant-dropdown-menu-title-content-label');
   const btn = Array.from(labels).find(el => el.textContent.trim() === '下载数据');
   if (btn) { (btn.closest('li') || btn.parentElement).click(); }
   ```
3. 等待 10 秒后检查 Downloads 目录是否有新 ZIP 文件
4. 若 JS 方案也失败（DOM 结构变化），再尝试纯鼠标方案定位「下载数据」菜单项坐标点击

### B-3：解压 ZIP 到月报数据目录

```bash
python -c "
import zipfile, os, glob
downloads = os.path.join(os.path.expanduser('~'), 'Downloads')
zips = sorted(glob.glob(os.path.join(downloads, '*.zip')), key=os.path.getmtime, reverse=True)
if not zips: raise FileNotFoundError('Downloads 目录未找到 ZIP 文件')
dest = r'D:/claudecode/monthly_report/data/<产品名>_<月份>'
os.makedirs(dest, exist_ok=True)
with zipfile.ZipFile(zips[0], 'r') as zf:
    zf.extractall(dest)
    names = zf.namelist()
subdirs = [d for d in os.listdir(dest) if os.path.isdir(os.path.join(dest, d))]
actual_csv_dir = os.path.join(dest, subdirs[0]) if subdirs and not glob.glob(os.path.join(dest, '*.csv')) else dest
print(f'解压完成：{os.path.basename(zips[0])} -> {actual_csv_dir}，共 {len(names)} 个文件')
"
```

解压成功后，运行一键聚合脚本：

```bash
set PYTHONUTF8=1 && python D:/claudecode/monthly_report/skill/scripts/run_all.py \
  --data-dir "<actual_csv_dir>" \
  --month "<本月YYYY-MM>" \
  --prev-month "<上月YYYY-MM>" \
  --output D:/claudecode/monthly_report/skill/extracted_data.json
```

脚本会自动识别 CSV 文件并聚合所有章节数据，输出 `extracted_data.json`。
输出摘要确认各章节数据已就绪后，进入第一步。

---

## 月报章节顺序（全量，按平台裁剪）

```
1.  版本发布节奏           → 手动填写，无 CSV         → platform: all
2.  机台轮换 - 付费用户大盘  → 付费用户总结数据 CSV     → platform: all
3.  机台轮换 - 机台参与率    → spin 数据总览 CSV       → platform: all
4.  机台轮换 - 钻石消耗      → 付费用户资源监控 CSV     → platform: all
5.  付费礼包监控            → 内购数据_分点位 CSV      → platform: all
6.  推广数据监控            → 推广数据监控 CSV         → platform: all
7.  基础大盘 iOS           → 基础数据 CSV             → platform: ios
8.  基础大盘 安卓           → 基础数据 CSV             → platform: android
9.  进阶数据 iOS           → 进阶指标表               → platform: ios
10. 进阶数据 安卓           → 进阶指标表               → platform: android
11. 运营策略调整            → 手动填写，无 CSV         → platform: all
```

**平台裁剪规则**：
- iOS 报告 → 保留 platform=all + platform=ios，跳过 platform=android
- Android 报告 → 保留 platform=all + platform=android，跳过 platform=ios
- 全平台报告 → 保留全部

> **注意**：每个产品的每个渠道单独一份月报文档。不在同一文档中混合多产品或多渠道数据。

---

## 第一步：逐章节接收数据并生成段落

对每个章节，执行以下循环：

### 1-A 识别章节类型

用户发来数据后，根据 `section_registry.json` 中的 `trigger_fields` 自动识别章节类型。
若无法自动识别，询问用户：「这份数据对应哪个章节？」

### 1-B 数据确认

**必须先列出核心数字并提问，再生成段落。** 确认规则：
- 空缺值（如 30 日留存、未到期 ROI）：确认是否正常缺失
- 环比变化超过 ±30% 的指标：确认是否有背景原因需写入报告
- 新增/消失的数据项：确认是否需要说明
- **每次确认问题不超过 5 个**，非关键异常直接在段落中用 ⚠️ 标注，不打断流程

### 1-C 参考上月结论

生成段落前，从已读取的上月 md 文档中定位对应章节的结论，作为环比判断的参照。
**不重复上月的结论，只用于判断方向和提供对比锚点。**

### 1-D 生成段落

按照 `section_registry.json` 中该章节的 `analysis_focus` 和 `style_guide.json` 的文风规范生成段落。

写作规范：
- 数据是什么就写什么，不过度推测
- 每个指标都要有对比锚点（上月值 / 环比变化）
- 百分点差值用 pp，倍数用 x，增减用 +/- 百分比，环比可加 ↑↓
- 禁用：「可以看出」「通过分析」「整体来看」「综合以上数据」等废话开头
- 异常指标用 ⚠️ 前置标注
- 每章 100-200 字，资源监控等数据量大的章节可适当放宽
- **区间范围用 `-` 连接，禁止用 `~`**：pandoc 转 Word 时 `~text~` 被解析为下标，两个 `~` 之间的文字会缩小。写 `0-7天`、`90-120天段`，不写 `0~7天`、`90~120天段`

### 1-E 追加写入草稿

将生成的段落追加写入 `wip_report.md` 对应章节位置，然后提示用户：
> "第 X 章【章节名】已完成，请发送下一章数据，或告知需要调整。"

### 1-F 处理追加分析

若用户针对当前段落提出补充分析需求（如「按生命周期重新分析」「拆分付费层级」），在当前段落下追加补充段落，不重新生成整段，完成后继续等待下一章数据。

---

## 第二步：手动章节处理

**版本发布节奏**（章节1）和**运营策略调整**（章节11）无 CSV，直接提示用户：
> "【版本发布节奏】章节需要手动填写，请提供本月版本号、发布日期和主要内容，我来帮你格式化写入。"

---

## 第三步：完成汇总

所有章节完成后：

1. 读取 `wip_report.md` 全文，检查各章节是否齐全
2. 若有缺失章节，列出并询问用户是否补充或跳过
3. 将最终报告从 `wip_report.md` 复制到正式存档：
   ```
   D:/claudecode/monthly_report/reports/<产品名>_<平台>月度复盘 - <月份>.md
   ```
4. 告知用户报告完成，输出文件路径，并给出 3-5 条跨章节的月度核心结论

---

## 常见问题处理

**CSV 文件名与 csv_mapping.json 不匹配**：告知用户当前文件名，请用户更新 `csv_mapping.json` 中对应字段后重试，或直接手动上传 CSV。

**上月 md 文件不存在**：告知用户路径，请其手动粘贴上月对应章节结论，或跳过上月参考直接根据数据生成。

**看板 Session 过期**：浏览器截图显示登录页时，告知用户手动登录，等用户回复「好了」后继续。

**ZIP 解压路径问题**：若 Python 找不到 ZIP 文件，请用户手动告知 ZIP 的完整路径。

**数据量过大的 CSV**：触发 Python 聚合脚本处理（参考 version-report 的 data_extractor 逻辑），不直接逐行读取。
