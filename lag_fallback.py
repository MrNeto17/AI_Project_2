import sqlite3


def _normalize_week_day(value: str) -> str:
    return str(value or "").strip().lower()


def _normalize_event(value: str) -> str:
    return str(value or "NONE").strip().upper()


def _normalize_weather(value: str) -> str:
    return str(value or "NOT_RAINING").strip().upper()


def _get_historical_lags_with_fallback(
    conn: sqlite3.Connection,
    prod: str,
    time_window: str,
    week_day: str,
    event: str,
    weather: str,
) -> tuple[float, float]:
    """
    Return (avg_real_orders, avg_trashed) with fallback cascade.

    OrdersInsight currently stores date/time_window/prod counters.
    Context columns (week_day/event/weather) are obtained by joining Calendar on date.

    Cascade:
      1) prod + time_window + week_day + event + weather
      2) prod + time_window + week_day
      3) prod + time_window
      4) default (0.0, 0.0)
    """
    wd = _normalize_week_day(week_day)
    ev = _normalize_event(event)
    we = _normalize_weather(weather)

    # Level 1: full contextual match
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS n,
            AVG(COALESCE(oi.nr_real_orders, 0)) AS avg_real,
            AVG(COALESCE(oi.nr_trashed, 0)) AS avg_trash
        FROM OrdersInsight oi
        INNER JOIN Calendar c ON c.date = oi.date
        WHERE oi.prod = ?
          AND oi.time_window = ?
          AND LOWER(c.week_day) = ?
          AND UPPER(c.event) = ?
          AND UPPER(c.weather) = ?;
        """,
        (prod, time_window, wd, ev, we),
    ).fetchone()
    if row and int(row[0] or 0) > 0:
        return float(row[1] or 0.0), float(row[2] or 0.0)

    # Level 2: ignore event/weather (weekday only)
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS n,
            AVG(COALESCE(oi.nr_real_orders, 0)) AS avg_real,
            AVG(COALESCE(oi.nr_trashed, 0)) AS avg_trash
        FROM OrdersInsight oi
        INNER JOIN Calendar c ON c.date = oi.date
        WHERE oi.prod = ?
          AND oi.time_window = ?
          AND LOWER(c.week_day) = ?;
        """,
        (prod, time_window, wd),
    ).fetchone()
    if row and int(row[0] or 0) > 0:
        return float(row[1] or 0.0), float(row[2] or 0.0)

    # Level 3: global prod+window average (context-agnostic)
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS n,
            AVG(COALESCE(nr_real_orders, 0)) AS avg_real,
            AVG(COALESCE(nr_trashed, 0)) AS avg_trash
        FROM OrdersInsight
        WHERE prod = ?
          AND time_window = ?;
        """,
        (prod, time_window),
    ).fetchone()
    if row and int(row[0] or 0) > 0:
        return float(row[1] or 0.0), float(row[2] or 0.0)

    return 0.0, 0.0
