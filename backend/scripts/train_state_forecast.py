"""Train the STATE-LEVEL price forecast on app/data/state_prices.csv.

Same features, split, model selection and honesty checks as scripts/train_price_forecast.py (it calls the same
train_from_frame); only the series differ: one statewide arrival-weighted daily average modal price per
state and crop, instead of one series per mandi. Artifacts go to models/price_forecast_state/.

    python -m scripts.train_state_forecast [--models hgb,catboost] [--min-leaf 30]
"""
import argparse
from pathlib import Path

import pandas as pd

from scripts import train_price_forecast as T

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IN = ROOT / "app" / "data" / "state_prices.csv"
DEFAULT_OUT = ROOT / "models" / "price_forecast_state"


def state_frame(path: Path) -> pd.DataFrame:
    s = pd.read_csv(path)
    df = pd.DataFrame({"state": s["state"], "market": s["state"] + " (state average)", "crop": s["crop"],
                       "date": pd.to_datetime(s["date"]), "modal_price": s["modal"].astype(float)})
    return df


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(DEFAULT_IN))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--models", default="hgb,catboost")
    ap.add_argument("--min-leaf", type=int, default=30)
    ap.add_argument("--max-iter", type=int, default=300)
    a = ap.parse_args(argv)
    df = state_frame(Path(a.inp))
    meta = T.train_from_frame(df, Path(a.out_dir), dataset_handle="Agmarknet state-wide daily average (state_prices.csv)",
                              dataset_files=[Path(a.inp).name], max_iter=a.max_iter, min_train_rows=1000,
                              min_leaf=a.min_leaf, families=tuple(a.models.split(",")), min_heldout_rows=100)
    T.print_report(meta)


if __name__ == "__main__":
    main()
