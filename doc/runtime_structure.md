now in main after printing the day prediction i want it to go to this "Simulate the day (dd/mm/yyyy)" section where it asks the user "Do you want to proceed with the simulation (y/n):" (no will simply exit the programm), and then ask the questions: "Time of a simulated minute (default 1.0 seconds): "

then at teh end of main after calling the order simulation function and the updating the calendar table, make a call for a function that will be called day_simulation(seconds, predictions, order_simulation)
that will recieve the input of teh user to teh question how many seconds for simulated minute, and the data from predictions in main, and order_simulation in main

this day_simulation function/method will treat both the time and the logic
 the logic is explain behind, with the arrays behavirou map, and the arrays situation will be evaluted each simulated minute that passes, and the transactions between them will happen, becaus ethey evalute through time most of the time (it basically os is a repeated by the minute evaluation  of the state, and taking action if the rules say so). these logical map is here:

 as for as teh data scructuees "Orders" and Items" are concenred:
 - "Items" need to be computed from the info on "predictions"
 - "Orders" are basically each array in the array of arrays "order_simulation"
 


###  Array-by-Array Insert/Remove Map

#### 1. `FATURAS` (Global)
| Action | Condition | Details |
|:---|:---|:---|
| 🔹 **INSERT** | `tempo_atual == invoice.HORA_EMISSAO` | Append the full invoice entry to the end of the array. Parser has already distributed production items to `ORDERS_QUEUE`. |
| 🔸 **REMOVE** | *Never* | Append-only observation array. |
| 🔄 **UPDATE** | None | Fields remain static after insertion. |
| 📦 **STRUCTURE** | Runtime retrieval from DB | `[hour, invoice_id, invoice_nr, [[line_nr, parent_id, product_id, product_name, quantity, price], ...], [[item, item_quantity], ...]]`<br>Data grouped by `invoice_id`, pulled live from `Sales` (line items) and `ItemOrders` (bottleneck mapping). |

#### 2. `ORDERS_QUEUE` (x6 Products)
| Action | Condition | Details |
|:---|:---|:---|
| 🔹 **INSERT** | Day initialization (Parser) | All simulated orders for the day are pre-loaded. Structure: `[NOME, INVOICE_ID, HORA_EMISSAO, HORA_RECEBIDO, ESTADO]`. Initially `HORA_RECEBIDO = None/""`, `ESTADO = "INATIVO"`. |
| 🔹 **ACTIVATE** | `tempo_atual == order.HORA_EMISSAO` | `ESTADO` → `"ESPERA"`. **Increment `nr_real_orders++`** for this product's current time window. |
| 🔹 **STAY (UNPREDICTED)** | Activated but **NO** matching `SHELF` item in same tick | Order remains in queue (`ESTADO="ESPERA"`). Triggers immediate `Item` creation (see `ITEM_PREP`/`ITEM_QUEUE` rules). |
| 🔸 **REMOVE** | Order matched with `SHELF` item | Item removed from queue and transferred to `ORDERS_ANSWERED`. |
| 🔄 **UPDATE** | On match | `HORA_RECEBIDO` → `tempo_atual`, `ESTADO` → `"ENTREGUE"`. `INVOICE_ID` remains constant for traceability. |

#### 3. `ORDERS_ANSWERED` (x6 Products)
| Action | Condition | Details |
|:---|:---|:---|
| 🔹 **INSERT** | Successful match from `ORDERS_QUEUE` | Order moves here immediately after being fulfilled from `SHELF`. Inherits exact 5-element array structure from queue. |
| 🔸 **REMOVE** | *Never* | Historical append-only array. |
| 🔄 **UPDATE** | On insertion | `HORA_RECEBIDO` and `ESTADO` finalized. **If `HORA_EMISSAO == HORA_RECEBIDO` (same tick), increment `nr_predicted_orders++`**. `INVOICE_ID` preserved for audit matching. |

#### 4. `ITEM_QUEUE` (x6 Products)
| Action | Condition | Details |
|:---|:---|:---|
| 🔹 **INSERT** | `len(ITEM_PREP) == MAX_CAPACITY` **AND** production requested (predictive or unpredicted order) | Item created with `ESTADO="ESPERA"`, all timestamps `""`. **Guard:** Only insert if `len(ITEM_QUEUE) < MAX_LIMIT`. |
| 🔸 **REMOVE** | `len(ITEM_PREP) < MAX_CAPACITY` | Oldest item (FIFO) moves to `ITEM_PREP`. |
| 🔄 **UPDATE** | On removal/transfer | `ESTADO` → `"PREPARACAO"`. `HORA_PRONTO = tempo_atual + TEMPO_PREPARACAO`. `HORA_PRAZO = HORA_PRONTO + TEMPO_PRATELEIRA`. |

