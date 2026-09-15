#!/usr/bin/env python3
"""Summarize manually supplied beta questionnaires locally. Never uploads or decides release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VERSION = "0.1.0b1"
OPTIONS = {
    "stage": ("first_use", "follow_up"),
    "participant_type": ("external", "team", "synthetic"),
    "platform": ("macos_arm64", "macos_x86", "ubuntu_arm64", "ubuntu_x86", "other"),
    "tool": ("codex", "claude-code", "cursor", "other"),
    "workflow": ("cli", "editor", "other"),
    "install": ("not_attempted", "succeeded", "blocked"),
    "exercise": ("not_attempted", "guided_example", "real_project"),
    "receipt": ("not_attempted", "created", "failed"),
    "time_to_result": ("unknown", "under_5_minutes", "5_to_10_minutes", "10_to_30_minutes", "over_30_minutes"),
    "usefulness": ("not_reviewed", "not_useful", "somewhat_useful", "useful", "very_useful"),
    "incorrect_change": ("not_reviewed", "no", "yes", "unsure"),
    "keep_installed": ("undecided", "yes", "maybe", "no"),
    "repeat_use": ("not_yet", "same_day_only", "another_day"),
    "share_card": ("not_attempted", "created", "shared", "failed"),
}
FRICTION = ("prerequisites", "installation", "command_path", "session_boundaries", "missing_changes", "incorrect_changes", "passport_confusion", "coverage", "privacy", "card_export", "none")
UUID = re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}\Z")


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate_feedback_field")
        result[key] = value
    return result


def validate(value, *, as_of):
    keys = {"schema_version", "kind", "version", "participant_id", "report_id", "recorded_on", "consent", "friction", *OPTIONS}
    if type(value) is not dict or set(value) != keys or value["schema_version"] != "1.0" or value["kind"] != "forkit_beta_feedback" or value["version"] != VERSION or value["consent"] is not True:
        raise ValueError("invalid_feedback_contract")
    for key in ("participant_id", "report_id"):
        if type(value[key]) is not str or not UUID.fullmatch(value[key]):
            raise ValueError("invalid_feedback_identifier")
    observed = value["recorded_on"]
    if type(observed) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", observed):
        raise ValueError("invalid_feedback_date")
    parsed = date.fromisoformat(observed)
    if parsed.isoformat() != observed or parsed > as_of:
        raise ValueError("future_feedback_date")
    if any(type(value[k]) is not str or value[k] not in options for k, options in OPTIONS.items()):
        raise ValueError("invalid_feedback_choice")
    f = value["friction"]
    if type(f) is not list or not 1 <= len(f) <= 10 or any(type(x) is not str or x not in FRICTION for x in f) or len(set(f)) != len(f) or ("none" in f and len(f) != 1):
        raise ValueError("invalid_feedback_friction")
    if value["receipt"] == "created" and (value["install"] != "succeeded" or value["exercise"] == "not_attempted"):
        raise ValueError("contradictory_receipt_feedback")
    if value["receipt"] != "created" and (value["usefulness"] != "not_reviewed" or value["incorrect_change"] != "not_reviewed" or value["share_card"] in {"created", "shared"} or value["repeat_use"] != "not_yet"):
        raise ValueError("receipt_required_for_review")
    return value


def read_report(path, as_of):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 16_384:
            raise ValueError("unsafe_or_oversized_feedback")
        raw = handle.read(16_385)
    if len(raw) > 16_384:
        raise ValueError("oversized_feedback")
    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, RecursionError, UnicodeError):
        raise ValueError("invalid_feedback_json") from None
    return validate(value, as_of=as_of)


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "basis_points": numerator * 10000 // denominator if denominator else None}


def summarize(directory, *, as_of):
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("feedback_directory_required")
    files = []
    for p in directory.iterdir():
        if len(files) >= 500:
            raise ValueError("feedback_directory_limit")
        files.append(p)
    documents, hashes, reports, participants = [], set(), {}, {}
    duplicates = 0
    for p in sorted(files):
        if p.suffix != ".json":
            continue
        v = read_report(p, as_of)
        canonical = json.dumps(v, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        if fingerprint in hashes:
            duplicates += 1
            continue
        hashes.add(fingerprint)
        if v["report_id"] in reports:
            raise ValueError("conflicting_report_id")
        reports[v["report_id"]] = fingerprint
        key = (v["participant_id"], v["stage"])
        if key in participants:
            raise ValueError("multiple_reports_for_participant_stage_review_required")
        participants[key] = v
        documents.append(v)
    for v in documents:
        initial = participants.get((v["participant_id"], "first_use"))
        if initial and v["stage"] == "follow_up" and (v["recorded_on"] < initial["recorded_on"] or v["participant_type"] != initial["participant_type"]):
            raise ValueError("inconsistent_follow_up")
    first = [v for v in documents if v["stage"] == "first_use" and v["participant_type"] == "external"]
    successful = [v for v in first if v["install"] == "succeeded"]
    real = [v for v in first if v["receipt"] == "created" and v["exercise"] == "real_project"]
    useful = [v for v in real if v["usefulness"] in {"useful", "very_useful"}]
    eligible = [v for v in first if date.fromisoformat(v["recorded_on"]) <= as_of - timedelta(days=7)]
    follow = [participants[(v["participant_id"], "follow_up")] for v in eligible if (v["participant_id"], "follow_up") in participants and date.fromisoformat(participants[(v["participant_id"], "follow_up")]["recorded_on"]) >= date.fromisoformat(v["recorded_on"]) + timedelta(days=7)]
    repeat = [v for v in follow if v["exercise"] == "real_project" and v["repeat_use"] == "another_day"]
    return {"schema_version": "1.0", "kind": "forkit_beta_summary", "version": VERSION, "as_of": as_of.isoformat(),
            "basis": "voluntary_self_reported_questionnaires", "total_installs": None,
            "external_first_use_respondents": len(first), "reported_install_success": ratio(len(successful), len(first)),
            "real_project_receipts": len(real), "reported_useful_real_receipts": ratio(len(useful), len(real)),
            "time_to_real_receipt": dict(sorted(Counter(v["time_to_result"] for v in real).items())),
            "reported_incorrect_changes": dict(sorted(Counter(v["incorrect_change"] for v in real).items())),
            "keep_installed": dict(sorted(Counter(v["keep_installed"] for v in first).items())),
            "tools": dict(sorted(Counter(v["tool"] for v in first).items())),
            "platforms": dict(sorted(Counter(v["platform"] for v in first).items())),
            "workflows": dict(sorted(Counter(v["workflow"] for v in first).items())),
            "friction": dict(sorted(Counter(x for v in first for x in v["friction"]).items())),
            "follow_up_eligible_after_7_days": len(eligible), "eligible_follow_up_responses": len(follow),
            "follow_up_nonresponses": len(eligible) - len(follow),
            "repeat_use_lower_bound": ratio(len(repeat), len(eligible)), "repeat_use_among_follow_up_respondents": ratio(len(repeat), len(follow)),
            "excluded_team_or_synthetic_reports": sum(v["participant_type"] != "external" for v in documents),
            "unmatched_follow_up_reports": sum(v["stage"] == "follow_up" and (v["participant_id"], "first_use") not in participants for v in documents),
            "duplicate_files_ignored": duplicates,
            "pilot_targets": {"external_first_use_target": 8, "different_day_repeat_target": 3,
                              "reported_targets_reached": len(first) >= 8 and len(repeat) >= 3},
            "release_decision": "manual_review_required",
            "limitations": ["No claim of unique authenticated people, total installs, representative adoption or verified AI execution.",
                            "Guided examples, team and synthetic reports do not count as real-project activation.",
                            "Nonresponses remain in the eligible repeat denominator; lower-bound and respondent rates are separate.",
                            "Dates and experiences are self-reported; inspect actual feedback and unresolved issues before a release decision."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    args = parser.parse_args()
    try:
        result = summarize(args.reports, as_of=args.as_of)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as f:
            json.dump(result, f, indent=2)
            f.write("\n")
        print("Local questionnaire summary saved. Review it before sharing. No network request made.")
        return 0
    except (ValueError, OSError, TypeError):
        print("Beta summary not created. Check report contracts, duplicate participant stages, dates and a new output path. No private input was logged.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
