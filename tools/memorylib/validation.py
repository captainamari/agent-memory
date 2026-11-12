from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .model import ROOTS, TYPES, Document, MemoryError, Store, date_value, normalize, safe_path, slug


@dataclass
class Issue:
    severity: str
    code: str
    path: str
    message: str

    def as_dict(self):
        return asdict(self)


def prose(text: str) -> str:
    # Skip fenced and inline code; code examples are not live references.
    lines, fence, result = text.splitlines(), None, []
    for line in lines:
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None:
            result.append(re.sub(r"`+[^`]*`+", "", line))
    return "\n".join(result)


def anchors(body: str) -> set[str]:
    result, counts = set(), {}
    for line in prose(body).splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            name = normalize(match[1])
            name = re.sub(r"[^\w\s-]", "", name)
            name = re.sub(r"\s+", "-", name)
            count = counts.get(name, 0)
            counts[name] = count + 1
            result.add(f"{name}-{count}" if count else name)
    result.update(re.findall(r'<(?:a|span)\s+id=["\']([^"\']+)["\']', body))
    return result


def unfinished(body: str) -> bool:
    return bool(re.search(r"(?m)^\s*(?:[-*]\s*)?TODO(?:[:：\s]|$)", prose(body)))


def links(body: str) -> list[str]:
    text = prose(body)
    inline = re.findall(r"!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)", text)
    definitions = re.findall(r"^\s*\[[^\]\n]+\]:\s*(<[^>]+>|\S+)", text, re.M)
    return [x.strip("<>") for x in inline + definitions]


def resolve_link(store: Store, source_path: str, target: str) -> tuple[str | None, str]:
    if target.startswith("memory:"):
        identity, _, fragment = target[7:].partition("#")
        if identity not in store.by_id:
            raise MemoryError(f"Unknown document ID in link: {identity}")
        return store.by_id[identity].path, unquote(fragment)
    parsed = urlsplit(target)
    if parsed.scheme in {"http", "https", "mailto", "tel"}:
        return None, ""
    if parsed.scheme or parsed.netloc:
        raise MemoryError(f"Unsupported link scheme: {target}")
    if not parsed.path:
        destination = store.root / source_path
    elif parsed.path.startswith("/"):
        destination = store.root / unquote(parsed.path).lstrip("/")
    else:
        destination = (store.root / source_path).parent / unquote(parsed.path)
    resolved = destination.resolve()
    if not resolved.is_relative_to(store.root):
        raise MemoryError(f"Link escapes repository: {target}")
    relative = resolved.relative_to(store.root).as_posix()
    safe_path(store.root, relative)
    if not resolved.exists():
        raise MemoryError(f"Missing link target: {target}")
    return relative, unquote(parsed.fragment)


def references(store: Store, doc: Document) -> set[str]:
    result = set()
    for field in ("related", "supersedes"):
        values = doc.meta.get(field, [])
        if isinstance(values, list):
            result.update(v for v in values if isinstance(v, str))
    reverse = {d.path: d.id for d in store.documents if isinstance(d.id, str)}
    for target in links(doc.body):
        try:
            path, _ = resolve_link(store, doc.path, target)
            if path in reverse:
                result.add(reverse[path])
        except MemoryError:
            pass
    return result


