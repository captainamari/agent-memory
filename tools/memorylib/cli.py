from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .evaluation import evaluate
from .indexing import build_indices
from .model import MemoryError, date_value, json_text, load_json
from .operations import impact, init_domain, manage, new_memory, transaction
from .retrieval import read_document, recall
from .validation import validate


def main(command):
    parser = argparse.ArgumentParser(description=f"agent-memory: {command}")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2], help="Memory repository root")
    if command == "check":
        parser.add_argument("--strict", action="store_true", help="Promote style and review-due warnings to errors")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--as-of", type=date_value, help="Reproducible review date YYYY-MM-DD")
    elif command == "index":
        parser.add_argument("--check", action="store_true")
    elif command == "init":
        parser.add_argument("name")
        parser.add_argument("--title")
        parser.add_argument("--profile", default="general")
    elif command == "new":
        parser.add_argument("--title", required=True)
        parser.add_argument("--summary", required=True)
        parser.add_argument("--type", required=True)
        parser.add_argument("--domain")
        parser.add_argument("--category")
    elif command == "manage":
        parser.add_argument("action", choices=["impact", "move", "promote", "archive", "delete"])
        parser.add_argument("id")
        parser.add_argument("--to")
        parser.add_argument("--apply", action="store_true", help="Apply a validated mutation; otherwise show impact only")
    elif command == "recall":
        parser.add_argument("query")
        parser.add_argument("--domain")
        parser.add_argument("--top-k", type=int)
        parser.add_argument("--max-chars", type=int)
        parser.add_argument("--include-archived", action="store_true")
        parser.add_argument("--include-spec", action="store_true")
        parser.add_argument("--cross-domain-related", action="store_true")
    elif command == "read":
        parser.add_argument("id")
        parser.add_argument("--include-inbox", action="store_true")
        parser.add_argument("--include-archived", action="store_true")
    elif command == "eval":
        parser.add_argument("--suite", type=Path, required=True)
        parser.add_argument("--baseline", type=Path)
        parser.add_argument("--output", type=Path, help="Create a new report; existing reports are never overwritten")
    args = parser.parse_args()
    try:
        code = 0
        if command == "check":
            store, issues = validate(args.root, args.strict, today=args.as_of)
            result = {"documents": len(store.documents), "domains": len(store.domains),
                      "errors": sum(i.severity == "error" for i in issues),
                      "warnings": sum(i.severity == "warning" for i in issues), "issues": [i.as_dict() for i in issues]}
            code = 1 if result["errors"] else 0
            if not args.json:
                print(f"Documents: {result['documents']}; domains: {result['domains']}; errors: {result['errors']}; warnings: {result['warnings']}")
                for i in issues:
                    print(f"{i.severity.upper()} [{i.code}] {i.path}: {i.message}")
                return code
        elif command == "index":
            if args.check:
                result = {"stale": build_indices(args.root, check=True)}
                code = int(bool(result["stale"]))
            else:
                result = transaction(args.root, lambda stage: {"operation": "build-index"})
        elif command == "init":
            result = init_domain(args.root, args.name, args.title or args.name, args.profile)
        elif command == "new":
            result = new_memory(args.root, args.title, args.summary, args.type, args.domain, args.category)
        elif command == "manage":
            result = impact(args.root, args.id) if args.action == "impact" else manage(args.root, args.id, args.action, args.to, args.apply)
        elif command == "recall":
            result = recall(args.root, args.query, args.domain, args.top_k, args.include_archived,
                            args.include_spec, args.cross_domain_related, args.max_chars)
        elif command == "read":
            result = read_document(args.root, args.id, args.include_inbox, args.include_archived)
        elif command == "eval":
            suite = args.suite if args.suite.is_absolute() else args.root / args.suite
            baseline = load_json(args.baseline) if args.baseline else None
            result = evaluate(args.root, suite, baseline)
            code = int(any(not c["passed"] for c in result["cases"]))
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("x", encoding="utf-8") as stream:
                    stream.write(json_text(result))
        print(json_text(result), end="")
        return code
    except (MemoryError, OSError) as exc:
        print(json_text({"error": str(exc)}), file=sys.stderr, end="")
        return 2
