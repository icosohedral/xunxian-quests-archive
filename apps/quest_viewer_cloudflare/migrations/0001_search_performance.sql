CREATE INDEX IF NOT EXISTS idx_web_quest_level_order
ON web_quest(
    (level_requirement IS NULL),
    level_requirement,
    quest_id
);

CREATE INDEX IF NOT EXISTS idx_web_quest_area_level_order
ON web_quest(
    root_area_name,
    (level_requirement IS NULL),
    level_requirement,
    quest_id
);

CREATE INDEX IF NOT EXISTS idx_web_quest_category_level_order
ON web_quest(
    main_category_name,
    (level_requirement IS NULL),
    level_requirement,
    quest_id
);

CREATE INDEX IF NOT EXISTS idx_web_quest_subcategory_level_order
ON web_quest(
    main_category_name,
    sub_category_name,
    (level_requirement IS NULL),
    level_requirement,
    quest_id
);

DROP INDEX IF EXISTS idx_web_quest_area;
DROP INDEX IF EXISTS idx_web_quest_category;
