# 寻仙任务数据库项目概况与完成记录

> 状态日期：2026-07-26  
> 线上地址：<https://quests.xunxian.wiki>  
> 当前数据库发布版：`1.0.1`

## 1. 项目概况

本项目用于整理《寻仙》客户端资源中的任务资料，以
`original_data/mb/quest/quest_info.txt` 为任务主表，结合任务文本、NPC、目标、
物品、地区、分类、奖励、状态、称号和任务关系等资源，建立可追溯的 SQLite
任务数据库，并提供本地与 Cloudflare 线上只读检索网站。

项目当前由三部分组成：

1. **资源整理与数据库流水线**：解析原始文本、建立字段字典、关联对象并生成
   版本化 SQLite 数据库和质量报告。
2. **本地 Web 原型**：基于 FastAPI 和 SQLite，供开发、验证及数据排错使用。
3. **线上 Web 版本**：基于 Cloudflare Python Worker、D1 和 Static Assets，
   通过 `quests.xunxian.wiki` 对外提供查询。

项目坚持以下数据原则：

- 原始资源只读，不直接覆盖或手工改写；
- 无法确认的字段和对象保留原值，不凭空推断；
- 解析结果保留来源文件、原始行号、原始值和运行 ID，能够追溯；
- 数据库发布使用版本目录，旧版本不被新构建覆盖；
- 网站只读，不向任务数据库写入内容。

## 2. 主要目录与文件

| 路径 | 用途 |
| --- | --- |
| `original_data/` | 解包后的原始游戏资源，数据库构建的权威输入 |
| `original_data/index_list.txt` | 原始资源索引，可用于定位相关资源文件 |
| `src/questdb/` | 数据解析、清洗、建库和质量检查代码 |
| `tests/` | 数据流水线测试 |
| `docs/database_schema.md` | 数据库结构说明 |
| `docs/PROJECT_DECISIONS.md` | 问题发现、修改原因和最终处理决策 |
| `docs/quest_info_schema.json` | `quest_info` 字段定义及置信度 |
| `docs/quest_info_dictionary_draft.xlsx` | 任务字段字典 |
| `reports/` | 覆盖率、映射、关系、质量和可复现性报告 |
| `plans/quest_database/AI_EXECUTION_PLAN.md` | 数据库 AI 执行计划 |
| `plans/quest_web_prototype/AI_VIBECODING_PLAN.md` | Web 原型 AI 开发计划 |
| `outputs/quest_database/releases/1.0.1/quest.db` | 当前本地 SQLite 发布库 |
| `apps/quest_viewer/` | 本地只读 Web 应用 |
| `apps/quest_viewer_cloudflare/` | Cloudflare 线上应用及 D1 构建脚本 |

## 3. 当前数据规模

当前发布库 `outputs/quest_database/releases/1.0.1/quest.db` 的主要记录数量如下：

| 数据 | 数量 |
| --- | ---: |
| 唯一任务身份 `quest_identity` | 8,828 |
| 任务版本 `quest` | 8,829 |
| 任务文本 `quest_text` | 8,723 |
| 任务关系 `quest_relation` | 13,559 |
| 任务条件 `quest_condition` | 8,151 |
| 任务目标 `quest_objective` | 7,682 |
| 任务奖励 `quest_reward` | 6,842 |

任务身份比任务版本少一条，是因为任务 ID `11257` 在资源中存在两个版本。数据库
无损保留两个版本，网站将其合并为一个任务入口展示。

## 4. 已完成工作

### 4.1 原始资源与编码

- 检查了 `original_data` 中的文本编码，将需要修复的 UTF-8/GBK 乱码文件统一为
  可稳定读取的 UTF-8。
- 编码转换记录保存在 `encoding_conversion_manifest.json`。
- 转换前资源备份为 `original_data_before_utf8_20260724.tar.gz`，可用于回溯。
- 确认以 `quest_info` 为基础，并找出任务文本、分类、NPC、对象、地区、奖励和
  任务关系等关联资源。

### 4.2 AI 数据库执行计划

- 已建立可供 AI 连续执行的 Markdown 计划。
- AI01 至 AI21 全部完成。
- G01、G02、G03 三个人工审批节点均已按推荐方案通过。
- 已完成 `quest_info` 64 个字段的含义梳理；高置信字段正式命名，中低置信字段
  标注置信度，不能确认的字段继续按原列和原值保存。
- 已完成原始加载、规范化建模、文本关联、对象路由、NPC/目标映射、任务关系、
  质量检查、回归检查和版本发布。

执行状态的机器可读记录位于
`plans/quest_database/execution_state.json`，审批记录位于 `approvals/`。

### 4.3 SQLite 任务数据库

