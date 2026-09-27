ALTER TABLE web_quest ADD COLUMN sort_position INTEGER;

WITH ranked AS MATERIALIZED (
    SELECT quest_id,
           ROW_NUMBER() OVER (
               ORDER BY level_requirement IS NULL,
                        level_requirement,
                        quest_id
           ) AS position
    FROM web_quest
)
UPDATE web_quest
SET sort_position = (
    SELECT position
    FROM ranked
    WHERE ranked.quest_id = web_quest.quest_id
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_web_quest_sort_position
ON web_quest(sort_position);
