"""
Single reusable place to translate between CropRetain's user-facing naming
and the exact strings the data.gov.in mandi-price resources expect in
their `filters[...]` query parameters.

Why this exists: data.gov.in's source data is not internally consistent
with common spelling/formatting, and CropRetain must never silently return
the wrong record because a name "looked close enough". Two concrete,
manually-verified examples (via curl.exe against resource id
9ef84268-d588-465a-a308-a864a43d0070):

    CropRetain / correct spelling   data.gov.in source value
    ----------------------------  --------------------------
    Chhattisgarh                  Chattisgarh   (single h)
    Paddy                         Paddy(Common)

Every live-data request builder (live_market_data.py, mandi_directory.py,
district_market_data.py) must route state and commodity values through
`to_source_state()` / `to_source_commodity()` before putting them in a
`filters[...]` param, and must use `display_state()` for anything shown
to the user. Do not build a second copy of this mapping elsewhere.

This is intentionally a small, explicit, auditable table -- not fuzzy
matching. Fuzzy-matching a commodity or state name risks silently
returning a *different* crop/state's real government price, which is
worse than an honest "no record found for this selection".
"""

# CropRetain display spelling -> exact data.gov.in source spelling.
# Keys are matched case-insensitively; the source value is used verbatim.
_STATE_TO_SOURCE = {
    "chhattisgarh": "Chattisgarh",
}

# Reverse map, for turning a raw source record's `state` field back into
# CropRetain's display spelling (used when rendering a live result).
_SOURCE_TO_DISPLAY_STATE = {v.lower(): k.title() if k != "chhattisgarh" else "Chhattisgarh"
                            for k, v in _STATE_TO_SOURCE.items()}

# CropRetain crop name -> exact data.gov.in source commodity string.
# Only add an entry here once it has been manually verified against a
# real source record -- see the module docstring. An unmapped crop name
# is passed through unchanged (still correct for the many commodities
# data.gov.in lists under their plain name, e.g. "Wheat", "Onion").
_COMMODITY_TO_SOURCE = {
    "paddy": "Paddy(Common)",
    # CropRetain's canonical crop-catalogue name for this commodity (see
    # app/mock_data/crops.py) is "Paddy (Rice)", not "Paddy" -- without
    # this second key, to_source_commodity() never matches the "paddy"
    # entry above (it lowercases to "paddy (rice)"), so live lookups for
    # this crop silently miss every time regardless of whether a live
    # record actually exists. Same verified source value as "paddy".
    "paddy (rice)": "Paddy(Common)",
}


def to_source_state(state: str) -> str:
    """CropRetain display spelling -> exact data.gov.in filters[state] value."""
    if not state:
        return state
    return _STATE_TO_SOURCE.get(state.strip().lower(), state)


def display_state(source_state: str) -> str:
    """data.gov.in source `state` field value -> CropRetain display spelling."""
    if not source_state:
        return source_state
    return _SOURCE_TO_DISPLAY_STATE.get(source_state.strip().lower(), source_state)


def to_source_commodity(crop_name: str) -> str:
    """CropRetain crop name -> exact data.gov.in filters[commodity] value."""
    if not crop_name:
        return crop_name
    return _COMMODITY_TO_SOURCE.get(crop_name.strip().lower(), crop_name)
