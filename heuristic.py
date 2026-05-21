import math
import sqlite3
from datetime import datetime, timedelta

_WEATHER_COLUMN_BY_VALUE = {
    "RAINING": "pct_dif_raining",
    "NOT_RAINING": "pct_dif_not_raining",
}

_EVENT_COLUMN_BY_VALUE = {
    "NONE": "pct_dif_event_none",
    "HOLIDAY": "pct_dif_event_holiday",
    "SMALL_EVENT": "pct_dif_event_small",
    "BIG_EVENT": "pct_dif_event_big",
}


def _format_minutes(total_minutes: int) -> str:
    """Format minutes since midnight as HH:MM."""
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def _generate_windows(prod: str, shelf_time: int) -> list[tuple[str, str, str, str]]:
    """
    Generate product-specific public-hours windows from 11:00 to 23:59.

    Each row is: (prod, time_window, start_hour, end_hour), matching the same window format
    used by DayPrediction and EventWeatherInsight.
    """
    if shelf_time <= 0:
        raise ValueError(
            f"Invalid shelf_time for product '{prod}': expected a positive integer, got {shelf_time}."
        )

    opening_minutes = 11 * 60
    closing_minutes = 23 * 60 + 59
    windows: list[tuple[str, str, str, str]] = []

    start = opening_minutes
    while start <= closing_minutes:
        end = min(start + shelf_time - 1, closing_minutes)
        start_hour = _format_minutes(start)
        end_hour = _format_minutes(end)
        windows.append((prod, f"{start_hour}_{end_hour}", start_hour, end_hour))
        start += shelf_time

    return windows


def _calculate_prep_hour(time_window: str, production_time: int) -> str:
    """
    Extract the start of a HH:MM_HH:MM window and subtract production_time + 1 minutes.

    If a malformed window somehow reaches this function, default to 00:00 instead of crashing
    the pre-shift calculation.
    """
    try:
        window_start = time_window.split("_", 1)[0]
        start_dt = datetime.strptime(window_start, "%H:%M")
        prep_dt = start_dt - timedelta(minutes=int(production_time) + 1)
        return prep_dt.strftime("%H:%M")
    except (AttributeError, IndexError, TypeError, ValueError):
        return "00:00"


def pre_calc_heuristic(
    db_path: str,
    date: str,
    week_day: str,
    event: str = "NONE",
    weather: str = "NOT_RAINING",
    mult_manual: float = 1.0,
) -> list[dict]:
    """
    Calculate pre-shift production predictions (CALCULO) for all production items/windows.

    Formula:
        CALCULO = VALUE * PCT_EVENT * PCT_WEATHER * MULTIPLICADOR_MANUAL

    Returns a list of dictionaries with keys:
        {"prod": str, "time_window": str, "prep_hour": str, "nr": int}
    """
    _ = date  # The current schema's pre-shift baseline is keyed by week_day, not by date.

    normalized_week_day = (week_day or "").strip().lower()
    normalized_event = (event or "NONE").strip().upper()
    normalized_weather = (weather or "NOT_RAINING").strip().upper()

    # Step 2: Map weather/event inputs to the proper EventWeatherInsight columns.
    # Unknown context values gracefully default to multiplier 1.0.
    weather_column = _WEATHER_COLUMN_BY_VALUE.get(normalized_weather)
    event_column = _EVENT_COLUMN_BY_VALUE.get(normalized_event)
    weather_expr = f"COALESCE(ewi.{weather_column}, 1.0)" if weather_column else "1.0"
    event_expr = f"COALESCE(ewi.{event_column}, 1.0)" if event_column else "1.0"

    try:
        manual_multiplier = float(mult_manual)
    except (TypeError, ValueError):
        manual_multiplier = 1.0

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")

            # Step 1: Generate product-specific time windows dynamically from Items.shelf_time.
            item_rows = conn.execute(
                """
                SELECT name, shelf_time
                FROM Items
                ORDER BY name;
                """
            ).fetchall()

            if not item_rows:
                return []

            window_rows: list[tuple[str, str, str, str]] = []
            for item in item_rows:
                window_rows.extend(
                    _generate_windows(str(item["name"]), int(item["shelf_time"]))
                )

            conn.execute("DROP TABLE IF EXISTS temp_pre_calc_windows;")
            conn.execute(
                """
                CREATE TEMP TABLE temp_pre_calc_windows (
                    prod TEXT NOT NULL,
                    time_window TEXT NOT NULL,
                    start_hour TEXT NOT NULL,
                    end_hour TEXT NOT NULL,
                    PRIMARY KEY (prod, time_window)
                );
                """
            )
            conn.executemany(
                """
                INSERT INTO temp_pre_calc_windows
                    (prod, time_window, start_hour, end_hour)
                VALUES (?, ?, ?, ?);
                """,
                window_rows,
            )

            # Steps 1 and 2: Single SQL JOIN fetch for windows, DayPrediction, EventWeatherInsight,
            # and Items. Missing VALUE/PCT rows are defaulted with COALESCE.
            rows = conn.execute(
                f"""
                SELECT
                    w.prod,
                    w.time_window,
                    i.production_time,
                    COALESCE(dp.prediction, 0.0) AS value_prediction,
                    {weather_expr} AS pct_weather,
                    {event_expr} AS pct_event
                FROM temp_pre_calc_windows w
                INNER JOIN Items i
                    ON i.name = w.prod
                LEFT JOIN DayPrediction dp
                    ON dp.week_day = ?
                   AND dp.time_window = w.time_window
                   AND dp.prod = w.prod
                LEFT JOIN EventWeatherInsight ewi
                    ON ewi.time_window = w.time_window
                   AND ewi.prod = w.prod
                ORDER BY w.prod, w.time_window;
                """,
                (normalized_week_day,),
            ).fetchall()

            conn.execute("DROP TABLE IF EXISTS temp_pre_calc_windows;")

    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Failed to calculate pre-shift heuristic for database '{db_path}': {exc}"
        ) from exc

    results: list[dict] = []
    for row in rows:
        value = float(row["value_prediction"] or 0.0)
        pct_weather = float(row["pct_weather"] or 1.0)
        pct_event = float(row["pct_event"] or 1.0)

        # Step 1: Apply CALCULO formula.
        raw_calc = value * pct_event * pct_weather * manual_multiplier

        # Step 3: Calculate prep_hour from window start minus production_time + 1 minute buffer.
        prep_hour = _calculate_prep_hour(
            row["time_window"], int(row["production_time"] or 0)
        )

        # Step 4: Round up and guarantee a non-negative production quantity.
        nr = max(0, raw_calc)  # nr = max(0, math.trunc(raw_calc))

        results.append(
            {
                "prod": str(row["prod"]),
                "time_window": str(row["time_window"]),
                "prep_hour": prep_hour,
                "nr": nr,
            }
        )

    return results
