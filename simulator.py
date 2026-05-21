"""Statistical sales-day generator for the production simulator.

Public entry point:
    generate_day(week_day, event, weather, db_path)

The generator intentionally uses only calendar-condition inputs for behaviour.  The concrete
simulation date is derived only to satisfy the database schema and to make the generated rows
queryable through the ItemOrders view.
"""

from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

ROOT_DIR = Path(__file__).resolve().parent
DATA_OVERVIEW_PATH = ROOT_DIR / "dataset_description" / "DATA_OVERVIEW.md"

OPENING_HOUR = 11
CLOSING_HOUR = 23
WEEKEND_DAYS = {"SATURDAY", "SUNDAY"}
ORDER_STATE_INACTIVE = "INATIVO"

_RNG = np.random.default_rng()
_PRIORS_CACHE: dict[str, Any] | None = None


@dataclass(frozen=True)
class Product:
    product_id: int
    product_name: str
    base_price: float | None
    item: str | None
    item_quantity: int | None
    category: str


@dataclass(frozen=True)
class Priors:
    mean_daily_orders: float
    mean_aov: float
    none_order_quantiles: list[float]
    weekday_mean_orders: dict[str, float]
    event_order_multipliers: dict[str, float]
    event_aov_multipliers: dict[str, float]
    weather_order_multipliers: dict[tuple[str, str], float]
    weather_aov_multipliers: dict[tuple[str, str], float]
    category_mix: dict[str, float]
    event_category_mix: dict[str, dict[str, float]]
    weather_category_mix: dict[str, dict[str, float]]
    hourly_shares: dict[int, float]
    parent_lines_mean: float
    parent_lines_p75: float
    parent_lines_p90: float


# ---------------------------------------------------------------------------
# Public RNG controls
# ---------------------------------------------------------------------------


def seed_rng(seed: int | None = None) -> None:
    """Reset the module-level RNG for reproducible generation."""
    global _RNG
    _RNG = np.random.default_rng(seed)


# ---------------------------------------------------------------------------
# Markdown prior parsing
# ---------------------------------------------------------------------------


def _read_overview(path: Path = DATA_OVERVIEW_PATH) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(
            f"Failed to read statistical overview '{path}': {exc}"
        ) from exc


def _extract_required_float(pattern: str, text: str, label: str) -> float:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not parse required prior: {label}")
    return float(match.group(1).replace(",", ""))


def _extract_float_list(pattern: str, text: str, label: str) -> list[float]:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not parse required prior list: {label}")
    captured = " / ".join(group for group in match.groups() if group is not None)
    return [float(value) for value in re.findall(r"\d+(?:\.\d+)?", captured)]


def _normalize_context(value: Any) -> str:
    text = str(value or "").strip().upper().replace(" ", "_")
    aliases = {
        "SMALL": "SMALL_EVENT",
        "BIG": "BIG_EVENT",
        "NO_EVENT": "NONE",
        "NOTRAINING": "NOT_RAINING",
        "NOT_RAIN": "NOT_RAINING",
        "RAIN": "RAINING",
    }
    return aliases.get(text, text)


def _normalize_weekday(value: Any) -> str:
    text = str(value or "").strip().capitalize()
    valid = {
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    }
    if text not in valid:
        raise ValueError(
            f"Invalid week_day '{value}'. Expected one of: {', '.join(sorted(valid))}."
        )
    return text


