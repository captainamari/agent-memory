from __future__ import annotations

import datetime as dt
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from .indexing import build_indices
from .model import ROOTS, MemoryError, Store, json_text, render_document, safe_path, slug
from .validation import links, references, require_valid, unfinished, validate


def managed_files(root):
    result = {}
    for name in ROOTS:
        base = root / name
        if base.exists():
            for path in base.rglob("*"):
                safe_path(root, path.relative_to(root).as_posix())
                if path.is_file():
                    result[path.relative_to(root).as_posix()] = path.read_bytes()
    if (root / "INDEX.md").exists():
        result["INDEX.md"] = (root / "INDEX.md").read_bytes()
    return result


def transaction(root: Path, operation) -> dict:
    """Validate a staged copy, then replace changed files, rolling back ordinary I/O failures.

    A lock coordinates these CLIs. This is not an OS transaction or protection
    against power loss or editors that ignore the lock; use Git for recovery.
    """
    root = root.resolve()
    lock = root / ".memory.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise MemoryError("Another write is active; do not remove its lock while it runs") from exc
    os.close(fd)
    try:
        before = managed_files(root)
        with tempfile.TemporaryDirectory(prefix="agent-memory-stage-") as tmp:
            stage = Path(tmp) / "repo"
            # Ignore tooling at the repository root only. A domain may legitimately
            # contain attachments named data/ or runs/; never drop them from staging.
            shutil.copytree(root, stage, ignore=lambda directory, names:
                            set(names) & {".git", ".venv", ".memory.lock"} if Path(directory) == root else set())
            result = operation(stage) or {}
            build_indices(stage)
            _, issues = validate(stage)
            errors = [i for i in issues if i.severity == "error"]
            if errors:
                raise MemoryError("Staged change rejected:\n" + "\n".join(f"{i.path}: {i.message}" for i in errors))
            after = managed_files(stage)
            if managed_files(root) != before:
                raise MemoryError("Files changed outside the CLI while staging; retry from the new state")
            changed = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
            applied = []
            try:
                for relative in changed:
                    target = safe_path(root, relative)
                    applied.append(relative)
                    if relative in after:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        temp = target.with_name(".memory-write-" + target.name)
                        try:
                            temp.write_bytes(after[relative])
                            os.replace(temp, target)
                        finally:
                            temp.unlink(missing_ok=True)
                    elif target.exists():
                        target.unlink()
            except OSError:
                for relative in reversed(applied):
                    target = root / relative
                    if relative in before:
                        target.write_bytes(before[relative])
                    elif target.exists():
                        target.unlink()
                raise
            return {**result, "changed": changed, "warnings": [i.as_dict() for i in issues if i.severity == "warning"]}
    finally:
        lock.unlink(missing_ok=True)


def base_meta(identity, title, summary, type_, domain, status="active", category=None):
    today = dt.date.today().isoformat()
    result = {"id": identity, "title": title, "summary": summary, "type": type_, "domain": domain,
              "status": status, "created": today, "updated": today, "tags": [], "aliases": [],
              "symbols": [], "related": [], "sources": []}
    if category:
        result["category"] = category
    return result


def init_domain(root: Path, name: str, title: str, profile="general") -> dict:
    slug(name, "domain")

    def change(stage):
        store = Store(stage)
        if profile not in store.config["profiles"]:
            raise MemoryError(f"Unknown profile: {profile}")
        target = safe_path(stage, f"domains/{name}")
        if target.exists():
            raise MemoryError("Domain already exists; initialization never overwrites it")
        (target / "0-overview").mkdir(parents=True)
        info = {"name": name, "title": title, "profile": profile, "categories": store.config["profiles"][profile]}
        (target / "domain.json").write_text(json_text(info), encoding="utf-8")
        meta = base_meta(f"{name}-overview", title, "领域入口；业务资料尚待整理。", "overview", name, category="0-overview")
        meta["sources"] = [{"kind": "observation", "ref": "由 init_domain.py 创建的领域初始化状态"}]
        (target / "0-overview" / "overview.md").write_text(render_document(meta, "## 用途与边界\n\n此领域刚建立，尚未录入业务结论。首次整理时补充范围与常见问题。\n"), encoding="utf-8")
        return {"domain": name, "profile": profile}
    return transaction(root, change)


