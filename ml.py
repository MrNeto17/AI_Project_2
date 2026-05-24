import sqlite3
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from lag_fallback import _get_historical_lags_with_fallback
from train import train_and_save_pipeline

MODEL_FILENAME = "kitchen_model.pkl"

FEATURE_COLS = [
    "prod",
    "start_hour",
    "start_minute",
    "sin_time",
    "cos_time",
    "week_day",
    "event",
    "weather",
    "lag_sales",
    "lag_trash",
]


def _resolve_model_path() -> Path | None:
    """Resolve model path robustly for CLI and web app entrypoints."""
    cwd_candidate = Path.cwd() / MODEL_FILENAME
    module_candidate = Path(__file__).resolve().parent / MODEL_FILENAME

    if cwd_candidate.exists():
        return cwd_candidate
    if module_candidate.exists():
        return module_candidate
    return None


def _format_minutes(total_minutes: int) -> str:
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def _generate_windows(shelf_time: int) -> list[tuple[str, int, int, float, float]]:
    """
    Generate product windows from 11:00 to 23:59 (inclusive), matching simulation logic.

    Returns tuples:
        (time_window, start_hour, start_minute, sin_time, cos_time)
    """
    if shelf_time <= 0:
        return []

    opening_minutes = 11 * 60
    closing_minutes = 23 * 60 + 59

    windows: list[tuple[str, int, int, float, float]] = []
    start = opening_minutes

    while start <= closing_minutes:
        end = min(start + shelf_time - 1, closing_minutes)
        start_hhmm = _format_minutes(start)
        end_hhmm = _format_minutes(end)

        start_hour = start // 60
        start_minute = start % 60

        sin_time = float(np.sin(2 * np.pi * start / 1440.0))
        cos_time = float(np.cos(2 * np.pi * start / 1440.0))

        windows.append(
            (f"{start_hhmm}_{end_hhmm}", start_hour, start_minute, sin_time, cos_time)
        )
        start += shelf_time

    return windows


def predict_ml(
    db_path: str, week_day: str, event: str, weather: str
) -> list[dict] | None:
    model_path = _resolve_model_path()

    # Auto-generate the model on first ML run if file is missing.
    if model_path is None:
        print(
            "'kitchen_model.pkl' not found. Generating model from database history..."
        )
        try:
            train_and_save_pipeline(db_path=db_path, model_path=MODEL_FILENAME)
            model_path = _resolve_model_path()
        except Exception as exc:
            print(f"❌ Could not auto-train model: {exc}. Falling back to baseline.")
            return None

    if model_path is None:
        return None

    try:
        model_pipeline = joblib.load(str(model_path))
    except Exception as exc:
        print(f"❌ Could not load ML model '{model_path}': {exc}")
        return None

    normalized_week_day = str(week_day or "").strip().lower()
    normalized_event = str(event or "NONE").strip().upper()
    normalized_weather = str(weather or "NOT_RAINING").strip().upper()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        items_df = pd.read_sql_query(
            """
            SELECT name, production_time, shelf_time
            FROM Items
            ORDER BY name;
            """,
            conn,
        )

        if items_df.empty:
            return []

        @lru_cache(maxsize=None)
        def _cached_lags(
            prod_value: str,
            time_window_value: str,
            week_day_value: str,
            event_value: str,
            weather_value: str,
        ) -> tuple[float, float]:
            return _get_historical_lags_with_fallback(
                conn,
                prod_value,
                time_window_value,
                week_day_value,
                event_value,
                weather_value,
            )

        prediction_rows: list[dict] = []

        for _, item in items_df.iterrows():
            prod = str(item["name"])
            try:
                shelf_time = int(item["shelf_time"])
                production_time = int(item["production_time"])
            except (TypeError, ValueError):
                continue

            windows = _generate_windows(shelf_time)
            for time_window, start_hour, start_minute, sin_time, cos_time in windows:
                lag_sales, lag_trash = _cached_lags(
                    prod,
                    time_window,
                    normalized_week_day,
                    normalized_event,
                    normalized_weather,
                )

                prediction_rows.append(
                    {
                        "prod": prod,
                        "start_hour": start_hour,
                        "start_minute": start_minute,
                        "sin_time": sin_time,
                        "cos_time": cos_time,
                        "week_day": normalized_week_day,
                        "event": normalized_event,
                        "weather": normalized_weather,
                        "lag_sales": lag_sales,
                        "lag_trash": lag_trash,
                        "_prod_time": production_time,
                        "_window": time_window,
                    }
                )

    if not prediction_rows:
        return []

    df_feat = pd.DataFrame(prediction_rows)
    X_pred = df_feat[FEATURE_COLS]

    raw_preds = model_pipeline.predict(X_pred)

    results: list[dict] = []
    for idx, row in df_feat.iterrows():
        pred_val = max(0.0, float(raw_preds[idx]))

        window_start = str(row["_window"]).split("_", 1)[0]
        start_dt = datetime.strptime(window_start, "%H:%M")
        prep_dt = start_dt - timedelta(minutes=int(row["_prod_time"]) + 1)

        results.append(
            {
                "prod": str(row["prod"]),
                "time_window": str(row["_window"]),
                "prep_hour": prep_dt.strftime("%H:%M"),
                "nr": round(pred_val, 2),
            }
        )

    return results
