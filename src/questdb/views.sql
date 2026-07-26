PRAGMA foreign_keys = ON;

CREATE INDEX IF NOT EXISTS idx_category_name ON quest_category(category_name);
CREATE INDEX IF NOT EXISTS idx_npc_name ON quest_npc(quest_npc_name);
CREATE INDEX IF NOT EXISTS idx_item_name ON item(item_name);
CREATE INDEX IF NOT EXISTS idx_area_name ON area(area_name);
CREATE INDEX IF NOT EXISTS idx_target_name ON quest_target(target_name);

DROP VIEW IF EXISTS quest_full;
CREATE VIEW quest_full AS
SELECT
    q.quest_id,
    q.version_no,
    q.conflict_flag,
    q.quest_name,
    q.category_id,
    c.category_name,
    q.level_requirement,
    q.max_level,
    q.accept_object_type,
    q.accept_object_id,
    CASE q.accept_object_type
      WHEN 2 THEN (SELECT qi.quest_item_name FROM quest_item qi WHERE qi.quest_item_id=q.accept_object_id)
      WHEN 3 THEN (SELECT n.quest_npc_name FROM quest_npc n WHERE n.quest_npc_id=q.accept_object_id)
      WHEN 5 THEN (SELECT q2.quest_name FROM quest q2 WHERE q2.quest_id=q.accept_object_id ORDER BY q2.version_no LIMIT 1)
      WHEN 6 THEN (SELECT a.attribute_name FROM quest_attribute a WHERE a.attribute_id=q.accept_object_id)
      WHEN 13 THEN (SELECT e.quest_event_name FROM quest_event e WHERE e.quest_event_id=q.accept_object_id)
      WHEN 15 THEN (SELECT cp.camp_name FROM quest_camp cp WHERE cp.camp_id=q.accept_object_id)
    END AS accept_object_name,
    q.submit_object_type,
    q.submit_object_id,
    CASE q.submit_object_type
      WHEN 2 THEN (SELECT qi.quest_item_name FROM quest_item qi WHERE qi.quest_item_id=q.submit_object_id)
      WHEN 3 THEN (SELECT n.quest_npc_name FROM quest_npc n WHERE n.quest_npc_id=q.submit_object_id)
      WHEN 5 THEN (SELECT q2.quest_name FROM quest q2 WHERE q2.quest_id=q.submit_object_id ORDER BY q2.version_no LIMIT 1)
      WHEN 6 THEN (SELECT a.attribute_name FROM quest_attribute a WHERE a.attribute_id=q.submit_object_id)
      WHEN 13 THEN (SELECT e.quest_event_name FROM quest_event e WHERE e.quest_event_id=q.submit_object_id)
      WHEN 15 THEN (SELECT cp.camp_name FROM quest_camp cp WHERE cp.camp_id=q.submit_object_id)
    END AS submit_object_name,
    q.next_quest_id,
    q.tracking_target_id,
    t.target_name,
    lc.area_id,
    COALESCE(ar.area_name, lc.fallback_area_name) AS area_name,
    (SELECT COUNT(*) FROM quest_text tx WHERE tx.source_quest_id=q.quest_id) AS text_row_count,
    (SELECT COUNT(*) FROM quest_condition qc WHERE qc.quest_id=q.quest_id AND qc.version_no=q.version_no) AS condition_count,
    (SELECT COUNT(*) FROM quest_objective qo WHERE qo.quest_id=q.quest_id AND qo.version_no=q.version_no) AS objective_count,
    (SELECT COUNT(*) FROM quest_reward qr WHERE qr.quest_id=q.quest_id AND qr.version_no=q.version_no) AS reward_count,
    (SELECT COUNT(*) FROM quest_relation rel WHERE rel.from_quest_id=q.quest_id AND rel.from_version_no=q.version_no) AS outgoing_relation_count,
    q.source_file,
    q.source_row,
    q.run_id
FROM quest q
LEFT JOIN quest_category c ON c.category_id=q.category_id
LEFT JOIN quest_target t ON t.target_id=q.tracking_target_id
LEFT JOIN location_context lc ON lc.target_id=t.target_id
LEFT JOIN area ar ON ar.area_id=lc.area_id;

