"""
Repair a messy Agmarknet-style daily price CSV into the clean file that
scripts/train_price_forecast.py expects.

    cd backend
    python -m scripts.prepare_price_data --input path/to/messy.csv --out-dir data/clean_prices
    python -m scripts.train_price_forecast --dataset-dir data/clean_prices --since 2023-01-01

Input columns (case/spacing tolerant): STATE, District Name, Market Name,
Commodity, Variety, Min_Price, Max_Price, Modal_Price, Price Date.

Output (in --out-dir):
    clean_prices.csv   state, market, commodity, date (ISO YYYY-MM-DD), modal_price (INR/quintal)
    prep_report.json   row funnel + every repair rule + a simulated accuracy check

PRINCIPLES -- this script only *recovers* an identifier when the data itself
determines it, and otherwise drops the row. It NEVER invents a price:
  * dates   : a blank date is filled ONLY when the nearest known dates before
              and after it (file order) are identical. Accuracy of that rule is
              measured by hiding known dates and re-deriving them (reported).
  * state   : filled only from a market (or district) that maps to exactly one state.
  * market  : filled only from a (state, district) that has exactly one market.
  * commodity: filled only from a variety that maps to exactly one commodity.
  * modal   : never imputed. Rows without a modal price are dropped.
  * prices  : unit errors / contradictory rows are dropped (rules below).
Date order is written as ISO so the trainer cannot mis-read 5/11/2025 as 5 Nov.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

COLUMN_CANDIDATES = {
    "state": ["state", "state_name"],
    "district": ["district", "district_name"],
    "market": ["market", "market_name"],
    "commodity": ["commodity", "commodity_name"],
    "variety": ["variety"],
    "min": ["min_price", "min"],
    "max": ["max_price", "max"],
    "modal": ["modal_price", "modal"],
    "date": ["price_date", "arrival_date", "date", "reported_date"],
}
REQUIRED = ["state", "market", "commodity", "modal", "date"]

STATE_FIXES = {
    "tamilnadu": "Tamil Nadu", "tamil nadu": "Tamil Nadu",
    "orissa": "Odisha", "odisha": "Odisha",
    "chattisgarh": "Chhattisgarh", "chhattisgarh": "Chhattisgarh",
    "gao": "Goa", "uttrakhand": "Uttarakhand", "uttarakhand": "Uttarakhand",
    "jammu & kashmir": "Jammu and Kashmir", "jammu and kashmir": "Jammu and Kashmir",
    "nct of delhi": "Delhi",
}

# price sanity (per commodity, relative to that commodity's national median modal price)
BAND_LOW, BAND_HIGH = 0.15, 8.0
MIN_VARIETY_EVIDENCE = 20      # rows needed before a variety may identify a commodity
SIM_MASK_FRACTION = 0.25


def _canon(c) -> str:
    return re.sub(r"\s+", "_", str(c).strip().lower())


def detect_columns(cols) -> dict:
    inv = {}
    for c in cols:
        inv.setdefault(_canon(c), c)
    found = {}
    for logical, cands in COLUMN_CANDIDATES.items():
        for cand in cands:
            if cand in inv:
                found[logical] = inv[cand]
                break
    return found


def norm_text(s: pd.Series) -> pd.Series:
    """Trim/collapse whitespace; textual null markers become NaN."""
    t = s.astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    return t.mask(t.str.lower().isin(["nan", "none", "null", "n/a", "na", "-", ""]))


def canonical_state(s: pd.Series) -> pd.Series:
    low = norm_text(s).str.lower()
    fixed = low.map(lambda v: STATE_FIXES.get(v, v.title()) if isinstance(v, str) else pd.NA)
    return fixed.astype("string")


def detect_date_format(raw: pd.Series, forced: str | None) -> str:
    if forced:
        return forced
    sample = raw.dropna().astype(str).str.strip().head(200_000)
    rates = {}
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        rates[fmt] = float(pd.to_datetime(sample, format=fmt, errors="coerce").notna().mean())
    best = max(rates, key=rates.get)
    ranked = sorted(rates.values(), reverse=True)
    if ranked[0] - ranked[1] < 0.01 and best != "%Y-%m-%d":
        raise SystemExit(f"Ambiguous date format (parse rates {rates}); pass --date-format explicitly.")
    return best


def recover_dates(d: pd.Series) -> pd.Series:
    """Fill a missing date only when the nearest known dates before and after (file order) agree."""
    prev, nxt = d.ffill(), d.bfill()
    fill = d.isna() & prev.notna() & (prev == nxt)
    return d.mask(fill, prev)


def simulate_date_recovery(d: pd.Series, frac: float, seed: int = 0) -> dict:
    """Hide a random share of KNOWN dates, re-derive them with the same rule, report accuracy."""
    rng = np.random.default_rng(seed)
    known_idx = np.flatnonzero(d.notna().to_numpy())
    hide = rng.choice(known_idx, size=int(len(known_idx) * frac), replace=False)
    masked = d.copy()
    masked.iloc[hide] = pd.NaT
    rec = recover_dates(masked)
    hidden = pd.Series(False, index=d.index)
    hidden.iloc[hide] = True
    fired = hidden & rec.notna()
    acc = float((rec[fired] == d[fired]).mean()) if fired.any() else float("nan")
    return {"hidden": int(hidden.sum()), "recovered": int(fired.sum()),
            "recovered_share": round(float(fired.sum() / max(hidden.sum(), 1)), 4),
            "accuracy_when_recovered": round(acc, 6)}


def unique_map(df: pd.DataFrame, keys: list, target: str, min_rows: int = 1) -> pd.Series:
    """key -> target, only for keys where the target is unique and seen >= min_rows times."""
    sub = df.dropna(subset=keys + [target])
    g = sub.groupby(keys)[target].agg(["nunique", "size", "first"])
    g = g[(g["nunique"] == 1) & (g["size"] >= min_rows)]
    return g["first"]


def fill_from_map(df: pd.DataFrame, keys: list, target: str, mapping: pd.Series) -> int:
    miss = df[target].isna() & df[keys].notna().all(axis=1)
    if not miss.any():
        return 0
    if len(keys) == 1:
        filled = df.loc[miss, keys[0]].map(mapping)
    else:
        idx = pd.MultiIndex.from_frame(df.loc[miss, keys])
        filled = pd.Series(mapping.reindex(idx).to_numpy(), index=df.index[miss])
    ok = filled.notna()
    df.loc[filled.index[ok], target] = filled[ok]
    return int(ok.sum())


def simulate_fill(df: pd.DataFrame, target: str, keys_list: list, min_rows: int = 1,
                  frac: float = SIM_MASK_FRACTION, seed: int = 1) -> dict:
    """Hide a random share of KNOWN `target` values, re-derive them with the same
    unique-mapping rule used for real gaps, and report how often the rule was right."""
    rng = np.random.default_rng(seed)
    d = df[[target] + sorted({k for keys in keys_list for k in keys})].copy()
    base = d[target].notna() & d[keys_list[0][0]].notna()
    known = np.flatnonzero(base.to_numpy())
    hide = rng.choice(known, size=int(len(known) * frac), replace=False)
    truth = d[target].copy()
    d.iloc[hide, d.columns.get_loc(target)] = pd.NA
    for keys in keys_list:
        fill_from_map(d, keys, target, unique_map(d, keys, target, min_rows))
    hidden = pd.Series(False, index=d.index)
    hidden.iloc[hide] = True
    fired = hidden & d[target].notna()
    acc = float((d.loc[fired, target] == truth[fired]).mean()) if fired.any() else float("nan")
    return {"hidden": int(hidden.sum()), "recovered": int(fired.sum()),
            "recovered_share": round(float(fired.sum() / max(hidden.sum(), 1)), 4),
            "accuracy_when_recovered": round(acc, 6)}


def prepare(path: Path, date_format: str | None = None) -> tuple:
    raw = pd.read_csv(path, low_memory=False, on_bad_lines="skip")
    cols = detect_columns(raw.columns)
    missing = [k for k in REQUIRED if k not in cols]
    if missing:
        raise SystemExit(f"Missing required columns {missing}; found {list(raw.columns)}")
    df = pd.DataFrame({k: raw[v] for k, v in cols.items()})
    for k in ("district", "variety", "min", "max"):
        if k not in df:
            df[k] = pd.NA
    report: dict = {"input_file": path.name, "rows_in": int(len(df)), "steps": []}

    def step(name: str, **kw):
        report["steps"].append({"step": name, **kw})
        print(f"  {name}: " + ", ".join(f"{k}={v:,}" if isinstance(v, int) else f"{k}={v}" for k, v in kw.items()))

    # ---- text normalisation --------------------------------------------------------------
    state_raw_variants = int(df["state"].astype("string").nunique())
    df["state"] = canonical_state(df["state"])
    for k in ("market", "district", "commodity", "variety"):
        df[k] = norm_text(df[k])
    # one display spelling per case/space-insensitive key (most frequent raw form)
    for k in ("market", "district"):
        key = df[k].str.lower()
        disp = df.groupby(key)[k].agg(lambda x: x.value_counts().index[0])
        df[k] = key.map(disp)
    df["commodity"] = df["commodity"].str.title()
    step("normalise_text", state_spellings_before=state_raw_variants,
         states_after=int(df["state"].nunique()))

    # ---- exact duplicates ----------------------------------------------------------------
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    step("drop_exact_duplicates", removed=before - len(df))

    # ---- dates -----------------------------------------------------------------------------
    fmt = detect_date_format(df["date"], date_format)
    d = pd.to_datetime(df["date"].astype("string").str.strip(), format=fmt, errors="coerce")
    unparsable = int(d.isna().sum() - df["date"].isna().sum())
    missing_before = int(d.isna().sum())
    sim = simulate_date_recovery(d, SIM_MASK_FRACTION)
    d = recover_dates(d)
    df["date"] = d
    step("dates", format=fmt, unparsable_values=unparsable, missing_before=missing_before,
         recovered_from_neighbours=missing_before - int(d.isna().sum()),
         simulated_recovery_accuracy=sim["accuracy_when_recovered"])
    report["date_recovery_simulation"] = sim

    # ---- recover identifiers only where the data determines them (two passes) --------------
    report["identifier_recovery_simulation"] = {
        "state_from_market_or_district": simulate_fill(df, "state", [["market"], ["district"]]),
        "market_from_state_district": simulate_fill(df, "market", [["state", "district"]]),
        "commodity_from_variety": simulate_fill(df, "commodity", [["variety"]], MIN_VARIETY_EVIDENCE),
    }
    n_state = n_market = n_comm = 0
    for _ in range(2):
        n_state += fill_from_map(df, ["market"], "state", unique_map(df, ["market"], "state"))
        n_state += fill_from_map(df, ["district"], "state", unique_map(df, ["district"], "state"))
        n_market += fill_from_map(df, ["state", "district"], "market", unique_map(df, ["state", "district"], "market"))
    n_comm += fill_from_map(df, ["variety"], "commodity",
                            unique_map(df, ["variety"], "commodity", MIN_VARIETY_EVIDENCE))
    step("recover_identifiers", state_filled=n_state, market_filled=n_market, commodity_filled=n_comm)

    # ---- required fields -------------------------------------------------------------------
    df["modal"] = pd.to_numeric(df["modal"], errors="coerce")
    df["min"] = pd.to_numeric(df["min"], errors="coerce")
    df["max"] = pd.to_numeric(df["max"], errors="coerce")
    before = len(df)
    drops = {k: int(df[k].isna().sum()) for k in ("modal", "date", "commodity", "market", "state")}
    df = df.dropna(subset=["modal", "date", "commodity", "market", "state"])
    step("drop_rows_missing_required_fields", removed=before - len(df), missing_counts=str(drops))

    # ---- price sanity ---------------------------------------------------------------------
    before = len(df)
    df = df[df["modal"] > 0]
    nonpos = before - len(df)
    both = df["min"].notna() & df["max"].notna()
    contradictory = (both & (df["max"] < df["min"])) | (
        both & ((df["modal"] < df["min"] * 0.999) | (df["modal"] > df["max"] * 1.001)))
    n_contra = int(contradictory.sum())
    df = df[~contradictory]
    med = df.groupby("commodity")["modal"].transform("median")
    ratio = df["modal"] / med
    outlier = (ratio < BAND_LOW) | (ratio > BAND_HIGH)
    n_out = int(outlier.sum())
    df = df[~outlier]
    step("price_sanity", non_positive=nonpos, modal_outside_min_max_or_max_lt_min=n_contra,
         unit_error_outliers=n_out, band=f"{BAND_LOW}x..{BAND_HIGH}x of commodity median")

    out = (df[["state", "market", "commodity", "date", "modal"]]
           .rename(columns={"modal": "modal_price"})
           .assign(date=lambda x: x["date"].dt.strftime("%Y-%m-%d"))
           .sort_values(["state", "market", "commodity", "date"]).reset_index(drop=True))
    report["rows_out"] = int(len(out))
    report["rows_out_share_of_input"] = round(len(out) / max(report["rows_in"], 1), 4)
    report["date_range"] = [out["date"].min(), out["date"].max()]
    report["commodities"] = {k: int(v) for k, v in out["commodity"].value_counts().items()}
    report["states"] = int(out["state"].nunique())
    report["markets"] = int(out.groupby(["state", "market"]).ngroups)
    report["series"] = int(out.groupby(["state", "market", "commodity"]).ngroups)
    report["notes"] = [
        "No prices were imputed; rows without a modal price were dropped.",
        "A blank date is filled only when the nearest known dates before and after it are identical.",
        "State/market/commodity are filled only when the dataset maps the key to exactly one value.",
        f"Unit-error filter drops modal prices outside {BAND_LOW}x-{BAND_HIGH}x of the commodity median.",
    ]
    return out, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="messy CSV file")
    ap.add_argument("--out-dir", required=True, help="directory to write clean_prices.csv + prep_report.json")
    ap.add_argument("--date-format", help="strptime format of the input dates (auto-detected if omitted)")
    args = ap.parse_args(argv)

    print(f"[prepare] reading {args.input}")
    out, report = prepare(Path(args.input), args.date_format)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_dir / "clean_prices.csv", index=False)
    (out_dir / "prep_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[prepare] {report['rows_in']:,} rows in -> {report['rows_out']:,} rows out "
          f"({report['rows_out_share_of_input']:.1%}); {report['series']:,} series; wrote {out_dir}")


if __name__ == "__main__":
    main()
