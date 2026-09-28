"""Report editorial progress from reviewed texts and documented exclusions.

This script never grants a review or approval. Run it after recording the
separate reviewer's decision and fingerprint for each completed article.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from release_gate import editorial_fingerprint

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def main():
    inventory = read(ROOT / "data/inventory.json")
    sources = {r["issue_number"]: r for r in inventory["items"] if r.get("issue_number")}
    exclusions_path = ROOT / "data/exclusions.json"
    exclusions = read(exclusions_path)["items"] if exclusions_path.exists() else []
    excluded = {r["issue_number"] for r in exclusions}
    if len(excluded) != len(exclusions) or not excluded.issubset(sources):
        raise ValueError("Duplicate or unknown exclusions.")
    rows = []
    seen = set()
    for path in sorted((ROOT / "content/en").glob("[0-9][0-9][0-9].json")):
        meta = read(path)
        number = meta["issue_number"]
        if number in seen or number in excluded or number not in sources:
            raise ValueError("Duplicate, excluded or unknown translated issue.")
        seen.add(number)
        body = path.with_suffix(".md").read_bytes()
        fingerprint = editorial_fingerprint(body, meta)
        reviewed = meta.get("assisted_review_status") == "passed"
        if reviewed and meta.get("assisted_review_hash") != fingerprint:
            raise ValueError(f"Stale assisted review for issue {number}.")
        accepted = meta.get("human_approval") == "approved"
        if accepted and meta.get("human_approval_hash") != fingerprint:
            raise ValueError(f"Stale human acceptance for issue {number}.")
        rows.append({
            "issue_number": number, "title": meta["title"],
            "author": meta["author"]["name"],
            "english_words": len(body.decode("utf-8-sig").split()),
            "assisted_review_status": meta.get("assisted_review_status", "pending"),
            "assisted_review_hash": meta.get("assisted_review_hash"),
            "human_approval": meta.get("human_approval", "pending"),
        })
    boundary_ids = {r["issue_number"] for r in inventory["items"]
                    if r.get("extraction_status") == "reviewed_source_boundaries"}
    boundary_files = sorted((ROOT / "evidence").glob("BOUNDARIES_*.json"))
    for path in boundary_files:
        report = read(path)
        for item in report.get("items", []):
            number = item["issue_number"]
            if number not in sources:
                raise ValueError("Unknown source boundary.")
            actual = hashlib.sha256(Path(sources[number]["source_file"]).read_bytes()).hexdigest()
            if item.get("source_sha256") != actual:
                raise ValueError(f"Source changed since boundary review: {number}.")
            boundary_ids.add(number)
    for item in exclusions:
        number = item["issue_number"]
        actual = hashlib.sha256(Path(sources[number]["source_file"]).read_bytes()).hexdigest()
        if item.get("source_sha256") != actual:
            raise ValueError(f"Source changed since scope decision: {number}.")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "priority": "text_first_preserve_original_images_defer_graphic_redesign",
        "translated_issues": len(rows),
        "independently_reviewed_issues": sum(r["assisted_review_status"] == "passed" for r in rows),
        "human_accepted_issues": sum(r["human_approval"] == "approved" for r in rows),
        "english_words": sum(r["english_words"] for r in rows),
        "reviewed_main_article_boundary_ids": sorted(boundary_ids - excluded),
        "excluded_non_article_issues": sorted(excluded),
        "numbered_issues_still_to_review_or_translate": sorted(set(sources) - seen - excluded),
        "source_inventory_snapshot": "data/inventory.json",
        "additional_source_boundary_reviews": [p.relative_to(ROOT).as_posix() for p in boundary_files],
        "exclusions": exclusions,
        "articles": rows,
    }
    for path, value in ((ROOT / "data/progress.json", report),
                        (ROOT / "evidence/REVIEW_FINGERPRINTS.json", rows)):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "translated_issues", "independently_reviewed_issues", "human_accepted_issues",
        "english_words", "excluded_non_article_issues")}))
if __name__ == "__main__":
    main()
