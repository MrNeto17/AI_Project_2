"""Minute-by-minute real-time day simulation loop.

This module owns only runtime state transitions for the 7-column simulation structure
and OrdersInsight counter flushing. It does not calculate prediction multipliers.
"""

from __future__ import annotations

import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pprint import pformat
from typing import Any

OPEN_MINUTES = 10 * 60 + 30
PUBLIC_START_MINUTES = 11 * 60
END_MINUTES = 24 * 60

ORDER_NAME = 0
ORDER_INVOICE_ID = 1
ORDER_HORA_EMISSAO = 2
ORDER_HORA_RECEBIDO = 3
ORDER_ESTADO = 4

ITEM_NAME = 0
ITEM_HORA_PRONTO = 1
ITEM_HORA_PRAZO = 2
ITEM_HORA_ENTREGUE = 3
ITEM_ESTADO = 4

STATE_INATIVO = "INATIVO"
STATE_ESPERA = "ESPERA"
STATE_ENTREGUE = "ENTREGUE"
STATE_PREPARACAO = "PREPARACAO"
STATE_PRATELEIRA = "PRATELEIRA"
STATE_LIXO = "LIXO"

PRODUCT_PRINT_ORDER = [
    "BEEF_BURGER",
    "CHICKEN_BURGER",
    "FISH_BURGER",
    "VEGAN_BURGER",
    "FRIES",
    "APPLE_PIE",
]


@dataclass(frozen=True)
class ItemConfig:
    name: str
    production_time: int
    shelf_time: int
    max_capacity: int


@dataclass(frozen=True)
class WindowInfo:
    time_window: str
    start_minute: int
    end_minute: int


@dataclass(frozen=True)
class PredictionEvent:
    prod: str
    time_window: str
    nr: int


def _normalize_prod(value: Any) -> str:
    return str(value or "").strip().lower()


