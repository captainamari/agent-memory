from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .model import Document, MemoryError, normalize
from .validation import references, require_valid


def terms(text: str) -> set[str]:
    text = normalize(text)
    result = set(re.findall(r"[a-z0-9_]+", text))
    for group in re.findall(r"[\u3400-\u9fff]+", text):
        result.update(group[i:i + 2] for i in range(len(group) - 1))
        if len(group) == 1:
            result.add(group)
    return result


def score(query: str, doc: Document) -> float:
    q = normalize(query.strip())
    if not q:
        return 0
    m = doc.meta
    exact = [doc.id, *m.get("symbols", [])]
    total = 100.0 if any(q == normalize(x) for x in exact) else 0.0
    fields = [(m["title"], 8), (" ".join(m.get("aliases", [])), 7),
              (" ".join(m.get("symbols", [])), 7), (" ".join(m.get("tags", [])), 5),
              (m["summary"], 4), (doc.body, 1)]
    query_terms = terms(q)
    for text, weight in fields:
        if q in normalize(text):
            total += weight * 2
        if query_terms:
            total += weight * len(query_terms & terms(text)) / len(query_terms)
    return total


def evidence(doc: Document, reason: str, value=None) -> dict:
    return {"id": doc.id, "path": doc.path, "title": doc.meta["title"],
            "type": doc.meta["type"], "domain": doc.meta.get("domain"),
            "status": doc.meta["status"], "review_after": doc.meta.get("review_after"),
            "sources": doc.meta["sources"], "reason": reason, "score": value,
            "sha256": hashlib.sha256(doc.raw.encode()).hexdigest(), "content": doc.raw}


def recall(root: Path, query: str, domain=None, top_k=None, include_archived=False,
           include_spec=False, cross_domain_related=False, max_chars=None) -> dict:
    store = require_valid(root)
    if not isinstance(query, str) or not query.strip():
        raise MemoryError("Query must be nonempty")
    if domain is not None and domain not in store.domains:
        raise MemoryError(f"Unknown domain: {domain}")
    top_k = store.config["default_top_k"] if top_k is None else top_k
    budget = store.config["max_context_chars"] if max_chars is None else max_chars
    if type(top_k) is not int or top_k <= 0 or type(budget) is not int or budget <= 0:
        raise MemoryError("top_k and max_chars must be positive integers")

    def allowed(doc, related=False):
        top = doc.path.split("/")[0]
        if top == "inbox" or doc.meta["status"] == "candidate":
            return False
        if top == "spec" and not include_spec:
            return False
        if doc.meta["status"] == "archived" and not include_archived:
            return False
        if top == "global":
            return False  # Supplied in the always-loaded channel, not ranked hits.
        return domain is None or doc.meta.get("domain") in {None, domain} or (related and cross_domain_related)

    globals_ = [d for d in store.documents if d.path.startswith("global/")]
    used = sum(len(d.raw) for d in globals_)
    if used > budget:
        raise MemoryError("Context budget cannot fit global memory; increase budget or shorten global/")
    ranked = sorted(((score(query, d), d) for d in store.documents if allowed(d)), key=lambda pair: (-pair[0], pair[1].id))
    hits, omitted, selected = [], [], set()
    for value, doc in ranked:
        if value <= 0 or len(hits) >= top_k:
            break
        if used + len(doc.raw) > budget:
            omitted.append({"id": doc.id, "reason": "context_budget"})
            continue
        used += len(doc.raw)
        selected.add(doc.id)
        hits.append(evidence(doc, "query", round(value, 4)))
    related_evidence = []
    # One hop only, with a shared budget; reading one domain does not silently search all others.
    for item in list(hits):
        for identity in sorted(references(store, store.by_id[item["id"]])):
            doc = store.by_id[identity]
            if identity in selected or not allowed(doc, related=True):
                continue
            if used + len(doc.raw) > budget:
                omitted.append({"id": identity, "reason": "related_context_budget"})
                continue
            used += len(doc.raw)
            selected.add(identity)
            related_evidence.append(evidence(doc, "related:" + item["id"]))
    return {"schema_version": 1, "retriever": "lexical-v1", "corpus_sha256": store.fingerprint(),
            "query": query, "domain": domain, "include_archived": include_archived,
            "include_spec": include_spec, "cross_domain_related": cross_domain_related,
            "top_k": top_k, "max_chars": budget, "used_chars": used,
            "global": [evidence(d, "always-loaded") for d in globals_], "hits": hits,
            "related": related_evidence, "omitted": omitted,
            "answer_status": "not_generated",
            "note": "Character budget, not a token estimate. Scores measure lexical overlap, not truth."}


def read_document(root: Path, identity: str, include_inbox=False, include_archived=False):
    store = require_valid(root)
    if identity not in store.by_id:
        raise MemoryError(f"Unknown document ID: {identity}")
    doc = store.by_id[identity]
    if doc.meta["status"] == "candidate" and not include_inbox:
        raise MemoryError("Candidate document: use --include-inbox for explicit maintenance")
    if doc.meta["status"] == "archived" and not include_archived:
        raise MemoryError("Archived document: use --include-archived for explicit history queries")
    return evidence(doc, "explicit-id")
