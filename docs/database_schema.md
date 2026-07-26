# 任务数据库 Schema

本 Schema 在 G01 推荐方案获批后建立。`original_data/**` 始终作为只读权威输入，规范化记录必须保留 `source_file`、`source_row`、`raw_value` 和 `run_id`。

## 核心原则

- `quest_identity` 保存任务 ID 身份；`quest` 保存一个或多个原始版本。
- `quest` 使用 `(quest_id, version_no)` 复合主键，不静默覆盖重复 ID。
- 任务 `11257` 的两个版本均保存，并设置 `conflict_flag=1`。
- 低置信度字段继续保存在 `quest.raw_values_json` 中，不强行映射业务语义。
- 文本允许缺失、重复或孤立；`source_quest_id` 保存原始 ID，`linked_quest_id` 只在任务存在时填写。
- 物品跨三张来源表保存在 `item_source`，`item` 只保存按明确优先级选出的规范记录。

## 主要表

| 表 | 用途 | 主键 |
|---|---|---|
| `quest_identity` | 唯一任务 ID 及版本数 | `quest_id` |
| `quest` | 任务版本与原始宽行 | `(quest_id, version_no)` |
| `quest_category` | 任务分类 | `category_id` |
| `quest_text` | 任务文本原始行及常用文本列 | `text_row_id` |
| `object_type` | 对象类型和目标表路由 | `object_type_id` |
| `quest_item` | 任务逻辑道具规范记录 | `quest_item_id` |
| `quest_item_source` | 重复任务逻辑道具的全部原始版本 | `quest_item_id + version_no` |
| `quest_event` | 任务事件 | `quest_event_id` |
| `quest_attribute` | 任务属性 | `attribute_id` |
| `quest_camp` | 任务阵营 | `camp_id` |
| `quest_npc` | 任务逻辑 NPC | `quest_npc_id` |
| `quest_target` | 寻路目标 | `target_id` |
| `quest_endpoint` | 接取和提交对象 | 任务版本 + endpoint 类型 |
| `item` | 规范物品记录 | `item_id` |
| `item_source` | 三张物品表的全部来源版本 | `item_id + source_table` |
| `quest_reward` | 固定和通用奖励槽位 | 自增 ID；任务/分组/槽位唯一 |
| `quest_condition` | 条件槽位（后续任务填充） | 自增 ID |
| `quest_objective` | 目标槽位（后续任务填充） | 自增 ID |
| `quest_relation` | 任务关系（后续任务填充） | 自增 ID |
| `quest_precondition_group` | 复杂前置条件原始组 | `group_id` |
| `character` | 实际角色/NPC资源 | `character_id` |
| `character_call_profile` | 动态玩家称谓模板 | `call_profile_id` |
| `character_call_variant` | 称谓模板的玩家类型变体 | `(call_profile_id, variant_no)` |
| `object_mapping` | 实际对象与任务逻辑对象映射 | `mapping_id` |
| `area` / `province` / `scene` | 地理和场景上下文 | 各自 ID |
| `location_context` | 寻路目标到区域的连接 | `target_id` |
| `quest_pool` | 跑环、日常、任务池配置 | `config_id` |
| `special_quest_config` | 特殊任务配置原始行 | `config_id` |
| `quest_feature_config` | 奖励、剧情、快速完成等功能配置 | `config_id` |
| `unresolved_reference` | 缺失标志位等不可解析引用 | `unresolved_id` |
| `external_dependency` | 缺失外部资源清单 | `dependency_id` |
| `load_audit` | 各执行任务加载审计 | `audit_id` |

## 审计与索引

所有业务导入表均保留原始来源字段。任务名称、分类、后续任务、追踪目标、文本任务 ID、对象引用和奖励引用均建立查询索引。SQLite 外键检查在每次自动验收中执行。
