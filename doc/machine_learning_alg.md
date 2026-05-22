# 📘 PART 1: CONCEPTUAL FRAMEWORK (Mapped to Class Material)

### 1. Problem Paradigm: Supervised Regression
Your class covers Classification (discrete labels) and Clustering (unsupervised grouping), but explicitly introduces **Regression** for continuous targets (e.g., *House Prices*). Predicting `nr_orders` per `(prod, time_window)` is a regression task. The learning pipeline maps directly:
- **Experience (E):** Historical `ItemOrders` + calendar context (`week_day`, `event`, `weather`)
- **Task (T):** Predict continuous `item_quantity` for unseen future windows
- **Performance (P):** Instead of Accuracy, we use **MAE** (Mean Absolute Error). Lower error = better model.

### 2. Baseline Benchmark (Adapted Majority Class)
The class mandates a naive baseline to prove model value. For regression, this is the **Historical Mean Baseline**:
- `DummyRegressor(strategy='mean')` predicts the global average regardless of context.
- **Rule:** The ML model is only accepted if its test MAE is **strictly lower** than this baseline.

### 3. Algorithm: Decision Tree Regressor
Directly maps to your class's deep dive into **Decision Tree Learning**:
- Instead of maximizing Information Gain/Gini, the tree splits to **minimize variance (MSE)**.
- Naturally captures interactions like `"Holiday + Raining → 30% drop at 19:00"`.
- Highly interpretable, matches class diagrams of axis-parallel decision boundaries.

### 4. Validation: Chronological Holdout Split
The class teaches a 70/30 random split. For forecasting, **random splitting leaks future data**. We adapt the holdout principle:
- **Training Domain:** Oldest 80% of dates
- **Testing Domain:** Newest 20% of dates
- This respects causality and mirrors the class's `Train vs Test` isolation principle.

### 5. Overfitting Diagnosis (Class Core Concept)
We track the exact curve taught in class: **Training Error vs Testing Error**.
- If `Train MAE ≈ 0` but `Test MAE` is high → **Overfitting** (tree memorized noise)
- If both errors are high → **Underfitting** (tree too shallow)
- We fix this by tuning `max_depth` (pre-pruning), exactly as shown in your class slides.

### 6. 🔑 Autoregressive Features (Lag & Rolling)
**Why it's critical:** Decision trees have no memory of row order. Without lag features, the model only learns static context averages (e.g., `"Monday 12pm Holiday = 15 orders"`), completely missing momentum signals like `"demand jumped 20% in the last window"` or `"rainy streak is cooling down"`.
- **Solution:** Explicitly engineer temporal features so the tree can learn dynamics:
  - `lag_1w`: Orders in the exact same `(prod, time_window)` last week
  - `rolling_3d_avg`: 3-day moving average of recent demand
- This aligns with the class's emphasis on **feature selection over raw IDs**: we transform raw sequential data into predictive signals the algorithm can actually split on.

---

# ⚙️ PART 2: IMPLEMENTATION SPECIFICATION (sklearn)

This replaces **only** the `VALUE * PCT_EVENT * PCT_WEATHER` step. All other layers (`MULTIPLICADOR_MANUAL`, `MULTIPLICADOR_PROPRIO_DIA`, runtime queues, `DayPrediction` table) remain identical.

