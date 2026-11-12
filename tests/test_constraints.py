import ast
from pathlib import Path
import unittest


class AssignmentConstraintTests(unittest.TestCase):
    def test_core_uses_no_ready_made_collections_or_hashing_library(self):
        root = Path(__file__).resolve().parents[1] / "medkeep"
        for name in ("structures", "hashing", "records", "chain", "storage", "service"):
            tree = ast.parse((root / f"{name}.py").read_text(encoding="utf-8"))
            annotations = tuple(id(child) for parent in ast.walk(tree)
                                if isinstance(parent, (ast.arg, ast.AnnAssign)) and parent.annotation is not None
                                for child in ast.walk(parent.annotation))
            for node in ast.walk(tree):
                if id(node) in annotations:
                    continue
                with self.subTest(module=name, line=getattr(node, "lineno", 0)):
                    self.assertNotIsInstance(node, (ast.List, ast.ListComp, ast.Dict, ast.DictComp, ast.Set, ast.SetComp))
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertNotIn(alias.name.split(".")[0], ("queue", "collections", "hashlib", "array", "numpy"))
                    if isinstance(node, ast.ImportFrom):
                        self.assertNotIn((node.module or "").split(".")[0], ("queue", "collections", "hashlib", "array", "numpy"))
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, ("list", "dict", "set", "deque", "Queue", "LifoQueue", "PriorityQueue"))


if __name__ == "__main__":
    unittest.main()
