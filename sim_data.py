"""Simulation data formatting utilities.

This module only defines data structures + formatting helpers that transform ItemOrders
rows into the queue-array format expected by the real-time simulation engine.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

INITIAL_ORDER_STATE = "INATIVO"


@dataclass(frozen=True)
class OrderQueueEntry:
    """Canonical order entry shape used by the simulation queue layer.

    Layout (spec-aligned):
        [NOME, INVOICE_ID, HORA_EMITIDA, HORA_RECEBIDO, ESTADO]
    """

    nome: str
    invoice_id: int
    hora_emitida: datetime
    hora_recebido: None | str
    estado: str = INITIAL_ORDER_STATE

    def as_list(self) -> list[Any]:
        return [
            self.nome,
            self.invoice_id,
            self.hora_emitida,
            self.hora_recebido,
            self.estado,
        ]


def _parse_sim_date(sim_date: str) -> datetime:
    """Parse simulation date into a date anchor for timestamp composition.

    Accepts DD/MM/YYYY (project format) and ISO YYYY-MM-DD for robustness.
    """
    raw = str(sim_date or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Invalid sim_date '{sim_date}'. Expected DD/MM/YYYY (or YYYY-MM-DD)."
    )


def _parse_hour_to_timestamp(sim_date: datetime, hour_value: Any) -> datetime:
    """Build full emission timestamp from date anchor + DB hour string.

    Handles SQLite TIME values like HH:MM, HH:MM:SS, and similar textual forms.
    """
    hour_text = str(hour_value or "").strip()
    if not hour_text:
        raise ValueError(
            "ItemOrders.hour is empty; cannot build HORA_EMITIDA timestamp."
        )

    # Strip date portion if any accidental datetime-like value appears.
    if " " in hour_text:
        hour_text = hour_text.split()[-1]

    parts = hour_text.split(":")
    if len(parts) < 2:
        raise ValueError(
            f"Invalid hour value '{hour_value}'. Expected HH:MM or HH:MM:SS."
        )

    try:
        hh = int(parts[0])
        mm = int(parts[1])
        ss = int(parts[2]) if len(parts) >= 3 else 0
    except ValueError as exc:
        raise ValueError(f"Invalid numeric hour components in '{hour_value}'.") from exc

    if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        raise ValueError(f"Hour out of range in '{hour_value}'.")

    return sim_date.replace(hour=hh, minute=mm, second=ss, microsecond=0)


def format_item_orders_to_queue(db_path: str, sim_date: str) -> list[list[Any]]:
    """Format ItemOrders rows for one simulation day into queue-entry arrays.

    Output format (strict):
        [NOME, INVOICE_ID, HORA_EMITIDA, HORA_RECEBIDO, ESTADO]

    - NOME: ItemOrders.item
    - INVOICE_ID: ItemOrders.invoice_id (int)
    - HORA_EMITIDA: datetime anchored to sim_date + ItemOrders.hour
    - HORA_RECEBIDO: None
    - ESTADO: "INATIVO"

    Notes:
    - The function expands rows by item_quantity so each queued production unit is explicit.
    - No queue logic/state transitions are performed here.
    """
    date_anchor = _parse_sim_date(sim_date)

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT item, invoice_id, hour, item_quantity
                FROM ItemOrders
                WHERE date = ?
                ORDER BY hour, invoice_id, item;
                """,
                (sim_date,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Failed to load ItemOrders for date '{sim_date}' from '{db_path}': {exc}"
        ) from exc

    formatted: list[list[Any]] = []
    for row in rows:
        item_name = str(row["item"])
        invoice_id = int(row["invoice_id"])
        hora_emitida = _parse_hour_to_timestamp(date_anchor, row["hour"])
        quantity = max(0, int(row["item_quantity"] or 0))

        entry = OrderQueueEntry(
            nome=item_name,
            invoice_id=invoice_id,
            hora_emitida=hora_emitida,
            hora_recebido=None,
            estado=INITIAL_ORDER_STATE,
        ).as_list()

        for _ in range(quantity):
            formatted.append(list(entry))

    return formatted


__all__ = ["OrderQueueEntry", "format_item_orders_to_queue", "INITIAL_ORDER_STATE"]
