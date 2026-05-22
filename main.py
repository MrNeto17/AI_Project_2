import argparse
import math
import sqlite3
import sys
from datetime import datetime, timedelta

from day_sim import day_simulation, print_end_of_day_report
from heuristic import pre_calc_heuristic
from ml import predict_ml
from sim_data import format_item_orders_to_queue
from simulator import generate_day
from update_db import update_day_prediction_table, update_event_weather_insight_table

DEFAULT_DB_PATH = "database.db"

WEATHER_CHOICES = {
    "1": "NOT_RAINING",
    "2": "RAINING",
}

EVENT_CHOICES = {
    "1": "NONE",
    "2": "HOLIDAY",
    "3": "SMALL_EVENT",
    "4": "BIG_EVENT",
}

MODEL_CHOICES = {
    "1": "Heuristic Model (Baseline)",
    "2": "Machine Learning Model (Experimental)",
}

PRODUCT_PRINT_ORDER = [
    "BEEF_BURGER",
    "CHICKEN_BURGER",
    "FISH_BURGER",
    "VEGAN_BURGER",
    "FRIES",
    "APPLE_PIE",
]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run the production prediction simulator pre-shift workflow."
    )
    parser.add_argument(
        "db_path",
        nargs="?",
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database file. Default: {DEFAULT_DB_PATH}",
    )
    return parser.parse_args()


def get_next_simulation_day(db_path: str) -> tuple[str, str]:
    """
    Resolve the next simulation date from the latest Calendar date.

    Calendar dates are stored as DD/MM/YYYY. The query orders by a converted ISO date so the
    latest date is chronologically correct even when multiple months are present.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT date
                FROM Calendar
                WHERE date IS NOT NULL AND TRIM(date) != ''
                ORDER BY
                    CASE
                        WHEN date LIKE '__/__/____'
                            THEN substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)
                        ELSE date
                    END DESC
                LIMIT 1;
                """
            ).fetchone()
    except sqlite3.Error as exc:
        raise RuntimeError(f"Failed to read latest Calendar date: {exc}") from exc

    if row is None or row[0] is None:
        raise RuntimeError(
            "Calendar table is empty; cannot derive next simulation day."
        )

    try:
        latest_date = datetime.strptime(str(row[0]), "%d/%m/%Y")
    except ValueError as exc:
        raise RuntimeError(
            f"Latest Calendar date '{row[0]}' is not in expected DD/MM/YYYY format."
        ) from exc

    next_date = latest_date + timedelta(days=1)
    return next_date.strftime("%d/%m/%Y"), next_date.strftime("%A")


def prompt_menu_choice(title: str, choices: dict[str, str]) -> str:
    """Prompt until the user selects a valid numbered choice."""
    while True:
        print(title)
        for key, value in choices.items():
            print(f"  {key} - {value.replace('_', ' ').title()}")

        selected = input("Choice: ").strip()
        if selected in choices:
            return choices[selected]

        print("Invalid choice. Please enter one of the listed numbers.\n")


def prompt_multiplier() -> float:
    """Prompt for the manual multiplier, defaulting to 1.0 on empty input."""
    while True:
        raw_value = input("Multiplier (press Enter for default 1.0): ").strip()
        if raw_value == "":
            return 1.0

        try:
            return float(raw_value)
        except ValueError:
            print(
                "Invalid multiplier. Please enter a valid number, e.g. 1.0 or 1.25.\n"
            )


def collect_user_inputs() -> tuple[str, str, float]:
    """Collect weather, event, and manual multiplier, then ask for confirmation."""
    while True:
        print("\nChoose simulation conditions:")
        weather = prompt_menu_choice("Weather:", WEATHER_CHOICES)
        print()
        event = prompt_menu_choice("Event:", EVENT_CHOICES)
        print()
        mult_manual = prompt_multiplier()

        print("\nSelected configuration:")
        print(f"  Weather:    {weather}")
        print(f"  Event:      {event}")
        print(f"  Multiplier: {mult_manual}")

        while True:
            confirmation = input("Confirm these values? (y/n): ").strip().lower()
            if confirmation in {"y", "yes"}:
                return weather, event, mult_manual
            if confirmation in {"n", "no"}:
                print("\nLet's enter the values again.")
                break
            print("Please answer 'y' or 'n'.")