- 建立了规范化 SQLite Schema，并提供 `quest_full` 和各类 `*_detail` 查询视图。
- 任务信息已整合：
  - 名称、等级、主类型和子类型；
  - 原所属地区和地区层级；
  - 接取人、交付人及相关 NPC；
  - 接取对话、背景描述、提示文字、进行中对话和完成对话；
  - 前置条件、任务目标、任务奖励；
  - 前置、后续及其他直接任务关系；
  - 文本内敌人、目标、角色、动态玩家称谓等对象。
- 保留来源文件、原始行号、原始标签、原始值和构建运行 ID，便于排错和复核。
- 已发布 `1.0.1`，所有 P0 检查通过，并附带校验和、质量报告、回归报告和重建脚本。

### 4.4 文本标签解析

已完成或采用的显示规则如下：

- `<enemy:名称>`、`<target:ID>`、`<character:ID>`：能确定对象时建立可点击对象；
- `<friend:...>`：能唯一匹配角色时建立角色链接，否则保留文字；
- 动态玩家称谓：默认显示第一个候选称谓，同时保留可点击切换；
- `<name>`：显示为“玩家”；
- `<c:...>`：忽略颜色标签，保留标签之间的文字；
- `<area:文字>`、`<brief>`、`<aim>`：去掉标签，保留可读文字；
- 无法匹配对象的 `<enemy>`：去掉标签，保留文字；
- 包含“提示：”的导航提示按普通提示文字展示，不强制生成对象链接；
- 修正常见 `target` 拼写错误和全角冒号；
- 资源中的 `item` 标签按实际语境作为提示对象处理，不简单等同于任务道具；
- “点击带有下划线的文字便可以出现寻路路线”等通用操作提示不显示。

`<ic:ID>` 的资源对应关系仍属于待继续确认项；在没有可靠映射前不生成虚假对象。

### 4.5 数据补全与专项修复

- 补充称号资源映射：
  - 解析 `mb/etc/title_list.txt`；
  - 141 个带称号奖励的任务和 78 个带称号条件的任务已接入名称；
  - 例如称号 ID `505` 显示为“十方名士”，ID `506` 显示为“十方上师”；
  - 前置需求显示为“称号 十方上师”，奖励显示为“称号”，不再显示“称号ID”。
- 补充状态资源映射：
  - 解析 `mb/skill/state_group.txt`；
  - 67 个被任务引用的状态 ID 均已匹配，覆盖 211 个任务、234 处引用；
  - 状态条件和奖励使用正确文字描述，不再只显示状态 ID。
- 补充阵营声望名称：
  - 阵营 ID `15` 已匹配为“鬼谷仙派”；
  - 同类遗漏已检查并补充；
  - 前端统一显示“阵营声望 +数值”。
- 增加经验值奖励展示。
- 大数值采用紧凑格式：一万以上显示整数“万”，一亿以上显示整数“亿”。
- 修正任务“【正传】阅秘书解析天劫”的原所属地区为“云梦山”。

### 4.6 本地 Web 原型

已完成 `apps/quest_viewer`：

- 桌面三栏工作台和移动端抽屉布局；
- 按任务名称、NPC、地区、主类型和子类型检索；
- 前台不暴露任务 ID 检索；
- 检索结果按任务等级从低到高排序，每页最多 5 条并显示总页数；
- 检索翻页使用局部刷新，不再刷新整页，并预取相邻页面；
- 从任务语境跳转到其他任务时保留原检索条件、结果和页码；
- 主类型按任务数量降序排列；
- 任务详情展示完整文本、条件与目标、奖励、任务语境、相关任务和对象详情；
- 前置任务、相关任务和可确认对象均可点击跳转；
- 相关任务最多 5 条并支持独立分页；
- 奖励和被截断内容支持鼠标悬停查看完整文字；
- 移除了原始来源面板、原始标签开关及不适合普通访客的内部 ID。

### 4.7 分类与地区整理

分类采用“主类型 + 子类型”：

- 副本任务、声望任务、阵营任务和活动任务的指定旧分类已归并为子类型；
- 休闲任务归入活动任务；
- 奇缘任务归入重复任务；
- 支线、重复和系列任务保留适合检索的子类型；
- 有未进一步归类的任务时提供“未分类”；
- 若主类型只有一个“未分类”子类型，则不显示该子类型；
- 任务详情的子类型为“未分类”时只显示主类型。

地区筛选栏对小区域做归并，但任务详情仍显示原所属地区。例如筛选使用“小桑村”，
详情可显示“小桑村·桃花林”。目前还包含宁海县、京城、石塘县、茅山、东山岛、
地府、副本场景、湘云州、通天河、摩云山、门派广场、五岳山麓、瑶池仙境、
不周山、女儿国、车迟国、乌鸡国等归并规则。

