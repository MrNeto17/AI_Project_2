from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from day_sim import (
    ORDER_HORA_EMISSAO,
    ORDER_HORA_RECEBIDO,
    ORDER_INVOICE_ID,
    PRODUCT_PRINT_ORDER,
    SimulationEngine,
)
from heuristic import pre_calc_heuristic
from main import (
    DEFAULT_DB_PATH,
    EVENT_CHOICES,
    MODEL_CHOICES,
    WEATHER_CHOICES,
    apply_manual_multiplier,
    extract_start_hour,
    get_next_simulation_day,
    sort_time_window,
    upsert_calendar_entry,
)
from ml import predict_ml
from sim_data import format_item_orders_to_queue
from simulator import generate_day
from update_db import update_day_prediction_table, update_event_weather_insight_table

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-in-production")

# Keep large runtime objects out of cookie-based Flask sessions.
_HOME_DATA: dict[str, dict[str, Any]] = {}
_SIMULATION_DATA: dict[str, dict[str, Any]] = {}


def _db_path() -> str:
    return str(session.get("db_path", DEFAULT_DB_PATH))


def _client_id() -> str:
    existing = session.get("client_id")
    if isinstance(existing, str) and existing:
        return existing

    created = str(uuid4())
    session["client_id"] = created
    return created