def validate(root: Path, strict=False, check_indices=True, today=None) -> tuple[Store, list[Issue]]:
    store = Store(root)
    today = today or dt.date.today()
    issues = [Issue("error", "parse", p, m) for p, m in store.errors]

    def add(code, path, message, warning=False):
        issues.append(Issue("warning" if warning and not strict else "error", code, path, message))

    for name in ROOTS:
        if not (store.root / name).is_dir():
            add("root", name, "Managed directory is missing")
    seen_paths = {}
    for doc in store.documents:
        m, p = doc.meta, doc.path
        normalized = normalize(p)
        if normalized in seen_paths:
            add("path-collision", p, f"Case/Unicode collision with {seen_paths[normalized]}")
        seen_paths[normalized] = p
        for field in ("id", "title", "summary", "type", "status"):
            if not isinstance(m.get(field), str) or not m[field].strip():
                add("field", p, f"{field} must be nonempty text")
        try:
            slug(m.get("id"), "document id")
        except MemoryError as exc:
            add("id", p, str(exc))
        if not isinstance(m.get("type"), str) or m["type"] not in TYPES:
            add("type", p, "Unknown document type")
        status = m.get("status")
        if not isinstance(status, str) or status not in {"active", "candidate", "archived"}:
            add("status", p, "status must be active, candidate or archived")
        top = p.split("/")[0]
        required_status = "candidate" if top == "inbox" else "archived" if top == "archive" else "active"
        if status != required_status:
            add("placement", p, f"{top}/ requires status={required_status}")
        domain = m.get("domain")
        if domain is not None and (not isinstance(domain, str) or domain not in store.domains):
            add("domain", p, "domain must name an existing domain, or be null")
        if top in {"spec", "global", "playbooks"} and domain is not None:
            add("domain", p, f"{top}/ must have domain: null")
        if top == "spec" and m.get("type") != "rule":
            add("type", p, "spec/ contains governance rules only")
        if top == "domains":
            parts = Path(p).parts
            if len(parts) < 4 or parts[1] != domain:
                add("placement", p, "Use domains/<domain>/<category>/<document>.md")
            elif domain in store.domains:
                category = parts[2]
                allowed = store.domains[domain]["categories"]
                if category not in allowed or m.get("type") not in store.config["categories"].get(category, []):
                    add("category", p, "Document type/category is not enabled in domain.json")
                if m.get("category") != category:
                    add("category", p, "frontmatter category must match the path")
        for field in ("tags", "aliases", "symbols", "related", "supersedes"):
            values = m.get(field, [])
            if not isinstance(values, list) or any(not isinstance(x, str) or not x.strip() for x in values):
                add("field", p, f"{field} must be a list of nonempty strings")
            elif len(set(values)) != len(values):
                add("duplicate", p, f"Duplicate value in {field}")
        for field in ("related", "supersedes"):
            for identity in m.get(field, []) if isinstance(m.get(field, []), list) else []:
                if not isinstance(identity, str) or identity not in store.by_id:
                    add("reference", p, f"Unknown {field} ID: {identity}")
                elif identity == doc.id:
                    add("reference", p, f"Self-reference in {field}")
        dates = {}
        for field in ("created", "updated", "review_after"):
            if field == "review_after" and m.get(field) is None:
                continue
            try:
                dates[field] = date_value(m.get(field))
            except MemoryError as exc:
                add("date", p, f"{field}: {exc}")
        if "created" in dates and "updated" in dates and dates["updated"] < dates["created"]:
            add("date", p, "updated precedes created")
        if status == "active" and dates.get("review_after", today) < today:
            add("review-due", p, "Review is due; this does not establish that the knowledge is false", True)
        sources = m.get("sources")
        if not isinstance(sources, list):
            add("source", p, "sources must be a list")
        else:
            if status == "active" and not sources:
                add("source", p, "Active documents need a source or an explicit observation/note")
            for source in sources:
                if not isinstance(source, dict) or not isinstance(source.get("kind"), str) or source["kind"] not in {"url", "file", "note", "observation"} or not isinstance(source.get("ref"), str) or not source["ref"].strip():
                    add("source", p, "Each source needs kind and ref")
                elif source["kind"] == "file":
                    try:
                        path = safe_path(store.root, source["ref"])
                        if not path.is_file():
                            raise MemoryError("Missing source file")
                    except MemoryError as exc:
                        add("source", p, str(exc))
                elif source["kind"] == "url" and not re.match(r"^https?://[^/\s]+", source["ref"]):
                    add("source", p, "URL sources need http(s) URLs")
        if not doc.body.strip():
            add("body", p, "Empty body")
        if status == "active" and unfinished(doc.body):
            add("unfinished", p, "Active document contains TODO", True)
        if isinstance(m.get("summary"), str) and len(m["summary"]) > store.config["summary_max_chars"]:
            add("summary-length", p, "Summary exceeds configured character budget", True)
        if len(doc.body) > store.config["document_warn_chars"]:
            add("body-length", p, "Consider a scenario entry or independent subtopics; do not truncate reasoning", True)
        for target in links(doc.body):
            try:
                destination, fragment = resolve_link(store, p, target)
                if destination and fragment and destination.endswith(".md"):
                    raw = (store.root / destination).read_text(encoding="utf-8")
                    if fragment not in anchors(raw):
                        raise MemoryError(f"Missing anchor: {target}")
            except MemoryError as exc:
                add("link", p, str(exc))
    global_chars = sum(len(d.raw) for d in store.documents if d.path.startswith("global/"))
    if global_chars > store.config["global_max_chars"]:
        add("global-budget", "global/", f"{global_chars} characters exceeds total budget {store.config['global_max_chars']}")
    for name in store.domains:
        for child in (store.root / "domains" / name).iterdir():
            if child.is_dir() and child.name not in store.domains[name]["categories"]:
                add("category", f"domains/{name}/{child.name}", "Directory category is not enabled")
        if not any(d.path.startswith(f"domains/{name}/0-overview/") and d.meta.get("type") == "overview" for d in store.documents):
            add("overview", f"domains/{name}", "Domain needs an overview document")
    # User regression suites are repository contracts, never retrieval input.
    from .evaluation import load_suite
    case_root = store.root / "evals" / "cases"
    for case_file in sorted(case_root.rglob("*.yaml")) if case_root.exists() else []:
        try:
            suite = load_suite(case_file)
            for case in suite["cases"]:
                if case["status"] != "confirmed":
                    continue
                ids = case.get("required_ids", []) + [i for group in case.get("any_of", []) for i in group]
                if any(identity not in store.by_id for identity in ids):
                    raise MemoryError(f"{case['id']}: expected evidence ID is missing; review the label")
        except (MemoryError, OSError, UnicodeError) as exc:
            add("eval-schema", case_file.relative_to(store.root).as_posix(), str(exc))
    if check_indices and not store.errors:
        from .indexing import expected_indices
        try:
            for path, expected in expected_indices(store).items():
                file = store.root / path
                if not file.exists() or file.read_text(encoding="utf-8") != expected:
                    add("index-stale", path, "Run tools/build_index.py")
                if len(expected) > store.config["index_warn_chars"]:
                    add("index-length", path, "Index exceeds configured character budget", True)
                if file.exists():
                    for target in links(file.read_text(encoding="utf-8")):
                        try:
                            destination, fragment = resolve_link(store, path, target)
                            if destination and fragment and destination.endswith(".md"):
                                if fragment not in anchors((store.root / destination).read_text(encoding="utf-8")):
                                    raise MemoryError(f"Missing anchor: {target}")
                        except MemoryError as exc:
                            add("index-link", path, str(exc))
        except MemoryError as exc:
            add("index", "INDEX.md", str(exc))
    return store, issues


def require_valid(root: Path) -> Store:
    store, issues = validate(root)
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise MemoryError("Validation failed:\n" + "\n".join(f"{i.path}: {i.message}" for i in errors))
    return store