def _parse_weekday_table(text: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for day, _days, mean_orders, _mean_revenue, _mean_aov in re.findall(
        r"\|\s*(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|",
        text,
        flags=re.IGNORECASE,
    ):
        result[day.capitalize()] = float(mean_orders)

    if len(result) != 7:
        raise RuntimeError(
            "Could not parse all weekday mean-order priors from DATA_OVERVIEW.md."
        )
    return result


def _parse_event_multipliers(text: str) -> tuple[dict[str, float], dict[str, float]]:
    order_multipliers = {"NONE": 1.0}
    aov_multipliers = {"NONE": 1.0}

    for event in ("SMALL_EVENT", "BIG_EVENT", "HOLIDAY"):
        block_match = re.search(
            rf"`{event}`:\s*orders\s*\*\*([\d.]+)x\*\*.*?AOV\s*\*\*([\d.]+)x\*\*",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if block_match:
            order_multipliers[event] = float(block_match.group(1))
            aov_multipliers[event] = float(block_match.group(2))

    missing = {"SMALL_EVENT", "BIG_EVENT", "HOLIDAY"} - set(order_multipliers)
    if missing:
        raise RuntimeError(
            f"Could not parse event multipliers for: {', '.join(sorted(missing))}"
        )

    return order_multipliers, aov_multipliers


def _parse_weather_interactions(
    text: str,
) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], float]]:
    weekday_block = re.search(
        r"- Weekday split:\s*(.*?)- Weekend split:",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    weekend_block = re.search(
        r"- Weekend split:\s*(.*?)\n\s*Simulation implication:",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not weekday_block or not weekend_block:
        raise RuntimeError(
            "Could not locate weather interaction blocks in DATA_OVERVIEW.md."
        )

    def parse_weather_row(block: str, weather: str) -> tuple[float, float]:
        match = re.search(
            rf"`{weather}`:\s*\*\*([\d.]+) orders\*\*,\s*\*\*[\d.]+ revenue\*\*,\s*\*\*([\d.]+) AOV\*\*",
            block,
            flags=re.IGNORECASE,
        )
        if not match:
            raise RuntimeError(f"Could not parse {weather} interaction prior.")
        return float(match.group(1)), float(match.group(2))

    weekday_not_orders, weekday_not_aov = parse_weather_row(
        weekday_block.group(1), "NOT_RAINING"
    )
    weekday_rain_orders, weekday_rain_aov = parse_weather_row(
        weekday_block.group(1), "RAINING"
    )
    weekend_not_orders, weekend_not_aov = parse_weather_row(
        weekend_block.group(1), "NOT_RAINING"
    )
    weekend_rain_orders, weekend_rain_aov = parse_weather_row(
        weekend_block.group(1), "RAINING"
    )

    order = {
        ("WEEKDAY", "NOT_RAINING"): 1.0,
        ("WEEKDAY", "RAINING"): weekday_rain_orders / weekday_not_orders,
        ("WEEKEND", "NOT_RAINING"): 1.0,
        ("WEEKEND", "RAINING"): weekend_rain_orders / weekend_not_orders,
    }
    aov = {
        ("WEEKDAY", "NOT_RAINING"): 1.0,
        ("WEEKDAY", "RAINING"): weekday_rain_aov / weekday_not_aov,
        ("WEEKEND", "NOT_RAINING"): 1.0,
        ("WEEKEND", "RAINING"): weekend_rain_aov / weekend_not_aov,
    }
    return order, aov


def _parse_category_line(line: str) -> dict[str, float]:
    categories = {}
    for category, value in re.findall(
        r"(MENU|MAIN|DRINK|SIDE|DESSERT)\s+\*\*([\d.]+)%\*\*", line
    ):
        categories[category] = float(value) / 100.0
    return categories


def _parse_category_mixes(
    text: str,
) -> tuple[dict[str, float], dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    baseline: dict[str, float] = {}
    for category in ("MENU", "MAIN", "DRINK", "SIDE", "DESSERT"):
        match = re.search(rf"- `{category}`:\s*\*\*([\d.]+)%\*\*", text)
        if not match:
            raise RuntimeError(
                f"Could not parse baseline category share for {category}."
            )
        baseline[category] = float(match.group(1)) / 100.0

    event_mix: dict[str, dict[str, float]] = {}
    for event in ("NONE", "SMALL_EVENT", "BIG_EVENT", "HOLIDAY"):
        match = re.search(rf"- `{event}`:\s*(.+)", text)
        if match:
            parsed = _parse_category_line(match.group(1))
            if parsed:
                event_mix[event] = parsed

    weather_mix: dict[str, dict[str, float]] = {}
    for weather in ("NOT_RAINING", "RAINING"):
        match = re.search(rf"- `{weather}`:\s*(.+)", text)
        if match:
            parsed = _parse_category_line(match.group(1))
            if parsed:
                weather_mix[weather] = parsed

    return baseline, event_mix, weather_mix


def _parse_hourly_shares(text: str) -> dict[int, float]:
    explicit: dict[int, float] = {}
    for hour, pct in re.findall(r"(\d{1,2})h:\s*\*\*([\d.]+)%\*\*", text):
        explicit[int(hour)] = float(pct) / 100.0

    window_patterns = {
        "pre_lunch": (range(0, 12), r"`pre_lunch`\s*\(<=11\):\s*\*\*([\d.]+)%\*\*"),
        "lunch": (range(12, 15), r"`lunch`\s*\(12-14\):\s*\*\*([\d.]+)%\*\*"),
        "afternoon": (range(15, 19), r"`afternoon`\s*\(15-18\):\s*\*\*([\d.]+)%\*\*"),
        "dinner_peak": (
            range(19, 23),
            r"`dinner_peak`\s*\(19-22\):\s*\*\*([\d.]+)%\*\*",
        ),
        "late": (range(23, 24), r"`late`\s*\(23\+\):\s*\*\*([\d.]+)%\*\*"),
    }

    shares: dict[int, float] = {
        hour: 0.0 for hour in range(OPENING_HOUR, CLOSING_HOUR + 1)
    }
    for _name, (hours, pattern) in window_patterns.items():
        match = re.search(pattern, text)
        if not match:
            raise RuntimeError(
                "Could not parse all hourly window shares from DATA_OVERVIEW.md."
            )
        window_share = float(match.group(1)) / 100.0
        valid_hours = [hour for hour in hours if OPENING_HOUR <= hour <= CLOSING_HOUR]
        known_share = sum(explicit.get(hour, 0.0) for hour in valid_hours)
        missing_hours = [hour for hour in valid_hours if hour not in explicit]
        remaining_share = max(0.0, window_share - known_share)
        if missing_hours:
            # Give lunch/dinner shoulder hours a little mass, while preserving explicit peaks.
            for hour in missing_hours:
                shares[hour] = remaining_share / len(missing_hours)
        for hour in valid_hours:
            if hour in explicit:
                shares[hour] = explicit[hour]

    total = sum(shares.values())
    if total <= 0:
        raise RuntimeError("Parsed hourly shares are invalid (sum <= 0).")
    return {hour: value / total for hour, value in shares.items()}


def _load_priors() -> Priors:
    global _PRIORS_CACHE
    if _PRIORS_CACHE is not None:
        return _PRIORS_CACHE["priors"]

    text = _read_overview()
    mean_daily_orders = _extract_required_float(
        r"Mean daily orders:\s*\*\*([\d.]+)\*\*", text, "mean daily orders"
    )
    mean_aov = _extract_required_float(
        r"Mean AOV:\s*\*\*([\d.]+)\*\*", text, "mean AOV"
    )
    none_order_quantiles = _extract_float_list(
        r"Orders quantiles \(p10/p25/p50/p75/p90\):\s*\*\*([^*]+)\*\*",
        text,
        "NONE-day order quantiles",
    )
    weekday_mean_orders = _parse_weekday_table(text)
    event_order, event_aov = _parse_event_multipliers(text)
    weather_order, weather_aov = _parse_weather_interactions(text)
    category_mix, event_category_mix, weather_category_mix = _parse_category_mixes(text)
    hourly_shares = _parse_hourly_shares(text)
    parent_lines = _extract_float_list(
        r"Parent lines/order distribution target:\s*mean\s*\*\*([\d.]+)\*\*,\s*median\s*\*\*[\d.]+\*\*,\s*p75\s*\*\*([\d.]+)\*\*,\s*p90\s*\*\*([\d.]+)\*\*",
        text,
        "parent lines per order",
    )

    priors = Priors(
        mean_daily_orders=mean_daily_orders,
        mean_aov=mean_aov,
        none_order_quantiles=none_order_quantiles,
        weekday_mean_orders=weekday_mean_orders,
        event_order_multipliers=event_order,
        event_aov_multipliers=event_aov,
        weather_order_multipliers=weather_order,
        weather_aov_multipliers=weather_aov,
        category_mix=category_mix,
        event_category_mix=event_category_mix,
        weather_category_mix=weather_category_mix,
        hourly_shares=hourly_shares,
        parent_lines_mean=parent_lines[0],
        parent_lines_p75=parent_lines[1],
        parent_lines_p90=parent_lines[2],
    )
    _PRIORS_CACHE = {"priors": priors}
    return priors


# ---------------------------------------------------------------------------
# Database and product helpers
# ---------------------------------------------------------------------------


def _parse_money(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _classify_product(product_name: str) -> str:
    name = product_name.strip().lower()
    if name.startswith("menu "):
        return "MENU"
    if "burger" in name:
        return "MAIN"
    if name in {"coke", "fanta", "water", "orange juice", "beer"}:
        return "DRINK"
    if name in {"sundae", "apple pie", "ice-cream cone", "ice cream cone"}:
        return "DESSERT"
    return "SIDE"


def _load_products(conn: sqlite3.Connection) -> dict[str, list[Product]]:
    rows = conn.execute(
        """
        SELECT product_id, product_name, base_price, item, item_quantity
        FROM Menu
        ORDER BY product_id;
        """
    ).fetchall()
    if not rows:
        raise RuntimeError("Menu table is empty; cannot generate Sales rows.")

    products: dict[str, list[Product]] = {
        category: [] for category in ("MENU", "MAIN", "DRINK", "SIDE", "DESSERT")
    }
    for row in rows:
        name = str(row["product_name"])
        product = Product(
            product_id=int(row["product_id"]),
            product_name=name,
            base_price=_parse_money(row["base_price"]),
            item=str(row["item"])
            if row["item"] is not None and str(row["item"]).strip()
            else None,
            item_quantity=int(row["item_quantity"])
            if row["item_quantity"] is not None
            else None,
            category=_classify_product(name),
        )
        products[product.category].append(product)

    for category in products:
        if not products[category]:
            raise RuntimeError(
                f"No Menu products found for generated category {category}."
            )
    return products


def _next_simulation_date(conn: sqlite3.Connection) -> str:
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
        return datetime.now().strftime("%d/%m/%Y")
    try:
        latest = datetime.strptime(str(row["date"]), "%d/%m/%Y")
        return (latest + timedelta(days=1)).strftime("%d/%m/%Y")
    except ValueError as exc:
        raise RuntimeError(
            f"Latest Calendar date '{row['date']}' is not DD/MM/YYYY."
        ) from exc


def _next_invoice_id(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(invoice_id), 0) + 1 AS next_id FROM Sales;"
    ).fetchone()
    return int(row["next_id"])


def _format_invoice_nr(invoice_id: int) -> str:
    return f"FT 26/{invoice_id:05d}"


# ---------------------------------------------------------------------------
# Statistical generation
# ---------------------------------------------------------------------------


def _is_weekend(week_day: str) -> bool:
    return week_day.upper() in WEEKEND_DAYS


def _bounded_lognormal(
    center: float, sigma: float, lower: float, upper: float
) -> float:
    if center <= 0:
        return lower
    sampled = float(_RNG.lognormal(mean=math.log(center), sigma=sigma))
    return min(max(sampled, lower), upper)


def _sample_daily_orders(
    priors: Priors, week_day: str, event: str, weather: str
) -> int:
    base = priors.weekday_mean_orders[week_day]
    week_class = "WEEKEND" if _is_weekend(week_day) else "WEEKDAY"
    event_multiplier = priors.event_order_multipliers.get(event, 1.0)
    weather_multiplier = priors.weather_order_multipliers.get(
        (week_class, weather), 1.0
    )

    location = base * event_multiplier * weather_multiplier
    location = _bounded_lognormal(
        location, sigma=0.08, lower=location * 0.85, upper=location * 1.18
    )

    # Overdispersed negative binomial parameterization: variance = mean + mean^2 / size.
    size = max(8.0, location / 3.0)
    probability = size / (size + location)
    sampled = int(_RNG.negative_binomial(size, probability))

    p10, _p25, _p50, _p75, p90 = priors.none_order_quantiles
    lower = max(1, int(round(p10 * 0.55)))
    upper = int(round(max(p90 * 1.75, location * 1.55)))
    return int(np.clip(sampled, lower, upper))


def _contextual_hourly_shares(
    priors: Priors, event: str, weather: str
) -> dict[int, float]:
    shares = dict(priors.hourly_shares)

    if event in {"BIG_EVENT", "HOLIDAY"}:
        # Compress some shoulder/afternoon mass toward the observed evening peak.
        transfer = sum(shares.get(hour, 0.0) for hour in (15, 16, 17, 18)) * 0.12
        for hour in (15, 16, 17, 18):
            shares[hour] *= 0.88
        shares[20] = shares.get(20, 0.0) + transfer * 0.45
        shares[21] = shares.get(21, 0.0) + transfer * 0.40
        shares[22] = shares.get(22, 0.0) + transfer * 0.15

    if weather == "RAINING":
        # Rain in the overview slightly favours more contained peak windows.
        transfer = sum(shares.get(hour, 0.0) for hour in (11, 15, 16, 17)) * 0.08
        for hour in (11, 15, 16, 17):
            shares[hour] *= 0.92
        shares[12] = shares.get(12, 0.0) + transfer * 0.25
        shares[20] = shares.get(20, 0.0) + transfer * 0.35
        shares[21] = shares.get(21, 0.0) + transfer * 0.40

    total = sum(shares.values())
    return {hour: value / total for hour, value in shares.items()}


def _sample_hourly_allocations(
    total_orders: int, priors: Priors, event: str, weather: str
) -> dict[int, int]:
    shares = _contextual_hourly_shares(priors, event, weather)
    hours = sorted(shares)
    alpha = np.array([max(shares[hour] * 140.0, 0.15) for hour in hours], dtype=float)
    probabilities = _RNG.dirichlet(alpha)
    counts = _RNG.multinomial(total_orders, probabilities)
    allocations = {hour: int(count) for hour, count in zip(hours, counts)}

    if sum(allocations.values()) != total_orders:
        raise AssertionError("Hourly allocations do not sum to total generated orders.")
    return allocations


def _blend_mix(*mixes: dict[str, float]) -> dict[str, float]:
    categories = ("MENU", "MAIN", "DRINK", "SIDE", "DESSERT")
    combined = {category: 0.0 for category in categories}
    weights = [0.60, 0.25, 0.15][: len(mixes)]
    for mix, weight in zip(mixes, weights):
        for category in categories:
            combined[category] += mix.get(category, 0.0) * weight
    total = sum(combined.values())
    if total <= 0:
        raise RuntimeError("Invalid category-mix priors; combined mix sums to zero.")
    return {category: combined[category] / total for category in categories}


def _category_probabilities(
    priors: Priors, event: str, weather: str
) -> tuple[list[str], np.ndarray]:
    mix = _blend_mix(
        priors.category_mix,
        priors.event_category_mix.get(event, priors.category_mix),
        priors.weather_category_mix.get(weather, priors.category_mix),
    )
    categories = list(mix)
    probabilities = np.array(
        [max(mix[category], 0.001) for category in categories], dtype=float
    )
    probabilities = probabilities / probabilities.sum()
    return categories, probabilities


def _sample_parent_line_count(priors: Priors) -> int:
    # Geometric-like basket breadth with quantile constraints from the overview.
    base = max(1, int(_RNG.geometric(1.0 / max(priors.parent_lines_mean, 1.05))))
    cap = max(2, int(round(priors.parent_lines_p90 + 1)))
    if _RNG.random() < 0.03:
        cap += 1
    return int(np.clip(base, 1, cap))


def _choose_product(
    products: dict[str, list[Product]], category: str, weather: str
) -> Product:
    choices = products[category]
    if category != "DRINK":
        return choices[int(_RNG.integers(0, len(choices)))]

    # Weather-conditioned beverage perturbation: rain lowers beer probability.
    weights = []
    for product in choices:
        name = product.product_name.lower()
        weight = 1.0
        if name == "beer" and weather == "RAINING":
            weight = 0.58
        elif name in {"coke", "fanta", "orange juice"} and weather == "RAINING":
            weight = 1.12
        weights.append(weight)
    probabilities = np.array(weights, dtype=float)
    probabilities /= probabilities.sum()
    return choices[int(_RNG.choice(len(choices), p=probabilities))]


def _menu_children(
    menu: Product, products: dict[str, list[Product]], weather: str
) -> list[Product]:
    menu_key = menu.product_name.lower().replace("menu ", "", 1)
    burger = next(
        (
            product
            for product in products["MAIN"]
            if product.product_name.lower() == menu_key
        ),
        _choose_product(products, "MAIN", weather),
    )
    side = _choose_product(products, "SIDE", weather)
    drink = _choose_product(products, "DRINK", weather)
    dessert = _choose_product(products, "DESSERT", weather)
    return [burger, side, drink, dessert]


def _line_price(product: Product) -> float:
    if product.base_price is None:
        raise RuntimeError(
            f"Product '{product.product_name}' has no numeric base price."
        )
    return round(product.base_price, 2)


def _random_minute_for_hour(hour: int) -> str:
    minute = int(_RNG.integers(0, 60))
    second = int(_RNG.integers(0, 60))
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _build_invoice_rows(
    *,
    date: str,
    invoice_id: int,
    hour: str,
    products: dict[str, list[Product]],
    categories: list[str],
    category_probabilities: np.ndarray,
    parent_line_count: int,
    weather: str,
) -> tuple[list[tuple[Any, ...]], float]:
    rows: list[tuple[Any, ...]] = []
    invoice_nr = _format_invoice_nr(invoice_id)
    line_nr = 1
    deduped_revenue = 0.0

    sampled_categories = list(
        _RNG.choice(categories, size=parent_line_count, p=category_probabilities)
    )
    if "MENU" not in sampled_categories and _RNG.random() < 0.35:
        sampled_categories[0] = "MENU"

    for category in sampled_categories:
        parent = _choose_product(products, str(category), weather)
        if parent.category == "MENU":
            children = _menu_children(parent, products, weather)
            parent_price = round(sum(_line_price(child) for child in children), 2)
        else:
            children = []
            parent_price = _line_price(parent)

        parent_line_nr = line_nr
        rows.append(
            (
                date,
                hour,
                invoice_id,
                invoice_nr,
                parent_line_nr,
                None,
                parent.product_id,
                parent.product_name,
                1,
                parent_price,
            )
        )
        deduped_revenue += parent_price
        line_nr += 1

        for child in children:
            rows.append(
                (
                    date,
                    hour,
                    invoice_id,
                    invoice_nr,
                    line_nr,
                    parent_line_nr,
                    child.product_id,
                    child.product_name,
                    1,
                    _line_price(child),
                )
            )
            line_nr += 1

    _validate_invoice_rows(rows)
    return rows, deduped_revenue


# ---------------------------------------------------------------------------
# Validation and extraction
# ---------------------------------------------------------------------------


def _validate_invoice_rows(rows: list[tuple[Any, ...]]) -> None:
    parent_lines = {int(row[4]) for row in rows if row[5] is None}
    all_lines = {int(row[4]) for row in rows}
    if len(all_lines) != len(rows):
        raise AssertionError("Duplicate line_nr generated inside invoice.")
    for row in rows:
        parent_id = row[5]
        if parent_id is not None and int(parent_id) not in parent_lines:
            raise AssertionError(
                "Generated child row references a missing parent line."
            )


def _validate_day_rows(rows: list[tuple[Any, ...]], expected_orders: int) -> None:
    invoices = {int(row[2]) for row in rows}
    if len(invoices) != expected_orders:
        raise AssertionError(
            "Generated invoice count does not match requested daily order count."
        )
    deduped_revenue = sum(float(row[9]) * int(row[8]) for row in rows if row[5] is None)
    child_revenue = sum(
        float(row[9]) * int(row[8]) for row in rows if row[5] is not None
    )
    if deduped_revenue <= 0 or child_revenue < 0:
        raise AssertionError("Generated revenue structure is invalid.")


def _extract_orders_queue(
    conn: sqlite3.Connection, date: str, first_invoice_id: int, last_invoice_id: int
) -> list[list[Any]]:
    rows = conn.execute(
        """
        SELECT hour, invoice_id, item, item_quantity
        FROM ItemOrders
        WHERE date = ?
          AND invoice_id BETWEEN ? AND ?
        ORDER BY hour, invoice_id, item;
        """,
        (date, first_invoice_id, last_invoice_id),
    ).fetchall()

    orders_queue: list[list[Any]] = []
    for row in rows:
        quantity = max(0, int(row["item_quantity"] or 0))
        emission_hour = str(row["hour"] or "")[:5]
        item_name = str(row["item"])
        for _ in range(quantity):
            orders_queue.append([item_name, emission_hour, "", ORDER_STATE_INACTIVE])
    return orders_queue


# ---------------------------------------------------------------------------
# Public generation entry point
# ---------------------------------------------------------------------------


def generate_day(
    week_day: str,
    event: str,
    weather: str,
    db_path: str,
    seed: int | None = None,
) -> list[list[Any]]:
    """Generate one synthetic sales day, persist it to Sales, and return ORDERS_QUEUE rows.

    Args:
        week_day: Calendar weekday label. Behaviour depends on this category only.
        event: One of NONE, SMALL_EVENT, BIG_EVENT, HOLIDAY (aliases SMALL/BIG accepted).
        weather: One of NOT_RAINING, RAINING.
        db_path: SQLite database path containing Sales, Calendar, Menu, Items, and ItemOrders.
        seed: Optional one-call reproducibility seed. If omitted, the module RNG state advances.

    Returns:
        A flat ORDERS_QUEUE-compatible list. Each entry is:
        [NOME, HORA_EMISSAO, HORA_RECEBIDO, ESTADO]
        where HORA_RECEBIDO is initially empty and ESTADO is INATIVO.
    """
    if seed is not None:
        seed_rng(seed)

    normalized_week_day = _normalize_weekday(week_day)
    normalized_event = _normalize_context(event or "NONE")
    normalized_weather = _normalize_context(weather or "NOT_RAINING")
    if normalized_event not in {"NONE", "SMALL_EVENT", "BIG_EVENT", "HOLIDAY"}:
        raise ValueError(f"Unsupported event '{event}'.")
    if normalized_weather not in {"NOT_RAINING", "RAINING"}:
        raise ValueError(f"Unsupported weather '{weather}'.")

    priors = _load_priors()
    total_orders = _sample_daily_orders(
        priors, normalized_week_day, normalized_event, normalized_weather
    )
    hourly_allocations = _sample_hourly_allocations(
        total_orders, priors, normalized_event, normalized_weather
    )
    if sum(hourly_allocations.values()) != total_orders:
        raise AssertionError("Total orders mismatch after hourly allocation.")

    week_class = "WEEKEND" if _is_weekend(normalized_week_day) else "WEEKDAY"
    aov_center = (
        priors.mean_aov
        * priors.event_aov_multipliers.get(normalized_event, 1.0)
        * priors.weather_aov_multipliers.get((week_class, normalized_weather), 1.0)
    )
    categories, category_probabilities = _category_probabilities(
        priors, normalized_event, normalized_weather
    )

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            products = _load_products(conn)
            simulation_date = _next_simulation_date(conn)
            first_invoice_id = _next_invoice_id(conn)

            rows_to_insert: list[tuple[Any, ...]] = []
            invoice_id = first_invoice_id
            for hour, count in sorted(hourly_allocations.items()):
                for _ in range(count):
                    # AOV is sampled as a tight target; basket breadth remains the dominant mechanism.
                    target_aov = _bounded_lognormal(
                        aov_center,
                        sigma=0.16,
                        lower=aov_center * 0.55,
                        upper=aov_center * 1.75,
                    )
                    parent_count = _sample_parent_line_count(priors)
                    if target_aov > aov_center * 1.25 and parent_count < int(
                        round(priors.parent_lines_p75)
                    ):
                        parent_count += 1
                    elif target_aov < aov_center * 0.75:
                        parent_count = 1

                    invoice_rows, _invoice_revenue = _build_invoice_rows(
                        date=simulation_date,
                        invoice_id=invoice_id,
                        hour=_random_minute_for_hour(hour),
                        products=products,
                        categories=categories,
                        category_probabilities=category_probabilities,
                        parent_line_count=parent_count,
                        weather=normalized_weather,
                    )
                    rows_to_insert.extend(invoice_rows)
                    invoice_id += 1

            _validate_day_rows(rows_to_insert, total_orders)
            last_invoice_id = invoice_id - 1

            conn.executemany(
                """
                INSERT INTO Sales
                    (date, hour, invoice_id, invoice_nr, line_nr, parent_id, product_id, product_name, quantity, price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                rows_to_insert,
            )
            conn.commit()

            orders_queue = _extract_orders_queue(
                conn, simulation_date, first_invoice_id, last_invoice_id
            )

    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Failed to generate and insert synthetic day into '{db_path}': {exc}"
        ) from exc

    if not orders_queue and total_orders > 0:
        raise RuntimeError(
            "Generated Sales rows produced no ItemOrders; check Menu production mappings."
        )

    return orders_queue


__all__ = ["generate_day", "seed_rng"]