def prompt_prediction_model() -> str:
    """Prompt until the user selects the heuristic or ML prediction model."""
    while True:
        print("\nChoose prediction model:")
        for key, value in MODEL_CHOICES.items():
            print(f"  {key} - {value}")

        selected = input("Choice: ").strip()
        if selected in MODEL_CHOICES:
            return selected

        print("Invalid choice. Please enter 1 or 2.")


def apply_manual_multiplier(predictions: list[dict], mult_manual: float) -> list[dict]:
    """Apply the operator multiplier to already formatted prediction rows."""
    try:
        multiplier = float(mult_manual)
    except (TypeError, ValueError):
        multiplier = 1.0

    adjusted: list[dict] = []
    for row in predictions:
        adjusted_row = dict(row)
        adjusted_row["nr"] = max(0, math.trunc(int(row.get("nr", 0) or 0) * multiplier))
        adjusted.append(adjusted_row)

    return adjusted


def extract_start_hour(time_window: str) -> int | None:
    """Extract the starting hour from a HH:MM_HH:MM time-window string."""
    try:
        return int(time_window.split("_", 1)[0].split(":", 1)[0])
    except (AttributeError, IndexError, TypeError, ValueError):
        return None


def sort_time_window(time_window: str) -> tuple[int, int, str]:
    """Sort helper for HH:MM_HH:MM strings."""
    try:
        start = time_window.split("_", 1)[0]
        hour, minute = start.split(":", 1)
        return int(hour), int(minute), time_window
    except (AttributeError, IndexError, TypeError, ValueError):
        return 99, 99, str(time_window)


def print_production_schedule(predictions: list[dict]) -> None:
    """Print TOTAL and per-product production schedule sections."""
    header = f"{'Time Window':<13} - {'Prep Time':<9} - Prediction"

    print("\n[TOTAL]")
    print(header)

    totals_by_hour = {hour: 0 for hour in range(11, 24)}
    for row in predictions:
        hour = extract_start_hour(str(row.get("time_window", "")))
        if hour in totals_by_hour:
            totals_by_hour[hour] += int(row.get("nr", 0) or 0)

    for hour in range(11, 24):
        total_window = f"{hour:02d}:00_{hour:02d}:59"
        print(f"{total_window:<13} - {'- - -':<9} - {totals_by_hour[hour]}")

    grouped: dict[str, list[dict]] = {}
    for row in predictions:
        prod = str(row.get("prod", "")).upper()
        if prod:
            grouped.setdefault(prod, []).append(row)

    ordered_products = [prod for prod in PRODUCT_PRINT_ORDER if prod in grouped]
    extra_products = sorted(prod for prod in grouped if prod not in PRODUCT_PRINT_ORDER)

    for prod in ordered_products + extra_products:
        print(f"\n[{prod}]")
        print(header)
        for row in sorted(
            grouped[prod],
            key=lambda item: sort_time_window(str(item.get("time_window", ""))),
        ):
            time_window = str(row.get("time_window", ""))
            prep_hour = str(row.get("prep_hour", ""))
            nr = int(row.get("nr", 0) or 0)
            print(f"{time_window:<13} - {prep_hour:<9} - {nr}")