### Step 1: Temporal Data Ingestion & Lag Feature Engineering
**Goal:** Build a row-per-observation matrix where `date` is preserved, and temporal momentum features are added.
```python
import pandas as pd
import numpy as np

# 1. Load & Join (keeps date intact)
orders = pd.read_sql("SELECT date, hour, item, item_quantity FROM ItemOrders", conn)
cal = pd.read_sql("SELECT date, week_day, event, weather FROM Calendar", conn)
items = pd.read_sql("SELECT name, shelf_time FROM Items", conn)

df = orders.merge(cal, on="date").merge(items, left_on="item", right_on="name")

# 2. Aggregate per (date, prod, time_window)
# Reuse your existing _generate_windows logic to assign orders to product-specific windows
df["time_window"] = df.apply(lambda r: assign_to_window(r.hour, r.shelf_time), axis=1)
df_agg = df.groupby(["date", "week_day", "event", "weather", "item", "time_window"])["item_quantity"].sum().reset_index()
df_agg.rename(columns={"item": "prod"}, inplace=True)

# 3. Create Autoregressive Features (Lag/Rolling)
# Sort chronologically per product+window so shifts look BACK in time, never forward
df_agg = df_agg.sort_values("date").reset_index(drop=True)
df_agg["start_hour"] = df_agg["time_window"].str.split("_").str[0].apply(lambda h: float(h.split(":")[0]))

# Group by product + window, then shift/roll along the date axis
for _, grp in df_agg.groupby(["prod", "time_window"]):
    idx = grp.index
    df_agg.loc[idx, "lag_1w"] = grp["item_quantity"].shift(1)
    df_agg.loc[idx, "rolling_3d"] = grp["item_quantity"].rolling(window=3, min_periods=1).mean()

# Fill initial NaN lags with 0 (cold start = no previous demand)
df_agg[["lag_1w", "rolling_3d"]] = df_agg[["lag_1w", "rolling_3d"]].fillna(0)

# 4. One-Hot Encode & Define X/y
df_agg = pd.get_dummies(df_agg, columns=["week_day", "event", "weather", "prod"], drop_first=True)
feature_cols = [c for c in df_agg.columns if c not in ["date", "item_quantity"]]
X = df_agg[feature_cols].values
y = df_agg["item_quantity"].values
dates = df_agg["date"].values
```

### Step 2: Chronological Train/Test Split
**Goal:** Isolate past vs future without shuffling.
```python
from sklearn.model_selection import train_test_split

# Chronological split by index (data is already date-sorted)
split_idx = int(len(X) * 0.8)
X_train, X_test = X[:split_idx], X[split_idx:]
y_train, y_test = y[:split_idx], y[split_idx:]
```

### Step 3: Baseline & Decision Tree Training
**Goal:** Fit model and verify it beats the naive floor.
```python
from sklearn.tree import DecisionTreeRegressor
from sklearn.dummy import DummyRegressor
from sklearn.metrics import mean_absolute_error

# A) Baseline (Adapted Majority Class)
baseline = DummyRegressor(strategy="mean")
baseline.fit(X_train, y_train)
mae_base = mean_absolute_error(y_test, baseline.predict(X_test))

# B) Decision Tree Regressor (Class Algorithm)
tree_model = DecisionTreeRegressor(max_depth=5, min_samples_split=10, random_state=42)
tree_model.fit(X_train, y_train)

mae_train = mean_absolute_error(y_train, tree_model.predict(X_train))
mae_test  = mean_absolute_error(y_test, tree_model.predict(X_test))

print(f"Baseline MAE: {mae_base:.2f} | Train MAE: {mae_train:.2f} | Test MAE: {mae_test:.2f}")
```

### Step 4: Overfitting Check & Tuning
- **If `mae_test < mae_base`**: Model is valid. Proceed.
- **If `mae_test >> mae_train`** (ΔE is large): Tree memorized noise. Reduce `max_depth` or increase `min_samples_leaf`.
- **If `mae_test > mae_base`**: Underfitting or weak signal. Keep heuristic as fallback.



### 🔗 How It Plugs Into Your System
| Component | Heuristic Mode | ML Mode |
|-----------|----------------|---------|
| `PRE_CALCULO` | `VALUE * PCT_EVENT * PCT_WEATHER` | `DecisionTree.predict(X)` |
| Runtime Formula | `PRE * MULT_MANUAL * MULT_PROPRIO_DIA` | **Identical** |
| Database Table | `DayPrediction` | **Identical** (`DayPrediction`) |
| Fallback | N/A | If `mae_test > baseline`, auto-switch to heuristic |
