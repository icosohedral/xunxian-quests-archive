# 寻仙任务存档

本地只读 Web 原型，用于检索并查看寻仙任务数据库中的任务文本、NPC、目标、奖励、地区、任务关系和角色相关任务。

## 当前能力

- 按任务名称、NPC、一级地区、主类型和子类型检索；
- 主类型按任务数量降序；支线、重复和系列任务可继续选择子类型；
- 尚未进一步归入子类型的任务统一显示为“未分类”；
- 地区筛选只展示“小桑村”等一级区域，详情使用“小桑村·桃花林”展示完整层级；
- 查看接取对话、任务背景、提示文字、进行中和完成对话；
- 解析 `<enemy:...>`、`<target:...>` 和 `<item:...>` 文本标签；
- 展示前置条件、任务目标、奖励和直接任务关系；
- 将任务 11257 无损合并为一项展示，同时保留别名；
- 提供只读 JSON API；
- 桌面三栏工作台和移动端底部抽屉布局。

## 环境要求

- Python 3.11+
- `uv`
- 项目发布版 `quest.db`

应用运行时不会修改 SQLite 数据库或 `original_data/**`。地区层级会只读加载
`original_data/mb/scn/prov_info.txt`；该文件缺失时回退到任务目标中可确认的层级。

## 启动

在本目录执行：

```bash
./start.sh
```

或手动执行：

```bash
uv sync --group dev
uv run uvicorn quest_viewer.app:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`，默认展示任务 90“大战黄风洞”。

停止服务：在启动服务的终端中按 `Ctrl+C`。

## 指定数据库

默认数据库：

```text
../../outputs/quest_database/releases/1.0.1/quest.db
```

也可以指定其他兼容版本：

```bash
QUEST_DB_PATH=/绝对路径/quest.db ./start.sh
```

启动时会检查数据库完整性和 6 个查询视图。SQLite 使用 `mode=ro` 和 `PRAGMA query_only=ON` 打开。

## 常用页面与接口

```text
GET /                               页面
GET /?q=黄风洞                      按名称查询
GET /?npc=刘老太太                  按 NPC 查询
GET /?area=宁海县                   按地区查询
GET /?category=重复任务             按主类型查询
GET /?category=重复任务&subcategory=六百里号山
                                      按主类型和子类型查询
GET /health                         数据库健康状态
GET /api/quests                     任务列表 JSON
GET /api/quests/90                  任务详情 JSON
GET /api/quests/90/relations        一层任务关系 JSON
```

## 测试

```bash
uv run pytest -q
```

关键回归任务：

- 任务 2：完整新手任务数据；
- 任务 90：五类文本及 `enemy`、`target` 标签；
- 任务 11257：同 ID 无损合并和双来源。

浏览器验收记录见 [reports/browser_qa.md](reports/browser_qa.md)。

## 更新数据库

1. 生成新的版本化任务数据库；
2. 不覆盖旧版本；
3. 使用 `QUEST_DB_PATH` 指向新文件；
4. 运行 `/health` 和测试；
5. 检查任务 2、90、11257。

只要 Schema 和 6 个视图保持兼容，无需修改 Web 应用。

## 已知限制

- 页面只展示直接一层任务关系，不递归展开完整图谱；
- 任务文本中的标签只解析数据库能够唯一确认的对象；
- 无法唯一解析的同名对象会显示“候选不唯一”或“未解析”；
- 任务 11257 的合并仅发生在展示模型中，底层两条数据库记录保持不变；
- “任务关闭”目前仍作为主类型保留，后续可拆分为独立状态筛选。
