"""Build app/data/past_prices.csv: the bundled past-price series shown on the Price Forecast page.

Inputs
  --history   clean_prices.csv from scripts/prepare_price_data.py (state,market,commodity,date,modal_price)
  --snapshot  optional raw Agmarknet/data.gov.in one-day export (State,District,Market,Commodity,Variety,
              Grade,Arrival_Date,Min_x0020_Price,Max_x0020_Price,Modal_x0020_Price; dd/mm/yyyy)

Only crops and markets the app knows are kept. Nothing is interpolated or invented: every output row is a
recorded price, tagged with the file it came from. Snapshot rows for one market/crop/day are collapsed to the
median across varieties/grades (prices are INR/quintal).
"""
import argparse
from pathlib import Path

import pandas as pd

APP_CROPS = {"Onion": "Onion", "Potato": "Potato", "Tomato": "Tomato", "Wheat": "Wheat",
             "Paddy(Common)": "Paddy (Rice)", "Maize": "Maize", "Groundnut": "Groundnut"}
# The Agmarknet export spells the state "Chattisgarh"; accept both spellings.
CG_STATES = {"chattisgarh", "chhattisgarh"}
MARKET_ALIASES = {"Chattrapati Sambhajinagar": "Chhatrapati Sambhajinagar"}
APP_MARKETS = ["Bilaspur", "Raipur", "Durg", "Raigarh", "Korba", "Bilha", "Ambikapur", "Rajnandgaon", "Mahasamund",
               "Jagdalpur", "Nashik", "Sangli", "Solapur", "Pune", "Kolhapur", "Ahilyanagar",
               "Chhatrapati Sambhajinagar", "Nagpur", "Amravati", "Akola"]


def _market(name: str):
    n = str(name).strip()
    if n.upper().startswith("APMC "):
        n = n[5:].strip()
    n = MARKET_ALIASES.get(n, n)
    return n if n in APP_MARKETS else None


def build(history: Path, snapshot: Path = None, snapshot_label: str = None) -> pd.DataFrame:
    h = pd.read_csv(history)
    h["market"] = h["market"].map(_market)
    h["crop"] = h["commodity"].map(APP_CROPS)
    h = h.dropna(subset=["market", "crop"])
    h = h.groupby(["crop", "market", "date"], as_index=False)["modal_price"].median()
    h["min"] = pd.NA
    h["max"] = pd.NA
    h = h.rename(columns={"modal_price": "modal"})
    h["source"] = "history"
    h["note"] = ""
    parts = [h]
    if snapshot is not None:
        s = pd.read_csv(snapshot)
        s.columns = ["state", "district", "market", "commodity", "variety", "grade", "date", "min", "max", "modal"]
        s["date"] = pd.to_datetime(s["date"], format="%d/%m/%Y", errors="raise").dt.strftime("%Y-%m-%d")
        s["mandi"] = s["market"].astype(str).str.strip()
        direct = s["market"].map(_market)
        # Chhattisgarh rows usually name small APMCs (e.g. "Kharora APMC"), not the district town.
        # Where the district is an app market, use it and keep the real mandi names in `note`.
        is_cg = s["state"].astype(str).str.strip().str.lower().isin(CG_STATES)
        district = s["district"].astype(str).str.strip().where(lambda d: d.isin(APP_MARKETS))
        s["market"] = direct.fillna(district.where(is_cg))
        s["by_district"] = direct.isna() & s["market"].notna()
        s["crop"] = s["commodity"].map(APP_CROPS)
        s = s.dropna(subset=["market", "crop"])
        for c in ("min", "max", "modal"):
            s[c] = pd.to_numeric(s[c], errors="coerce")
        s = s[s["modal"] > 0]
        g = s.groupby(["crop", "market", "date"], as_index=False)
        names = g.apply(lambda x: ", ".join(sorted(set(x["mandi"]))) if x["by_district"].all() else "",
                        include_groups=False).rename(columns={None: "note"})
        s = g[["min", "max", "modal"]].median().merge(names, on=["crop", "market", "date"])
        s["note"] = s["note"].where(s["note"] == "", "district mandis: " + s["note"])
        s["source"] = snapshot_label or "snapshot"
        parts.append(s)
    out = pd.concat(parts, ignore_index=True)
    out = out.sort_values(["crop", "market", "date", "source"]).drop_duplicates(["crop", "market", "date"], keep="last")
    return out[["crop", "market", "date", "min", "max", "modal", "source", "note"]]


