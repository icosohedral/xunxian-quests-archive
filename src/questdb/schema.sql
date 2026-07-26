PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS build_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS load_audit (
    audit_id INTEGER PRIMARY KEY,
    task_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    source_file TEXT,
    run_id TEXT NOT NULL,
    loaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_category (
    category_id INTEGER PRIMARY KEY,
    category_name TEXT,
    sort_order INTEGER,
    source_file TEXT,
    source_row INTEGER,
    raw_value TEXT,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_identity (
    quest_id INTEGER PRIMARY KEY,
    version_count INTEGER NOT NULL DEFAULT 1,
    has_conflict INTEGER NOT NULL DEFAULT 0 CHECK (has_conflict IN (0, 1))
);

CREATE TABLE IF NOT EXISTS quest (
    quest_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    conflict_flag INTEGER NOT NULL DEFAULT 0 CHECK (conflict_flag IN (0, 1)),
    quest_name TEXT NOT NULL,
    category_id INTEGER,
    max_level INTEGER,
    level_requirement INTEGER,
    accept_object_type INTEGER,
    accept_object_id INTEGER,
    submit_object_type INTEGER,
    submit_object_id INTEGER,
    next_quest_id INTEGER,
    tracking_target_id INTEGER,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (quest_id, version_no),
    UNIQUE (source_file, source_row, run_id),
    FOREIGN KEY (quest_id) REFERENCES quest_identity(quest_id),
    FOREIGN KEY (category_id) REFERENCES quest_category(category_id)
);

CREATE TABLE IF NOT EXISTS quest_text (
    text_row_id INTEGER PRIMARY KEY,
    source_quest_id INTEGER NOT NULL,
    linked_quest_id INTEGER,
    language TEXT NOT NULL DEFAULT 'zh-CN',
    accept_dialogue TEXT,
    voice_key TEXT,
    quest_description TEXT,
    hint_text TEXT,
    progress_dialogue TEXT,
    completion_dialogue TEXT,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    UNIQUE (source_file, source_row, run_id),
    FOREIGN KEY (linked_quest_id) REFERENCES quest_identity(quest_id)
);

CREATE TABLE IF NOT EXISTS object_type (
    object_type_id INTEGER PRIMARY KEY,
    object_type_name TEXT NOT NULL,
    route_table TEXT,
    index_no INTEGER,
    is_known_route INTEGER NOT NULL CHECK (is_known_route IN (0, 1)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_item (
    quest_item_id INTEGER PRIMARY KEY,
    quest_item_name TEXT NOT NULL,
    version_count INTEGER NOT NULL DEFAULT 1,
    conflict_flag INTEGER NOT NULL DEFAULT 0 CHECK (conflict_flag IN (0, 1)),
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_item_source (
    quest_item_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    quest_item_name TEXT NOT NULL,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (quest_item_id, version_no),
    FOREIGN KEY (quest_item_id) REFERENCES quest_item(quest_item_id)
);

CREATE TABLE IF NOT EXISTS quest_event (
    quest_event_id INTEGER PRIMARY KEY,
    quest_event_name TEXT NOT NULL,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_attribute (
    attribute_id INTEGER PRIMARY KEY,
    attribute_name TEXT NOT NULL,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_camp (
    camp_id INTEGER PRIMARY KEY,
    camp_name TEXT NOT NULL,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_npc (
    quest_npc_id INTEGER PRIMARY KEY,
    quest_npc_name TEXT NOT NULL,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_target (
    target_id INTEGER PRIMARY KEY,
    target_name TEXT NOT NULL,
    area_name TEXT,
    resource_key TEXT,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_endpoint (
    quest_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    endpoint_kind TEXT NOT NULL CHECK (endpoint_kind IN ('accept', 'submit')),
    object_type_id INTEGER NOT NULL,
    object_id INTEGER NOT NULL,
    resolved INTEGER NOT NULL CHECK (resolved IN (0, 1)),
    source_column_type INTEGER NOT NULL,
    source_column_id INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (quest_id, version_no, endpoint_kind),
    FOREIGN KEY (quest_id, version_no) REFERENCES quest(quest_id, version_no),
    FOREIGN KEY (object_type_id) REFERENCES object_type(object_type_id)
);

CREATE TABLE IF NOT EXISTS item (
    item_id INTEGER PRIMARY KEY,
    item_name TEXT NOT NULL,
    canonical_source TEXT NOT NULL,
    source_priority INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS item_source (
    item_id INTEGER NOT NULL,
    source_table TEXT NOT NULL,
    item_name TEXT NOT NULL,
    source_priority INTEGER NOT NULL,
    is_canonical INTEGER NOT NULL CHECK (is_canonical IN (0, 1)),
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (item_id, source_table),
    FOREIGN KEY (item_id) REFERENCES item(item_id)
);

CREATE TABLE IF NOT EXISTS quest_condition (
    condition_id INTEGER PRIMARY KEY,
    quest_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    condition_kind TEXT NOT NULL CHECK (condition_kind IN ('precondition', 'required_object')),
    slot_no INTEGER NOT NULL,
    object_type_id INTEGER,
    object_id INTEGER,
    comparison_code INTEGER,
    comparison_value INTEGER,
    raw_group_json TEXT NOT NULL CHECK (json_valid(raw_group_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    UNIQUE (quest_id, version_no, condition_kind, slot_no),
    FOREIGN KEY (quest_id, version_no) REFERENCES quest(quest_id, version_no)
);

CREATE TABLE IF NOT EXISTS quest_objective (
    objective_id INTEGER PRIMARY KEY,
    quest_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    slot_no INTEGER NOT NULL,
    object_type_id INTEGER,
    object_id INTEGER,
    amount INTEGER,
    raw_group_json TEXT NOT NULL CHECK (json_valid(raw_group_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    UNIQUE (quest_id, version_no, slot_no),
    FOREIGN KEY (quest_id, version_no) REFERENCES quest(quest_id, version_no)
);

CREATE TABLE IF NOT EXISTS quest_precondition_group (
    group_id INTEGER PRIMARY KEY,
    group_name TEXT NOT NULL,
    group_mode TEXT,
    object_types_json TEXT NOT NULL CHECK (json_valid(object_types_json)),
    object_ids_json TEXT NOT NULL CHECK (json_valid(object_ids_json)),
    comparison_codes_json TEXT NOT NULL CHECK (json_valid(comparison_codes_json)),
    comparison_values_json TEXT NOT NULL CHECK (json_valid(comparison_values_json)),
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_reward (
    reward_id INTEGER PRIMARY KEY,
    quest_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    reward_group TEXT NOT NULL CHECK (reward_group IN ('fixed', 'general')),
    slot_no INTEGER NOT NULL,
    object_type_id INTEGER NOT NULL,
    object_id INTEGER,
    amount INTEGER,
    item_resolved INTEGER NOT NULL DEFAULT 0 CHECK (item_resolved IN (0, 1)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    UNIQUE (quest_id, version_no, reward_group, slot_no),
    FOREIGN KEY (quest_id, version_no) REFERENCES quest(quest_id, version_no),
    FOREIGN KEY (object_type_id) REFERENCES object_type(object_type_id)
);

CREATE TABLE IF NOT EXISTS quest_relation (
    relation_id INTEGER PRIMARY KEY,
    from_quest_id INTEGER NOT NULL,
    from_version_no INTEGER NOT NULL,
    to_quest_id INTEGER,
    relation_type TEXT NOT NULL,
    slot_no INTEGER,
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    FOREIGN KEY (from_quest_id, from_version_no) REFERENCES quest(quest_id, version_no)
);

CREATE TABLE IF NOT EXISTS character (
    character_id INTEGER PRIMARY KEY,
    character_name TEXT NOT NULL,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS character_call_profile (
    call_profile_id INTEGER PRIMARY KEY,
    speaker_profile_name TEXT NOT NULL,
    variant_count INTEGER NOT NULL,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS character_call_variant (
    call_profile_id INTEGER NOT NULL,
    variant_no INTEGER NOT NULL,
    call_text TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (call_profile_id, variant_no),
    FOREIGN KEY (call_profile_id)
      REFERENCES character_call_profile(call_profile_id)
);

CREATE TABLE IF NOT EXISTS quest_item_ex (
    quest_item_ex_id INTEGER PRIMARY KEY,
    quest_item_ex_name TEXT NOT NULL,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_event_ex (
    quest_event_ex_id INTEGER PRIMARY KEY,
    quest_event_ex_name TEXT NOT NULL,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS object_mapping (
    mapping_id INTEGER PRIMARY KEY,
    mapping_kind TEXT NOT NULL,
    source_object_type TEXT NOT NULL,
    source_object_id INTEGER,
    target_object_type TEXT NOT NULL,
    target_object_id INTEGER,
    group_index INTEGER,
    weight INTEGER,
    source_resolved INTEGER NOT NULL CHECK (source_resolved IN (0, 1)),
    target_resolved INTEGER NOT NULL CHECK (target_resolved IN (0, 1)),
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS area (
    area_id INTEGER PRIMARY KEY,
    area_name TEXT NOT NULL,
    resource_key TEXT,
    version_count INTEGER NOT NULL DEFAULT 1,
    conflict_flag INTEGER NOT NULL DEFAULT 0 CHECK (conflict_flag IN (0, 1)),
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS area_source (
    area_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    area_name TEXT NOT NULL,
    resource_key TEXT,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (area_id, version_no),
    FOREIGN KEY (area_id) REFERENCES area(area_id)
);

CREATE TABLE IF NOT EXISTS province (
    province_id INTEGER PRIMARY KEY,
    province_name TEXT NOT NULL,
    resource_key TEXT,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scene (
    scene_id INTEGER PRIMARY KEY,
    scene_name TEXT,
    resource_key TEXT,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS location_context (
    target_id INTEGER PRIMARY KEY,
    area_id INTEGER,
    fallback_area_name TEXT,
    area_resolved INTEGER NOT NULL CHECK (area_resolved IN (0, 1)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    FOREIGN KEY (target_id) REFERENCES quest_target(target_id),
    FOREIGN KEY (area_id) REFERENCES area(area_id)
);

CREATE TABLE IF NOT EXISTS quest_pool (
    config_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    linked_quest_id INTEGER,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    FOREIGN KEY (linked_quest_id) REFERENCES quest_identity(quest_id)
);

CREATE TABLE IF NOT EXISTS special_quest_config (
    config_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    linked_quest_id INTEGER,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    FOREIGN KEY (linked_quest_id) REFERENCES quest_identity(quest_id)
);

CREATE TABLE IF NOT EXISTS quest_feature_config (
    config_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    linked_quest_id INTEGER,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    FOREIGN KEY (linked_quest_id) REFERENCES quest_identity(quest_id)
);

CREATE TABLE IF NOT EXISTS unresolved_reference (
    unresolved_id INTEGER PRIMARY KEY,
    quest_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    reference_context TEXT NOT NULL,
    slot_no INTEGER NOT NULL,
    object_type_id INTEGER NOT NULL,
    object_id INTEGER,
    comparison_code INTEGER,
    comparison_value INTEGER,
    reason TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL,
    FOREIGN KEY (quest_id, version_no) REFERENCES quest(quest_id, version_no)
);

CREATE TABLE IF NOT EXISTS external_dependency (
    dependency_id INTEGER PRIMARY KEY,
    dependency_kind TEXT NOT NULL,
    expected_path TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    impact TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quest_name ON quest(quest_name);
CREATE INDEX IF NOT EXISTS idx_quest_category ON quest(category_id);
CREATE INDEX IF NOT EXISTS idx_quest_next ON quest(next_quest_id);
CREATE INDEX IF NOT EXISTS idx_quest_target ON quest(tracking_target_id);
CREATE INDEX IF NOT EXISTS idx_text_source_quest ON quest_text(source_quest_id);
CREATE INDEX IF NOT EXISTS idx_text_linked_quest ON quest_text(linked_quest_id);
CREATE INDEX IF NOT EXISTS idx_endpoint_object ON quest_endpoint(object_type_id, object_id);
CREATE INDEX IF NOT EXISTS idx_reward_quest ON quest_reward(quest_id, version_no);
CREATE INDEX IF NOT EXISTS idx_reward_object ON quest_reward(object_type_id, object_id);
CREATE INDEX IF NOT EXISTS idx_condition_object ON quest_condition(object_type_id, object_id);
CREATE INDEX IF NOT EXISTS idx_objective_object ON quest_objective(object_type_id, object_id);
CREATE INDEX IF NOT EXISTS idx_relation_from ON quest_relation(from_quest_id, from_version_no);
CREATE INDEX IF NOT EXISTS idx_relation_to ON quest_relation(to_quest_id);
CREATE INDEX IF NOT EXISTS idx_mapping_source ON object_mapping(source_object_type, source_object_id);
CREATE INDEX IF NOT EXISTS idx_mapping_target ON object_mapping(target_object_type, target_object_id);
CREATE INDEX IF NOT EXISTS idx_character_call_text ON character_call_variant(call_text);
CREATE INDEX IF NOT EXISTS idx_location_area ON location_context(area_id);
CREATE INDEX IF NOT EXISTS idx_unresolved_type ON unresolved_reference(object_type_id, object_id);
