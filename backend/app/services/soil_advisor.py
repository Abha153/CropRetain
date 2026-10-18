"""
Explainable crop-suitability screening from soil/season/water inputs.

What this is: a transparent rule check against published guidance
(see soil_crop_rules.py for every source). For each crop that HAS cited
rules it reports, factor by factor, whether the farmer's input falls inside
what the cited sources report.

What this is NOT:
  * not a trained model, not photo/sensor-based soil detection;
  * not a yield or profit prediction (money figures are attached by the
    router from the existing market-comparison / net_profit_breakdown
    logic, never computed here);
  * not a substitute for a soil test.

There is deliberately no invented numeric "score": a crop is described by
`checks_passed` out of `checks_assessed`, so nothing hides behind a made-up
weighting. Crops with no cited rules, or with no input that maps onto a
cited rule, are returned as UNAVAILABLE instead of being guessed.
"""
from typing import Optional

from app.mock_data.crops import CROP_BY_NAME, crop_names
from app.services.soil_crop_rules import (
    CROP_RULES, SOURCES, REGIONAL_LIMITATION,
)

DATA_QUALITY_ESTIMATED = "ESTIMATED"
DATA_QUALITY_UNAVAILABLE = "UNAVAILABLE"
INPUT_PROVENANCE = "USER_PROVIDED"


def _check_ph(ph: float, claims: list) -> dict:
    ranges = []
    inside = 0
    for c in claims:
        ok = c["min"] <= ph <= c["max"]
        inside += 1 if ok else 0
        ranges.append({
            "min": c["min"], "max": c["max"], "label": c["label"],
            "source": c["source"], "within": ok,
        })
    # "match" = inside at least one cited range. When sources disagree
    # about this exact pH that is surfaced via `sources_disagree` below
    # rather than silently picking a side.
    status = "match" if inside > 0 else "mismatch"
    return {
        "factor": "ph", "status": status, "value": ph,
        "ranges": ranges,
        # True when at least one cited range contains the value and at least
        # one does not -- the sources themselves disagree about this pH.
        "sources_disagree": 0 < inside < len(claims),
    }


def _check_texture(texture: str, claims: list) -> dict:
    matched = [c for c in claims if texture in c["classes"]]
    return {
        "factor": "texture",
        "status": "match" if matched else "mismatch",
        "value": texture,
        "supporting": [
            {"label": c["label"], "source": c["source"], "interpreted": c["interpreted"]}
            for c in matched
        ],
        "listed_classes": sorted({cls for c in claims for cls in c["classes"]}),
    }


def _check_season(season: str, claims: list) -> dict:
    matched = [c for c in claims if season in c["seasons"]]
    return {
        "factor": "season",
        "status": "match" if matched else "mismatch",
        "value": season,
        "supporting": [{"label": c["label"], "source": c["source"]} for c in matched],
        "listed_seasons": sorted({s for c in claims for s in c["seasons"]}),
    }


def evaluate_crop(crop: str, *, soil_ph: Optional[float], soil_texture: Optional[str],
                  season: Optional[str], irrigation: Optional[str]) -> dict:
    """Evaluate one catalogue crop. Returns a dict with `assessable` False
    when the crop has no cited rules or no provided input maps onto one."""
    rules = CROP_RULES.get(crop)
    if rules is None:
        return {"crop": crop, "assessable": False,
                "reason_code": "NO_CITED_RULES",
                "reason": "No cited agronomic rule has been loaded for this crop yet."}

    checks, not_assessed = [], []

    if soil_ph is not None:
        if rules["ph"]:
            checks.append(_check_ph(soil_ph, rules["ph"]))
        else:
            not_assessed.append("ph")
    if soil_texture is not None:
        if rules["texture"]:
            checks.append(_check_texture(soil_texture, rules["texture"]))
        else:
            not_assessed.append("texture")
    if season is not None:
        if rules["season"]:
            checks.append(_check_season(season, rules["season"]))
        else:
            not_assessed.append("season")

    notes = []
    if irrigation is not None:
        for w in rules["water"]:
            if irrigation in w["applies_to"]:
                notes.append({"code": w["code"], "source": w["source"],
                              "params": w["params"], "text": w["text"]})

    if not checks:
        return {"crop": crop, "assessable": False,
                "reason_code": "NO_MATCHING_INPUT",
                "reason": "None of the soil inputs you gave maps onto a cited rule for this crop.",
                "not_assessed_factors": not_assessed, "notes": notes}

    passed = sum(1 for c in checks if c["status"] == "match")
    warnings = []
    for c in checks:
        if c["factor"] == "ph" and c.get("sources_disagree"):
            warnings.append({"code": "PH_SOURCES_DISAGREE"})
        if c["status"] == "mismatch":
            warnings.append({"code": f"{c['factor'].upper()}_OUTSIDE_REPORTED"})

    info = CROP_BY_NAME.get(crop, {})
    return {
        "crop": crop, "emoji": info.get("emoji"), "assessable": True,
        "checks": checks, "checks_passed": passed, "checks_assessed": len(checks),
        "not_assessed_factors": not_assessed,
        "warnings": warnings, "notes": notes,
        "source_ids": sorted({
            s for c in checks
            for s in ([r["source"] for r in c.get("ranges", [])]
                      + [r["source"] for r in c.get("supporting", [])])
        } | {n["source"] for n in notes}),
    }


def evaluate_all(*, soil_ph: Optional[float], soil_texture: Optional[str],
                 season: Optional[str], irrigation: Optional[str]) -> dict:
    """Evaluate every crop in the catalogue. Ranked by share of assessed
    checks passed, then by number of checks assessed (more evidence first),
    then by name for a stable order."""
    ranked, unavailable = [], []
    for name in crop_names():
        r = evaluate_crop(name, soil_ph=soil_ph, soil_texture=soil_texture,
                          season=season, irrigation=irrigation)
        if r["assessable"]:
            ranked.append(r)
        else:
            unavailable.append({
                "crop": name, "data_quality": DATA_QUALITY_UNAVAILABLE,
                "reason_code": r["reason_code"], "reason": r["reason"],
            })
    ranked.sort(key=lambda r: (-(r["checks_passed"] / r["checks_assessed"]),
                               -r["checks_assessed"], r["crop"]))
    return {"ranked": ranked, "unavailable": unavailable}


def sources_for(ids) -> list:
    return [{"id": i, **SOURCES[i]} for i in sorted(set(ids)) if i in SOURCES]


__all__ = [
    "evaluate_crop", "evaluate_all", "sources_for", "REGIONAL_LIMITATION",
    "DATA_QUALITY_ESTIMATED", "DATA_QUALITY_UNAVAILABLE", "INPUT_PROVENANCE",
]
