# MARCH-APRIL SALES OVERVIEW (CALENDAR-CONDITIONED, GENERATION-ORIENTED)

## 1) Scope and objective
Characterize observed sales behavior in March-April 2026 as a function of `week_day`, `event` (`NONE`, `SMALL_EVENT`, `BIG_EVENT`, `HOLIDAY`), `weather` (`RAINING`, `NOT_RAINING`), and `hour`.

Objective: provide generation-grade technical constraints and statistical priors for synthetic data simulation driven only by calendar attributes, without day-of-month identity rules.

## 2) Metric definitions (important for correct simulation)
- **Orders**: count of DISTINCT `invoice_id` per day/period.
- **Deduped Revenue**: sum of `price * quantity` only where `parent_id IS NULL` (or empty). Rows with populated `parent_id` are child components and are excluded from revenue totals.
- **AOV**: `Deduped Revenue / Total Orders`.
- **Parent Lines per Order**: count of parent rows per `invoice_id` (basket-breadth proxy).

## 3) Global baselines
- Total orders: **8826**
- Total deduped revenue: **77203.75**
- Mean daily orders: **144.69**
- Mean daily revenue: **1265.64**
- Mean AOV: **8.74**
- Distributional baseline on `event = NONE` days:
  - Orders quantiles (p10/p25/p50/p75/p90): **96.40 / 110.00 / 128.00 / 166.00 / 210.00**
  - Revenue quantiles (p10/p25/p50/p75/p90): **806.56 / 935.60 / 1120.15 / 1535.55 / 1758.34**

Interpretation for synthesis: non-event demand has a broad envelope (high p90 vs p10 spread), so order generation should be overdispersed with strong day-level stochasticity around structural baselines.

## 4) Weekday effects (dominant structural driver)
| week_day | days | mean orders | mean revenue | mean AOV |
|---|---:|---:|---:|---:|
| Monday | 9 | 124.89 | 1066.34 | 8.49 |
| Tuesday | 9 | 107.78 | 917.55 | 8.46 |
| Wednesday | 9 | 109.78 | 964.63 | 8.79 |
| Thursday | 9 | 116.22 | 1032.00 | 8.93 |
| Friday | 8 | 152.00 | 1374.98 | 9.01 |
| Saturday | 8 | 221.25 | 1915.04 | 8.67 |
| Sunday | 9 | 190.22 | 1673.21 | 8.84 |

Key conclusions:
- Weekday (Mon-Fri) mean orders/revenue: **121.45 / 1064.19**
- Weekend (Sat-Sun) mean orders/revenue: **204.82 / 1787.01**
- Weekend multipliers vs weekday:
  - Orders: **1.69x**
  - Revenue: **1.68x**
- AOV is comparatively stable across weekdays; primary lift is volume (traffic), not ticket-size inflation.

Simulation implication:
Use weekday as the first-order structural driver for daily volume (`lambda_orders`). Apply event and weather adjustments after weekday baseline; keep AOV modulation mild relative to order-count modulation.

## 5) Event effects (conditioned on sparse observations)
| event | days | mean orders | mean revenue | mean AOV |
|---|---:|---:|---:|---:|
| NONE | 53 | 141.51 | 1239.77 | 8.76 |
| SMALL_EVENT | 5 | 143.20 | 1173.17 | 8.22 |
| BIG_EVENT | 2 | 172.00 | 1507.10 | 8.78 |
| HOLIDAY | 1 | 266.00 | 2615.90 | 9.83 |

Reliability note:
`SMALL_EVENT` (5 days), `BIG_EVENT` (2 days), and `HOLIDAY` (1 day) are sparse; treat as high-variance priors.

More robust interpretation:
Relative to matched `NONE` baseline (same `week_day` + same `weather`):
- `SMALL_EVENT`: orders **1.05x** (range **0.91-1.18x**), revenue **0.94x** (range **0.77-1.20x**), AOV **0.89x**.
- `BIG_EVENT`: orders **1.47x** (range **1.34-1.61x**), revenue **1.42x**, AOV **0.97x**.
- `HOLIDAY`: orders **1.27x**, revenue **1.56x**, AOV **1.21x** (single-observation prior).

Simulation implication:
Model events primarily as demand-volume multipliers with uncertainty bands. Keep `SMALL_EVENT` weak/moderate and noisy; apply stronger uplift for `BIG_EVENT` and `HOLIDAY`, while allowing AOV to remain near baseline unless explicitly sampled upward.

## 6) Weather effects and interactions
| weather | days | mean orders | mean revenue | mean AOV |
|---|---:|---:|---:|---:|
| NOT_RAINING | 46 | 144.74 | 1270.14 | 8.82 |
| RAINING | 15 | 144.53 | 1251.81 | 8.49 |

Interaction diagnostics:
- Weekday split:
  - `NOT_RAINING`: **124.88 orders**, **1116.67 revenue**, **8.92 AOV** (34 days)
  - `RAINING`: **109.80 orders**, **885.79 revenue**, **8.07 AOV** (10 days)
- Weekend split:
  - `NOT_RAINING`: **201.00 orders**, **1704.99 revenue**, **8.53 AOV** (12 days)
  - `RAINING`: **214.00 orders**, **1983.86 revenue**, **9.31 AOV** (5 days)

Simulation implication:
Do not apply a single global rain coefficient. Use interaction terms (`weather x weekend/weekday`): rain is negative on weekdays in this sample, but mildly positive on weekends.

## 7) Product-type behavior (what is sold)
Approximate parent-quantity shares (pattern-based from `product_name`):
- `MENU`: **40.55%**
- `MAIN`: **28.40%**
- `DRINK`: **13.30%**
- `SIDE`: **11.92%**
- `DESSERT`: **5.83%**

