from datetime import date
from pathlib import Path
import tempfile
import time
import unittest
import subprocess
import sys

try:
    import tkinter as tk
except ImportError:
    tk = None

from medkeep.service import MedKeepService
from medkeep.platform_support import enable_dpi_awareness

enable_dpi_awareness()


class UITests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"No graphical display: {error}")
        self.root.withdraw()
        self.temporary = tempfile.TemporaryDirectory()
        self.service = MedKeepService(Path(self.temporary.name))
        from medkeep.ui import MedKeepApp
        self.app = MedKeepApp(self.root, self.service)
        self.root.update()

    def tearDown(self):
        if hasattr(self, "app"):
            if not self.app.closed:
                self.wait_idle()
                self.app.close()
            self.temporary.cleanup()
        elif hasattr(self, "root"):
            self.root.destroy()

    def wait_idle(self):
        limit = time.monotonic() + 8
        while self.app.busy and time.monotonic() < limit:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        self.assertFalse(self.app.busy, "UI worker did not finish")

    def fill(self, title="Follow-up consultation"):
        self.app.patient.set("PT-1048")
        self.app.author.set("Clinician 07")
        self.app.record_title.set(title)
        self.app.notes.delete("1.0", "end")
        self.app.notes.insert("1.0", "Follow-up visit. Continue the current care plan.")
        self.root.update()

    def test_four_tabs_and_live_preview(self):
        self.assertEqual(len(self.app.tabs.tabs()), 4)
        self.assertTrue(all(not feedback.winfo_manager() for feedback in self.app._status_labels))
        self.fill()
        self.assertEqual(self.app.preview_patient.get(), "PT-1048")
        self.assertEqual(self.app.preview_title.get(), "Follow-up consultation")
        self.assertIn("Follow-up visit", self.app.preview_notes.get())

    def test_complete_native_workflow_and_archive(self):
        self.fill()
        self.app.enqueue()
        self.wait_idle()
        self.assertIsNone(self.app.last_error)
        self.assertEqual(self.service.pending_count, 1)
        self.assertEqual(self.app.patient.get(), "")
        self.assertEqual(self.app.author.get(), "Clinician 07")
        self.app.tabs.select(self.app.queue_page)
        self.root.update()
        self.assertEqual(len(self.app.queue_tree.get_children()), 1)
        self.app.process_next()
        self.wait_idle()
        self.assertEqual(self.service.record_count, 1)
        self.assertEqual(self.service.pending_count, 0)
        self.assertIsNone(self.service.report)
        self.app.verify()
        self.wait_idle()
        self.assertTrue(self.service.report.ok)
        self.assertEqual(len(self.app.check_tree.get_children()), 2)
        self.app.tabs.select(self.app.history_page)
        self.root.update()
        self.wait_idle()
        self.assertEqual(len(self.app.history_tree.get_children()), 1)
        self.assertIn("Follow-up visit", self.app.history_notes.get("1.0", "end"))
        self.app.archive_date.set(date.today().isoformat())
        self.app.export_archive()
        self.wait_idle()
        self.assertIsNotNone(self.app.last_archive)
        self.assertTrue(self.app.last_archive.exists())

    def test_validation_retains_draft(self):
        from medkeep.appearance import DANGER

        self.fill()
        self.app.visit_date.set("not a date")
        self.app.enqueue()
        self.wait_idle()
        self.assertIsNotNone(self.app.last_error)
        self.assertEqual(self.service.pending_count, 0)
        self.assertEqual(self.app.patient.get(), "PT-1048")
        self.assertIn("YYYY-MM-DD", self.app.status.get())
        feedback = self.app._status_labels[0]
        self.assertEqual(feedback.winfo_manager(), "grid")
        self.assertEqual(feedback["foreground"], DANGER)

    def test_history_gate_and_filter(self):
        self.app.tabs.select(self.app.history_page)
        self.root.update()
        self.assertIsNone(self.service.report)
        self.assertEqual(self.app.history_content.winfo_manager(), "")
        for title in ("Assessment", "Follow-up"):
            self.fill(title)
            self.app.enqueue()
            self.wait_idle()
            self.app.process_next()
            self.wait_idle()
        self.app.verify()
        self.wait_idle()
        self.app.history_search.set("assessment")
        self.root.update()
        self.assertEqual(len(self.app.history_tree.get_children()), 1)
        self.app.history_search.set("no match")
        self.root.update()
        self.assertEqual(len(self.app.history_tree.get_children()), 0)

    def test_duplicate_click_does_not_duplicate_request(self):
        self.fill()
        self.app.enqueue()
        self.app.enqueue()
        self.wait_idle()
        self.assertEqual(self.service.pending_count, 1)

    def test_failed_integrity_hides_history(self):
        self.fill()
        self.app.enqueue()
        self.wait_idle()
        self.app.process_next()
        self.wait_idle()
        self.service._state.chain.tail.link_hash = "f" * 64
        self.app.verify()
        self.wait_idle()
        self.assertFalse(self.service.report.ok)
        self.assertEqual(self.app.history_content.winfo_manager(), "")
        self.assertIn("failed", self.app.approval_title["text"])
        self.assertEqual(len(self.app.history_tree.get_children()), 0)

    def test_close_waits_for_current_save(self):
        self.fill()
        self.app.enqueue()
        self.app.close()
        until = time.monotonic() + 8
        while not self.app.closed and time.monotonic() < until:
            self.root.update()
            time.sleep(0.01)
        self.assertTrue(self.app.closed)
        reopened = MedKeepService(Path(self.temporary.name))
        try:
            self.assertEqual(reopened.pending_count, 1)
        finally:
            reopened.close()

    def test_visible_window_remains_responsive(self):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("visible_window_probe.py")),
             str(Path(self.temporary.name) / "visible-probe")],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


UITests = unittest.skipIf(tk is None, "Tkinter is not installed")(UITests)


if __name__ == "__main__":
    unittest.main()