def _safe_float(value: Any, default: float = 1.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _refresh_prediction_tables(db_path: str) -> None:
    update_event_weather_insight_table(db_path)
    update_day_prediction_table(db_path)


def _build_schedule_tables(
    predictions: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    totals_by_hour = {hour: 0 for hour in range(11, 24)}
    grouped: dict[str, list[dict[str, Any]]] = {}

    for row in predictions:
        hour = extract_start_hour(str(row.get("time_window", "")))
        if hour in totals_by_hour:
            totals_by_hour[hour] += int(row.get("nr", 0) or 0)

        prod = str(row.get("prod", "")).upper()
        if not prod:
            continue

        grouped.setdefault(prod, []).append(
            {
                "time_window": str(row.get("time_window", "")),
                "prep_hour": str(row.get("prep_hour", "")),
                "nr": int(row.get("nr", 0) or 0),
            }
        )

    schedule: dict[str, list[dict[str, Any]]] = {
        "TOTAL": [
            {
                "time_window": f"{hour:02d}:00_{hour:02d}:59",
                "prep_hour": "- - -",
                "nr": totals_by_hour[hour],
            }
            for hour in range(11, 24)
        ]
    }

    for product in PRODUCT_PRINT_ORDER:
        product_rows = grouped.get(product, [])
        product_rows.sort(key=lambda item: sort_time_window(item["time_window"]))
        schedule[product] = product_rows

    return schedule


def _prediction_totals_by_hour(
    predictions: list[dict[str, Any]],
) -> dict[str, list[Any]]:
    totals_by_hour = {hour: 0 for hour in range(11, 24)}
    for row in predictions:
        hour = extract_start_hour(str(row.get("time_window", "")))
        if hour in totals_by_hour:
            totals_by_hour[hour] += int(row.get("nr", 0) or 0)

    labels = [f"{hour:02d}:00_{hour:02d}:59" for hour in range(11, 24)]
    values = [totals_by_hour[hour] for hour in range(11, 24)]
    return {"time_windows": labels, "values": values}


def _build_metrics_payload(
    db_path: str, sim_date: str, orders_answered: dict[str, list[list[Any]]]
) -> dict[str, Any]:
    try:
        with sqlite3.connect(db_path) as conn:
            items_row = conn.execute(
                """
                SELECT COALESCE(SUM(total_waiting_time),0), COALESCE(SUM(nr_trash_items),0)
                FROM ItemsInsight
                WHERE date=?;
                """,
                (sim_date,),
            ).fetchone()
            orders_row = conn.execute(
                """
                SELECT COALESCE(SUM(nr_predicted_orders),0), COALESCE(SUM(nr_real_orders),0)
                FROM OrdersInsight
                WHERE date=?;
                """,
                (sim_date,),
            ).fetchone()
            details_rows = conn.execute(
                """
                SELECT time_window, prod, nr_predicted_orders, nr_real_orders, nr_trashed
                FROM OrdersInsight
                WHERE date=?
                ORDER BY prod, time_window;
                """,
                (sim_date,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError(f"Failed to load metrics for {sim_date}: {exc}") from exc

    total_waiting_time = int((items_row[0] if items_row else 0) or 0)
    trashed = int((items_row[1] if items_row else 0) or 0)
    predicted = int((orders_row[0] if orders_row else 0) or 0)
    real_orders = int((orders_row[1] if orders_row else 0) or 0)

    immediate_orders = 0
    invoice_ids: set[int] = set()

    for prod_orders in orders_answered.values():
        for order in prod_orders:
            if len(order) <= ORDER_HORA_RECEBIDO:
                continue

            invoice_id = (
                order[ORDER_INVOICE_ID] if len(order) > ORDER_INVOICE_ID else None
            )
            if isinstance(invoice_id, int):
                invoice_ids.add(invoice_id)

            hora_emitida = order[ORDER_HORA_EMISSAO]
            hora_recebido = order[ORDER_HORA_RECEBIDO]
            if not isinstance(hora_emitida, datetime) or not isinstance(
                hora_recebido, datetime
            ):
                continue

            if hora_emitida.replace(second=0, microsecond=0) == hora_recebido.replace(
                second=0, microsecond=0
            ):
                immediate_orders += 1

    waste_denominator = trashed + real_orders
    waste_ratio = trashed / waste_denominator if waste_denominator > 0 else 0.0
    immediate_service_ratio = immediate_orders / real_orders if real_orders > 0 else 0.0
    avg_waiting_time = total_waiting_time / real_orders if real_orders > 0 else 0.0

    totals_by_hour: dict[int, dict[str, int]] = {
        hour: {"predicted": 0, "real": 0, "trashed": 0} for hour in range(11, 24)
    }
    per_product: dict[str, list[dict[str, Any]]] = {
        product: [] for product in PRODUCT_PRINT_ORDER
    }

    for time_window, prod, nr_pred, nr_real, nr_trashed in details_rows:
        time_window = str(time_window or "")
        product = str(prod or "").strip().upper()
        predicted_value = int(nr_pred or 0)
        real_value = int(nr_real or 0)
        trashed_value = int(nr_trashed or 0)

        if "_" in time_window and ":" in time_window:
            try:
                start_hour = int(time_window.split("_", 1)[0].split(":", 1)[0])
                if start_hour in totals_by_hour:
                    totals_by_hour[start_hour]["predicted"] += predicted_value
                    totals_by_hour[start_hour]["real"] += real_value
                    totals_by_hour[start_hour]["trashed"] += trashed_value
            except (TypeError, ValueError, IndexError):
                pass

        if product in per_product:
            per_product[product].append(
                {
                    "time_window": time_window,
                    "predicted": predicted_value,
                    "real": real_value,
                    "trashed": trashed_value,
                }
            )

    total_rows = [
        {
            "time_window": f"{hour:02d}:00_{hour:02d}:59",
            "predicted": totals_by_hour[hour]["predicted"],
            "real": totals_by_hour[hour]["real"],
            "trashed": totals_by_hour[hour]["trashed"],
        }
        for hour in range(11, 24)
    ]

    return {
        "summary": {
            "total_invoices": len(invoice_ids),
            "trashed": trashed,
            "predicted": predicted,
            "real_orders": real_orders,
            "immediate_orders": immediate_orders,
            "waste_ratio": waste_ratio,
            "immediate_service_ratio": immediate_service_ratio,
            "total_waiting_time": total_waiting_time,
            "avg_waiting_time": avg_waiting_time,
        },
        "tables": {
            "TOTAL": total_rows,
            **per_product,
        },
    }


@app.route("/", methods=["GET", "POST"])
def home() -> str:
    db_path = _db_path()

    errors: list[str] = []
    info_messages: list[str] = []

    client_id = _client_id()
    home_state = _HOME_DATA.get(client_id, {})
    schedule = home_state.get("schedule_tables")
    config = session.get("home_config", {})

    try:
        _refresh_prediction_tables(db_path)
        simulation_date, week_day = get_next_simulation_day(db_path)
    except (RuntimeError, sqlite3.Error, ValueError) as exc:
        return render_template(
            "home.html",
            error=f"Failed to prepare prediction tables: {exc}",
            schedule=None,
            simulation_date="-",
            week_day="-",
            weather_choices=WEATHER_CHOICES,
            event_choices=EVENT_CHOICES,
            model_choices=MODEL_CHOICES,
            config=config,
            has_predictions=False,
            info_messages=[],
        )

    if request.method == "POST":
        action = str(request.form.get("action", "confirm")).strip().lower()

        if action == "confirm":
            weather = str(request.form.get("weather", "")).strip().upper()
            event = str(request.form.get("event", "")).strip().upper()
            model_choice = str(request.form.get("model_choice", "")).strip()
            multiplier = _safe_float(request.form.get("multiplier"), 1.0)
            sim_speed = _safe_float(request.form.get("sim_speed"), 0.5)
            if sim_speed <= 0:
                sim_speed = 1.0

            valid_models = set(MODEL_CHOICES)
            if weather not in WEATHER_CHOICES.values():
                errors.append("Invalid weather selection.")
            if event not in EVENT_CHOICES.values():
                errors.append("Invalid event selection.")
            if model_choice not in valid_models:
                errors.append("Invalid model selection.")
            if multiplier < 0:
                errors.append("Multiplier must be non-negative.")

            config = {
                "weather": weather,
                "event": event,
                "model_choice": model_choice,
                "multiplier": multiplier,
                "sim_speed": sim_speed,
                "use_realtime_correction": bool(
                    request.form.get("use_realtime_correction")
                ),
                "simulation_date": simulation_date,
                "week_day": week_day,
            }

            if not errors:
                try:
                    if model_choice == "1":
                        predictions = pre_calc_heuristic(
                            db_path=db_path,
                            date=simulation_date,
                            week_day=week_day,
                            event=event,
                            weather=weather,
                            mult_manual=multiplier,
                        )
                    else:
                        predictions = predict_ml(
                            db_path=db_path,
                            week_day=week_day,
                            event=event,
                            weather=weather,
                        )
                        if predictions is None:
                            info_messages.append(
                                "ML model error. Heuristic fallback was used."
                            )
                            predictions = pre_calc_heuristic(
                                db_path=db_path,
                                date=simulation_date,
                                week_day=week_day,
                                event=event,
                                weather=weather,
                                mult_manual=multiplier,
                            )
                        else:
                            predictions = apply_manual_multiplier(
                                predictions, multiplier
                            )

                    if not predictions:
                        errors.append(
                            "No predictions were generated. Check Items and DayPrediction tables."
                        )
                    else:
                        schedule = _build_schedule_tables(predictions)
                        _HOME_DATA[client_id] = {
                            "predictions": predictions,
                            "schedule_tables": schedule,
                        }
                        session["home_config"] = config

                        heuristic_predictions = pre_calc_heuristic(
                            db_path=db_path,
                            date=simulation_date,
                            week_day=week_day,
                            event=event,
                            weather=weather,
                            mult_manual=multiplier,
                        )
                        ml_predictions = predict_ml(
                            db_path=db_path,
                            week_day=week_day,
                            event=event,
                            weather=weather,
                        )
                        if ml_predictions is not None:
                            ml_predictions = apply_manual_multiplier(
                                ml_predictions, multiplier
                            )

                        _HOME_DATA[client_id]["graph_compare"] = {
                            "heuristic": _prediction_totals_by_hour(
                                heuristic_predictions
                            ),
                            "ml": _prediction_totals_by_hour(ml_predictions or []),
                        }
                except (RuntimeError, sqlite3.Error, ValueError) as exc:
                    errors.append(str(exc))

        elif action == "proceed":
            predictions = home_state.get("predictions")
            config = session.get("home_config", config)
            if not predictions or not config:
                errors.append("Please confirm prediction inputs before proceeding.")
            else:
                use_realtime_correction = bool(
                    request.form.get("use_realtime_correction")
                )
                sim_speed = _safe_float(request.form.get("sim_speed"), 0.5)
                if sim_speed <= 0:
                    sim_speed = 1.0

                config["use_realtime_correction"] = use_realtime_correction
                config["sim_speed"] = sim_speed
                session["home_config"] = config

                try:
                    simulation_date = str(config["simulation_date"])
                    week_day = str(config["week_day"])
                    weather = str(config["weather"])
                    event = str(config["event"])

                    generate_day(
                        week_day=week_day,
                        event=event,
                        weather=weather,
                        db_path=db_path,
                    )

                    upsert_calendar_entry(
                        db_path=db_path,
                        sim_date=simulation_date,
                        week_day=week_day,
                        event=event,
                        weather=weather,
                    )

                    order_simulation = format_item_orders_to_queue(
                        db_path=db_path,
                        sim_date=simulation_date,
                    )

                    engine = SimulationEngine(
                        db_path=db_path,
                        predictions=predictions,
                        order_simulation=order_simulation,
                        use_dynamic_multiplier=use_realtime_correction,
                    )
                    _SIMULATION_DATA[client_id] = {
                        **engine.to_session_dict(),
                        "paused": False,
                    }
                    return redirect(url_for("simulation_page"))
                except (RuntimeError, sqlite3.Error, ValueError) as exc:
                    errors.append(f"Failed to initialize simulation: {exc}")

    has_predictions = bool(schedule)

    return render_template(
        "home.html",
        error="\n".join(errors) if errors else None,
        info_messages=info_messages,
        schedule=schedule,
        simulation_date=simulation_date,
        week_day=week_day,
        weather_choices=WEATHER_CHOICES,
        event_choices=EVENT_CHOICES,
        model_choices=MODEL_CHOICES,
        config=config,
        has_predictions=has_predictions,
    )


@app.route("/graph/<product>")
def graph_data(product: str):
    client_id = _client_id()
    schedule = _HOME_DATA.get(client_id, {}).get("schedule_tables")
    if not schedule:
        return jsonify({"error": "No schedule found. Confirm inputs first."}), 400

    normalized = str(product or "").strip().upper()
    if normalized in {"ALL", "ALL_ALGORITHMS", "ALL-ALGORITHMS"}:
        compare = _HOME_DATA.get(client_id, {}).get("graph_compare", {})
        heuristic = compare.get("heuristic", {"time_windows": [], "values": []})
        ml = compare.get("ml", {"time_windows": [], "values": []})
        return jsonify(
            {
                "mode": "compare",
                "time_windows": heuristic.get("time_windows", []),
                "heuristic": heuristic.get("values", []),
                "ml": ml.get("values", []),
            }
        )

    table_key = normalized if normalized in schedule else "TOTAL"
    rows = schedule.get(table_key, [])
    return jsonify(
        {
            "mode": "single",
            "product": table_key,
            "time_windows": [str(row.get("time_window", "")) for row in rows],
            "predictions": [int(row.get("nr", 0) or 0) for row in rows],
        }
    )


@app.route("/simulation")
def simulation_page() -> str:
    client_id = _client_id()
    state = _SIMULATION_DATA.get(client_id)
    config = session.get("home_config", {})
    if not state or not config:
        return redirect(url_for("home"))

    engine = SimulationEngine.from_session_dict(state)
    view = str(request.args.get("view", "GERAL")).strip().upper()
    paused = bool(state.get("paused", False))
    dashboard_state = engine.get_dashboard_state(view=view)
    dashboard_state["paused"] = paused
    _SIMULATION_DATA[client_id] = {
        **engine.to_session_dict(),
        "paused": paused,
    }

    refresh_ms = max(100, int(_safe_float(config.get("sim_speed"), 0.5) * 1000))

    return render_template(
        "simulation.html",
        state=dashboard_state,
        config=config,
        products=["GERAL", *PRODUCT_PRINT_ORDER],
        refresh_ms=refresh_ms,
    )


@app.route("/api/simulation/state")
def simulation_state_api():
    client_id = _client_id()
    state = _SIMULATION_DATA.get(client_id)
    if not state:
        return jsonify({"error": "Simulation not initialized."}), 400

    view = str(request.args.get("view", "GERAL")).strip().upper()
    paused = bool(state.get("paused", False))
    engine = SimulationEngine.from_session_dict(state)
    dashboard_state = engine.get_dashboard_state(view=view)
    dashboard_state["paused"] = paused
    _SIMULATION_DATA[client_id] = {
        **engine.to_session_dict(),
        "paused": paused,
    }
    return jsonify(dashboard_state)


@app.route("/api/simulation/tick", methods=["POST"])
def simulation_tick_api():
    client_id = _client_id()
    state = _SIMULATION_DATA.get(client_id)
    if not state:
        return jsonify({"error": "Simulation not initialized."}), 400

    payload = request.get_json(silent=True) or {}
    view = str(payload.get("view", "GERAL")).strip().upper()
    engine = SimulationEngine.from_session_dict(state)

    if bool(state.get("paused", False)):
        dashboard_state = engine.get_dashboard_state(view=view)
        dashboard_state["paused"] = True
        return jsonify(dashboard_state)

    dashboard_state = engine.tick(view=view)
    dashboard_state["paused"] = False
    _SIMULATION_DATA[client_id] = {
        **engine.to_session_dict(),
        "paused": False,
    }
    return jsonify(dashboard_state)


@app.route("/api/simulation/toggle-pause", methods=["POST"])
def toggle_pause_api():
    client_id = _client_id()
    state = _SIMULATION_DATA.get(client_id)
    if not state:
        return jsonify({"error": "Simulation not initialized."}), 400

    state["paused"] = not bool(state.get("paused", False))
    return jsonify({"paused": bool(state["paused"])})


@app.route("/metrics")
def metrics_page() -> str:
    client_id = _client_id()
    state = _SIMULATION_DATA.get(client_id)
    config = session.get("home_config", {})
    if not state or not config:
        return redirect(url_for("home"))

    engine = SimulationEngine.from_session_dict(state)
    if not engine.is_complete:
        return redirect(url_for("simulation_page"))

    payload = _build_metrics_payload(
        db_path=engine.db_path,
        sim_date=engine.sim_date,
        orders_answered=engine.orders_answered,
    )

    return render_template(
        "metrics.html",
        simulation_date=engine.sim_date,
        config=config,
        summary=payload["summary"],
        tables=payload["tables"],
        products=PRODUCT_PRINT_ORDER,
    )


@app.route("/api/metrics/graph/<product>")
def metrics_graph_api(product: str):
    client_id = _client_id()
    state = _SIMULATION_DATA.get(client_id)
    if not state:
        return jsonify({"error": "Simulation not initialized."}), 400

    engine = SimulationEngine.from_session_dict(state)
    payload = _build_metrics_payload(
        db_path=engine.db_path,
        sim_date=engine.sim_date,
        orders_answered=engine.orders_answered,
    )

    key = str(product or "").strip().upper()
    if key not in payload["tables"]:
        key = "TOTAL"

    rows = payload["tables"][key]
    return jsonify(
        {
            "product": key,
            "time_windows": [row["time_window"] for row in rows],
            "predicted": [int(row["predicted"]) for row in rows],
            "real": [int(row["real"]) for row in rows],
            "trashed": [int(row.get("trashed", 0)) for row in rows],
        }
    )


@app.route("/next-day", methods=["POST"])
def next_day() -> Any:
    client_id = _client_id()
    _HOME_DATA.pop(client_id, None)
    _SIMULATION_DATA.pop(client_id, None)
    session.pop("home_config", None)
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
