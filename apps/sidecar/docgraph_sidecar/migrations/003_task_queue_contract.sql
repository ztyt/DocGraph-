PRAGMA foreign_keys=ON;

ALTER TABLE task_queue
  ADD COLUMN retry_count INTEGER DEFAULT 0 NOT NULL;

UPDATE task_queue
SET task_status = 'queued'
WHERE task_status = 'pending';

UPDATE task_queue
SET retry_count = attempts
WHERE retry_count = 0 AND attempts > 0;

CREATE INDEX IF NOT EXISTS idx_task_queue_claim
  ON task_queue(task_status, priority, scheduled_at, created_at);