DROP VIEW IF EXISTS quest_text_detail;
CREATE VIEW quest_text_detail AS
SELECT
    tx.text_row_id,
    tx.source_quest_id AS quest_id,
    tx.linked_quest_id,
    q.quest_name,
    tx.language,
    tx.accept_dialogue,
    tx.quest_description,
    tx.hint_text,
    tx.progress_dialogue,
    tx.completion_dialogue,
    tx.source_file,
    tx.source_row,
    tx.run_id
FROM quest_text tx
LEFT JOIN quest q
  ON q.quest_id=tx.linked_quest_id AND q.version_no=1;

DROP VIEW IF EXISTS quest_npc_detail;
CREATE VIEW quest_npc_detail AS
SELECT
    ep.quest_id,
    ep.version_no,
    q.quest_name,
    ep.endpoint_kind,
    ep.object_type_id,
    ot.object_type_name,
    ep.object_id,
    CASE ep.object_type_id
      WHEN 2 THEN (SELECT qi.quest_item_name FROM quest_item qi WHERE qi.quest_item_id=ep.object_id)
      WHEN 3 THEN (SELECT n.quest_npc_name FROM quest_npc n WHERE n.quest_npc_id=ep.object_id)
    END AS object_name,
    ep.resolved,
    ep.source_file,
    ep.source_row,
    ep.run_id
FROM quest_endpoint ep
JOIN quest q ON q.quest_id=ep.quest_id AND q.version_no=ep.version_no
JOIN object_type ot ON ot.object_type_id=ep.object_type_id;

DROP VIEW IF EXISTS quest_reward_detail;
CREATE VIEW quest_reward_detail AS
SELECT
    qr.reward_id,
    qr.quest_id,
    qr.version_no,
    q.quest_name,
    qr.reward_group,
    qr.slot_no,
    qr.object_type_id,
    ot.object_type_name,
    qr.object_id,
    CASE qr.object_type_id
      WHEN 2 THEN (SELECT i.item_name FROM item i WHERE i.item_id=qr.object_id)
      WHEN 3 THEN (SELECT n.quest_npc_name FROM quest_npc n WHERE n.quest_npc_id=qr.object_id)
      WHEN 5 THEN (SELECT q2.quest_name FROM quest q2 WHERE q2.quest_id=qr.object_id ORDER BY q2.version_no LIMIT 1)
      WHEN 6 THEN (SELECT a.attribute_name FROM quest_attribute a WHERE a.attribute_id=qr.object_id)
      WHEN 13 THEN (SELECT e.quest_event_name FROM quest_event e WHERE e.quest_event_id=qr.object_id)
      WHEN 15 THEN (SELECT cp.camp_name FROM quest_camp cp WHERE cp.camp_id=qr.object_id)
    END AS object_name,
    qr.amount,
    qr.item_resolved,
    qr.source_file,
    qr.source_row,
    qr.run_id
FROM quest_reward qr
JOIN quest q ON q.quest_id=qr.quest_id AND q.version_no=qr.version_no
JOIN object_type ot ON ot.object_type_id=qr.object_type_id;

DROP VIEW IF EXISTS quest_relation_detail;
CREATE VIEW quest_relation_detail AS
SELECT
    rel.relation_id,
    rel.from_quest_id,
    rel.from_version_no,
    q1.quest_name AS from_quest_name,
    rel.to_quest_id,
    (SELECT q2.quest_name FROM quest q2 WHERE q2.quest_id=rel.to_quest_id ORDER BY q2.version_no LIMIT 1) AS to_quest_name,
    rel.relation_type,
    rel.slot_no,
    rel.source_file,
    rel.source_row,
    rel.run_id
FROM quest_relation rel
JOIN quest q1 ON q1.quest_id=rel.from_quest_id AND q1.version_no=rel.from_version_no;

DROP VIEW IF EXISTS quest_location_detail;
CREATE VIEW quest_location_detail AS
SELECT
    q.quest_id,
    q.version_no,
    q.quest_name,
    t.target_id,
    t.target_name,
    t.resource_key,
    lc.area_id,
    COALESCE(a.area_name, lc.fallback_area_name) AS area_name,
    a.resource_key AS area_resource_key,
    lc.area_resolved,
    t.source_file,
    t.source_row,
    t.run_id
FROM quest q
JOIN quest_target t ON t.target_id=q.tracking_target_id
LEFT JOIN location_context lc ON lc.target_id=t.target_id
LEFT JOIN area a ON a.area_id=lc.area_id;
