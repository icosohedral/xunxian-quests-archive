# 寻仙任务存档 · Cloudflare

线上架构：

- Cloudflare Python Worker + FastAPI
- Cloudflare D1 任务数据库
- Workers Static Assets
- 自定义域名 `quests.xunxian.wiki`

## 构建部署数据

```bash
cd apps/quest_viewer_cloudflare
../quest_viewer/.venv/bin/python scripts/build_web_database.py
```

脚本会从本地任务数据库生成：

- `data/quest_web.db`：本地校验数据库
- `data/quest_web.sql`：D1 导入文件
- `src/generated_template.py`：线上 Jinja 模板
- `src/generated_facets.py`：分类与地区筛选数据

## 本地运行

```bash
uv sync
npx wrangler d1 execute xunxian-quest-archive --local --file=data/quest_web.sql
npx wrangler d1 execute xunxian-visits --local --file=data/visits.sql
uv run pywrangler dev
```

## 部署

网站版本号的唯一来源是 `../quest_viewer/VERSION`。当前为 `1.0.0`。

后续每次向 Cloudflare 同步正式版本，使用以下命令；脚本会先将补丁版本号加一，
再生成线上模块并部署。若部署失败，版本号和生成文件会自动回滚：

```bash
uv run python scripts/deploy_release.py
```

只有数据库结构或数据需要更新时，才在部署前执行对应的远程 D1 导入：

```bash
npx wrangler d1 execute xunxian-quest-archive --remote --file=data/quest_web.sql
npx wrangler d1 execute xunxian-visits --remote --file=data/visits.sql
```

已有线上数据库只需按顺序执行尚未应用的迁移。例如任务检索索引和
无筛选列表的顺序号分页：

```bash
npx wrangler d1 execute xunxian-quest-archive --remote \
  --file=migrations/0001_search_performance.sql
npx wrangler d1 execute xunxian-quest-archive --remote \
  --file=migrations/0002_sort_position_pagination.sql
```
