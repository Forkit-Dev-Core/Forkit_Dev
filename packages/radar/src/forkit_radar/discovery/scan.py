"""Compose candidates into S02 observations without identity inference."""

from __future__ import annotations

import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..contracts import EvidenceState, Manifest, Observation
from .catalog import PRODUCT_NAMES
from .runner import run_worker
from .types import (
    DEFAULT_DETECTORS,
    DETECTORS,
    Candidate,
    Detector,
    Finding,
    MetadataCandidate,
    ScanReport,
    SourceScan,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def candidate_manifest(candidate: Candidate) -> Manifest:
    unknown = {"value": None, "origin": "unknown"}
    return Manifest.model_validate(
        {
            "schema_version": "1.0",
            "logical_agent_id": None,
            "provisional_component_key": str(uuid4()),
            "passport_id": None,
            "component_kind": "runtime" if candidate.product == "ollama-runtime" else "application",
            "scope_profile": {
                "profile_id": "passive-metadata-v1",
                "normalization_version": "1",
                "dimensions": ["identity"],
            },
            "declared_identity": {
                "name": {"value": PRODUCT_NAMES[candidate.product], "origin": "supported_metadata"},
                "version": {"value": candidate.version, "origin": "supported_metadata"}
                if candidate.version is not None
                else unknown,
                "creator": unknown,
                "organization": unknown,
            },
            "tools": None,
            "models": None,
            "artifacts": None,
            "settings": None,
            "measurement_completeness": {
                "identity": "partial",
                "tools": "not_selected",
                "models": "not_selected",
                "artifacts": "not_selected",
                "settings": "not_selected",
            },
        }
    )


def scan(
    detectors: tuple[Detector, ...] | None = None,
    *,
    project: Path | None = None,
    models_root: Path | None = None,
    agent_file: Path | None = None,
    registry: Path | None = None,
) -> ScanReport:
    if detectors is None:
        detectors = (
            DEFAULT_DETECTORS
            + (("langgraph",) if project else ())
            + (("agent-manifest",) if agent_file else ())
        )
    options = {}
    for key, path in (
        ("project", project),
        ("models_root", models_root),
        ("agent_file", agent_file),
    ):
        if path is not None:
            value = str(path.absolute())
            if (
                len(value) > 4096
                or len(path.absolute().parts) > 16
                or ".." in path.parts
                or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value)
            ):
                raise ValueError("invalid_scope_selection")
            options[key] = value
    if (
        not detectors
        or len(set(detectors)) != len(detectors)
        or any(d not in DETECTORS for d in detectors)
    ):
        raise ValueError("invalid_detector_selection")
    started_at, started = _now(), time.monotonic()
    sources = []
    for detector in detectors:
        for result in run_worker(detector, options=options) if options else run_worker(detector):
            slot = str(uuid4())
            observed_at = _now()
            findings = []
            # Even empty, denied and missing sources have explicit observations.
            for candidate in result.candidates or (None,):
                discovery = "observed" if detector == "processes" else "configured"
                if candidate is None:
                    discovery = (
                        "unknown" if result.status in {"complete", "missing"} else "unavailable"
                    )
                findings.append(
                    Finding(
                        observation=Observation(
                            schema_version="1.0",
                            observation_id=str(uuid4()),
                            source_slot_id=slot,
                            observed_at=observed_at,
                            detector_id=detector,
                            detector_version="1.0.0",
                            source_status=result.status,
                            reason_code="metadata_declaration"
                            if isinstance(candidate, MetadataCandidate)
                            else candidate.basis
                            if candidate
                            else result.reason,
                            manifest=candidate.manifest
                            if isinstance(candidate, MetadataCandidate)
                            else candidate_manifest(candidate)
                            if candidate is not None
                            else None,
                        ),
                        evidence=EvidenceState(
                            discovery=discovery,
                            association="declared"
                            if isinstance(candidate, MetadataCandidate)
                            and candidate.manifest.passport_id
                            else "unmatched",
                            passport="unsupported",
                            artifact="declared_digest"
                            if isinstance(candidate, MetadataCandidate)
                            and candidate.manifest.artifacts
                            and any(a.digest.value for a in candidate.manifest.artifacts)
                            else "not_measured",
                            provenance="absent",
                            runtime="not_observed",
                            acceptance="unreviewed",
                            freshness="current_at_check" if candidate else "unknown",
                        ),
                        detail=candidate.detail
                        if isinstance(candidate, MetadataCandidate)
                        else None,
                    )
                )
            sources.append(
                SourceScan(
                    scope=result.scope,
                    source_slot_id=slot,
                    detector=detector,
                    status=result.status,
                    reason=result.reason,
                    findings=findings,
                    unknown_entries=result.unknown_entries,
                )
            )
    if registry is not None:
        from ..identity.association import resolve

        # An explicit local registry selection only checks existing references.
        # No name search, registry initialization, source binding or enrollment.
        checked_sources = []
        for source in sources:
            raw = source.model_dump()
            for finding in raw["findings"]:
                if finding["observation"]["manifest"] is None:
                    continue
                association = resolve(
                    Manifest.model_validate(finding["observation"]["manifest"]), registry
                )
                finding["association"] = association.model_dump()
                finding["evidence"]["association"] = association.state
                if len(association.candidates) == 1:
                    finding["evidence"]["passport"] = {
                        "consistent": "consistent",
                        "invalid": "invalid",
                        "missing": "absent",
                        "unavailable": "unsupported",
                        "unsupported": "unsupported",
                    }[association.candidates[0].status]
            checked_sources.append(SourceScan.model_validate(raw))
        sources = checked_sources
    return ScanReport(
        schema_version="1.0",
        scan_id=str(uuid4()),
        started_at=started_at,
        finished_at=_now(),
        elapsed_ms=max(0, int((time.monotonic() - started) * 1000)),
        storage="not_saved",
        continuity="not_evaluated",
        scope="selected-passive-metadata-v2",
        sources=sources,
    )