#### 5. `ITEM_PREP` (x6 Products)
| Action | Condition | Details |
|:---|:---|:---|
| 🔹 **INSERT** | Capacity available (`len < MAX_CAPACITY`) for predicted items, `ITEM_QUEUE` promotions, **OR unpredicted order triggers** | Bypasses `ITEM_QUEUE` if space exists. Directly enters cooking state. |
| 🔸 **REMOVE** | `tempo_atual == item.HORA_PRONTO` | Item finishes cooking and moves to `SHELF`. |
| 🔄 **UPDATE** | On insertion | `ESTADO` → `"PREPARACAO"`. Timestamps calculated as above. |

#### 6. `SHELF` (x6 Products)
| Action | Condition | Details |
|:---|:---|:---|
| 🔹 **INSERT** | `tempo_atual == item.HORA_PRONTO` (from `ITEM_PREP`) | Item becomes available for sale. `ESTADO` → `"PRATELEIRA"`. |
| 🔸 **REMOVE** | 1. Matched with `ORDERS_QUEUE` (fulfilled)<br>2. `tempo_atual >= item.HORA_PRAZO` (expired) | Fulfilled items disappear (tracked via `ORDERS_ANSWERED`). Expired items move to `TRASH`. |
| 🔄 **UPDATE** | On match | `ESTADO` → `"ENTREGUE"`, `HORA_ENTREGUE` → `tempo_atual`. Item logically exits `SHELF`. |

#### 7. `TRASH` (x6 Products)
| Action | Condition | Details |
|:---|:---|:---|
| 🔹 **INSERT** | 1. `tempo_atual >= item.HORA_PRAZO`<br>2. `tempo_atual == "00:00"` (end of day cleanup) | All remaining `SHELF` items are dumped. `ESTADO` → `"LIXO"`. |
| 🔸 **REMOVE** | *Never* | Historical append-only array. |
| 🔄 **UPDATE** | On insertion | `ESTADO` → `"LIXO"`. `HORA_ENTREGUE` remains `""` (or logged for audit). |

---

###  Real-Time Counter Logic (`nr_predicted_orders` & `nr_real_orders`)
*(x6 Products | Reset at end of each time_window | Flushed to `MULTIPLICADOR_PROPRIO_DIA` DB table)*

| Counter | Trigger Condition | Behavior & DB Flush |
|:---|:---|:---|
| **`nr_real_orders`**(x6 one for each item) | `tempo_atual == order.HORA_EMISSAO` (Order activates to `"ESPERA"`) | Increments **+1** per activated order, regardless of shelf availability. Accumulates in memory during the current `time_window`. Flushed to DB as `nr_real_orders` when window closes. |
| **`nr_predicted_orders`** (x6 one for each item) | `order.HORA_EMISSAO == order.HORA_RECEBIDO` (Activated & fulfilled in same tick) | Increments **+1** only if the order finds a `SHELF` item immediately upon activation. Accumulates in memory. Flushed to DB as `nr_predicted_orders` when window closes. |
| **DB Sync Rule** | `tempo_atual` reaches end of product-specific `time_window` (e.g., `11:20` for Pork Burger) | Current accumulators are written to: `INSERT INTO MULTIPLICADOR_PROPRIO_DIA (time_window, prod, nr_predicted_orders, nr_real_orders) VALUES (...)`. Counters reset to `0` for the next window. |

---

###  Critical Implementation Rules (Updated)

| Rule | Spec Reference | Implementation Note |
|:---|:---|:---|
| **FEFO Matching** | Sec 2.5 Ação 1 | When matching `SHELF` to `ORDERS_QUEUE`, **always pick the item with the earliest `HORA_PRAZO`**. Do not use FIFO. |
| **Unpredicted Order Trigger** | Sec 2.5 Ação 3 + Your Rule | If an order activates but finds no `SHELF` match, it **stays in `ORDERS_QUEUE`** and immediately spawns a production `Item`. This item respects capacity (`ITEM_PREP` or `ITEM_QUEUE`) and is treated as urgent on-demand production. |
| **Counter Definition** | Sec 5 + Your Rule | `nr_real_orders` = All activations in the window.<br>`nr_predicted_orders` = Activations fulfilled instantly (`HORA_EMISSAO == HORA_RECEBIDO`). Used to compute `MULTIPLICADOR_PROPRIO_DIA`. |
| **Capacity Split** | Sec 1.6 | If prediction > `MAX_CAPACITY`, fill `ITEM_PREP` to max, push remainder to `ITEM_QUEUE`. Next tick, as space frees, `ITEM_QUEUE` drains automatically. |
| **Predictive Trigger Time** | Sec 1.6 / 4 | Trigger production at: `window_start_time - (TEMPO_PREPARACAO + 1)`. E.g., Pork Burger (prep=4, buffer=1) triggers at `10:55` for `11:00` shelf window. |
| `MAX_LIMIT` Guard | Sec 2.2 | `ITEM_QUEUE` insertion **must** be blocked if `len >= (ORDERS_QUEUE_len + PREDICTION_val - ITEM_PREP_len - ANSWERED_this_window_len)`. Prevents memory bloat. |
| **Zero-Hour Cleanup** | Sec 2.5 Ação 2 | At `00:00`, run a final sweep: move all items remaining in `SHELF` to `TRASH`, set `ESTADO="LIXO"`. Flush final window counters to DB. |