def new_memory(root: Path, title: str, summary: str, type_: str, domain=None, category=None) -> dict:
    def change(stage):
        store = Store(stage)
        if domain is not None:
            if domain not in store.domains:
                raise MemoryError("Initialize the domain first")
            if category not in store.domains[domain]["categories"] or type_ not in store.config["categories"].get(category, []):
                raise MemoryError("Choose an enabled category compatible with the document type")
        identity = "mem-" + uuid.uuid4().hex[:16]
        meta = base_meta(identity, title, summary, type_, domain, "candidate", category)
        body = "## 待整理\n\nTODO：补充正文、来源、适用条件和未知项。完成后再提升为有效知识。\n"
        path = f"inbox/{identity}.md"
        (stage / path).write_text(render_document(meta, body), encoding="utf-8")
        return {"id": identity, "path": path, "status": "candidate"}
    return transaction(root, change)


def impact(root: Path, identity: str) -> dict:
    store = require_valid(root)
    if identity not in store.by_id:
        raise MemoryError(f"Unknown ID: {identity}")
    target = store.by_id[identity]
    inbound = []
    for doc in store.documents:
        source_refs = [s.get("ref") for s in doc.meta["sources"] if s.get("kind") == "file"]
        if doc.id != identity and (identity in references(store, doc) or target.path in source_refs):
            history_only = (identity in doc.meta.get("supersedes", []) and identity not in doc.meta.get("related", [])
                            and target.path not in source_refs and not any(identity in link or target.path in link for link in links(doc.body)))
            inbound.append({"id": doc.id, "path": doc.path, "status": doc.meta["status"], "history_only": history_only})
    # Evals are not retrieval input. Report their identity references separately.
    eval_mentions = []
    for file in sorted((store.root / "evals").rglob("*.yaml")) if (store.root / "evals").exists() else []:
        if identity in file.read_text(encoding="utf-8"):
            eval_mentions.append(file.relative_to(store.root).as_posix())
    return {"id": identity, "path": target.path, "inbound": inbound, "eval_mentions": eval_mentions,
            "note": "Eval mentions are textual hints. Review semantic dependencies and external links separately."}


def manage(root: Path, identity: str, action: str, destination=None, apply=False) -> dict:
    report = impact(root, identity)
    if not apply:
        return {**report, "action": action, "applied": False}

    def change(stage):
        current_report = impact(stage, identity)
        store = require_valid(stage)
        doc = store.by_id[identity]
        source = stage / doc.path
        if action == "delete":
            if current_report["inbound"] or current_report["eval_mentions"]:
                raise MemoryError("Delete blocked by references; review and resolve them before retrying")
            source.unlink()
            return {"id": identity, "action": action, "applied": True}
        if action == "archive":
            if doc.meta["status"] != "active":
                raise MemoryError("Only active knowledge can be archived")
            if any(item["status"] == "active" and not item["history_only"] for item in current_report["inbound"]):
                raise MemoryError("Active documents still depend on this document; resolve them before archiving")
            target_path = f"archive/{doc.meta.get('domain') or 'shared'}/{identity}.md"
            doc.meta["status"] = "archived"
        elif action == "promote":
            if doc.meta["status"] != "candidate":
                raise MemoryError("Only inbox candidates can be promoted")
            if unfinished(doc.body) or not doc.meta["sources"]:
                raise MemoryError("Complete the body and sources before promoting")
            target_path = destination
            if not target_path:
                if not doc.meta.get("domain") or not doc.meta.get("category"):
                    raise MemoryError("Provide --to for shared knowledge, or set domain/category")
                target_path = f"domains/{doc.meta['domain']}/{doc.meta['category']}/{identity}.md"
            if target_path.split("/")[0] not in {"domains", "global", "playbooks"}:
                raise MemoryError("Promote into domains/, global/ or playbooks/")
            doc.meta["status"] = "active"
        elif action == "move":
            if not destination:
                raise MemoryError("move requires --to")
            target_path = destination
        else:
            raise MemoryError("Unknown maintenance action")
        if not isinstance(target_path, str) or not target_path.endswith(".md") or Path(target_path).name == "INDEX.md" or target_path.split("/")[0] not in ROOTS:
            raise MemoryError("Destination must be a document in a managed root")
        target = safe_path(stage, target_path)
        if target.exists():
            raise MemoryError("Destination already exists")
        # ID links survive relocation. Path links are not silently rewritten; report them first.
        doc.meta["updated"] = dt.date.today().isoformat()
        if target_path.startswith("domains/") and len(Path(target_path).parts) >= 4:
            doc.meta["category"] = Path(target_path).parts[2]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_document(doc.meta, doc.body), encoding="utf-8")
        source.unlink()
        return {"id": identity, "action": action, "path": target_path, "applied": True}
    return transaction(root, change)
