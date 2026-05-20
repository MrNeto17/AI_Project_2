"""Machine-learning demand prediction for the production simulator.

The public entry point is ``predict_ml(db_path, week_day, event, weather)``.  It builds a
historical training set from ItemOrders + Calendar + Items, validates a Decision Tree
Regressor against a mean baseline, and returns predictions in the same format used by
``heuristic.pre_calc_heuristic``.  If there is not enough data, or if the tree does not
beat the baseline on the chronological test set, the function returns ``None`` so the
caller can fall back to the heuristic model.
"""

from __future__ import annotations

import math
import sqlite3
from typing import Any

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.tree import DecisionTreeRegressor

from heuristic import _calculate_prep_hour, _generate_windows

MIN_TRAINING_RECORDS = 10
OPENING_MINUTES = 11 * 60
CLOSING_MINUTES = 23 * 60 + 59

_EVENT_ALIASES = {
    "SMALL_EVENT": "SMALL",
    "BIG_EVENT": "BIG",
}


def _normalize_text(value: Any) -> str:
    """Normalize database/user categorical labels for consistent one-hot encoding."""
    return str(value or "").strip().upper()


def _normalize_event(value: Any) -> str:
    """Normalize event labels, accepting both SMALL/BIG and SMALL_EVENT/BIG_EVENT."""
    normalized = _normalize_text(value)
    return _EVENT_ALIASES.get(normalized, normalized)


def _time_to_minutes(value: Any) -> int | None:
    """Convert HH:MM or HH:MM:SS-like values to minutes since midnight."""
    if pd.isna(value):
        return None

    text = str(value).strip()
    if not text:
        return None

    # SQLite TIME values commonly arrive as HH:MM:SS.  Pandas Timestamp/Timedelta
    # string forms are also handled by taking the final whitespace-separated token.
    if " " in text:
        text = text.split()[-1]

    parts = text.split(":")
    if len(parts) < 2:
        return None

    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None

    if hour < 0 or minute < 0 or minute > 59:
        return None

    return hour * 60 + minute


def _window_bounds(time_window: str) -> tuple[int, int] | None:
    """Return numeric start/end minutes for a HH:MM_HH:MM window string."""
    try:
        start_text, end_text = time_window.split("_", 1)
    except ValueError:
        return None

    start = _time_to_minutes(start_text)
    end = _time_to_minutes(end_text)
    if start is None or end is None:
        return None
    return start, end


