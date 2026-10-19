"""Tests for scripts/prepare_price_data.py -- the messy-CSV repair step.
The guiding rule under test: recover an identifier only when the data determines it,
otherwise drop the row; never invent a price."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest

from scripts import prepare_price_data as P

HEADER = "STATE,District Name,Market Name,Commodity,Variety,Grade,Min_Price,Max_Price,Modal_Price,Price Date\n"


def _write(tmp_path, rows):
    p = tmp_path / "messy.csv"
    p.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return p


def test_dates_filled_only_when_neighbours_agree_and_never_across_a_change():
    d = pd.Series(pd.to_datetime(["2024-01-05", None, "2024-01-05", None, "2024-01-06"]))
    out = P.recover_dates(d)
    assert out.iloc[1] == pd.Timestamp("2024-01-05")      # both neighbours agree
    assert pd.isna(out.iloc[3])                           # neighbours differ -> left missing, never guessed


def test_date_recovery_simulation_reports_accuracy():
    days = pd.to_datetime(np.repeat(pd.date_range("2024-01-01", periods=60), 12))
    sim = P.simulate_date_recovery(pd.Series(days), 0.25)
    assert sim["recovered"] > 0 and sim["accuracy_when_recovered"] > 0.95


def test_identifiers_filled_only_from_unambiguous_keys():
    df = pd.DataFrame({
        "market": ["a", "a", "b", "b", "a", "b"],
        "state": ["Goa", "Goa", "Kerala", "Assam", pd.NA, pd.NA],     # market 'b' maps to TWO states
    })
    df["state"] = df["state"].astype("string")
    n = P.fill_from_map(df, ["market"], "state", P.unique_map(df, ["market"], "state"))
    assert n == 1 and df.loc[4, "state"] == "Goa"          # unambiguous -> filled
    assert pd.isna(df.loc[5, "state"])                     # ambiguous -> left missing


def test_prepare_never_invents_prices_and_cleans_text(tmp_path):
    rows = []
    for i in range(30):                                    # a healthy Nashik onion series (month/day/year dates)
        rows.append(f"Maharashtra,nashik,Lasalgaon,Onion,Red,FAQ,1000,1400,{1200 + i},1/{i % 28 + 1}/2024")
    rows += [
        "maharashtra , nashik ,Lasalgaon,Onion,Red,FAQ,1000,1400,,1/5/2024",          # no modal -> dropped
        "Orissa,puri,Puri,Potato,Local,FAQ,500,700,600,1/5/2024",                       # alias fix -> Odisha
        "Maharashtra,nashik,Lasalgaon,Onion,Red,FAQ,1000,1400,1500000,1/5/2024",        # unit error -> dropped
        "Maharashtra,nashik,Lasalgaon,Onion,Red,FAQ,2000,1000,1500,1/5/2024",           # max < min -> dropped
        "Maharashtra,nashik,Lasalgaon,Onion,Red,FAQ,1000,1400,1200,1/5/2024",           # exact duplicate pair below
        "Maharashtra,nashik,Lasalgaon,Onion,Red,FAQ,1000,1400,1200,1/5/2024",
    ]
    out, rep = P.prepare(_write(tmp_path, rows))
    assert set(out.columns) == {"state", "market", "commodity", "date", "modal_price"}
    assert (out["modal_price"] > 0).all() and out["modal_price"].max() < 100000
    assert "Odisha" in set(out["state"]) and "Orissa" not in set(out["state"])
    assert out["date"].str.match(r"^\d{4}-\d{2}-\d{2}$").all()          # ISO, no day/month ambiguity left
    # every output price existed verbatim in the input
    src = pd.read_csv(_write(tmp_path, rows), low_memory=False)["Modal_Price"].dropna().astype(float)
    assert set(out["modal_price"]).issubset(set(src))
    assert rep["rows_out"] == len(out) and rep["rows_out"] < rep["rows_in"]


def test_ambiguous_date_format_demands_an_explicit_choice():
    raw = pd.Series(["1/2/2024", "3/4/2024", "5/6/2024"])          # parses as both d/m and m/d
    with pytest.raises(SystemExit):
        P.detect_date_format(raw, None)
    assert P.detect_date_format(raw, "%d/%m/%Y") == "%d/%m/%Y"
