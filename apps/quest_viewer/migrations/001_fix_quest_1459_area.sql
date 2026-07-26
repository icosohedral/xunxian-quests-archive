BEGIN IMMEDIATE;

-- 原始 quest_target 2703 将任务 1459 错标为“乌鸡国·上崖郡”。
-- 保留 raw_value 作为原始证据，只修正用于应用查询的结构化字段。
UPDATE quest_target
SET area_name = '云梦山',
    raw_values_json = json_set(
        raw_values_json,
        '$[8]', '云梦山',
        '$[9]', '云梦山'
    )
WHERE target_id = 2703;

UPDATE location_context
SET area_id = 210,
    fallback_area_name = '云梦山',
    area_resolved = 1
WHERE target_id = 2703;

COMMIT;