Event-conditioned shifts (share of parent quantity):
- `NONE`: MENU **40.75%**, MAIN **28.29%**, DRINK **13.33%**, SIDE **11.94%**, DESSERT **5.69%**
- `SMALL_EVENT`: MENU **42.41%**, MAIN **25.21%**, DRINK **12.56%**, SIDE **12.23%**, DESSERT **7.59%**
- `BIG_EVENT`: MENU **34.30%**, MAIN **35.06%**, DRINK **14.18%**, SIDE **11.43%**, DESSERT **5.03%**
- `HOLIDAY`: MENU **39.07%**, MAIN **30.00%**, DRINK **13.15%**, SIDE **11.30%**, DESSERT **6.48%**

Weather/day-conditioned shifts:
- By weather:
  - `NOT_RAINING`: MENU **39.92%**, MAIN **28.89%**, DRINK **13.54%**, SIDE **11.85%**, DESSERT **5.80%**
  - `RAINING`: MENU **42.55%**, MAIN **26.83%**, DRINK **12.55%**, SIDE **12.15%**, DESSERT **5.92%**
- Beverage mix (`DRINK` subset) under rain shows lower beer share:
  - `NOT_RAINING`: Beer **14.93%** of beverage quantity
  - `RAINING`: Beer **10.83%** of beverage quantity

Simulation implication:
Use a stable core mix (`MENU`-first, then `MAIN`) with context perturbations: increase standalone `MAIN` in `BIG_EVENT`; slightly increase `MENU` and reduce beer tendency under `RAINING`; keep shifts bounded (small absolute pp changes except sparse-event cases).

## 8) Intra-day demand curve (hourly)
Hour-level order distribution (share of total orders):
- 12h: **10.40%**, 13h: **11.26%**
- 19h: **12.21%**, 20h: **18.31%**, 21h: **19.15%**, 22h: **6.87%**
- Top single hour: **21h**, then **20h**, then **19h**.

Windowed shares:
- `pre_lunch` (<=11): **1.25%**
- `lunch` (12-14): **25.27%**
- `afternoon` (15-18): **13.80%**
- `dinner_peak` (19-22): **56.54%**
- `late` (23+): **3.15%**

Weekday-specific top hours (avg orders/hour/day):
- Monday: **20h > 21h > 19h**
- Tuesday: **21h > 20h > 13h**
- Wednesday: **21h > 20h > 19h**
- Thursday: **21h > 12h > 13h**
- Friday: **21h > 20h > 19h**
- Saturday: **20h > 21h > 19h**
- Sunday: **20h > 21h > 19h**

Hourly AOV/menu share profile:
- Lunch window: AOV **9.70**, MENU share **48.06%**
- Afternoon window: AOV **7.90**, MENU share **37.96%**
- Dinner peak: AOV **8.58**, MENU share **37.60%**
- Pre-lunch/late are low-volume tails.

Simulation implication:
Generate orders with a bimodal curve (lunch + dominant dinner), concentrating most mass in 19-22h. Keep higher MENU intensity at lunch and lower AOV in afternoon shoulder hours.

## 9) Practical generation blueprint for calendar-driven synthetic months
1. **Daily orders**
   - Baseline by weekday from observed means.
   - Apply multiplicative factors:
     - `m_event_orders`: `SMALL_EVENT ~1.05x` (high variance), `BIG_EVENT ~1.47x`, `HOLIDAY ~1.27x` (very sparse).
     - `m_weather_orders`: condition on weekend/weekday (weekday rain downshift; weekend rain mild uplift).
   - Sample with overdispersion (Negative Binomial preferred).

2. **Daily AOV**
   - Use tighter distribution than orders (global mean daily AOV **8.74**).
   - Event/weather effects are secondary; only sparse `HOLIDAY` shows strong uplift and should be treated as uncertain prior.

3. **Hourly allocation**
   - Allocate daily orders via window shares: `pre_lunch 1.25%`, `lunch 25.27%`, `afternoon 13.80%`, `dinner_peak 56.54%`, `late 3.15%`.
   - Inside dinner peak, prioritize `20h-21h`.

4. **Basket composition**
   - Parent-category baseline: MENU **40.55%**, MAIN **28.40%**, DRINK **13.30%**, SIDE **11.92%**, DESSERT **5.83%**.
   - Parent lines/order distribution target: mean **1.63**, median **1**, p75 **2**, p90 **3**.
   - Apply contextual perturbations (not full remixes), notably `BIG_EVENT -> MAIN up / MENU down` and `RAINING -> beer share down`.

5. **Parent-child consistency**
   - Generate parent lines first; attach child component lines consistently to preserve structure.
   - KPI computation must keep deduped logic: revenue from parent rows only.

## 10) Hard constraints for downstream coding agent
1. Use only `week_day`, `event`, `weather`, and `hour` as behavioral drivers; never encode day-of-month identities.
2. Compute **Orders** as distinct `invoice_id` counts and **Deduped Revenue** only from parent rows (`parent_id IS NULL/empty`).
3. Preserve strong weekend uplift (~**1.69x** orders, ~**1.68x** revenue vs weekdays).
4. Preserve dominant intra-day structure: lunch secondary peak + dinner primary peak (19-22h majority mass).
5. Treat sparse event classes (`SMALL_EVENT`, `BIG_EVENT`, `HOLIDAY`) as high-variance priors with matched-baseline multipliers, not deterministic constants.
6. Keep AOV variability lower than order-count variability and enforce parent-child line coherence in generation and downstream metric calculations.