def upsert_calendar_entry(
    db_path: str,
    sim_date: str,
    week_day: str,
    event: str,
    weather: str,
) -> None:
    """Insert/update one Calendar row for the simulated day using uppercase context labels."""
    normalized_event = str(event or "").strip().upper()
    normalized_weather = str(weather or "").strip().upper()

    valid_events = {"NONE", "HOLIDAY", "SMALL_EVENT", "BIG_EVENT"}
    valid_weather = {"NOT_RAINING", "RAINING"}

    if normalized_event not in valid_events:
        raise ValueError(
            f"Invalid event '{event}'. Expected one of: {', '.join(sorted(valid_events))}."
        )
    if normalized_weather not in valid_weather:
        raise ValueError(
            f"Invalid weather '{weather}'. Expected one of: {', '.join(sorted(valid_weather))}."
        )

    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO Calendar (date, week_day, event, weather)
                VALUES (?, ?, ?, ?);
                """,
                (sim_date, week_day, normalized_event, normalized_weather),
            )
            conn.commit()
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Failed to upsert Calendar entry for {sim_date}: {exc}"
        ) from exc


def main() -> None:
    """Run the full production prediction simulator pre-shift workflow."""
    args = parse_args()
    db_path = args.db_path

    print(f"Using database: {db_path}")

    try:
        while True:
            # Step 1: Refresh pre-calculated database tables before generating predictions.
            print("Updating EventWeatherInsight...")
            update_event_weather_insight_table(db_path)
            print("EventWeatherInsight updated successfully.")

            print("Updating DayPrediction...")
            update_day_prediction_table(db_path)
            print("DayPrediction updated successfully.")

            # Step 2: Resolve the next simulation date from Calendar without inserting it.
            simulation_date, week_day = get_next_simulation_day(db_path)
            print(f"\nNext simulation date: {simulation_date}")
            print(f"Weekday: {week_day}")

            # Step 3: Gather operator inputs and choose the prediction model.
            weather, event, mult_manual = collect_user_inputs()
            model_choice = prompt_prediction_model()

            # Step 4: Run the selected pre-shift prediction model.
            print("\nCalculating pre-shift production schedule...")
            if model_choice == "1":
                predictions = pre_calc_heuristic(
                    db_path=db_path,
                    date=simulation_date,
                    week_day=week_day,
                    event=event,
                    weather=weather,
                    mult_manual=mult_manual,
                )
            else:
                predictions = predict_ml(
                    db_path=db_path,
                    week_day=week_day,
                    event=event,
                    weather=weather,
                )

                if predictions is None:
                    print(
                        "⚠️ ML Model performance below baseline. Falling back to Heuristic Model."
                    )
                    predictions = pre_calc_heuristic(
                        db_path=db_path,
                        date=simulation_date,
                        week_day=week_day,
                        event=event,
                        weather=weather,
                        mult_manual=mult_manual,
                    )
                else:
                    predictions = apply_manual_multiplier(predictions, mult_manual)

            if not predictions:
                print(
                    "No predictions were generated. Check that Items and DayPrediction contain data."
                )
                break

            # Step 5: Print the formatted production schedule.
            print_production_schedule(predictions)

            # SIMULATION SECTION
            proceed = (
                input("\nDo you want to proceed with the simulation (y/n): ")
                .strip()
                .lower()
            )
            if proceed not in ("y", "yes"):
                print("Simulation cancelled. Exiting.")
                break

            # Toggle for real-time correctness algorithm.
            use_realtime_correction = (
                input("Do you want a real-time correctness algorithm (y/n): ")
                .strip()
                .lower()
            )
            enable_multiplier = use_realtime_correction in ("y", "yes")

            raw_seconds = input(
                "Time of a simulated minute (default 1.0 seconds): "
            ).strip()
            sim_seconds = float(raw_seconds) if raw_seconds else 1.0

            # Generate the simulated sales day before reading ItemOrders for the real-time queue.
            generate_day(
                week_day=week_day,
                event=event,
                weather=weather,
                db_path=db_path,
            )

            # Upsert Calendar right before assigning order_simulation (requested integration point).
            upsert_calendar_entry(
                db_path=db_path,
                sim_date=simulation_date,
                week_day=week_day,
                event=event,
                weather=weather,
            )

            # Build simulation-order payload from the generated ItemOrders for the same simulation date.
            order_simulation = format_item_orders_to_queue(
                db_path=db_path, sim_date=simulation_date
            )

            orders_answered = day_simulation(
                sim_seconds,
                predictions,
                order_simulation,
                db_path,
                enable_multiplier,
            )
            print_end_of_day_report(db_path, simulation_date, orders_answered)

            restart_choice = input("\nGo to next day (y/n): ").strip().lower()
            if restart_choice not in ("y", "yes"):
                print("Simulation ended. Exiting.")
                break

    except (RuntimeError, sqlite3.Error, ValueError) as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)


if __name__ == "__main__":
    main()
