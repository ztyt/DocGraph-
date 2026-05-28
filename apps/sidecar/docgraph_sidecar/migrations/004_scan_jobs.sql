PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS scan_jobs (
  job_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  root_path TEXT NOT NULL,
  normalized_root_path TEXT NOT NULL,
  job_status TEXT DEFAULT 'queued' NOT NULL CHECK(job_status IN ('queued', 'running', 'paused', 'done', 'failed')),
  current_directory TEXT,
  scanned_count INTEGER DEFAULT 0 NOT NULL,
  failed_count INTEGER DEFAULT 0 NOT NULL,
  ignored_count INTEGER DEFAULT 0 NOT NULL,
  compute_hash INTEGER DEFAULT 0 NOT NULL,
  error_message TEXT,
  created_at TEXT,
  updated_at TEXT,
  started_at TEXT,
  finished_at TEXT,
  paused_at TEXT,
  FOREIGN KEY(task_id) REFERENCES task_queue(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_scan_jobs_status
ON scan_jobs(job_status, created_at);

CREATE INDEX IF NOT EXISTS idx_scan_jobs_task
ON scan_jobs(task_id);
