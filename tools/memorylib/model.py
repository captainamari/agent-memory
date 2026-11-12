from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOTS = ("spec", "global", "domains", "playbooks", "inbox", "archive")
TYPES = {"overview", "concept", "rule", "decision", "runbook", "pitfall",
         "use-case", "design", "interface", "contract", "verification", "source"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
BEGIN = "<!-- memory:index:start -->"
END = "<!-- memory:index:end -->"


class MemoryError(ValueError):
    pass


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise MemoryError(f"YAML key must be unique text: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_yaml(text: str) -> Any:
    try:
        return yaml.load(text, Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        raise MemoryError(f"Invalid YAML: {exc}") from exc


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise MemoryError("Path must be a nonempty repository-relative POSIX path")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise MemoryError(f"Path escapes repository: {relative}")
    for part in path.parts:
        if re.search(r'[<>:"|?*\x00-\x1f]', part) or part.endswith((".", " ")):
            raise MemoryError(f"Non-portable path component: {part}")
        if part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
            raise MemoryError(f"Reserved path component: {part}")
    target = root / path
    for component in (target, *target.parents):
        if component == root.parent:
            break
        if component.is_symlink():
            raise MemoryError(f"Symlinks are not supported: {relative}")
    if not target.resolve().is_relative_to(root.resolve()):
        raise MemoryError(f"Path escapes repository: {relative}")
    return target


def slug(value: str, label="name") -> str:
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        raise MemoryError(f"Invalid {label}: use lowercase letters, digits, '-' or '_'")
    if value.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise MemoryError(f"Reserved filename: {value}")
    return value


def date_value(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        raise MemoryError("Use a date YYYY-MM-DD, not a timestamp")
    if isinstance(value, dt.date):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise MemoryError("Use a date YYYY-MM-DD")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise MemoryError(str(exc)) from exc


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"


def load_json(path: Path) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise MemoryError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    except (OSError, json.JSONDecodeError) as exc:
        raise MemoryError(f"Cannot load {path.name}: {exc}") from exc


def load_config(root: Path) -> dict:
    cfg = load_json(safe_path(root, "memory.config.json"))
    if not isinstance(cfg, dict) or type(cfg.get("schema_version")) is not int or cfg["schema_version"] != 1:
        raise MemoryError("Unsupported memory.config.json schema_version")
    for field in ("global_max_chars", "summary_max_chars", "document_warn_chars", "index_warn_chars",
                  "default_top_k", "max_context_chars"):
        if type(cfg.get(field)) is not int or cfg[field] <= 0:
            raise MemoryError(f"{field} must be a positive integer")
    categories, profiles = cfg.get("categories"), cfg.get("profiles")
    if not isinstance(categories, dict) or not categories or not isinstance(profiles, dict) or not profiles:
        raise MemoryError("categories and profiles must be nonempty objects")
    for name, types in categories.items():
        slug(name, "category")
        if not isinstance(types, list) or not types or any(not isinstance(t, str) or t not in TYPES for t in types):
            raise MemoryError(f"Invalid types for category {name}")
    if categories.get("0-overview") != ["overview"]:
        raise MemoryError("0-overview must allow exactly the overview type")
    for name, entries in profiles.items():
        slug(name, "profile")
        if not isinstance(entries, list) or any(not isinstance(c, str) or c not in categories for c in entries):
            raise MemoryError(f"Invalid categories for profile {name}")
        if len(set(entries)) != len(entries) or "0-overview" not in entries:
            raise MemoryError(f"Profile {name} needs unique categories including 0-overview")
    return cfg


@dataclass
class Document:
    path: str
    meta: dict
    body: str
    raw: str

    @property
    def id(self):
        return self.meta.get("id", "")


def parse_document(path: str, raw: str) -> Document:
    raw = raw.replace("\r\n", "\n")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|$)(.*)\Z", raw, re.S)
    if not match:
        raise MemoryError("Missing YAML frontmatter delimited by ---")
    meta = load_yaml(match[1])
    if not isinstance(meta, dict):
        raise MemoryError("Frontmatter must be a mapping")
    return Document(path, meta, match[2], raw)


def render_document(meta: dict, body: str) -> str:
    return "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).rstrip() + "\n---\n\n" + body.lstrip()


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def content_paths(root: Path) -> list[Path]:
    found = []
    for name in ROOTS:
        base = safe_path(root, name)
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            safe_path(root, path.relative_to(root).as_posix())
            if path.is_file() and path.suffix == ".md" and path.name != "INDEX.md":
                found.append(path)
    return found


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        if (self.root / ".memory.lock").exists():
            raise MemoryError("Memory is being written; retry after the writer completes")
        self.config = load_config(self.root)
        self.errors: list[tuple[str, str]] = []
        self.documents: list[Document] = []
        self.by_id: dict[str, Document] = {}
        self.domains: dict[str, dict] = {}
        domains = safe_path(self.root, "domains")
        if domains.exists():
            for directory in sorted(domains.iterdir()):
                if not directory.is_dir():
                    continue
                safe_path(self.root, directory.relative_to(self.root).as_posix())
                try:
                    slug(directory.name, "domain")
                    data = load_json(safe_path(self.root, f"domains/{directory.name}/domain.json"))
                    if not isinstance(data, dict) or data.get("name") != directory.name:
                        raise MemoryError("domain.json name must equal its directory")
                    if not isinstance(data.get("profile"), str) or data["profile"] not in self.config["profiles"]:
                        raise MemoryError("Unknown domain profile")
                    enabled = data.get("categories")
                    if (not isinstance(enabled, list) or any(not isinstance(c, str) or c not in self.config["categories"] for c in enabled)
                            or len(set(enabled)) != len(enabled) or "0-overview" not in enabled):
                        raise MemoryError("Invalid domain categories; include 0-overview")
                    if not isinstance(data.get("title"), str) or not data["title"].strip():
                        raise MemoryError("Domain title is required")
                    self.domains[directory.name] = data
                except MemoryError as exc:
                    self.errors.append((f"domains/{directory.name}/domain.json", str(exc)))
        for path in content_paths(self.root):
            relative = path.relative_to(self.root).as_posix()
            try:
                doc = parse_document(relative, path.read_text(encoding="utf-8"))
                self.documents.append(doc)
                if isinstance(doc.id, str):
                    if doc.id in self.by_id:
                        self.errors.append((relative, f"Duplicate id: {doc.id}"))
                    else:
                        self.by_id[doc.id] = doc
            except (MemoryError, UnicodeError) as exc:
                self.errors.append((relative, str(exc)))

    def fingerprint(self) -> str:
        values = [("memory.config.json", json_text(self.config))]
        values += [(f"domains/{k}/domain.json", json_text(v)) for k, v in self.domains.items()]
        values += [(d.path, d.raw) for d in self.documents]
        return hashlib.sha256(json_text(sorted(values)).encode()).hexdigest()
