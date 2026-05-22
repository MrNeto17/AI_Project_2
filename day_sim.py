"""Minute-by-minute real-time day simulation loop.

This module owns only runtime state transitions for the 7-column simulation structure
and OrdersInsight counter flushing. It does not calculate prediction multipliers.
"""

from __future__ import annotations

import math
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
    # Inclusive shelf window end: if ready at 17:00 with shelf_time=30, deadline is 17:29.
    hora_prazo = hora_pronto + timedelta(minutes=config.shelf_time - 1)
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


def calculate_dynamic_multiplier(
    db_path: str,
    sim_date: str,
    prod: str,
    min_orders_threshold: int = 20,
) -> float:
    """Compute MULTIPLICADOR_PROPRIO_DIA from completed OrdersInsight windows.

    Formula:
        ratio_i = (nr_real_i + 1) / (nr_predicted_i + 1)
        weight_i = i ** 1.2   (oldest i=1 ... newest i=N)
        multiplier = sum(weight_i * ratio_i) / sum(weight_i)

    Returns bounded multiplier in [0.5, 5.0], with 1.0 fallback guards.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT nr_predicted_orders, nr_real_orders
                FROM OrdersInsight
                WHERE date = ?
                  AND prod = ?
                ORDER BY time_window ASC;
                """,
                (sim_date, prod),
            ).fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Failed to calculate dynamic multiplier for {sim_date} {prod}: {exc}"
        ) from exc

    if not rows:
        return 1.0

    total_real_orders = sum(int(row[1] or 0) for row in rows)
    if total_real_orders < int(min_orders_threshold):
        return 1.0

    weighted_sum = 0.0
    weight_total = 0.0
    for idx, row in enumerate(rows, start=1):
        nr_predicted = int(row[0] or 0)
        nr_real = int(row[1] or 0)

        ratio = (nr_real + 1.0) / (nr_predicted + 1.0)
        weight = float(idx) ** 1.5

        weighted_sum += weight * ratio
        weight_total += weight

    if weight_total <= 0.0:
        return 1.0

    multiplier = weighted_sum / weight_total
    if multiplier == 0.0:
        return 1.0

    return max(0.5, min(1.5, multiplier))


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
    db_path: str,
    sim_date: str,
    use_dynamic_multiplier: bool = True,
) -> None:
    multiplier_cache: dict[str, float] = {}

    for event in predictive_events.get(current_minute, []):
        current_window = _window_by_name(windows_by_prod[event.prod], event.time_window)

        if use_dynamic_multiplier:
            if event.prod not in multiplier_cache:
                multiplier_cache[event.prod] = calculate_dynamic_multiplier(
                    db_path=db_path, sim_date=sim_date, prod=event.prod
                )
            dynamic_mult = multiplier_cache[event.prod]
            adjusted_nr = max(0, math.trunc(event.nr * dynamic_mult))
        else:
            # Fallback: simply truncate the float prediction to integer
            adjusted_nr = max(0, math.trunc(event.nr))

        _request_production(
            prod=event.prod,
            quantity=adjusted_nr,
            tempo_atual=tempo_atual,
            configs=configs,
            orders_queue=orders_queue,
            orders_answered=orders_answered,
            item_queue=item_queue,
            item_prep=item_prep,
            current_window=current_window,
            prediction_val=adjusted_nr,
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
            # Inclusive shelf window end: HORA_PRAZO aligns with time_window end minute.
            queued_item[ITEM_HORA_PRAZO] = queued_item[ITEM_HORA_PRONTO] + timedelta(
                minutes=config.shelf_time - 1
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


def _flush_items_insight(
    db_path: str,
    sim_date: str,
    orders_answered: dict[str, list[list[Any]]],
    trash: dict[str, list[list[Any]]],
) -> None:
    """Flush end-of-day waiting-time and trash KPIs into ItemsInsight."""
    try:
        with sqlite3.connect(db_path) as conn:
            for prod in sorted(set(orders_answered) | set(trash)):
                total_waiting_time = 0.0
                for order in orders_answered.get(prod, []):
                    hora_emitida = order[ORDER_HORA_EMISSAO]
                    hora_recebido = order[ORDER_HORA_RECEBIDO]
                    if isinstance(hora_emitida, datetime) and isinstance(
                        hora_recebido, datetime
                    ):
                        total_waiting_time += (
                            hora_recebido - hora_emitida
                        ).total_seconds() / 60.0

                nr_trash_items = len(trash.get(prod, []))

                conn.execute(
                    """
                    INSERT INTO ItemsInsight (date, prod, total_waiting_time, nr_trash_items)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (date, prod) DO UPDATE SET
                        total_waiting_time = EXCLUDED.total_waiting_time,
                        nr_trash_items = EXCLUDED.nr_trash_items;
                    """,
                    (sim_date, prod, int(total_waiting_time), nr_trash_items),
                )
            conn.commit()
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Failed to flush ItemsInsight for {sim_date}: {exc}"
        ) from exc


def _flush_window_counters(
    current_minute: int,
    db_path: str,
    sim_date: str,
    windows_by_prod: dict[str, list[WindowInfo]],
    nr_real_orders: dict[str, int],
    predicted_demand_map: dict[str, dict[str, int]],
    force_final: bool = False,
) -> None:
    for prod, windows in windows_by_prod.items():
        for window in windows:
            should_flush = current_minute == window.end_minute
            if force_final and window.start_minute <= 23 * 60 + 59 <= window.end_minute:
                should_flush = True
            if not should_flush:
                continue

            # ✅ FIXED: Use original forecasted demand, NOT instant-match counter
            nr_predicted = predicted_demand_map[prod].get(window.time_window, 0)
            nr_real = nr_real_orders[prod]

            _flush_orders_insight(
                db_path=db_path,
                sim_date=sim_date,
                window=window,
                prod=prod,
                nr_predicted=nr_predicted,
                nr_real=nr_real,
            )
            # Only reset real counter; predicted is static per window
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


class SimulationEngine:
    """Stateful minute-by-minute simulation engine suitable for web/API usage."""

    def __init__(
        self,
        db_path: str,
        predictions: list[dict[str, Any]],
        order_simulation: list[list[Any]],
        use_dynamic_multiplier: bool = True,
    ) -> None:
        self.db_path = db_path
        self.use_dynamic_multiplier = bool(use_dynamic_multiplier)

        self.sim_date = _infer_sim_date(order_simulation, db_path)
        self.day_anchor = datetime.strptime(self.sim_date, "%d/%m/%Y")
        self.configs = _load_item_configs(db_path)
        self.product_names = set(self.configs)
        self.windows_by_prod = _build_windows(self.configs)

        self.faturas: list[list[Any]] = []
        self.orders_queue = _initialize_order_queues(
            order_simulation, self.product_names
        )
        self.orders_answered: dict[str, list[list[Any]]] = {
            prod: [] for prod in self.product_names
        }
        self.item_queue: dict[str, list[list[Any]]] = {
            prod: [] for prod in self.product_names
        }
        self.item_prep: dict[str, list[list[Any]]] = {
            prod: [] for prod in self.product_names
        }
        self.shelf: dict[str, list[list[Any]]] = {
            prod: [] for prod in self.product_names
        }
        self.trash: dict[str, list[list[Any]]] = {
            prod: [] for prod in self.product_names
        }

        self.nr_real_orders = {prod: 0 for prod in self.product_names}
        self.nr_predicted_orders = {prod: 0 for prod in self.product_names}
        self.faturas_by_minute = _load_faturas_by_minute(db_path, self.sim_date)
        self.predictive_events = _build_prediction_events(
            predictions, self.configs, self.windows_by_prod
        )

        self.predicted_demand_map: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        for events in self.predictive_events.values():
            for event in events:
                self.predicted_demand_map[event.prod][event.time_window] += event.nr

        self.urgent_spawned_orders: set[tuple[str, int, datetime]] = set()
        self.current_minute = OPEN_MINUTES
        self.is_complete = False

    @staticmethod
    def _serialize_dt(value: Any) -> Any:
        if isinstance(value, datetime):
            return {"__dt__": value.isoformat()}
        if isinstance(value, list):
            return [SimulationEngine._serialize_dt(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): SimulationEngine._serialize_dt(val)
                for key, val in value.items()
            }
        if isinstance(value, tuple):
            return [SimulationEngine._serialize_dt(item) for item in value]
        return value

    @staticmethod
    def _deserialize_dt(value: Any) -> Any:
        if isinstance(value, dict) and "__dt__" in value:
            return datetime.fromisoformat(str(value["__dt__"]))
        if isinstance(value, list):
            return [SimulationEngine._deserialize_dt(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): SimulationEngine._deserialize_dt(val)
                for key, val in value.items()
            }
        return value

    def to_session_dict(self) -> dict[str, Any]:
        return {
            "db_path": self.db_path,
            "sim_date": self.sim_date,
            "use_dynamic_multiplier": self.use_dynamic_multiplier,
            "current_minute": self.current_minute,
            "is_complete": self.is_complete,
            "faturas": self._serialize_dt(self.faturas),
            "orders_queue": self._serialize_dt(self.orders_queue),
            "orders_answered": self._serialize_dt(self.orders_answered),
            "item_queue": self._serialize_dt(self.item_queue),
            "item_prep": self._serialize_dt(self.item_prep),
            "shelf": self._serialize_dt(self.shelf),
            "trash": self._serialize_dt(self.trash),
            "nr_real_orders": self.nr_real_orders,
            "nr_predicted_orders": self.nr_predicted_orders,
            "predicted_demand_map": self.predicted_demand_map,
            "urgent_spawned_orders": self._serialize_dt(
                list(self.urgent_spawned_orders)
            ),
        }

    @classmethod
    def from_session_dict(cls, state: dict[str, Any]) -> "SimulationEngine":
        obj = cls.__new__(cls)
        obj.db_path = str(state["db_path"])
        obj.sim_date = str(state["sim_date"])
        obj.day_anchor = datetime.strptime(obj.sim_date, "%d/%m/%Y")
        obj.use_dynamic_multiplier = bool(state.get("use_dynamic_multiplier", True))

        obj.configs = _load_item_configs(obj.db_path)
        obj.product_names = set(obj.configs)
        obj.windows_by_prod = _build_windows(obj.configs)

        obj.current_minute = int(state.get("current_minute", OPEN_MINUTES))
        obj.is_complete = bool(state.get("is_complete", False))

        obj.faturas = cls._deserialize_dt(state.get("faturas", []))
        obj.orders_queue = cls._deserialize_dt(state.get("orders_queue", {}))
        obj.orders_answered = cls._deserialize_dt(state.get("orders_answered", {}))
        obj.item_queue = cls._deserialize_dt(state.get("item_queue", {}))
        obj.item_prep = cls._deserialize_dt(state.get("item_prep", {}))
        obj.shelf = cls._deserialize_dt(state.get("shelf", {}))
        obj.trash = cls._deserialize_dt(state.get("trash", {}))

        obj.nr_real_orders = {
            str(prod): int(value)
            for prod, value in dict(state.get("nr_real_orders", {})).items()
        }
        obj.nr_predicted_orders = {
            str(prod): int(value)
            for prod, value in dict(state.get("nr_predicted_orders", {})).items()
        }

        raw_predicted_map = dict(state.get("predicted_demand_map", {}))
        obj.predicted_demand_map = defaultdict(lambda: defaultdict(int))
        for prod, windows in raw_predicted_map.items():
            obj.predicted_demand_map[str(prod)] = defaultdict(
                int, {str(k): int(v) for k, v in dict(windows).items()}
            )

        raw_urgent = cls._deserialize_dt(state.get("urgent_spawned_orders", []))
        obj.urgent_spawned_orders = set()
        for entry in raw_urgent:
            if (
                isinstance(entry, list)
                and len(entry) == 3
                and isinstance(entry[2], datetime)
            ):
                obj.urgent_spawned_orders.add((str(entry[0]), int(entry[1]), entry[2]))

        obj.faturas_by_minute = _load_faturas_by_minute(obj.db_path, obj.sim_date)
        # Predictive events are reconstructed from static predicted_demand_map.
        obj.predictive_events = defaultdict(list)
        for prod, windows in obj.predicted_demand_map.items():
            for time_window, nr in dict(windows).items():
                if nr <= 0:
                    continue
                window = _window_by_name(obj.windows_by_prod.get(prod, []), time_window)
                if window is None:
                    continue
                prep_minute = window.start_minute - (
                    obj.configs[prod].production_time + 1
                )
                obj.predictive_events[prep_minute].append(
                    PredictionEvent(prod=prod, time_window=time_window, nr=int(nr))
                )

        return obj

    def _entry_sort_key(self, entry: Any) -> tuple[int, int]:
        if isinstance(entry, list):
            if entry and isinstance(entry[0], str) and ":" in entry[0]:
                try:
                    minute = _parse_clock_to_minute(entry[0])
                    return minute, 0
                except ValueError:
                    pass
            best = -1
            for value in entry:
                if isinstance(value, datetime):
                    best = max(best, _datetime_to_minute(value))
            if best >= 0:
                return best, 0
        return -1, 0

    def _flatten_view(
        self, data: dict[str, list[list[Any]]], view: str
    ) -> list[list[Any]]:
        view_key = str(view or "GERAL").strip().upper()
        if view_key != "GERAL":
            return list(data.get(view_key.lower(), []))

        merged: list[list[Any]] = []
        for prod_entries in data.values():
            merged.extend(prod_entries)
        merged.sort(key=self._entry_sort_key, reverse=True)
        return merged

    def get_dashboard_state(self, view: str = "GERAL") -> dict[str, Any]:
        clock_dt = _minute_to_datetime(self.day_anchor, self.current_minute)

        queue_visible = {
            prod: [
                order
                for order in self.orders_queue.get(prod, [])
                if len(order) >= 5 and str(order[ORDER_ESTADO]) != STATE_INATIVO
            ]
            for prod in self.orders_queue
        }

        payload = {
            "clock": clock_dt.strftime("%H:%M"),
            "current_minute": self.current_minute,
            "view": str(view or "GERAL").strip().upper(),
            "faturas": self._flatten_view({"all": self.faturas}, "all"),
            "orders_queue": self._flatten_view(queue_visible, view),
            "orders_answered": self._flatten_view(self.orders_answered, view),
            "item_queue": self._flatten_view(self.item_queue, view),
            "item_prep": self._flatten_view(self.item_prep, view),
            "shelf": self._flatten_view(self.shelf, view),
            "trash": self._flatten_view(self.trash, view),
            "is_complete": self.is_complete,
        }

        for key in (
            "faturas",
            "orders_queue",
            "orders_answered",
            "item_queue",
            "item_prep",
            "shelf",
            "trash",
        ):
            payload[key] = _format_for_print(payload[key])

        return payload

    def tick(self, view: str = "GERAL") -> dict[str, Any]:
        if self.is_complete:
            return self.get_dashboard_state(view=view)

        tempo_atual = _minute_to_datetime(self.day_anchor, self.current_minute)

        if self.current_minute == END_MINUTES:
            _expire_shelf_items(tempo_atual, self.shelf, self.trash, force_all=True)
            _flush_items_insight(
                db_path=self.db_path,
                sim_date=self.sim_date,
                orders_answered=self.orders_answered,
                trash=self.trash,
            )
            self.is_complete = True
            return self.get_dashboard_state(view=view)

        _expire_shelf_items(tempo_atual, self.shelf, self.trash)
        self.faturas.extend(self.faturas_by_minute.get(self.current_minute, []))

        _activate_orders(tempo_atual, self.orders_queue, self.nr_real_orders)

        unmatched_requests = _match_orders(
            tempo_atual=tempo_atual,
            orders_queue=self.orders_queue,
            orders_answered=self.orders_answered,
            shelf=self.shelf,
            nr_predicted_orders=self.nr_predicted_orders,
            urgent_spawned_orders=self.urgent_spawned_orders,
        )

        current_window_by_prod = {
            prod: _window_for_minute(self.windows_by_prod[prod], self.current_minute)
            for prod in self.product_names
        }
        for prod, quantity in unmatched_requests.items():
            _request_production(
                prod=prod,
                quantity=quantity,
                tempo_atual=tempo_atual,
                configs=self.configs,
                orders_queue=self.orders_queue,
                orders_answered=self.orders_answered,
                item_queue=self.item_queue,
                item_prep=self.item_prep,
                current_window=current_window_by_prod.get(prod),
                prediction_val=0,
            )

        _run_predictive_events(
            current_minute=self.current_minute,
            tempo_atual=tempo_atual,
            predictive_events=self.predictive_events,
            configs=self.configs,
            windows_by_prod=self.windows_by_prod,
            orders_queue=self.orders_queue,
            orders_answered=self.orders_answered,
            item_queue=self.item_queue,
            item_prep=self.item_prep,
            db_path=self.db_path,
            sim_date=self.sim_date,
            use_dynamic_multiplier=self.use_dynamic_multiplier,
        )

        _advance_and_promote(
            tempo_atual, self.configs, self.item_queue, self.item_prep, self.shelf
        )

        _flush_window_counters(
            current_minute=self.current_minute,
            db_path=self.db_path,
            sim_date=self.sim_date,
            windows_by_prod=self.windows_by_prod,
            nr_real_orders=self.nr_real_orders,
            predicted_demand_map=self.predicted_demand_map,
        )

        self.current_minute += 1
        return self.get_dashboard_state(view=view)


def print_end_of_day_report(
    db_path: str,
    sim_date: str,
    orders_answered: dict[str, list[list[Any]]],
) -> None:
    """Print grouped end-of-day KPIs and OrdersInsight summary tables."""
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
                SELECT time_window, prod, nr_predicted_orders, nr_real_orders
                FROM OrdersInsight
                WHERE date=?
                ORDER BY prod, time_window;
                """,
                (sim_date,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Failed to load end-of-day metrics for {sim_date}: {exc}"
        ) from exc

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

            emit_minute = hora_emitida.replace(second=0, microsecond=0)
            recv_minute = hora_recebido.replace(second=0, microsecond=0)
            if emit_minute == recv_minute:
                immediate_orders += 1

    total_invoices = len(invoice_ids)

    waste_denominator = trashed + real_orders
    waste_ratio = (trashed / waste_denominator) if waste_denominator > 0 else 0.0
    immediate_service_ratio = immediate_orders / real_orders if real_orders > 0 else 0.0
    avg_waiting_time = total_waiting_time / real_orders if real_orders > 0 else 0.0

    print("=== END-OF-DAY METRICS ===")
    print()
    print("[INVOICES]")
    print(f"Total Invoices: {total_invoices}")
    print()
    print("[ORDERS INSIGHT]")
    print(f"Total Trashed Items: {trashed}")
    print(f"Total Predicted Orders: {predicted}")
    print(f"Total Real Orders: {real_orders}")
    print(f"Total Immediate Orders: {immediate_orders}")
    print()
    print("[RATIOS]")
    print(f"Waste Ratio: {waste_ratio:.2%}")
    print(f"Immediate Service Ratio: {immediate_service_ratio:.2%}")
    print()
    print("[TIME INSIGHT]")
    print(f"Total Waiting Time: {total_waiting_time} min")
    print(f"Waiting Time Average: {avg_waiting_time:.1f} min/order")

    header = "Time Window   - Predicted Orders - Real Orders"
    totals_by_hour: dict[int, dict[str, int]] = {
        hour: {"predicted": 0, "real": 0} for hour in range(11, 24)
    }
    by_product: dict[str, list[tuple[str, int, int]]] = defaultdict(list)

    for time_window, prod, nr_predicted_orders, nr_real_orders in details_rows:
        window_text = str(time_window or "")
        prod_text = str(prod or "").strip().upper()
        predicted_val = int(nr_predicted_orders or 0)
        real_val = int(nr_real_orders or 0)

        if "_" in window_text and ":" in window_text:
            try:
                start_hour = int(window_text.split("_", 1)[0].split(":", 1)[0])
            except (TypeError, ValueError, IndexError):
                start_hour = None
            if start_hour in totals_by_hour:
                totals_by_hour[start_hour]["predicted"] += predicted_val
                totals_by_hour[start_hour]["real"] += real_val

        by_product[prod_text].append((window_text, predicted_val, real_val))

    print("\n[TOTAL]")
    print(header)
    for hour in range(11, 24):
        time_window = f"{hour:02d}:00_{hour:02d}:59"
        predicted_val = totals_by_hour[hour]["predicted"]
        real_val = totals_by_hour[hour]["real"]
        print(f"{time_window:<13} - {predicted_val:<16} - {real_val:<16}")

    for product in PRODUCT_PRINT_ORDER:
        print(f"\n[{product}]")
        print(header)
        rows = by_product.get(product, [])
        for time_window, predicted_val, real_val in rows:
            print(f"{time_window:<13} - {predicted_val:<16} - {real_val:<16}")


def day_simulation(
    sim_minute_seconds: float,
    predictions: list[dict],
    order_simulation: list[list],
    db_path: str,
    use_dynamic_multiplier: bool = True,
) -> dict[str, list[list[Any]]]:
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
    # Internal KPI only (instant fulfill count). Not used for OrdersInsight DB flush.
    nr_predicted_orders = {prod: 0 for prod in product_names}

    faturas_by_minute = _load_faturas_by_minute(db_path, sim_date)
    predictive_events = _build_prediction_events(predictions, configs, windows_by_prod)

    # Map: {prod: {time_window: total_forecasted_nr}}
    predicted_demand_map: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for events in predictive_events.values():
        for event in events:
            predicted_demand_map[event.prod][event.time_window] += event.nr

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
            _flush_items_insight(
                db_path=db_path,
                sim_date=sim_date,
                orders_answered=ORDERS_ANSWERED,
                trash=TRASH,
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
            # Internal KPI only (not flushed as OrdersInsight.nr_predicted_orders).
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
            db_path=db_path,
            sim_date=sim_date,
            use_dynamic_multiplier=use_dynamic_multiplier,
        )

        # 6. Advance item lifecycle and promote queued items.
        _advance_and_promote(tempo_atual, configs, ITEM_QUEUE, ITEM_PREP, SHELF)

        # Counter flushes happen exactly at product-specific window end minutes.
        _flush_window_counters(
            current_minute=current_minute,
            db_path=db_path,
            sim_date=sim_date,
            windows_by_prod=windows_by_prod,
            nr_real_orders=nr_real_orders,
            predicted_demand_map=predicted_demand_map,
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

    return ORDERS_ANSWERED


__all__ = [
    "SimulationEngine",
    "day_simulation",
    "print_simulation_state",
    "print_end_of_day_report",
    "calculate_dynamic_multiplier",
]
