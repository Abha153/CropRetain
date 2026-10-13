"""
ML price forecast (KrishiSight-derived), kept separate from the existing
statistical forecaster in app/services/price_predictor.py.

    features.py   -- the ONLY feature/target definition, shared by training
                     (scripts/train_price_forecast.py) and inference.
    inference.py  -- loads saved artifacts and predicts. Never trains.
"""
