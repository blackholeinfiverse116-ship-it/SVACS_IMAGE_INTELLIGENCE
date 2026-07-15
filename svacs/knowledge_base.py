"""
Mock Maritime Knowledge Base — stand-in for Jane's Fighting Ships /
fleet-history / lineage data referenced in Task 2/3. In production this
would be backed by a licensed data source; here it is a small reference
set sufficient to exercise reasoning, confidence, and explainability.
"""
from typing import Optional, Dict, Any, List

JANES_REFERENCE: Dict[str, Dict[str, Any]] = {
    "BALEARIA": {
        "class": "Ro-Pax Ferry",
        "operator": "Balearia Eurolineas Maritimas",
        "fleet_history": ["Introduced Mediterranean Ro-Pax service from 1998 onward"],
        "lineage": "Balearia Ro-Pax family",
        "dimensions_m": {"length": 186.5, "beam": 26.0},
        "role": "Passenger / Vehicle Ferry",
    },
    "MAERSK": {
        "class": "Container Ship",
        "operator": "A.P. Moller-Maersk",
        "fleet_history": ["Triple-E class introduced 2013"],
        "lineage": "Maersk container fleet",
        "dimensions_m": {"length": 399.0, "beam": 59.0},
        "role": "Container Transport",
    },
    "COSCO": {
        "class": "Container Ship",
        "operator": "COSCO Shipping",
        "fleet_history": ["Expanded global fleet following 2016 merger"],
        "lineage": "COSCO container fleet",
        "dimensions_m": {"length": 366.0, "beam": 51.0},
        "role": "Container Transport",
    },
}


def lookup_by_name_fragment(name_fragment: str) -> Optional[Dict[str, Any]]:
    if not name_fragment:
        return None
    frag = name_fragment.upper().strip('"\' ')
    for key, record in JANES_REFERENCE.items():
        if key in frag or frag in key:
            return {"reference_key": key, **record}
    return None


def lookup_all_ocr_candidates(ocr_texts: List[str]) -> Optional[Dict[str, Any]]:
    for text in ocr_texts or []:
        match = lookup_by_name_fragment(text)
        if match:
            return match
    return None