地区筛选按最低任务等级从低到高排列，选项不显示“xx级起”。

### 4.8 线上部署

- 已建立 `apps/quest_viewer_cloudflare`。
- 使用 Cloudflare Python Worker + FastAPI 提供页面和 API。
- 使用 D1 保存任务查询数据，Static Assets 提供样式和脚本。
- 自定义域名 `quests.xunxian.wiki` 已接入并可访问。
- 页面标题为“寻仙任务存档”，右上角提供“关于网站”和“今日来访”。
- “关于网站”中已明确：
  - 作者与维护者：GitHub
    [@icosohedral](https://github.com/icosohedral)；
  - 特别鸣谢：贴吧用户「耳目清净」及其寻仙游戏资源解包工具。

### 4.9 今日来访统计

当前线上访问统计采用浏览器端匿名访客 ID：

1. 浏览器首次访问时生成随机匿名 ID，并保存到 `localStorage`；
2. 页面脚本向 `/api/visit` 提交该 ID；
3. D1 以“日期 + 匿名访客 ID”去重；
4. 同一浏览器同一天重复打开或刷新只计一次；
5. 不执行 JavaScript 的爬虫、`curl` 或单纯页面请求不会计数；
6. 不采集账号、IP 或其他个人身份信息。

早期统计数字予以保留，因此历史数字不能全部视为严格的独立访客数；新逻辑启用后的
每日数字才按上述规则去重。

## 5. 当前验证结果

- 数据库 AI01–AI21：全部完成；
- 人工审批 G01–G03：全部通过；
- 数据库发布版 P0 检查：全部通过；
- 本地 Web 自动化测试：`69 passed`；
- 当前仅有 1 条来自 Starlette TestClient 的弃用提示，不影响功能；
- 线上域名于 2026-07-26 再次检查，Cloudflare 服务正常响应。

## 6. 已知限制

- 数据库记录了完整直接关系，但页面目前只展开一层关系，不递归展示整个任务图谱。
- 157 个任务在原资源中没有任务文本，另有 49 个文本 ID 没有对应任务；均按原状保留。
- 原始任务关系中有 54 个环路，未自动打断。
- NPC 映射实际端缺 7 项、任务端缺 10 项。
- 不能唯一确认的同名对象只显示候选或普通文字。
- `<ic:ID>` 尚未形成足够可信的通用资源映射。
- “任务关闭”目前仍作为主类型，尚未拆成独立状态筛选。
- 网站是只读资料库，目前没有编辑后台或在线改库功能。

更完整的质量信息见
`outputs/quest_database/releases/1.0.1/reports/quality_report.html`。

称号、状态、阵营、主/子类型、地区层级以及界面功能为什么修改、怎样修改，见
`docs/PROJECT_DECISIONS.md`。

## 7. 常用维护命令

### 本地运行和测试

```bash
cd apps/quest_viewer
./start.sh
uv run pytest -q
```

本地地址为 <http://127.0.0.1:8000>。

### 重新生成线上查询数据

```bash
cd apps/quest_viewer_cloudflare
uv run python scripts/build_web_database.py
```

该命令会从本地发布库生成 D1 导入 SQL、本地校验库、线上模板和筛选数据。完整构建
需要逐任务整理详情，耗时会明显长于单纯部署。

仅同步模板与筛选模块时可执行：

```bash
uv run python -c "from scripts.build_web_database import _write_generated_modules; _write_generated_modules()"
```

### Cloudflare 本地运行与部署

```bash
cd apps/quest_viewer_cloudflare
uv sync
npx wrangler d1 execute xunxian-quest-archive --local --file=data/quest_web.sql
npx wrangler d1 execute xunxian-visits --local --file=data/visits.sql
uv run pywrangler dev
```

后续正式同步 Cloudflare 时使用发布脚本。脚本会自动将补丁版本号加一，并在部署失败
时回滚：

```bash
uv run python scripts/deploy_release.py
```

只有在任务 D1 需要全量重建时才执行：

```bash
npx wrangler d1 execute xunxian-quest-archive --remote --file=data/quest_web.sql
```

访问统计表结构需要更新时执行：

```bash
npx wrangler d1 execute xunxian-visits --remote --file=data/visits.sql
```

## 8. 后续建议

1. 继续调查 `<ic:ID>` 的权威资源来源，确认后再加入对象链接。
2. 为剩余缺失或歧义 NPC 建立人工复核清单。
3. 将“任务关闭”从任务类型中拆分为状态筛选。
4. 增加整条任务链图谱视图，但默认仍保持一层展示以控制复杂度。
5. 后续每次数据库或线上重要功能发布，都在本文档顶部更新状态日期，并在“已完成工作”
   中追加版本记录。
