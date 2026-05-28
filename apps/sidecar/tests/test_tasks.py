import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.core.tasks import TaskQueue, TaskQueueError


class TaskQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.queue = TaskQueue(data_dir=self.data_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_enqueue_and_get_task(self) -> None:
        task = self.queue.enqueue(
            "scan_directory",
            payload={"root": "C:/docs"},
            priority=20,
            max_attempts=4,
            task_id="task-fixed",
        )

        loaded = self.queue.get(task.task_id)

        self.assertEqual(task.task_status, "queued")
        self.assertEqual(task.retry_count, 0)
        self.assertEqual(task.payload, {"root": "C:/docs"})
        self.assertEqual(task.priority, 20)
        self.assertEqual(task.max_attempts, 4)
        self.assertEqual(loaded, task)

    def test_claim_next_respects_priority_and_schedule(self) -> None:
        self.queue.enqueue(
            "scan_directory",
            priority=50,
            task_id="task-low",
            scheduled_at="2026-01-01T00:00:00+00:00",
        )
        self.queue.enqueue(
            "scan_directory",
            priority=5,
            task_id="task-high",
            scheduled_at="2030-01-01T00:00:00+00:00",
        )
        self.queue.enqueue(
            "scan_directory",
            priority=10,
            task_id="task-ready",
            scheduled_at="2026-01-01T00:00:00+00:00",
        )

        claimed = self.queue.claim_next(now="2026-05-28T00:00:00+00:00")

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.task_id, "task-ready")
        self.assertEqual(claimed.task_status, "running")
        self.assertIsNotNone(claimed.started_at)

    def test_claim_next_can_filter_by_task_type(self) -> None:
        self.queue.enqueue("profile_build", priority=1, task_id="task-profile")
        self.queue.enqueue("scan_directory", priority=10, task_id="task-scan")

        claimed = self.queue.claim_next(task_type="scan_directory")

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.task_id, "task-scan")

    def test_complete_marks_task_done(self) -> None:
        task = self.queue.enqueue("scan_directory")
        claimed = self.queue.claim_next()
        self.assertEqual(claimed.task_id, task.task_id)

        completed = self.queue.complete(task.task_id)

        self.assertEqual(completed.task_status, "done")
        self.assertIsNotNone(completed.finished_at)
        self.assertIsNone(completed.last_error_code)

    def test_fail_requeues_until_max_attempts_then_fails(self) -> None:
        task = self.queue.enqueue("scan_directory", max_attempts=2)
        self.queue.claim_next()

        retry = self.queue.fail(
            task.task_id,
            error_code="SCAN_ERROR",
            error_message="first failure",
            retryable=True,
        )

        self.assertEqual(retry.task_status, "queued")
        self.assertEqual(retry.retry_count, 1)
        self.assertEqual(retry.last_error_code, "SCAN_ERROR")

        self.queue.claim_next()
        failed = self.queue.fail(
            task.task_id,
            error_code="SCAN_ERROR",
            error_message="second failure",
            retryable=True,
        )

        self.assertEqual(failed.task_status, "failed")
        self.assertEqual(failed.retry_count, 2)
        self.assertIsNotNone(failed.finished_at)

    def test_non_retryable_failure_marks_failed_immediately(self) -> None:
        task = self.queue.enqueue("scan_directory", max_attempts=3)
        self.queue.claim_next()

        failed = self.queue.fail(
            task.task_id,
            error_code="PERMISSION_DENIED",
            error_message="cannot read folder",
            retryable=False,
        )

        self.assertEqual(failed.task_status, "failed")
        self.assertEqual(failed.retry_count, 1)

    def test_list_filters_by_status(self) -> None:
        done = self.queue.enqueue("scan_directory", task_id="done-task")
        queued = self.queue.enqueue("scan_directory", task_id="queued-task")
        self.queue.claim_next()
        self.queue.complete(done.task_id)

        queued_tasks = self.queue.list(status="queued")

        self.assertEqual([task.task_id for task in queued_tasks], [queued.task_id])

    def test_unknown_task_errors(self) -> None:
        with self.assertRaises(TaskQueueError):
            self.queue.complete("missing")

    def test_migration_adds_retry_count_column(self) -> None:
        initialize_database(data_dir=self.data_dir)
        connection = connect(data_dir=self.data_dir)
        try:
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(task_queue)").fetchall()
            }
        finally:
            connection.close()

        self.assertIn("retry_count", columns)


if __name__ == "__main__":
    unittest.main()