def _minutes_to_hhmm(total_minutes: int) -> str:
    total_minutes %= 24 * 60
    hour, minute = divmod(total_minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def _datetime_to_minute(value: datetime) -> int:
    return value.hour * 60 + value.minute


def _parse_clock_to_minute(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Empty clock value cannot be parsed.")
    if " " in text:
        text = text.split()[-1]
    parts = text.split(":")
    if len(parts) < 2:
        raise ValueError(f"Invalid clock value '{value}'. Expected HH:MM.")
    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Clock value out of range: '{value}'.")
    return hour * 60 + minute


def _minute_to_datetime(day_anchor: datetime, minute: int) -> datetime:
    if minute >= 24 * 60:
        return day_anchor.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
    return day_anchor.replace(
        hour=minute // 60, minute=minute % 60, second=0, microsecond=0
    )


def _same_sim_minute(left: Any, right: datetime) -> bool:
    return isinstance(left, datetime) and left.replace(
        second=0, microsecond=0
    ) == right.replace(second=0, microsecond=0)


def _infer_sim_date(order_simulation: list[list[Any]], db_path: str) -> str:
    for order in order_simulation:
        if len(order) >= 3 and isinstance(order[ORDER_HORA_EMISSAO], datetime):
            return order[ORDER_HORA_EMISSAO].strftime("%d/%m/%Y")

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
    if row is None:
        raise RuntimeError(
            "Cannot infer simulation date: order_simulation and Calendar are empty."
        )
    return str(row[0])


def _load_item_configs(db_path: str) -> dict[str, ItemConfig]:
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT name, production_time, shelf_time, max_capacity
                FROM Items
                ORDER BY name;
                """
            ).fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError(f"Failed to load Items configuration: {exc}") from exc

    configs: dict[str, ItemConfig] = {}
    for row in rows:
        name = _normalize_prod(row["name"])
        configs[name] = ItemConfig(
            name=name,
            production_time=int(row["production_time"]),
            shelf_time=int(row["shelf_time"]),
            max_capacity=int(row["max_capacity"]),
        )
    if not configs:
        raise RuntimeError("Items table is empty; day simulation cannot run.")
    return configs


def _build_windows(configs: dict[str, ItemConfig]) -> dict[str, list[WindowInfo]]:
    windows: dict[str, list[WindowInfo]] = {}
    closing = 23 * 60 + 59
    for prod, config in configs.items():
        prod_windows: list[WindowInfo] = []
        start = PUBLIC_START_MINUTES
        while start <= closing:
            end = min(start + config.shelf_time - 1, closing)
            prod_windows.append(
                WindowInfo(
                    time_window=f"{_minutes_to_hhmm(start)}_{_minutes_to_hhmm(end)}",
                    start_minute=start,
                    end_minute=end,
                )
            )
            start += config.shelf_time
        windows[prod] = prod_windows
    return windows


def _window_for_minute(windows: list[WindowInfo], minute: int) -> WindowInfo | None:
    minute = minute % (24 * 60)
    for window in windows:
        if window.start_minute <= minute <= window.end_minute:
            return window
    return None


def _window_by_name(windows: list[WindowInfo], time_window: str) -> WindowInfo | None:
    for window in windows:
        if window.time_window == time_window:
            return window
    return None


def _build_prediction_events(
    predictions: list[dict],
    configs: dict[str, ItemConfig],
    windows_by_prod: dict[str, list[WindowInfo]],
) -> dict[int, list[PredictionEvent]]:
    events: dict[int, list[PredictionEvent]] = defaultdict(list)
    for row in predictions:
        prod = _normalize_prod(row.get("prod"))
        if prod not in configs:
            continue

        nr = max(0, int(row.get("nr", 0) or 0))
        if nr <= 0:
            continue

        time_window = str(row.get("time_window", "")).strip()
        prep_hour = str(row.get("prep_hour", "")).strip()
        if prep_hour:
            prep_minute = _parse_clock_to_minute(prep_hour)
        else:
            window = _window_by_name(windows_by_prod[prod], time_window)
            if window is None:
                continue
            prep_minute = window.start_minute - (configs[prod].production_time + 1)

        events[prep_minute].append(
            PredictionEvent(prod=prod, time_window=time_window, nr=nr)
        )
    return events


def _initialize_order_queues(
    order_simulation: list[list[Any]],
    product_names: set[str],
) -> dict[str, list[list[Any]]]:
    queues = {prod: [] for prod in product_names}
    for raw_order in order_simulation:
        if len(raw_order) != 5:
            raise ValueError(f"Invalid order_simulation entry length: {raw_order}")
        prod = _normalize_prod(raw_order[ORDER_NAME])
        if prod not in queues:
            queues[prod] = []
        order = list(raw_order)
        order[ORDER_NAME] = prod
        order[ORDER_INVOICE_ID] = int(order[ORDER_INVOICE_ID])
        if not isinstance(order[ORDER_HORA_EMISSAO], datetime):
            raise ValueError(
                f"HORA_EMISSAO must be datetime in order entry: {raw_order}"
            )
        order[ORDER_HORA_RECEBIDO] = None
        order[ORDER_ESTADO] = STATE_INATIVO
        queues[prod].append(order)
    return queues


def _load_faturas_by_minute(db_path: str, sim_date: str) -> dict[int, list[list[Any]]]:
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            sales_rows = conn.execute(
                """
                SELECT hour, invoice_id, invoice_nr, line_nr, parent_id,
                       product_id, product_name, quantity, price
                FROM Sales
                WHERE date = ?
                ORDER BY hour, invoice_id, line_nr;
                """,
                (sim_date,),
            ).fetchall()
            item_rows = conn.execute(
                """
                SELECT hour, invoice_id, item, item_quantity
                FROM ItemOrders
                WHERE date = ?
                ORDER BY hour, invoice_id, item;
                """,
                (sim_date,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Failed to load FATURAS data for {sim_date}: {exc}"
        ) from exc

    invoices: dict[int, dict[str, Any]] = {}
    for row in sales_rows:
        invoice_id = int(row["invoice_id"])
        invoice = invoices.setdefault(
            invoice_id,
            {
                "hour": str(row["hour"]),
                "invoice_id": invoice_id,
                "invoice_nr": str(row["invoice_nr"]),
                "lines": [],
                "items": [],
            },
        )
        invoice["lines"].append(
            [
                int(row["line_nr"]),
                row["parent_id"],
                int(row["product_id"]) if row["product_id"] is not None else None,
                str(row["product_name"]),
                int(row["quantity"]),
                float(row["price"]),
            ]
        )

    for row in item_rows:
        invoice_id = int(row["invoice_id"])
        invoice = invoices.get(invoice_id)
        if invoice is None:
            continue
        invoice["items"].append([str(row["item"]), int(row["item_quantity"] or 0)])

    by_minute: dict[int, list[list[Any]]] = defaultdict(list)
    for invoice in invoices.values():
        minute = _parse_clock_to_minute(invoice["hour"])
        by_minute[minute].append(
            [
                invoice["hour"],
                invoice["invoice_id"],
                invoice["invoice_nr"],
                invoice["lines"],
                invoice["items"],
            ]
        )
    return by_minute


def _make_item(prod: str, start_time: datetime, config: ItemConfig) -> list[Any]:
    hora_pronto = start_time + timedelta(minutes=config.production_time + 1)
    hora_prazo = hora_pronto + timedelta(minutes=config.shelf_time)
    return [prod, hora_pronto, hora_prazo, "", STATE_PREPARACAO]


def _make_waiting_item(prod: str) -> list[Any]:
    return [prod, "", "", "", STATE_ESPERA]


def _answered_in_current_window(
    orders_answered: dict[str, list[list[Any]]],
    prod: str,
    window: WindowInfo | None,
) -> int:
    if window is None:
        return 0
    count = 0
    for order in orders_answered[prod]:
        received = order[ORDER_HORA_RECEBIDO]
        if isinstance(received, datetime):
            minute = _datetime_to_minute(received)
            if window.start_minute <= minute <= window.end_minute:
                count += 1
    return count


def _waiting_orders_count(orders_queue: dict[str, list[list[Any]]], prod: str) -> int:
    return sum(1 for order in orders_queue[prod] if order[ORDER_ESTADO] == STATE_ESPERA)


def _request_production(
    prod: str,
    quantity: int,
    tempo_atual: datetime,
    configs: dict[str, ItemConfig],
    orders_queue: dict[str, list[list[Any]]],
    orders_answered: dict[str, list[list[Any]]],
    item_queue: dict[str, list[list[Any]]],
    item_prep: dict[str, list[list[Any]]],
    current_window: WindowInfo | None,
    prediction_val: int = 0,
) -> None:
    if quantity <= 0 or prod not in configs:
        return

    config = configs[prod]
    for _ in range(quantity):
        if len(item_prep[prod]) < config.max_capacity:
            item_prep[prod].append(_make_item(prod, tempo_atual, config))
            continue

        x = _waiting_orders_count(orders_queue, prod)
        y = max(0, int(prediction_val or 0))
        z = len(item_prep[prod])
        w = _answered_in_current_window(orders_answered, prod, current_window)
        max_limit = max(0, (x + y) - (z + w))
        if len(item_queue[prod]) < max_limit:
            item_queue[prod].append(_make_waiting_item(prod))


def _expire_shelf_items(
    tempo_atual: datetime,
    shelf: dict[str, list[list[Any]]],
    trash: dict[str, list[list[Any]]],
    force_all: bool = False,
) -> None:
    for prod, items in shelf.items():
        remaining: list[list[Any]] = []
        for item in items:
            deadline = item[ITEM_HORA_PRAZO]
            expired = force_all or (
                isinstance(deadline, datetime) and tempo_atual >= deadline
            )
            if expired:
                item[ITEM_ESTADO] = STATE_LIXO
                trash[prod].append(item)
            else:
                remaining.append(item)
        shelf[prod] = remaining


def _activate_orders(
    tempo_atual: datetime,
    orders_queue: dict[str, list[list[Any]]],
    nr_real_orders: dict[str, int],
) -> None:
    for prod, orders in orders_queue.items():
        for order in orders:
            if order[ORDER_ESTADO] == STATE_INATIVO and _same_sim_minute(
                order[ORDER_HORA_EMISSAO], tempo_atual
            ):
                order[ORDER_ESTADO] = STATE_ESPERA
                nr_real_orders[prod] += 1


def _match_orders(
    tempo_atual: datetime,
    orders_queue: dict[str, list[list[Any]]],
    orders_answered: dict[str, list[list[Any]]],
    shelf: dict[str, list[list[Any]]],
    nr_predicted_orders: dict[str, int],
    urgent_spawned_orders: set[tuple[str, int, datetime]],
) -> dict[str, int]:
    unmatched_requests: dict[str, int] = defaultdict(int)

    for prod in list(orders_queue):
        remaining_orders: list[list[Any]] = []
        for order in orders_queue[prod]:
            if order[ORDER_ESTADO] != STATE_ESPERA:
                remaining_orders.append(order)
                continue

            if shelf[prod]:
                best_idx = min(
                    range(len(shelf[prod])),
                    key=lambda idx: shelf[prod][idx][ITEM_HORA_PRAZO],
                )
                item = shelf[prod].pop(best_idx)
                item[ITEM_HORA_ENTREGUE] = tempo_atual
                item[ITEM_ESTADO] = STATE_ENTREGUE

                order[ORDER_HORA_RECEBIDO] = tempo_atual
                order[ORDER_ESTADO] = STATE_ENTREGUE
                orders_answered[prod].append(order)
                if _same_sim_minute(
                    order[ORDER_HORA_EMISSAO], order[ORDER_HORA_RECEBIDO]
                ):
                    nr_predicted_orders[prod] += 1
            else:
                remaining_orders.append(order)
                # Spawn only once per waiting order to avoid producing a duplicate every minute.
                spawn_key = (
                    prod,
                    int(order[ORDER_INVOICE_ID]),
                    order[ORDER_HORA_EMISSAO],
                )
                if spawn_key not in urgent_spawned_orders:
                    urgent_spawned_orders.add(spawn_key)
                    unmatched_requests[prod] += 1

        orders_queue[prod] = remaining_orders

    return unmatched_requests


def _run_predictive_events(
    current_minute: int,
    tempo_atual: datetime,
    predictive_events: dict[int, list[PredictionEvent]],
    configs: dict[str, ItemConfig],
    windows_by_prod: dict[str, list[WindowInfo]],
    orders_queue: dict[str, list[list[Any]]],
    orders_answered: dict[str, list[list[Any]]],
    item_queue: dict[str, list[list[Any]]],
    item_prep: dict[str, list[list[Any]]],
) -> None:
    for event in predictive_events.get(current_minute, []):
        current_window = _window_by_name(windows_by_prod[event.prod], event.time_window)
        _request_production(
            prod=event.prod,
            quantity=event.nr,
            tempo_atual=tempo_atual,
            configs=configs,
            orders_queue=orders_queue,
            orders_answered=orders_answered,
            item_queue=item_queue,
            item_prep=item_prep,
            current_window=current_window,
            prediction_val=event.nr,
        )


def _advance_and_promote(
    tempo_atual: datetime,
    configs: dict[str, ItemConfig],
    item_queue: dict[str, list[list[Any]]],
    item_prep: dict[str, list[list[Any]]],
    shelf: dict[str, list[list[Any]]],
) -> None:
    for prod in list(item_prep):
        remaining_prep: list[list[Any]] = []
        for item in item_prep[prod]:
            if (
                isinstance(item[ITEM_HORA_PRONTO], datetime)
                and tempo_atual >= item[ITEM_HORA_PRONTO]
            ):
                item[ITEM_ESTADO] = STATE_PRATELEIRA
                shelf[prod].append(item)
            else:
                remaining_prep.append(item)
        item_prep[prod] = remaining_prep

    for prod, queue in item_queue.items():
        config = configs[prod]
        while queue and len(item_prep[prod]) < config.max_capacity:
            queued_item = queue.pop(0)
            queued_item[ITEM_HORA_PRONTO] = tempo_atual + timedelta(
                minutes=config.production_time + 1
            )
            queued_item[ITEM_HORA_PRAZO] = queued_item[ITEM_HORA_PRONTO] + timedelta(
                minutes=config.shelf_time
            )
            queued_item[ITEM_HORA_ENTREGUE] = ""
            queued_item[ITEM_ESTADO] = STATE_PREPARACAO
            item_prep[prod].append(queued_item)


def _flush_orders_insight(
    db_path: str,
    sim_date: str,
    window: WindowInfo,
    prod: str,
    nr_predicted: int,
    nr_real: int,
) -> None:
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO OrdersInsight
                    (date, time_window, prod, nr_predicted_orders, nr_real_orders)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (date, time_window, prod)
                DO UPDATE SET
                    nr_predicted_orders = EXCLUDED.nr_predicted_orders,
                    nr_real_orders = EXCLUDED.nr_real_orders;
                """,
                (sim_date, window.time_window, prod, nr_predicted, nr_real),
            )
            conn.commit()
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Failed to flush OrdersInsight for {sim_date} {prod} {window.time_window}: {exc}"
        ) from exc