NATIONAL_CROPS = {"Onion": "Onion", "Potato": "Potato", "Tomato": "Tomato", "Wheat": "Wheat",
                  "Paddy": "Paddy (Rice)", "Gram": "Chana (Gram)"}
_NAT_LABELS = [("ONE WEEK-Price as on", "Latest"), ("ONE WEEK-Prices as on", "1 week earlier"),
               ("ONE MONTH", "1 month earlier"), ("ONE YEAR", "1 year earlier"),
               ("TWO YEAR", "2 years earlier"), ("THREE YEAR", "3 years earlier")]


def build_state(report: Path) -> pd.DataFrame:
    """Agmarknet 'All Type of Report (All Grades)' export: state, group, commodity, date, arrival, unit, modal, unit.

    One weighted-average modal price per state/commodity/day. Only INR/quintal rows for app crops are kept.
    """
    d = pd.read_csv(report, header=1)
    d.columns = ["state", "group", "commodity", "date", "arrival", "arrival_unit", "modal", "unit"]
    d = d[d["unit"].astype(str).str.contains("Quintal", case=False, na=False)].copy()
    d["crop"] = d["commodity"].map(APP_CROPS)
    d = d.dropna(subset=["crop"])
    d["state"] = d["state"].astype(str).str.strip().map(lambda x: "Chhattisgarh" if x.lower() in CG_STATES else x)
    d["date"] = pd.to_datetime(d["date"], format="%d-%m-%Y", errors="raise").dt.strftime("%Y-%m-%d")
    d["modal"] = pd.to_numeric(d["modal"], errors="coerce")
    d["arrival_tonnes"] = pd.to_numeric(d["arrival"], errors="coerce")
    d = d[d["modal"] > 0].drop_duplicates(["state", "crop", "date"], keep="last")
    d["source"] = "agmarknet_state_average"
    return d[["state", "crop", "date", "modal", "arrival_tonnes", "source"]].sort_values(["crop", "state", "date"])


def build_national(files) -> pd.DataFrame:
    """Wide 'Wholesale-Mandi-Prices-of-*' files: one row per commodity, one column per comparison date."""
    import re
    rows = []
    for f in files:
        w = pd.read_csv(f)
        cols = [c for c in w.columns if not c.startswith("%") and re.search(r"as on (\d\d-\d\d-\d{4})", c)]
        for _, r in w.iterrows():
            crop = NATIONAL_CROPS.get(str(r["Commodity"]).strip())
            if not crop:
                continue
            for c in cols:
                label = next((l for k, l in _NAT_LABELS if c.startswith(k)), None)
                v = pd.to_numeric(r[c], errors="coerce")
                if label and v > 0:
                    day = pd.to_datetime(re.search(r"as on (\d\d-\d\d-\d{4})", c).group(1), format="%d-%m-%Y")
                    rows.append({"crop": crop, "date": day.strftime("%Y-%m-%d"), "modal": float(v), "label": label})
    return pd.DataFrame(rows, columns=["crop", "date", "modal", "label"]).drop_duplicates(["crop", "date"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", required=True)
    ap.add_argument("--snapshot")
    ap.add_argument("--snapshot-label", default="snapshot")
    ap.add_argument("--state-report", help="Agmarknet 'All Type of Report' CSV -> app/data/state_prices.csv")
    ap.add_argument("--national", nargs="*", help="Wholesale-Mandi-Prices-of-*.csv files -> app/data/national_prices.csv")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "app" / "data" / "past_prices.csv"))
    a = ap.parse_args()
    df = build(Path(a.history), Path(a.snapshot) if a.snapshot else None, a.snapshot_label)
    df.to_csv(a.out, index=False)
    outdir = Path(a.out).parent
    if a.state_report:
        st = build_state(Path(a.state_report))
        st.to_csv(outdir / "state_prices.csv", index=False)
        print(f"wrote {len(st)} state rows -> {outdir / 'state_prices.csv'}")
    if a.national:
        nat = build_national(a.national)
        nat.to_csv(outdir / "national_prices.csv", index=False)
        print(f"wrote {len(nat)} national rows -> {outdir / 'national_prices.csv'}")
    print(f"wrote {len(df)} rows, {df.groupby(['crop','market']).ngroups} crop/market series -> {a.out}")


if __name__ == "__main__":
    main()
