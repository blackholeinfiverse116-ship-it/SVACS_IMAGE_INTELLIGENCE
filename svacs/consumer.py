"""
Task 1 - Structured Intelligence Consumer

Converts already-structured intelligence (produced upstream by Samachar/
Vision Runtime, AIS feeds, or manual operator entry) into the canonical
`Observation` model used by the rest of the SVACS runtime.

IMPORTANT: This module performs NO computer vision, NO OCR, and NO image
ingestion — it only maps fields that already exist on the upstream
payload. All three supported input shapes converge into ONE canonical
Observation type and flow through the SAME downstream pipeline (single
processing path, per Task 1 acceptance criteria — no parallel paths).
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import Observation, RawEntity, BoundingBox, ObservationSource


class StructuredIntelligenceConsumer:

    def consume(self, payload: Dict[str, Any],
                observation_source: Optional[ObservationSource] = None) -> Observation:
        source = observation_source or self._detect_source(payload)
        if source == "image":
            return self._from_samachar(payload)
        if source == "ais":
            return self._from_ais(payload)
        if source == "manual":
            return self._from_manual(payload)
        raise ValueError(f"Unsupported observation source: {source}")

    # ---- auto-detection -------------------------------------------------
    def _detect_source(self, payload: Dict[str, Any]) -> ObservationSource:
        if "detected_entities" in payload and "supporting_evidence" in payload:
            return "image"
        if "mmsi" in payload or "ais_type" in payload:
            return "ais"
        if payload.get("intelligence_type") == "manual" or "operator_id" in payload:
            return "manual"
        raise ValueError("Unable to auto-detect structured intelligence source shape")

    # ---- image-derived (Samachar / Vision Runtime contract) -------------
    def _from_samachar(self, payload: Dict[str, Any]) -> Observation:
        entities: List[RawEntity] = []
        for e in payload.get("detected_entities", []):
            bbox = None
            b = e.get("bounding_box")
            if b:
                bbox = BoundingBox(
                    x_min=b.get("xmin", b.get("x_min", 0.0)),
                    y_min=b.get("ymin", b.get("y_min", 0.0)),
                    x_max=b.get("xmax", b.get("x_max", 0.0)),
                    y_max=b.get("ymax", b.get("y_max", 0.0)),
                )
            entities.append(RawEntity(
                entity_id=e.get("entity_id", f"ent_{uuid.uuid4().hex[:8]}"),
                name=e.get("name", "Unknown"),
                entity_type=e.get("type", "unknown"),
                raw_confidence=float(e.get("confidence", 0.0)),
                bounding_box=bbox,
                ocr_text=self._extract_ocr(payload),
                metadata=e.get("metadata", {}) or {},
            ))

        return Observation(
            trace_id=payload["trace_id"],
            observation_id=payload["observation_id"],
            timestamp=payload.get("timestamp", datetime.utcnow().isoformat() + "Z"),
            observation_source="image",
            upstream_source_type=payload.get("source_type", "unknown"),
            entities=entities,
            upstream_confidence=float(payload.get("confidence", 0.0)),
            supporting_evidence=payload.get("supporting_evidence", {}) or {},
            provenance={
                "produced_by": (payload.get("processing_metadata") or {}).get(
                    "processed_by", "Samachar"),
                "schema_version": payload.get("schema_version", "1.0.0"),
            },
            schema_version=payload.get("schema_version", "1.0.0"),
        )

    def _extract_ocr(self, payload: Dict[str, Any]) -> Optional[List[str]]:
        ev = payload.get("supporting_evidence", {}) or {}
        text = ev.get("ocr_text")
        if not text or text == "No OCR text extracted":
            return None
        return [text] if isinstance(text, str) else list(text)

    # ---- AIS-derived -----------------------------------------------------
    def _from_ais(self, payload: Dict[str, Any]) -> Observation:
        entity = RawEntity(
            entity_id=f"ent_ais_{payload.get('mmsi', uuid.uuid4().hex[:8])}",
            name=payload.get("vessel_name", "Unknown Vessel"),
            entity_type=payload.get("ais_type", "vessel"),
            raw_confidence=float(payload.get("signal_quality", 0.9)),
            bounding_box=None,
            ocr_text=None,
            metadata={
                "mmsi": payload.get("mmsi"),
                "imo": payload.get("imo"),
                "callsign": payload.get("callsign"),
                "speed_knots": payload.get("speed_knots"),
                "heading": payload.get("heading"),
                "lat": payload.get("lat"),
                "lon": payload.get("lon"),
            },
        )
        return Observation(
            trace_id=payload.get("trace_id", f"trace_ais_{uuid.uuid4().hex}"),
            observation_id=payload.get("observation_id", f"obs_ais_{uuid.uuid4().hex}"),
            timestamp=payload.get("timestamp", datetime.utcnow().isoformat() + "Z"),
            observation_source="ais",
            upstream_source_type="ais_feed",
            entities=[entity],
            upstream_confidence=float(payload.get("signal_quality", 0.9)),
            supporting_evidence={"ais_raw": payload},
            provenance={"produced_by": "AIS Feed", "schema_version": "1.0.0"},
        )

    # ---- Manual operator intelligence ------------------------------------
    def _from_manual(self, payload: Dict[str, Any]) -> Observation:
        entity = RawEntity(
            entity_id=f"ent_manual_{uuid.uuid4().hex[:8]}",
            name=payload.get("reported_vessel_name", "Unknown Vessel"),
            entity_type=payload.get("reported_type", "vessel"),
            raw_confidence=float(payload.get("operator_confidence", 0.6)),
            bounding_box=None,
            ocr_text=None,
            metadata={
                "operator_id": payload.get("operator_id"),
                "notes": payload.get("notes"),
            },
        )
        return Observation(
            trace_id=payload.get("trace_id", f"trace_manual_{uuid.uuid4().hex}"),
            observation_id=payload.get("observation_id", f"obs_manual_{uuid.uuid4().hex}"),
            timestamp=payload.get("timestamp", datetime.utcnow().isoformat() + "Z"),
            observation_source="manual",
            upstream_source_type="manual_operator",
            entities=[entity],
            upstream_confidence=float(payload.get("operator_confidence", 0.6)),
            supporting_evidence={"manual_raw": payload},
            provenance={"produced_by": "Manual Operator Entry", "schema_version": "1.0.0"},
        )