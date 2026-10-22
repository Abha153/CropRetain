"""
Soil-test rating: classifies a farmer's soil-test values (organic carbon,
available N / P / K, pH, EC) against ONE cited rating chart.

Source: TNAU Agritech "Soil Rating Chart" (two pages carry the same chart,
read on 2026-10-22). It is Tamil Nadu material, not Chhattisgarh-specific
(see REGIONAL_LIMITATION in soil_crop_rules.py).

Honesty rules (same spirit as soil_crop_rules.py):
  * Only the thresholds printed by the source are used; nothing is invented.
  * Where the printed chart is inconsistent or silent, the result says so
    instead of guessing:
      - Organic carbon "medium" is printed as 0.5-7.5 % but "high" starts at
        >0.75 %, so 7.5 is almost certainly a typo for 0.75. We read medium
        as 0.5-0.75 and flag the rating `interpreted`.
      - pH between 8.5 and 8.9 has no class in the chart -> `unclassified`.
      - EC exact boundaries (1, 2, 4) are not specified by the chart; we use
        [1,2) -> germination, [2,4] -> sensitive crops, >4 -> injurious.
  * No fertiliser quantities are produced: none are cited. The output only
    says where a value sits and points to the Soil Health Card / KVK.
  * Units are those printed by the source; EC is printed as
    "milli mhos/cm2", so confirm the unit on your own report.
"""
from typing import Optional

SOURCE_ID = "tnau_soil_rating_chart"

SOURCES = {
    SOURCE_ID: {
        "title": "Soil Rating Chart (soil fertility / soil test rating)",
        "publisher": "TNAU Agritech Portal",
        "url": "https://agritech.tnau.ac.in/agriculture/agri_soil_soilratingchart.html",
        "region_scope": "Tamil Nadu",
    },
}

DATA_QUALITY_ESTIMATED = "ESTIMATED"

# parameter -> (unit as printed, low_below, high_above, interpreted_note or None)
# value < low_below -> low; value > high_above -> high; otherwise medium.
_NUTRIENT_CHART = {
    "organic_carbon": ("%", 0.5, 0.75,
                       "Chart prints medium as 0.5-7.5 % but high as >0.75 %; "
                       "medium is read here as 0.5-0.75 %."),
    "nitrogen": ("kg/ha", 240, 480, None),
    "phosphorus": ("kg/ha", 11.0, 22, None),
    "potassium": ("kg/ha", 110, 280, None),
}

PARAMETER_ORDER = ["organic_carbon", "nitrogen", "phosphorus", "potassium", "ph", "ec"]

NO_DOSE_NOTE = (
    "This rates your values against one published chart. It does not give "
    "fertiliser quantities: take those from your Soil Health Card "
    "recommendation or your local KVK."
)


def _rate_nutrient(name: str, value: float) -> dict:
    unit, low_below, high_above, note = _NUTRIENT_CHART[name]
    if value < low_below:
        rating = "low"
    elif value > high_above:
        rating = "high"
    else:
        rating = "medium"
    out = {
        "parameter": name, "value": value, "unit": unit, "rating": rating,
        "thresholds": {"low_below": low_below, "high_above": high_above},
        "source": SOURCE_ID, "interpreted": note is not None,
    }
    if note:
        out["note"] = note
    return out


def _rate_ph(value: float) -> dict:
    if value < 6.0:
        rating, label = "acid", "Acid (below 6.0)"
    elif value <= 8.5:
        rating, label = "normal_to_saline", "Normal to saline (6.0-8.5)"
    elif value < 8.9:
        rating, label = "unclassified", "Between 8.5 and 8.9: the chart gives no class"
    elif value <= 9.0:
        rating, label = "tending_alkaline", "Tending to become alkaline (8.9-9.0)"
    else:
        rating, label = "alkaline", "Alkaline (above 9.0)"
    return {"parameter": "ph", "value": value, "unit": None, "rating": rating,
            "label": label, "source": SOURCE_ID, "interpreted": False}


def _rate_ec(value: float) -> dict:
    if value < 1:
        rating, label = "normal", "Normal (below 1)"
    elif value < 2:
        rating, label = "critical_for_germination", "Critical for germination (1-2)"
    elif value <= 4:
        rating, label = "critical_for_sensitive_crops", "Critical for growth of sensitive crops (2-4)"
    else:
        rating, label = "injurious_to_most_crops", "Injurious to most crops (above 4)"
    return {"parameter": "ec", "value": value, "unit": "milli mhos/cm2 (as printed by the source)",
            "rating": rating, "label": label, "source": SOURCE_ID,
            "interpreted": True,
            "note": "The chart does not say whether the exact values 1, 2 and 4 "
                    "belong to the lower or upper class; this check uses [1,2), [2,4], >4."}


# Ratings that deserve the farmer's attention first.
_ATTENTION = {
    "low", "acid", "alkaline", "tending_alkaline", "unclassified",
    "critical_for_germination", "critical_for_sensitive_crops",
    "injurious_to_most_crops",
}


def rate_soil_health(*, organic_carbon: Optional[float] = None,
                     nitrogen: Optional[float] = None,
                     phosphorus: Optional[float] = None,
                     potassium: Optional[float] = None,
                     ph: Optional[float] = None,
                     ec: Optional[float] = None) -> dict:
    """Rate every provided value; parameters not provided are listed under
    `not_provided`, never estimated."""
    given = {
        "organic_carbon": organic_carbon, "nitrogen": nitrogen,
        "phosphorus": phosphorus, "potassium": potassium, "ph": ph, "ec": ec,
    }
    ratings = []
    for name in PARAMETER_ORDER:
        v = given[name]
        if v is None:
            continue
        if name == "ph":
            ratings.append(_rate_ph(v))
        elif name == "ec":
            ratings.append(_rate_ec(v))
        else:
            ratings.append(_rate_nutrient(name, v))
    return {
        "data_quality": DATA_QUALITY_ESTIMATED if ratings else "UNAVAILABLE",
        "method": "RATING_CHART_LOOKUP",
        "ratings": ratings,
        "needs_attention": [r["parameter"] for r in ratings if r["rating"] in _ATTENTION],
        "not_provided": [n for n in PARAMETER_ORDER if given[n] is None],
        "note": NO_DOSE_NOTE,
        "sources": [{"id": SOURCE_ID, **SOURCES[SOURCE_ID]}] if ratings else [],
    }


__all__ = ["rate_soil_health", "SOURCES", "SOURCE_ID", "PARAMETER_ORDER"]
