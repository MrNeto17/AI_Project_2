import sqlite3
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from lag_fallback import _get_historical_lags_with_fallback

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


def _format_minutes(total_minutes: int) -> str:
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def _generate_windows(shelf_time: int) -> list[tuple[str, str, int, int, float, float]]:
    """
    Generate product windows from 11:00 to 23:59 (inclusive), matching existing backend logic.

    Returns tuples:
        (time_window, start_hhmm, start_hour, start_minute, sin_time, cos_time)
    """
    if shelf_time <= 0:
        return []

    opening_minutes = 11 * 60
    closing_minutes = 23 * 60 + 59

    windows: list[tuple[str, str, int, int, float, float]] = []
    start = opening_minutes

    while start <= closing_minutes:
        end = min(start + shelf_time - 1, closing_minutes)

        start_hhmm = _format_minutes(start)
        end_hhmm = _format_minutes(end)
        time_window = f"{start_hhmm}_{end_hhmm}"

        start_hour = start // 60
        start_minute = start % 60
        mins_since_midnight = start
        sin_time = float(np.sin(2 * np.pi * mins_since_midnight / 1440.0))
        cos_time = float(np.cos(2 * np.pi * mins_since_midnight / 1440.0))

        windows.append(
            (time_window, start_hhmm, start_hour, start_minute, sin_time, cos_time)
        )
        start += shelf_time

    return windows


def build_training_dataset(db_path: str) -> pd.DataFrame:
    """
    Reconstruct training rows by iterating every Calendar day x Item x product-specific window.

    Output columns:
        prod, start_hour, start_minute, sin_time, cos_time,
        week_day, event, weather,
        lag_sales, lag_trash,
        target_real_qty
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        calendar_rows = conn.execute(
            """
            SELECT date, week_day, event, weather
            FROM Calendar
            WHERE date IS NOT NULL AND TRIM(date) != ''
            ORDER BY
                CASE
                    WHEN date LIKE '__/__/____'
                        THEN substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)
                    ELSE date
                END;
            """
        ).fetchall()

        item_rows = conn.execute(
            """
            SELECT name, shelf_time
            FROM Items
            ORDER BY name;
            """
        ).fetchall()

        if not calendar_rows or not item_rows:
            return pd.DataFrame(columns=[*FEATURE_COLS, "target_real_qty"])

        # Pre-aggregate target demand by (date, prod, HH:MM)
        demand_rows = conn.execute(
            """
            SELECT
                date,
                item AS prod,
                substr(hour, 1, 5) AS hhmm,
                COALESCE(SUM(item_quantity), 0) AS qty
            FROM ItemOrders
            GROUP BY date, item, substr(hour, 1, 5);
            """
        ).fetchall()

        demand_map: dict[tuple[str, str, str], float] = {
            (str(r["date"]), str(r["prod"]), str(r["hhmm"])): float(r["qty"] or 0.0)
            for r in demand_rows
        }

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

        records: list[dict] = []

        for cal in calendar_rows:
            date_value = str(cal["date"])
            week_day = str(cal["week_day"] or "").strip().lower()
            event = str(cal["event"] or "NONE").strip().upper()
            weather = str(cal["weather"] or "NOT_RAINING").strip().upper()

            for item in item_rows:
                prod = str(item["name"])
                try:
                    shelf_time = int(item["shelf_time"])
                except (TypeError, ValueError):
                    continue

                windows = _generate_windows(shelf_time)
                if not windows:
                    continue

                for (
                    time_window,
                    start_hhmm,
                    start_hour,
                    start_minute,
                    sin_time,
                    cos_time,
                ) in windows:
                    # Compute target by summing all minute-level orders inside the window bounds.
                    # Window is inclusive and encoded as HH:MM_HH:MM.
                    start_str, end_str = time_window.split("_", 1)

                    target_qty = 0.0
                    current_dt = datetime.strptime(start_str, "%H:%M")
                    end_dt = datetime.strptime(end_str, "%H:%M")
                    while current_dt <= end_dt:
                        hhmm = current_dt.strftime("%H:%M")
                        target_qty += demand_map.get((date_value, prod, hhmm), 0.0)
                        current_dt += timedelta(minutes=1)

                    lag_sales, lag_trash = _cached_lags(
                        prod,
                        time_window,
                        week_day,
                        event,
                        weather,
                    )

                    records.append(
                        {
                            "prod": prod,
                            "start_hour": start_hour,
                            "start_minute": start_minute,
                            "sin_time": sin_time,
                            "cos_time": cos_time,
                            "week_day": week_day,
                            "event": event,
                            "weather": weather,
                            "lag_sales": lag_sales,
                            "lag_trash": lag_trash,
                            "target_real_qty": float(target_qty),
                        }
                    )

        return pd.DataFrame.from_records(
            records, columns=[*FEATURE_COLS, "target_real_qty"]
        )


def train_and_save_pipeline(
    db_path: str = "database.db", model_path: str = "kitchen_model.pkl"
) -> None:
    df = build_training_dataset(db_path)

    if df.empty:
        print("No training data available. Model was not trained.")
        return

    X = df[FEATURE_COLS]
    y = df["target_real_qty"]

    categorical_features = ["prod", "week_day", "event", "weather"]
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                categorical_features,
            )
        ],
        remainder="passthrough",
    )

    model_pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "regressor",
                RandomForestRegressor(
                    n_estimators=150,
                    max_depth=12,
                    random_state=42,
                ),
            ),
        ]
    )

    model_pipeline.fit(X, y)

    output_path = Path(model_path)
    if not output_path.is_absolute():
        output_path = Path(__file__).resolve().parent / output_path

    joblib.dump(model_pipeline, str(output_path))
    print(f"Model saved to {output_path}")


if __name__ == "__main__":
    train_and_save_pipeline()
