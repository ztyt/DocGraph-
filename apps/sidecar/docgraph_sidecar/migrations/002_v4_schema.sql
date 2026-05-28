PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS files (
  file_id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  normalized_path TEXT,
  filename TEXT NOT NULL,
  extension TEXT,
  size_bytes INTEGER,
  sha256 TEXT,
  source_type TEXT,
  created_time TEXT,
  modified_time TEXT,
  indexed_time TEXT,
  file_status TEXT DEFAULT 'discovered' NOT NULL,
  parse_status TEXT DEFAULT 'pending' NOT NULL,
  role_label TEXT,
  role_confidence REAL,
  sensitivity_level TEXT DEFAULT 'unknown' NOT NULL,
  cluster_id TEXT,
  last_error_code TEXT,
  deleted_flag INTEGER DEFAULT 0 NOT NULL,
  created_at TEXT,
  updated_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_files_normalized_path
  ON files(normalized_path)
  WHERE normalized_path IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_files_status
  ON files(file_status, parse_status, deleted_flag);

CREATE INDEX IF NOT EXISTS idx_files_sha256
  ON files(sha256)
  WHERE sha256 IS NOT NULL;

CREATE TABLE IF NOT EXISTS document_elements (
  element_id TEXT PRIMARY KEY,
  file_id TEXT NOT NULL,
  element_index INTEGER NOT NULL,
  element_type TEXT,
  page_no INTEGER,
  sheet_name TEXT,
  slide_no INTEGER,
  section_path TEXT,
  bbox_json TEXT,
  text TEXT,
  metadata_json TEXT,
  confidence REAL,
  FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_document_elements_file
  ON document_elements(file_id, element_index);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY,
  file_id TEXT NOT NULL,
  element_id TEXT,
  chunk_index INTEGER NOT NULL,
  chunk_type TEXT,
  page_no INTEGER,
  sheet_name TEXT,
  slide_no INTEGER,
  heading TEXT,
  section_path TEXT,
  text TEXT NOT NULL,
  token_count INTEGER,
  start_offset INTEGER,
  end_offset INTEGER,
  evidence_json TEXT,
  created_at TEXT,
  FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE,
  FOREIGN KEY(element_id) REFERENCES document_elements(element_id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_file_index
  ON chunks(file_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_chunks_file
  ON chunks(file_id);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
  file_id UNINDEXED,
  chunk_id UNINDEXED,
  filename,
  heading,
  text,
  tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS task_queue (
  task_id TEXT PRIMARY KEY,
  task_type TEXT NOT NULL,
  task_status TEXT DEFAULT 'pending' NOT NULL,
  priority INTEGER DEFAULT 100 NOT NULL,
  payload_json TEXT,
  attempts INTEGER DEFAULT 0 NOT NULL,
  max_attempts INTEGER DEFAULT 3 NOT NULL,
  last_error_code TEXT,
  last_error_message TEXT,
  scheduled_at TEXT,
  started_at TEXT,
  finished_at TEXT,
  created_at TEXT,
  updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_task_queue_ready
  ON task_queue(task_status, priority, scheduled_at, created_at);

CREATE TABLE IF NOT EXISTS parse_errors (
  error_id TEXT PRIMARY KEY,
  file_id TEXT,
  task_id TEXT,
  error_code TEXT NOT NULL,
  error_message TEXT,
  retryable INTEGER DEFAULT 0 NOT NULL,
  parser_name TEXT,
  details_json TEXT,
  created_at TEXT,
  FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE,
  FOREIGN KEY(task_id) REFERENCES task_queue(task_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_parse_errors_file
  ON parse_errors(file_id, created_at);

CREATE TABLE IF NOT EXISTS document_profiles (
  file_id TEXT PRIMARY KEY,
  central_idea TEXT,
  document_role TEXT,
  role_confidence REAL,
  project_entities_json TEXT,
  business_objects_json TEXT,
  time_scope TEXT,
  keywords_json TEXT,
  summary_short TEXT,
  summary_long TEXT,
  evidence_chunks_json TEXT,
  profile_confidence REAL,
  generated_by TEXT,
  updated_at TEXT,
  FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entities (
  entity_id TEXT PRIMARY KEY,
  entity_text TEXT NOT NULL,
  normalized_text TEXT,
  entity_type TEXT,
  confidence REAL,
  created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_entities_type_text
  ON entities(entity_type, normalized_text);

CREATE TABLE IF NOT EXISTS file_entities (
  file_id TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  evidence_chunk_id TEXT,
  evidence_text TEXT,
  confidence REAL,
  created_at TEXT,
  PRIMARY KEY(file_id, entity_id, evidence_chunk_id),
  FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE,
  FOREIGN KEY(entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE,
  FOREIGN KEY(evidence_chunk_id) REFERENCES chunks(chunk_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_file_entities_entity
  ON file_entities(entity_id, file_id);

CREATE TABLE IF NOT EXISTS relation_candidates (
  source_file_id TEXT NOT NULL,
  target_file_id TEXT NOT NULL,
  candidate_source TEXT NOT NULL,
  raw_score REAL,
  payload_json TEXT,
  created_at TEXT,
  PRIMARY KEY(source_file_id, target_file_id, candidate_source),
  FOREIGN KEY(source_file_id) REFERENCES files(file_id) ON DELETE CASCADE,
  FOREIGN KEY(target_file_id) REFERENCES files(file_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS edges (
  edge_id TEXT PRIMARY KEY,
  source_file_id TEXT NOT NULL,
  target_file_id TEXT NOT NULL,
  relation_score REAL NOT NULL,
  confidence TEXT,
  relation_type TEXT,
  score_breakdown_json TEXT,
  relation_reason TEXT,
  evidence_chunks_json TEXT,
  created_at TEXT,
  UNIQUE(source_file_id, target_file_id),
  FOREIGN KEY(source_file_id) REFERENCES files(file_id) ON DELETE CASCADE,
  FOREIGN KEY(target_file_id) REFERENCES files(file_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_edges_source_score
  ON edges(source_file_id, relation_score DESC);

CREATE TABLE IF NOT EXISTS eval_queries (
  query_id TEXT PRIMARY KEY,
  query_text TEXT NOT NULL,
  intent TEXT,
  expected_file_ids_json TEXT,
  expected_cluster_id TEXT,
  tags_json TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS eval_runs (
  run_id TEXT PRIMARY KEY,
  run_type TEXT,
  metrics_json TEXT,
  config_json TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS api_logs (
  log_id TEXT PRIMARY KEY,
  trace_id TEXT,
  endpoint TEXT,
  method TEXT,
  status_code INTEGER,
  elapsed_ms INTEGER,
  task_type TEXT,
  file_id TEXT,
  upload_chars INTEGER DEFAULT 0 NOT NULL,
  redacted INTEGER DEFAULT 0 NOT NULL,
  model_name TEXT,
  error_code TEXT,
  created_at TEXT,
  FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_api_logs_trace
  ON api_logs(trace_id);

CREATE INDEX IF NOT EXISTS idx_api_logs_created
  ON api_logs(created_at);

CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_id TEXT PRIMARY KEY,
  snapshot_type TEXT DEFAULT 'manual' NOT NULL,
  db_path TEXT NOT NULL,
  settings_path TEXT,
  size_bytes INTEGER,
  schema_version TEXT,
  status TEXT DEFAULT 'created' NOT NULL,
  error_message TEXT,
  created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_snapshots_created
  ON snapshots(created_at);

