from __future__ import annotations

import datetime as dt
from pathlib import Path

from .model import MemoryError, load_yaml
from .retrieval import recall
from .validation import require_valid


def load_suite(path: Path) -> dict:
    suite = load_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(suite, dict) or type(suite.get("schema_version")) is not int or suite["schema_version"] != 1 or suite.get("suite_kind") not in ("user", "synthetic"):
        raise MemoryError("Suite needs schema_version: 1 and suite_kind: user|synthetic")
    cases = suite.get("cases")
    if not isinstance(cases, list):
        raise MemoryError("cases must be a list")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"] or case["id"] in seen:
            raise MemoryError("Case IDs must be unique nonempty strings")
        seen.add(case["id"])
        if case.get("status") not in ("candidate", "confirmed", "retired"):
            raise MemoryError(f"{case['id']}: invalid case status")
        if not isinstance(case.get("query"), str) or not case["query"].strip():
            raise MemoryError(f"{case['id']}: query is required")
        for field in ("required_ids", "forbidden_ids", "answer_requirements", "forbidden_claims"):
            values = case.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values) or len(values) != len(set(values)):
                raise MemoryError(f"{case['id']}: {field} must contain unique nonempty strings")
        groups = case.get("any_of", [])
        if not isinstance(groups, list) or any(not isinstance(g, list) or not g or any(not isinstance(v, str) or not v for v in g) for g in groups):
            raise MemoryError(f"{case['id']}: any_of must contain nonempty ID groups")
        if type(case.get("expect_no_results", False)) is not bool:
            raise MemoryError("expect_no_results must be boolean")
        if case.get("expect_no_results") and (case.get("required_ids") or groups):
            raise MemoryError("No-result case cannot require evidence")
        if not case.get("expect_no_results") and not case.get("required_ids") and not groups:
            raise MemoryError("Each case needs required evidence or expect_no_results")
        if set(case.get("required_ids", [])) & set(case.get("forbidden_ids", [])):
            raise MemoryError("Required and forbidden evidence overlap")
        for flag in ("include_archived", "include_spec", "cross_domain_related"):
            if type(case.get(flag, False)) is not bool:
                raise MemoryError(f"{flag} must be boolean")
        if case.get("domain") is not None and (not isinstance(case["domain"], str) or not case["domain"]):
            raise MemoryError("domain must be nonempty text or null")
        for limit in ("top_k", "max_chars"):
            if limit in case and (type(case[limit]) is not int or case[limit] <= 0):
                raise MemoryError(f"{limit} must be a positive integer")
    return suite


def evaluate(root: Path, suite_path: Path, baseline=None) -> dict:
    suite = load_suite(suite_path)
    store = require_valid(root)
    cases = [c for c in suite["cases"] if c["status"] == "confirmed"]
    outcomes, fingerprints = [], set()
    for case in cases:
        expected = case.get("required_ids", []) + [identity for group in case.get("any_of", []) for identity in group]
        if any(identity not in store.by_id for identity in expected):
            raise MemoryError(f"{case['id']}: expected evidence ID is missing from corpus; review the test label")
        result = recall(root, case["query"], domain=case.get("domain"), top_k=case.get("top_k"),
                        include_archived=case.get("include_archived", False), include_spec=case.get("include_spec", False),
                        cross_domain_related=case.get("cross_domain_related", False), max_chars=case.get("max_chars"))
        fingerprints.add(result["corpus_sha256"])
        # Only delivered content counts. No credit for omitted, path-only or nonexistent evidence.
        evidence = result["hits"] + result["related"] + result["global"]
        actual = {item["id"] for item in evidence if item["content"].strip()}
        required = set(case.get("required_ids", []))
        missing = sorted(required - actual)
        forbidden = sorted(actual & set(case.get("forbidden_ids", [])))
        missed_groups = [group for group in case.get("any_of", []) if not actual.intersection(group)]
        no_results_ok = not case.get("expect_no_results") or not result["hits"] and not result["related"]
        passed = not missing and not forbidden and not missed_groups and no_results_ok
        outcomes.append({"id": case["id"], "passed": passed, "actual_ids": sorted(actual),
                         "missing_ids": missing, "forbidden_ids": forbidden, "missed_any_of": missed_groups,
                         "recall": len(required & actual) / len(required) if required else None,
                         "no_results_ok": no_results_ok, "used_chars": result["used_chars"],
                         "omitted": result["omitted"], "answer_status": "not_evaluated"})
    report = {"schema_version": 1, "suite_kind": suite["suite_kind"], "evaluator": "reference-recall-v1",
              "evaluated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "status": "evaluated" if outcomes else "not_evaluated", "case_count": len(outcomes),
              "excluded_cases": len(suite["cases"]) - len(outcomes),
              "pass_rate": sum(c["passed"] for c in outcomes) / len(outcomes) if outcomes else None,
              "corpus_sha256": sorted(fingerprints), "cases": outcomes, "regressions": [],
              "note": "Reference lexical retriever only; this is not an agent reasoning or answer-quality score."}
    if baseline is not None:
        if baseline.get("evaluator") != report["evaluator"] or baseline.get("suite_kind") != report["suite_kind"]:
            raise MemoryError("Baseline evaluator/suite_kind is incompatible")
        old = {c["id"]: c["passed"] for c in baseline.get("cases", [])}
        report["regressions"] = [c["id"] for c in outcomes if old.get(c["id"]) is True and not c["passed"]]
        report["removed_cases"] = sorted(set(old) - {c["id"] for c in outcomes})
    return report
