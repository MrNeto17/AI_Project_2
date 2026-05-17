# APRIL SALES OVERVIEW (CALENDAR-CONDITIONED, GENERATION-ORIENTED)

## 1) Scope and objective

This document characterizes how sales behavior varies as a function of:
- `week_day`
- `event` (`NONE`, `SMALL_EVENT`, `BIG_EVENT`, `HOLIDAY`)
- `weather` (`RAINING`, `NOT_RAINING`)
- `hour` (intra-day demand profile)

The goal is to provide technical constraints and statistical priors for a coding agent that must generate realistic monthly sales datasets from a calendar file only.

---

## 2) Metric definitions (important for correct simulation)

### Revenue definition (deduped menu logic)
In this dataset, rows with non-empty `parent_id` are child components of a parent item/menu. Their prices are structurally linked to the parent row and must **not** be double-counted for order revenue.

- **Daily revenue** = sum of `price * quantity` over rows where `parent_id` is empty.

### Order-volume definition
- **Daily orders** = count of distinct `invoice_id` per day.

### Additional diagnostic metrics used in this overview
- **AOV** = `daily_revenue / daily_orders`
- **Parent lines per order** = number of parent rows per invoice (proxy for basket breadth at the purchasable-item level)

---

## 3) Global baselines

- Total orders: **2203**
- Total deduped revenue: **20671.70**
- Mean daily orders: **73.43**
- Mean daily revenue: **689.06**
- Mean AOV: **9.36**

Distributional baseline on `event = NONE` days:
- Orders quantiles (p10/p25/p50/p75/p90): **53 / 56.25 / 64 / 81.75 / 99**
- Revenue quantiles (p10/p25/p50/p75/p90): **487.30 / 516.89 / 570.47 / 797.89 / 961.15**

Interpretation for synthesis:
- Non-event days exhibit a wide demand envelope; generator logic should include substantial stochastic spread around weekday baselines.

---

## 4) Weekday effects (dominant structural driver)

| week_day | days | mean orders | mean revenue | mean AOV |
|---|---:|---:|---:|---:|
| Monday | 4 | 65.50 | 601.35 | 9.21 |
| Tuesday | 4 | 60.50 | 543.04 | 8.93 |
| Wednesday | 5 | 56.20 | 520.21 | 9.27 |
| Thursday | 5 | 56.60 | 525.77 | 9.32 |
| Friday | 4 | 79.25 | 764.14 | 9.64 |
| Saturday | 4 | 111.75 | 1060.88 | 9.51 |
| Sunday | 4 | 92.75 | 891.05 | 9.66 |

Key conclusions:
1. **Weekend uplift is large and persistent**.
   - Weekdays (Mon–Fri): mean orders **62.96**, mean revenue **584.73**
   - Weekend (Sat–Sun): mean orders **102.25**, mean revenue **975.96**
   - Weekend multipliers vs weekday:
     - Orders: **~1.62x**
     - Revenue: **~1.67x**
2. AOV changes less than volume; primary lift mechanism is **traffic**, not ticket-size inflation.

Simulation implication:
- Build first-order volume from weekday class (weekday/weekend + specific weekday).
- Apply event/weather modifiers after weekday baseline.

---

## 5) Event effects (conditioned on sparse observations)

| event | days | mean orders | mean revenue | mean AOV |
|---|---:|---:|---:|---:|
| NONE | 26 | 71.62 | 672.39 | 9.37 |
| SMALL_EVENT | 2 | 62.00 | 555.80 | 8.97 |
| BIG_EVENT | 1 | 84.00 | 780.70 | 9.29 |
| HOLIDAY | 1 | 133.00 | 1297.35 | 9.76 |

Reliability note:
- `BIG_EVENT` and `HOLIDAY` each have one observation, and `SMALL_EVENT` has two observations. Treat these as **high-variance priors**, not hard deterministic truths.

More robust interpretation (event compared against same weekday/weather `NONE` baseline):
- `SMALL_EVENT`: ~**1.13–1.19x orders**, with mixed revenue impact due to lower/highly variable AOV in one case.
- `BIG_EVENT`: ~**1.62x orders**, ~**1.50x revenue**, AOV slightly below same-context baseline.
- `HOLIDAY`: ~**1.55x orders**, ~**1.53x revenue**, AOV near same-context baseline.

Simulation implication:
- Event mainly scales **order volume**, not dramatically changing AOV.
- Use moderate uplift for `SMALL_EVENT`, strong uplift for `BIG_EVENT`/`HOLIDAY`, with stochastic noise due to sparse calibration data.

---

## 6) Weather effects and interactions

| weather | days | mean orders | mean revenue | mean AOV |
|---|---:|---:|---:|---:|
| NOT_RAINING | 25 | 68.32 | 642.54 | 9.36 |
| RAINING | 5 | 99.00 | 921.66 | 9.33 |

Raw effect appears strongly positive under `RAINING`, but this is confounded by calendar composition (rain mostly on high-traffic weekend contexts in this sample).

