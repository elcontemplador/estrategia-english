"""Fail-closed release checks. No network access and no source mutations.

Fingerprint contract v1: SHA-256 of the UTF-8 canonical JSON payload
{"contract":"estrategia-editorial-v1","markdown_sha256":SHA256(exact Markdown bytes),
 "editorial_metadata":all original metadata except the documented workflow fields}.
JSON keys are sorted recursively; ensure_ascii=False; separators=(",",":").
Unknown metadata fields are included. Original dates, authors, notes, title,
description, provenance, topics and genre are editorial inputs.

Set assisted_review_hash only after reviewing this fingerprint. Set
human_approval_hash only after explicit human acceptance of this fingerprint.
The generator never creates either approval on the operator's behalf.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

CONTRACT = "estrategia-editorial-v1"
WORKFLOW_FIELDS = frozenset({
    "human_approval", "translation_date", "assisted_review_date",
    "human_approval_date", "english_publication_date", "english_modified_date",
    "publication_date", "translated_at", "reviewed_at", "approved_at",
    "published_at", "updated_at", "created_at", "reviewed_by", "approved_by",
    "review_notes", "approval_notes",
})
MAX_ROBOTS_EVIDENCE_AGE = timedelta(hours=24)


def is_workflow_field(key: str) -> bool:
    return (
        key in WORKFLOW_FIELDS
        or key.endswith(("_status", "_approval", "_hash", "_sha256"))
        or key.startswith(("assisted_review_", "human_approval_"))
    )


def editorial_fingerprint(markdown_bytes: bytes, metadata: dict) -> str:
    editorial = {key: value for key, value in metadata.items()
                 if not is_workflow_field(key)}
    payload = {
        "contract": CONTRACT,
        "markdown_sha256": hashlib.sha256(markdown_bytes).hexdigest(),
        "editorial_metadata": editorial,
    }
    serialised = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                            separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def iso_date(value: object, field: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{field} must be a persisted YYYY-MM-DD date.")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} is not a valid date.") from error


def validate_article_release(metadata: dict, markdown_bytes: bytes,
                             previous_english_date: str | None = None) -> str:
    """Return the validated fingerprint; never mutate metadata or infer dates."""
    issue = metadata.get("issue_number", "?")
    if metadata.get("human_approval") != "approved":
        raise ValueError(f"Issue {issue}: human editorial acceptance is pending.")
    if metadata.get("assisted_review_status") != "passed":
        raise ValueError(f"Issue {issue}: assisted bilingual review is pending.")
    if not metadata.get("original_url"):
        raise ValueError(f"Issue {issue}: original URL is unresolved.")
    original = iso_date(metadata.get("original_date"), "original_date")
    publication = iso_date(metadata.get("english_publication_date"),
                           "english_publication_date")
    if publication < original:
        raise ValueError(f"Issue {issue}: English publication predates its Spanish original.")
    if previous_english_date and metadata["english_publication_date"] != previous_english_date:
        raise ValueError(f"Issue {issue}: English first-publication date cannot change.")
    if metadata.get("english_modified_date") is not None:
        modified = iso_date(metadata["english_modified_date"], "english_modified_date")
        if modified < publication:
            raise ValueError(f"Issue {issue}: modified date precedes first publication.")
    fingerprint = editorial_fingerprint(markdown_bytes, metadata)
    if metadata.get("assisted_review_hash") != fingerprint:
        raise ValueError(f"Issue {issue}: assisted review does not cover the current text and metadata.")
    if metadata.get("human_approval_hash") != fingerprint:
        raise ValueError(f"Issue {issue}: human approval does not cover the current text and metadata.")
    return fingerprint


def previous_publication_dates(output: Path) -> dict[str, str]:
    """Use the last generated public catalogue to guard persisted article dates."""
    if not (output / "build-manifest.json").is_file():
        return {}
    manifest = json.loads((output / "build-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("mode") != "public":
        raise ValueError("Existing public output has an unexpected build mode.")
    catalogue_path = output / "catalog.json"
    if not catalogue_path.is_file():
        raise ValueError("Existing public output has no catalogue; preserve it for recovery.")
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    previous = {}
    for article in catalogue.get("articles", []):
        value = article.get("english_publication_date")
        iso_date(value, "previous english_publication_date")
        previous[str(article["id"])] = value
    return previous


def _gptbot_disallows_prefix(body: str, prefix: str) -> bool:
    """Conservative support for ordinary robots groups, not complex wildcards.

    A specific GPTBot group must disallow the whole site path. Any Allow rule
    that could reopen this path makes the evidence insufficient. Unsupported
    wildcard/terminal patterns also fail rather than asserting compliance.
    """
    groups = []
    agents = []
    rules = []
    has_rules = False

    def finish():
        if agents:
            groups.append((list(agents), list(rules)))

    for line in body.lstrip("\ufeff").splitlines():
        if not line.strip():
            finish()
            agents, rules, has_rules = [], [], False
            continue
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if has_rules:
                finish()
                agents, rules, has_rules = [], [], False
            agents.append(value.lower())
        elif agents:
            if key in {"allow", "disallow"}:
                rules.append((key, value))
            has_rules = True
    finish()
    relevant = [rule for agents, rules in groups if "gptbot" in agents for rule in rules]
    if not relevant:
        return False
    if any("*" in path or "$" in path for _, path in relevant):
        return False
    if any(kind == "allow" and path and
           (prefix.startswith(path) or path.startswith(prefix))
           for kind, path in relevant):
        return False
    return any(kind == "disallow" and path and prefix.startswith(path)
               for kind, path in relevant)


def validate_training_policy(config: dict, project_root: Path,
                             now: datetime | None = None) -> dict:
    """Validate a choice without suggesting that robots grants indexing.

    For subpath opt-out, origin_robots_evidence names a JSON file within
    evidence/ with url, final_url, http_status, content_type, retrieved_at,
    body and body_sha256. The response must be a <=24h-old verified snapshot
    of the exact HTTPS origin /robots.txt, whose GPTBot group blocks the site.
    """
    policy = config.get("training_policy")
    if policy not in {"allow", "disallow"}:
        raise ValueError("Resolve training crawler policy before public release.")
    base = urlsplit(config["base_url"])
    if base.scheme != "https" or not base.netloc or base.query or base.fragment:
        raise ValueError("Public base_url must be an HTTPS origin/path without query or fragment.")
    if policy == "allow":
        return {"policy": "allow", "scope": "no_GPTBot_opt_out_requested",
                "indexing_guaranteed": False}
    prefix = base.path.rstrip("/") + "/"
    if prefix == "/":
        return {"policy": "disallow", "scope": "generated_origin_robots",
                "crawler": "GPTBot", "indexing_guaranteed": False}
    reference = config.get("origin_robots_evidence")
    if not isinstance(reference, str) or not reference:
        raise ValueError("GPTBot opt-out on a project subpath needs verified origin /robots.txt evidence; the project robots.txt is ineffective.")
    evidence_root = (project_root / "evidence").resolve()
    evidence_path = (project_root / reference).resolve()
    if not evidence_path.is_relative_to(evidence_root):
        raise ValueError("Origin robots evidence must be inside the project's evidence directory.")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    expected = urlunsplit((base.scheme, base.netloc, "/robots.txt", "", ""))
    if evidence.get("url") != expected or evidence.get("final_url") != expected:
        raise ValueError("Robots evidence is not from the exact public origin /robots.txt.")
    content_type = str(evidence.get("content_type", "")).split(";", 1)[0].strip().lower()
    if evidence.get("http_status") != 200 or content_type != "text/plain":
        raise ValueError("Robots evidence must be a successful text/plain response, not fallback HTML.")
    body = evidence.get("body")
    if not isinstance(body, str) or hashlib.sha256(body.encode("utf-8")).hexdigest() != evidence.get("body_sha256"):
        raise ValueError("Origin robots body and SHA-256 evidence do not match.")
    if "<html" in body.lower() or "<!doctype" in body.lower():
        raise ValueError("Origin robots evidence contains HTML.")
    try:
        retrieved = datetime.fromisoformat(evidence["retrieved_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError, AttributeError) as error:
        raise ValueError("Origin robots retrieval time is missing or invalid.") from error
    current = now or datetime.now(timezone.utc)
    if retrieved.tzinfo is None or current.tzinfo is None:
        raise ValueError("Robots evidence times must include a timezone.")
    age = current - retrieved
    if age < timedelta(0) or age > MAX_ROBOTS_EVIDENCE_AGE:
        raise ValueError("Origin robots evidence must have been verified within the last 24 hours.")
    if not _gptbot_disallows_prefix(body, prefix):
        raise ValueError("Origin robots evidence does not conclusively block GPTBot for this whole site path.")
    return {"policy": "disallow", "scope": "verified_origin_robots",
            "crawler": "GPTBot", "origin_robots_url": expected,
            "evidence_sha256": evidence["body_sha256"],
            "evidence_retrieved_at": evidence["retrieved_at"],
            "indexing_guaranteed": False}
