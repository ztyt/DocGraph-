import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.core.scan_jobs import ScanJobError, ScanJobStore
from docgraph_sidecar.core.tasks import TaskQueue


class ScanJobStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.scan_root = Path(self.temp_dir.name) / "docs"
        self.scan_root.mkdir()
        self.store = ScanJobStore(data_dir=self.data_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_scan_job_enqueues_task(self) -> None:
        job = self.store.create(self.scan_root, compute_hash=True, priority=25)
        task = TaskQueue(data_dir=self.data_dir).get(job.task_id)

        self.assertTrue(job.job_id.startswith("scan-"))
        self.assertEqual(job.job_status, "queued")
        self.assertEqual(job.root_path, str(self.scan_root.resolve()))
        self.assertEqual(job.current_directory, str(self.scan_root.resolve()))
        self.assertEqual(job.scanned_count, 0)
        self.assertEqual(job.failed_count, 0)
        self.assertEqual(job.ignored_count, 0)
        self.assertTrue(job.compute_hash)
        self.assertIsNotNone(task)
        self.assertEqual(task.task_type, "scan_directory")
        self.assertEqual(task.priority, 25)
        self.assertEqual(
            task.payload,
            {
                "job_id": job.job_id,
                "root_path": str(self.scan_root.resolve()),
                "compute_hash": True,
            },
        )

    def test_get_returns_scan_job(self) -> None:
        job = self.store.create(self.scan_root)

        loaded = self.store.get(job.job_id)

        self.assertEqual(loaded, job)

    def test_pause_and_resume_updates_status(self) -> None:
        job = self.store.create(self.scan_root)

        paused = self.store.pause(job.job_id)
        task_after_pause = TaskQueue(data_dir=self.data_dir).get(job.task_id)
        resumed = self.store.resume(job.job_id)
        task_after_resume = TaskQueue(data_dir=self.data_dir).get(job.task_id)

        self.assertEqual(paused.job_status, "paused")
        self.assertIsNotNone(paused.paused_at)
        self.assertEqual(task_after_pause.scheduled_at, "9999-12-31T23:59:59+00:00")
        self.assertEqual(resumed.job_status, "queued")
        self.assertIsNone(resumed.paused_at)
        self.assertIsNone(task_after_resume.scheduled_at)

    def test_paused_scan_job_is_not_claimed(self) -> None:
        job = self.store.create(self.scan_root)
        self.store.pause(job.job_id)

        claimed = TaskQueue(data_dir=self.data_dir).claim_next(now="2026-05-28T00:00:00+00:00")

        self.assertIsNone(claimed)

    def test_invalid_root_path_errors(self) -> None:
        with self.assertRaises(ScanJobError):
            self.store.create(Path(self.temp_dir.name) / "missing")

    def test_missing_job_errors_on_pause(self) -> None:
        with self.assertRaises(ScanJobError):
            self.store.pause("missing")


if __name__ == "__main__":
    unittest.main()
