-- 寻仙任务数据库查询示例
-- 多值关系保存在明细视图/表中；quest_full 只提供一任务版本一行的摘要。

-- 1. 按任务 ID 查询；重复 ID 会返回多个 version_no。
SELECT * FROM quest_full WHERE quest_id = 11257 ORDER BY version_no;

-- 2. 按名称模糊查询。
SELECT quest_id, version_no, quest_name, category_name, level_requirement
FROM quest_full
WHERE quest_name LIKE '%女儿国%'
ORDER BY quest_id, version_no;

-- 3. 按分类查询。
SELECT quest_id, version_no, quest_name, category_name
FROM quest_full
WHERE category_name = '【正传】'
ORDER BY quest_id, version_no;

-- 4. 查询由指定 NPC 接取或提交的任务。
SELECT quest_id, version_no, quest_name, endpoint_kind, object_id, object_name
FROM quest_npc_detail
WHERE object_type_id = 3 AND object_name = '戊阳子'
ORDER BY quest_id, version_no, endpoint_kind;

-- 5. 按地区查询带寻路目标的任务。
SELECT quest_id, version_no, quest_name, target_id, target_name, area_name
FROM quest_location_detail
WHERE area_name = '小桑村'
ORDER BY quest_id, version_no;

-- 6. 查询任务文本；允许一任务多行文本。
SELECT quest_id, quest_name, language, quest_description, hint_text
FROM quest_text_detail
WHERE quest_id = 2
ORDER BY text_row_id;

-- 7. 查询任务奖励；每个奖励槽位保持独立行。
SELECT quest_id, version_no, reward_group, slot_no,
       object_type_name, object_id, object_name, amount
FROM quest_reward_detail
WHERE quest_id = 2
ORDER BY reward_group, slot_no;

-- 8. 查询任务链、互斥和排斥关系。
SELECT from_quest_id, from_quest_name, relation_type,
       to_quest_id, to_quest_name, slot_no
FROM quest_relation_detail
WHERE from_quest_id = 1694
ORDER BY relation_type, slot_no;

-- 9. 查询未解决的标志位引用。
SELECT quest_id, version_no, reference_context, slot_no,
       object_type_id, object_id, comparison_code, comparison_value, reason
FROM unresolved_reference
ORDER BY quest_id, version_no, reference_context, slot_no;

-- 10. 查看全部原始版本冲突。
SELECT quest_id, version_no, quest_name, source_file, source_row
FROM quest
WHERE conflict_flag = 1
ORDER BY quest_id, version_no;