def _flush_window_counters(
    current_minute: int,
    db_path: str,
    sim_date: str,
    windows_by_prod: dict[str, list[WindowInfo]],
    nr_predicted_orders: dict[str, int],
    nr_real_orders: dict[str, int],
    force_final: bool = False,
) -> None:
    for prod, windows in windows_by_prod.items():
        for window in windows:
            should_flush = current_minute == window.end_minute
            if force_final and window.start_minute <= 23 * 60 + 59 <= window.end_minute:
                should_flush = True
            if not should_flush:
                continue
            _flush_orders_insight(
                db_path=db_path,
                sim_date=sim_date,
                window=window,
                prod=prod,
                nr_predicted=nr_predicted_orders[prod],
                nr_real=nr_real_orders[prod],
            )
            nr_predicted_orders[prod] = 0
            nr_real_orders[prod] = 0


def _format_for_print(value: Any) -> Any:
    """Recursively format runtime objects for consistent terminal printing."""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, list):
        return [_format_for_print(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_format_for_print(item) for item in value)
    if isinstance(value, dict):
        return {key: _format_for_print(val) for key, val in value.items()}
    return value


def print_simulation_state(
    tempo_atual: datetime,
    faturas: list,
    orders_queues: dict[str, list],
    orders_answered: dict[str, list],
    item_queues: dict[str, list],
    item_preps: dict[str, list],
    shelves: dict[str, list],
    trash_bins: dict[str, list],
) -> None:
    """Verbose per-tick state printer for debugging/runtime inspection."""
    print(f"=== SIMULATION TICK: {tempo_atual.strftime('%d/%m/%Y %H:%M')} ===\n")

    # FATURAS OUTPUT TEMPORARILY DISABLED (keep this block to re-enable quickly)
    # print("[GLOBAL FATURAS]")
    # print(pformat(_format_for_print(faturas), sort_dicts=False))
    # print()

    for product_label in PRODUCT_PRINT_ORDER:
        product_key = product_label.lower()
        queue_visible = [
            order
            for order in orders_queues.get(product_key, [])
            if len(order) >= 5 and str(order[ORDER_ESTADO]) != STATE_INATIVO
        ]

        print(f"--- [{product_label}] ---")
        print(
            "ORDERS_QUEUE:",
            pformat(_format_for_print(queue_visible), sort_dicts=False),
        )
        print(
            "ORDERS_ANSWERED:",
            pformat(
                _format_for_print(orders_answered.get(product_key, [])),
                sort_dicts=False,
            ),
        )
        print(
            "ITEM_QUEUE:",
            pformat(
                _format_for_print(item_queues.get(product_key, [])), sort_dicts=False
            ),
        )
        print(
            "ITEM_PREP:",
            pformat(
                _format_for_print(item_preps.get(product_key, [])), sort_dicts=False
            ),
        )
        print(
            "SHELF:",
            pformat(_format_for_print(shelves.get(product_key, [])), sort_dicts=False),
        )
        print(
            "TRASH:",
            pformat(
                _format_for_print(trash_bins.get(product_key, [])), sort_dicts=False
            ),
        )
        print()

    print("----------------------------------------")


def day_simulation(
    sim_minute_seconds: float,
    predictions: list[dict],
    order_simulation: list[list],
    db_path: str,
) -> None:
    """Run the real-time discrete-event day simulation.

    The loop follows the required order every minute:
    Expiration -> FATURAS -> Activate -> Match -> Schedule -> Advance/Promote.
    """
    try:
        sleep_seconds = max(0.0, float(sim_minute_seconds))
    except (TypeError, ValueError):
        sleep_seconds = 1.0

    sim_date = _infer_sim_date(order_simulation, db_path)
    day_anchor = datetime.strptime(sim_date, "%d/%m/%Y")
    configs = _load_item_configs(db_path)
    product_names = set(configs)
    windows_by_prod = _build_windows(configs)

    FATURAS: list[list[Any]] = []
    ORDERS_QUEUE = _initialize_order_queues(order_simulation, product_names)
    ORDERS_ANSWERED = {prod: [] for prod in product_names}
    ITEM_QUEUE = {prod: [] for prod in product_names}
    ITEM_PREP = {prod: [] for prod in product_names}
    SHELF = {prod: [] for prod in product_names}
    TRASH = {prod: [] for prod in product_names}

    nr_real_orders = {prod: 0 for prod in product_names}
    nr_predicted_orders = {prod: 0 for prod in product_names}

    faturas_by_minute = _load_faturas_by_minute(db_path, sim_date)
    predictive_events = _build_prediction_events(predictions, configs, windows_by_prod)
    urgent_spawned_orders: set[tuple[str, int, datetime]] = set()

    print(f"\nStarting real-time day simulation for {sim_date}...")
    current_minute = OPEN_MINUTES
    while current_minute <= END_MINUTES:
        tempo_atual = _minute_to_datetime(day_anchor, current_minute)

        # 1. Expiration & cleanup.
        if current_minute == END_MINUTES:
            _expire_shelf_items(tempo_atual, SHELF, TRASH, force_all=True)
            # Product windows close at 23:59 and are flushed on that tick; do not
            # re-flush here or the final window counts would be overwritten by zeros.
            print_simulation_state(
                tempo_atual=tempo_atual,
                faturas=FATURAS,
                orders_queues=ORDERS_QUEUE,
                orders_answered=ORDERS_ANSWERED,
                item_queues=ITEM_QUEUE,
                item_preps=ITEM_PREP,
                shelves=SHELF,
                trash_bins=TRASH,
            )
            print("Simulation reached 00:00. End-of-day shelf cleanup completed.")
            break

        _expire_shelf_items(tempo_atual, SHELF, TRASH)

        # 2. FATURAS insertion.
        FATURAS.extend(faturas_by_minute.get(current_minute, []))

        # 3. Activate orders.
        _activate_orders(tempo_atual, ORDERS_QUEUE, nr_real_orders)

        # 4. Match & fulfill; unmatched active orders trigger urgent production.
        unmatched_requests = _match_orders(
            tempo_atual=tempo_atual,
            orders_queue=ORDERS_QUEUE,
            orders_answered=ORDERS_ANSWERED,
            shelf=SHELF,
            nr_predicted_orders=nr_predicted_orders,
            urgent_spawned_orders=urgent_spawned_orders,
        )

        # 5. Schedule predictive and urgent unpredicted production requests.
        current_window_by_prod = {
            prod: _window_for_minute(windows_by_prod[prod], current_minute)
            for prod in product_names
        }
        for prod, quantity in unmatched_requests.items():
            _request_production(
                prod=prod,
                quantity=quantity,
                tempo_atual=tempo_atual,
                configs=configs,
                orders_queue=ORDERS_QUEUE,
                orders_answered=ORDERS_ANSWERED,
                item_queue=ITEM_QUEUE,
                item_prep=ITEM_PREP,
                current_window=current_window_by_prod.get(prod),
                prediction_val=0,
            )

        _run_predictive_events(
            current_minute=current_minute,
            tempo_atual=tempo_atual,
            predictive_events=predictive_events,
            configs=configs,
            windows_by_prod=windows_by_prod,
            orders_queue=ORDERS_QUEUE,
            orders_answered=ORDERS_ANSWERED,
            item_queue=ITEM_QUEUE,
            item_prep=ITEM_PREP,
        )

        # 6. Advance item lifecycle and promote queued items.
        _advance_and_promote(tempo_atual, configs, ITEM_QUEUE, ITEM_PREP, SHELF)

        # Counter flushes happen exactly at product-specific window end minutes.
        _flush_window_counters(
            current_minute=current_minute,
            db_path=db_path,
            sim_date=sim_date,
            windows_by_prod=windows_by_prod,
            nr_predicted_orders=nr_predicted_orders,
            nr_real_orders=nr_real_orders,
        )

        print_simulation_state(
            tempo_atual=tempo_atual,
            faturas=FATURAS,
            orders_queues=ORDERS_QUEUE,
            orders_answered=ORDERS_ANSWERED,
            item_queues=ITEM_QUEUE,
            item_preps=ITEM_PREP,
            shelves=SHELF,
            trash_bins=TRASH,
        )

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        current_minute += 1

    total_answered = sum(len(ORDERS_ANSWERED[prod]) for prod in product_names)
    total_trash = sum(len(TRASH[prod]) for prod in product_names)
    print(
        "Day simulation finished: "
        f"faturas={len(FATURAS)}, answered_orders={total_answered}, trashed_items={total_trash}."
    )


__all__ = ["day_simulation", "print_simulation_state"]
