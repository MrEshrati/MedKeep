from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.package_submission import create_package


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()
        self.output = Path(self.temporary.name) / "output"
        for name in ("README.md", "run.py", "run.pyw", "requirements.txt"):
            (self.root / name).write_text("source", encoding="utf-8")
        for name in ("medkeep", "tests", "docs", "tools", "data", "archives", ".git", ".venv"):
            (self.root / name).mkdir()
        (self.root / "medkeep" / "__init__.py").write_text("", encoding="utf-8")
        (self.root / "medkeep" / "core.py").write_text("# source", encoding="utf-8")
        (self.root / "medkeep" / "__pycache__").mkdir()
        (self.root / "medkeep" / "__pycache__" / "core.pyc").write_bytes(b"cache")
        (self.root / "docs" / "guide.md").write_text("guide", encoding="utf-8")
        for name in ("data", "archives", ".git", ".venv"):
            (self.root / name / "private.txt").write_text("exclude this", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_official_filename(self):
        path = create_package(self.output, project_root=self.root, first_name="First", last_name="Last", student_number="12345")
        self.assertEqual(path.name, "DSAProject1_FirstLast_12345.zip")

    def test_source_has_code_and_docs_without_runtime_data(self):
        path = create_package(self.output, project_root=self.root, source=True)
        self.assertEqual(path.name, "MedKeep-source.zip")
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            self.assertIn("run.py", names)
            self.assertIn("medkeep/core.py", names)
            self.assertIn("docs/guide.md", names)
            for name in names:
                self.assertNotIn("private", name)
                self.assertNotIn("__pycache__", name)
                self.assertFalse(name.startswith(("data/", "archives/", ".git/", ".venv/")))
            self.assertIsNone(archive.testzip())

    def test_bad_identity_cannot_create_paths(self):
        for value in ("../name", "name/name", "name\\name", "a b", "", "x" * 41):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    create_package(self.output, project_root=self.root, first_name=value, last_name="Last", student_number="123")
        self.assertFalse(self.output.exists())

    def test_rebuild_replaces_only_the_generated_zip(self):
        path = create_package(self.output, project_root=self.root, source=True)
        (self.root / "README.md").write_text("updated", encoding="utf-8")
        rebuilt = create_package(self.output, project_root=self.root, source=True)
        self.assertEqual(path, rebuilt)
        with zipfile.ZipFile(rebuilt) as archive:
            self.assertEqual(archive.read("README.md"), b"updated")


if __name__ == "__main__":
    unittest.main()