def _build_window_lookup(items_df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    """Generate all production windows per item using the heuristic helper."""
    lookup: dict[str, list[dict[str, Any]]] = {}

    for row in items_df.itertuples(index=False):
        prod = _normalize_text(row.name)
        shelf_time = int(row.shelf_time)
        windows: list[dict[str, Any]] = []

        for _, time_window, _, _ in _generate_windows(prod, shelf_time):
            bounds = _window_bounds(time_window)
            if bounds is None:
                continue
            start_minutes, end_minutes = bounds
            windows.append(
                {
                    "prod": prod,
                    "time_window": time_window,
                    "window_start_minutes": start_minutes,
                    "window_end_minutes": end_minutes,
                }
            )

        lookup[prod] = windows

    return lookup


def _assign_time_window(
    hour: Any, prod: Any, window_lookup: dict[str, list[dict[str, Any]]]
) -> str | None:
    """Assign an order hour to its product-specific generated window."""
    order_minutes = _time_to_minutes(hour)
    if (
        order_minutes is None
        or order_minutes < OPENING_MINUTES
        or order_minutes > CLOSING_MINUTES
    ):
        return None

    for window in window_lookup.get(_normalize_text(prod), []):
        if (
            window["window_start_minutes"]
            <= order_minutes
            <= window["window_end_minutes"]
        ):
            return str(window["time_window"])

    return None


def _parse_dates(date_series: pd.Series) -> pd.Series:
    """Parse project dates robustly; the existing app stores Calendar as DD/MM/YYYY."""
    parsed = pd.to_datetime(date_series, dayfirst=True, errors="coerce")

    # If day-first parsing failed for some ISO-like values, retry without dayfirst for
    # only those rows and keep the successful original parses.
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(date_series.loc[missing], errors="coerce")

    return parsed


def _load_training_frame(db_path: str) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Load and aggregate historical item orders into ML-ready observations."""
    try:
        with sqlite3.connect(db_path) as conn:
            orders = pd.read_sql_query(
                "SELECT date, hour, item, item_quantity FROM ItemOrders;", conn
            )
            calendar = pd.read_sql_query(
                "SELECT date, week_day, event, weather FROM Calendar;", conn
            )
            items = pd.read_sql_query(
                "SELECT name, production_time, shelf_time FROM Items;", conn
            )
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Failed to load ML training data from '{db_path}': {exc}"
        ) from exc

    if orders.empty or calendar.empty or items.empty:
        return None

    items = items.copy()
    items["prod"] = items["name"].map(_normalize_text)
    items["shelf_time"] = pd.to_numeric(items["shelf_time"], errors="coerce")
    items["production_time"] = pd.to_numeric(items["production_time"], errors="coerce")
    items = items.dropna(subset=["shelf_time", "production_time"])
    items = items[items["shelf_time"] > 0]
    if items.empty:
        return None

    orders = orders.copy()
    orders["prod"] = orders["item"].map(_normalize_text)
    orders["item_quantity"] = pd.to_numeric(
        orders["item_quantity"], errors="coerce"
    ).fillna(0)

    calendar = calendar.copy()
    calendar["week_day"] = calendar["week_day"].map(_normalize_text)
    calendar["event"] = calendar["event"].map(_normalize_event)
    calendar["weather"] = calendar["weather"].map(_normalize_text)

    df = orders.merge(
        calendar[["date", "week_day", "event", "weather"]],
        on="date",
        how="inner",
    ).merge(
        items[["prod", "shelf_time", "production_time"]],
        on="prod",
        how="inner",
    )

    if df.empty:
        return None

    window_lookup = _build_window_lookup(items)
    df["time_window"] = df.apply(
        lambda row: _assign_time_window(row["hour"], row["prod"], window_lookup), axis=1
    )
    df = df.dropna(subset=["time_window"])
    if df.empty:
        return None

    df["date_dt"] = _parse_dates(df["date"])
    df = df.dropna(subset=["date_dt"])
    if df.empty:
        return None

    aggregated = (
        df.groupby(
            ["date", "date_dt", "week_day", "event", "weather", "prod", "time_window"],
            as_index=False,
        )["item_quantity"]
        .sum()
        .sort_values(["date_dt", "prod", "time_window"])
        .reset_index(drop=True)
    )

    if len(aggregated) < MIN_TRAINING_RECORDS:
        return None

    # Numeric representation of the window lets the tree learn time-of-day effects
    # without treating raw HH:MM_HH:MM strings as continuous text.
    bounds = aggregated["time_window"].map(_window_bounds)
    aggregated["window_start_minutes"] = bounds.map(
        lambda value: value[0] if value else np.nan
    )
    aggregated["window_end_minutes"] = bounds.map(
        lambda value: value[1] if value else np.nan
    )
    aggregated = aggregated.dropna(
        subset=["window_start_minutes", "window_end_minutes"]
    )

    if len(aggregated) < MIN_TRAINING_RECORDS:
        return None

    return aggregated, items


def _add_autoregressive_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add lag and rolling features per product/window without future leakage."""
    df = df.sort_values(["prod", "time_window", "date_dt"]).copy()
    grouped = df.groupby(["prod", "time_window"], sort=False)["item_quantity"]

    # shift(1) is the requested sparse-data proxy for the previous comparable record.
    df["lag_1w"] = grouped.shift(1)

    # Use only previous observations for the rolling average so the target row does not
    # leak into its own features during training/evaluation.
    df["rolling_3d_avg"] = grouped.transform(
        lambda series: series.shift(1).rolling(window=3, min_periods=1).mean()
    )

    df[["lag_1w", "rolling_3d_avg"]] = df[["lag_1w", "rolling_3d_avg"]].fillna(0)
    return df.sort_values(["date_dt", "prod", "time_window"]).reset_index(drop=True)


def _prepare_model_matrix(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """One-hot encode categorical features and return X/y/feature column names."""
    encoded = pd.get_dummies(
        df,
        columns=["week_day", "event", "weather", "prod"],
        drop_first=False,
    )

    excluded = {"date", "date_dt", "item_quantity", "time_window"}
    feature_cols = [column for column in encoded.columns if column not in excluded]

    X = encoded[feature_cols].astype(float)
    y = encoded["item_quantity"].astype(float)
    return X, y, feature_cols


def _latest_history_features(
    df: pd.DataFrame,
) -> dict[tuple[str, str], dict[str, float]]:
    """Build current-context lag/rolling values from the latest historical records."""
    history: dict[tuple[str, str], dict[str, float]] = {}

    for (prod, time_window), group in df.groupby(["prod", "time_window"]):
        ordered = group.sort_values("date_dt")
        quantities = ordered["item_quantity"].astype(float)
        history[(str(prod), str(time_window))] = {
            "lag_1w": float(quantities.iloc[-1]) if len(quantities) else 0.0,
            "rolling_3d_avg": float(quantities.tail(3).mean())
            if len(quantities)
            else 0.0,
        }

    return history


def _build_prediction_frame(
    items: pd.DataFrame,
    history: dict[tuple[str, str], dict[str, float]],
    week_day: str,
    event: str,
    weather: str,
) -> pd.DataFrame:
    """Create one current-context row for every product-specific production window."""
    window_lookup = _build_window_lookup(items)
    rows: list[dict[str, Any]] = []

    for item in items.sort_values("prod").itertuples(index=False):
        prod = _normalize_text(item.prod)
        for window in window_lookup.get(prod, []):
            time_window = str(window["time_window"])
            hist = history.get(
                (prod, time_window), {"lag_1w": 0.0, "rolling_3d_avg": 0.0}
            )
            rows.append(
                {
                    "prod": prod,
                    "time_window": time_window,
                    "week_day": _normalize_text(week_day),
                    "event": _normalize_event(event),
                    "weather": _normalize_text(weather),
                    "window_start_minutes": float(window["window_start_minutes"]),
                    "window_end_minutes": float(window["window_end_minutes"]),
                    "lag_1w": hist["lag_1w"],
                    "rolling_3d_avg": hist["rolling_3d_avg"],
                    "production_time": int(item.production_time),
                }
            )

    return pd.DataFrame(rows)


def _align_prediction_matrix(
    prediction_rows: pd.DataFrame, feature_cols: list[str]
) -> pd.DataFrame:
    """One-hot encode current rows and align them to the training feature schema."""
    encoded = pd.get_dummies(
        prediction_rows.drop(columns=["production_time"]),
        columns=["week_day", "event", "weather", "prod"],
        drop_first=False,
    )

    for column in feature_cols:
        if column not in encoded.columns:
            encoded[column] = 0.0

    return encoded[feature_cols].astype(float)


def predict_ml(
    db_path: str, week_day: str, event: str, weather: str
) -> list[dict] | None:
    """
    Predict production quantities using a validated Decision Tree Regressor.

    Returns:
        A list of dictionaries compatible with ``pre_calc_heuristic`` when the ML model
        beats the DummyRegressor baseline on the chronological test set; otherwise
        ``None`` to signal that the caller should fall back to the heuristic model.
    """
    loaded = _load_training_frame(db_path)
    if loaded is None:
        return None

    historical_df, items = loaded
    historical_df = _add_autoregressive_features(historical_df)

    if len(historical_df) < MIN_TRAINING_RECORDS:
        return None

    X, y, feature_cols = _prepare_model_matrix(historical_df)
    split_idx = int(len(X) * 0.8)

    if split_idx <= 0 or split_idx >= len(X):
        return None

    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    if X_train.empty or X_test.empty:
        return None

    baseline = DummyRegressor(strategy="mean")
    baseline.fit(X_train, y_train)
    baseline_mae = mean_absolute_error(y_test, baseline.predict(X_test))

    tree_model = DecisionTreeRegressor(
        max_depth=5,
        min_samples_split=10,
        random_state=42,
    )
    tree_model.fit(X_train, y_train)
    tree_mae = mean_absolute_error(y_test, tree_model.predict(X_test))

    print(
        "ML validation MAE "
        f"| baseline: {baseline_mae:.2f} "
        f"| decision tree: {tree_mae:.2f}"
    )

    # Strictly require the tree to beat the naive historical-mean baseline.
    if tree_mae >= baseline_mae:
        return None

    history = _latest_history_features(historical_df)
    prediction_rows = _build_prediction_frame(items, history, week_day, event, weather)
    if prediction_rows.empty:
        return None

    X_current = _align_prediction_matrix(prediction_rows, feature_cols)
    raw_predictions = tree_model.predict(X_current)

    results: list[dict] = []
    for row, prediction in zip(prediction_rows.to_dict("records"), raw_predictions):
        nr = max(0, math.ceil(float(prediction)))
        results.append(
            {
                "prod": str(row["prod"]),
                "time_window": str(row["time_window"]),
                "prep_hour": _calculate_prep_hour(
                    str(row["time_window"]), int(row["production_time"])
                ),
                "nr": nr,
            }
        )

    return results