Interaction diagnostics:
- Weekend only:
  - `NOT_RAINING`: orders **96.75**, revenue **941.89**
  - `RAINING`: orders **107.75**, revenue **1010.04**
  - Rain uplift on weekend exists but is modest vs weekend baseline.
- Weekday only:
  - Too little rainy weekday coverage for robust standalone coefficient.

Simulation implication:
- Do **not** model rain as a universal large multiplier.
- Apply weather as a secondary modifier with interaction terms (especially weekend × rain).

---

## 7) Product-type behavior (what is sold)

Parent-line category share (approximate):
- `MENU`: dominant block (~41% on normal days)
- `MAIN` (standalone burgers): ~28%
- `DRINK`: ~14%
- `SIDE`: ~12%
- `DESSERT`: ~6%

Event-conditioned category shifts:
- `NONE`: MENU-heavy baseline.
- `SMALL_EVENT`: slight increase in `DRINK` and `SIDE` mix.
- `BIG_EVENT`: shift toward standalone `MAIN` relative to MENU (more à-la-carte behavior).
- `HOLIDAY`: close to baseline MENU-heavy structure with slightly stronger dessert share.

Menu share by weekday (parent lines):
- Range ~**36% to 43%** depending on weekday.
- Lower menu share on Monday/Tuesday; higher on Wednesday/Thursday/Sunday.

Weather-conditioned beverage child-line mix:
- `RAINING` shifts beverage composition toward **Coke** and away from **Beer**.
- `NOT_RAINING` has relatively higher beer share.

Simulation implication:
- Keep a stable core product-distribution template, then apply small context-conditioned perturbations by event/weather.

---

## 8) Intra-day demand curve (hourly)

Order start-hour distribution (share of total orders):
- **Lunch cluster (12–13h)**: ~**22.15%**
- **Dinner peak (19–21h)**: ~**48.94%**
- Strongest single hour: **21h** (~19.02%), then **20h** (~17.66%), then **19h** (~12.26%)

Windowed shares:
- `dinner_peak` (19–22): **55.92%**
- `lunch` (12–14): **25.65%**
- `afternoon` (15–18): **13.07%**
- `late` (23+): **3.72%**
- `pre_lunch` (<=11): **1.63%**

Weekday-specific top hours (avg orders/hour/day):
- Monday: 20h > 19h > 21h
- Tuesday: 21h > 20h > 13h
- Wednesday: 21h ≈ 19h > 13h
- Thursday: 21h > 12h > 13h
- Friday: 21h > 20h > (13h ≈ 19h)
- Saturday: 20h > 21h > 19h
- Sunday: 21h > 20h > 13h

Hourly ticket profile:
- Higher revenue/order at lunch (~11) and dinner (~9.4–9.5) versus shoulder hours (~7.8–8.3).
- Menu share is highest at lunch (~49%), lower during afternoon/dinner (~36–38%).

Simulation implication:
- Use a bimodal temporal model (lunch + stronger dinner mode).
- Scale evening intensity up on Friday/Saturday/Sunday and on major-event conditions.

---

## 9) Practical generation blueprint for calendar-driven synthetic months

Recommended factorized model for each day `d`:

1. **Daily orders**
   - Start with weekday baseline: `lambda_orders(week_day)`
   - Apply event multiplier: `m_event_orders(event)`
   - Apply weather multiplier with interaction: `m_weather_orders(weather, week_day_or_weekend)`
   - Sample from overdispersed count distribution (Negative Binomial preferred over Poisson).

2. **Daily AOV / revenue per order**
   - Keep tighter range than volume (AOV is much more stable).
   - Use mild context shifts only; avoid extreme event-driven AOV jumps.

3. **Hourly allocation**
   - Allocate daily orders using context-specific hourly proportions:
     - strong mass at 19–21h
     - secondary mass at 12–13h
   - Event/holiday/rain can further concentrate demand at 20–21h.

4. **Basket composition**
   - Keep MENU as top-level dominant class.
   - Introduce context perturbations:
     - `BIG_EVENT`: relatively more standalone mains
     - rainy contexts: beverage mix tilts to non-alcoholic soft drinks
   - Preserve realistic lines/order around observed central tendency (~5 lines median).

5. **Parent-child consistency constraints**
   - If a parent menu is generated, child lines should be generated coherently.
   - Revenue computation must still rely on parent-row dedup logic to avoid double counting.

---

## 10) Hard constraints for downstream coding agent

1. Never infer behavior from explicit day-of-month identities; use only `week_day`, `event`, `weather`, `hour`.
2. Preserve two-peak intraday shape (lunch + dinner, dinner dominant).
3. Preserve weekend traffic uplift as the strongest recurring pattern.
4. Treat event/weather coefficients as probabilistic (sparse-event uncertainty).
5. Keep AOV variability lower than order-volume variability.
6. Enforce parent-child pricing consistency in both generation and KPI calculations.

This set of constraints reproduces the observed April dynamics while remaining portable to arbitrary future months driven only by calendar attributes.