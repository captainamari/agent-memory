from pathlib import Path

from .model import MemoryError, load_yaml, render_document
from .operations import base_meta, init_domain, transaction


def populate(root: Path):
    """Install only the explicit fictional fixture into a disposable clone."""
    init_domain(root, "parcels", "虚构包裹服务", "engineering")
    init_domain(root, "garden", "虚构温室", "general")
    dataset = load_yaml((root / "examples/demo-corpus.yaml").read_text(encoding="utf-8"))

    def change(stage):
        from .model import safe_path
        for item in dataset["documents"]:
            meta = base_meta(item["id"], item["title"], item["summary"], item["type"], item.get("domain"),
                             item.get("status", "active"), item.get("category"))
            for key in ("aliases", "symbols", "related"):
                meta[key] = item.get(key, [])
            meta["sources"] = [{"kind": "note", "ref": "examples/demo-corpus.yaml 中的虚构演示资料"}]
            path = safe_path(stage, item["path"])
            if path.exists():
                raise MemoryError("Demo refuses to overwrite existing content")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_document(meta, item["body"]), encoding="utf-8")
    transaction(root, change)
