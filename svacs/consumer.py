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

Image-derived structured intelligence is accepted in TWO upstream shapes,
both normalized here into the same Observation model:

  1. Samachar / Chandragupta's ingestion contract:
       detected_entities[].{entity_id, name, type, confidence,
         bounding_box:{xmin,ymin,xmax,ymax}, metadata}
       supporting_evidence.ocr_text
       top-level trace_id, observation_id, confidence

  2. Vijay Dhawan's Vision Runtime output contract:
       entities[].{type, label, confidence, bbox:[x_min,y_min,x_max,y_max]}
       ocr_results[].{text, confidence}
       top-level observation_id (trace_id may be absent)

Both are mapped through the SAME code path in _from_samachar() below —
there is exactly one image-intelligence handler, not two.
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
        if "detected_entities" in payload or "entities" in payload:
            return "image"
        if "mmsi" in payload or "ais_type" in payload:
            return "ais"
        if payload.get("intelligence_type") == "manual" or "operator_id" in payload:
            return "manual"
        raise ValueError("Unable to auto-detect structured intelligence source shape")

    # ---- image-derived (Samachar contract AND Vision Runtime contract) --
    def _extract_entities_list(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Samachar uses `detected_entities`; Vision Runtime uses `entities`.
        Both are lists of per-entity dicts, just under different keys."""
        return payload.get("detected_entities") or payload.get("entities") or []

    def _extract_bounding_box(self, entity: Dict[str, Any]) -> Optional[BoundingBox]:
        """Samachar gives a `bounding_box` dict (xmin/ymin/xmax/ymax or
        x_min/y_min/x_max/y_max). Vision Runtime gives a `bbox` list
        [x_min, y_min, x_max, y_max]. Both are normalized to BoundingBox."""
        b = entity.get("bounding_box")
        if b:
            return BoundingBox(
                x_min=b.get("xmin", b.get("x_min", 0.0)),
                y_min=b.get("ymin", b.get("y_min", 0.0)),
                x_max=b.get("xmax", b.get("x_max", 0.0)),
                y_max=b.get("ymax", b.get("y_max", 0.0)),
            )
        bbox = entity.get("bbox")
        if bbox and len(bbox) == 4:
            x_min, y_min, x_max, y_max = bbox
            return BoundingBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)
        return None

    def _from_samachar(self, payload: Dict[str, Any]) -> Observation:
        raw_entities = self._extract_entities_list(payload)

        entities: List[RawEntity] = []
        for e in raw_entities:
            bbox = self._extract_bounding_box(e)

            # Samachar entities always carry `name`. Vision Runtime entities
            # carry no `name`, only `type` (broad, e.g. "VESSEL") and
            # `label` (specific, e.g. "cargo_ship") - label is the closer
            # analogue to a display name and to Samachar's specific `type`.
            name = e.get("name") or e.get("label") or e.get("type", "Unknown")
            entity_type = e.get("label") or e.get("type", "unknown")

            entities.append(RawEntity(
                entity_id=e.get("entity_id", f"ent_{uuid.uuid4().hex[:8]}"),
                name=name,
                entity_type=entity_type,
                raw_confidence=float(e.get("confidence", 0.0)),
                bounding_box=bbox,
                ocr_text=self._extract_ocr(payload),
                metadata=e.get("metadata", {}) or {},
            ))

        if "confidence" in payload:
            upstream_confidence = float(payload.get("confidence", 0.0))
        else:
            # Vision Runtime has no top-level overall confidence - fall
            # back to the strongest already-computed entity confidence
            # present in the payload. This reads an existing number; it
            # does not derive a new one.
            entity_confidences = [float(e.get("confidence", 0.0)) for e in raw_entities]
            upstream_confidence = max(entity_confidences) if entity_confidences else 0.0

        trace_id = payload.get("trace_id") or f"trace_image_{uuid.uuid4().hex}"
        observation_id = payload.get("observation_id") or f"obs_image_{uuid.uuid4().hex}"

        return Observation(
            trace_id=trace_id,
            observation_id=observation_id,
            timestamp=payload.get("timestamp", datetime.utcnow().isoformat() + "Z"),
            observation_source="image",
            upstream_source_type=payload.get("source_type", "unknown"),
            entities=entities,
            upstream_confidence=upstream_confidence,
            supporting_evidence=payload.get("supporting_evidence", {}) or {},
            provenance={
                "produced_by": (payload.get("processing_metadata") or {}).get(
                    "processed_by", "Samachar"),
                "schema_version": payload.get("schema_version", "1.0.0"),
            },
            schema_version=payload.get("schema_version", "1.0.0"),
        )

    def _extract_ocr(self, payload: Dict[str, Any]) -> Optional[List[str]]:
        """Merges OCR text from both supported shapes:
        Samachar: supporting_evidence.ocr_text (string or list of strings)
        Vision Runtime: top-level ocr_results[].text
        """
        texts: List[str] = []

        ev = payload.get("supporting_evidence", {}) or {}
        ev_text = ev.get("ocr_text")
        if ev_text and ev_text != "No OCR text extracted":
            texts.extend([ev_text] if isinstance(ev_text, str) else list(ev_text))

        for ocr_entry in payload.get("ocr_results", []) or []:
            text = ocr_entry.get("text") if isinstance(ocr_entry, dict) else None
            if text:
                texts.append(text)

        return texts or None

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