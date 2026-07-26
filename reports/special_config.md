# 特殊任务与功能配置导入报告

- 运行 ID：`20260724T132751Z`
- 纳入文件：18
- 普通任务表行数：8829 → 8829
- quest_pool：80 行
- special_quest_config：4317 行
- quest_feature_config：1607 行

所有未证实脚本语义均只保存原始列，没有写入核心任务字段。

| 文件 | 分类 | 目标表 | 加载行 | 可靠任务连接 | 状态 |
|---|---|---|---:|---:|---|
| `mb/quest/daily_dungeon.txt` | pool | `quest_pool` | 10 | 0 | 原值保留 |
| `mb/quest/dshd_guanfu.txt` | pool | `quest_pool` | 10 | 0 | 原值保留 |
| `mb/quest/dshd_paohuan.txt` | pool | `quest_pool` | 10 | 0 | 原值保留 |
| `mb/quest/dshd_xianpai.txt` | pool | `quest_pool` | 10 | 0 | 原值保留 |
| `mb/quest/fate_info.txt` | special | `special_quest_config` | 31 | 0 | 原值保留 |
| `mb/quest/hfl_paohuan.txt` | pool | `quest_pool` | 10 | 0 | 原值保留 |
| `mb/quest/i_reset_quest.txt` | feature | `quest_feature_config` | 1 | 0 | 原值保留 |
| `mb/quest/msh_guanfu.txt` | pool | `quest_pool` | 10 | 0 | 原值保留 |
| `mb/quest/msh_xianpai.txt` | pool | `quest_pool` | 10 | 0 | 原值保留 |
| `mb/quest/quest_additional_award.txt` | feature | `quest_feature_config` | 57 | 0 | 原值保留 |
| `mb/quest/quest_cartoon.txt` | feature | `quest_feature_config` | 2 | 2 | 原值保留 |
| `mb/quest/quest_define.txt` | special | `special_quest_config` | 77 | 0 | 原值保留 |
| `mb/quest/quest_extra_award.txt` | feature | `quest_feature_config` | 1 | 1 | 原值保留 |
| `mb/quest/quest_fastdispatch.txt` | feature | `quest_feature_config` | 1439 | 0 | 原值保留 |
| `mb/quest/quest_newlvl_exp.txt` | feature | `quest_feature_config` | 1 | 1 | 原值保留 |
| `mb/quest/quest_npc_chat.txt` | special | `special_quest_config` | 4209 | 0 | 原值保留 |
| `mb/quest/quest_quick_complete.txt` | feature | `quest_feature_config` | 106 | 106 | 原值保留 |
| `mb/quest/tth_paohuan.txt` | pool | `quest_pool` | 10 | 0 | 原值保留 |
