"""Run synthetic reference-retrieval checks in an isolated temporary clone."""
import shutil
import tempfile
from pathlib import Path

from memorylib.demo import populate
from memorylib.evaluation import evaluate
from memorylib.model import json_text


def main():
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="agent-memory-demo-") as temporary:
        root = Path(temporary) / "vault"
        shutil.copytree(source, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "runs", ".memory.lock"))
        # Demonstration is isolated from the user's actual corpus.
        for section in ("domains", "global", "playbooks", "inbox", "archive"):
            shutil.rmtree(root / section)
            (root / section).mkdir()
        from memorylib.indexing import build_indices
        build_indices(root)
        populate(root)
        report = evaluate(root, root / "examples/demo-suite.yaml")
        print(json_text(report), end="")
        return int(any(not row["passed"] for row in report["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
