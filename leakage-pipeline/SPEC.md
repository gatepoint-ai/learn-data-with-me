# Leakage pipeline: what the dbt project must produce

The generator writes raw files. The dbt project turns them into a small star schema and three
reconciliation marts. `check/acceptance.py` then reads `faults.json` and the marts, and passes only
if every planted fault is flagged, every control stays quiet, and nothing else is flagged.

## Sources (from `generate/generate.py`, in `data/`)

| File | Grain | Columns |
|---|---|---|
| `customers.csv` | one row per customer | `customer_id`, `segment`, `home_site` |
| `products.csv` | one row per product | `product_code`, `description`, `unit`, `rate` |
| `usage.csv` | one row per usage record | `record_id`, `customer_id`, `product_code`, `site`, `event_ts`, `received_ts`, `units` |
| `billed.csv` | one row per bill line | `bill_line_id`, `record_id`, `customer_id`, `product_code`, `bill_date`, `billed_amount` |

`billed.record_id` points at the usage record the line charges for. A record can have zero bill lines
(unbilled, or free by design) or more than one (billed twice).

## Layers

```
sources ─► staging ─► intermediate ─► marts
           stg_*      int_*            fct_usage, fct_billing, dim_customer, dim_product
                                       mart_unbilled_usage, mart_rating_variance, mart_duplicate_billing
```

- **Staging:** one model per source, renamed and typed, nothing else. Timestamps as `TIMESTAMP`, dates as `DATE`, amounts as `DECIMAL`.
- **Facts and dimensions:**

| Model | Grain | Notes |
|---|---|---|
| `dim_customer` | one row per `customer_id` | |
| `dim_product` | one row per `product_code` | carries `rate` |
| `fct_usage` | one row per `record_id` | `usage_date = event_ts::date`, `expected_amount = units × rate` |
| `fct_billing` | one row per `bill_line_id` | joined to `fct_usage` on `record_id` for `usage_date` |

- **Incremental:** `fct_usage` should be incremental on `received_ts` **with a lookback** (3 days is enough). Usage that arrives late belongs to its **event** date. The `late_arrival` control checks this.

## Marts: the contract the acceptance check reads

Column names and types must match. Every mart lives in the default schema of the DuckDB file.

### `mart_unbilled_usage` (grain: one row per `site`, `usage_date`)

Only **billable** usage counts (`expected_amount > 0`). Free products are expected to be unbilled.

| Column | Meaning |
|---|---|
| `site`, `usage_date` | the grain |
| `expected_amount` | sum of `expected_amount` for billable records |
| `billed_amount` | sum of `billed_amount` for bill lines of those records |
| `unbilled_amount` | `expected_amount − billed_amount` |
| `unbilled_ratio` | `unbilled_amount / expected_amount` |
| `is_flagged` | `unbilled_ratio > 0.10` |

### `mart_rating_variance` (grain: one row per `product_code`, `usage_date`)

Only usage that **was billed**: this mart asks "was it charged at the right price?", not "was it charged?".

| Column | Meaning |
|---|---|
| `product_code`, `usage_date` | the grain |
| `expected_amount` | `units × rate` for the billed records, counted once per bill line |
| `billed_amount` | sum of `billed_amount` |
| `variance_ratio` | `billed_amount / expected_amount − 1` |
| `is_flagged` | `abs(variance_ratio) > 0.01` |

### `mart_duplicate_billing` (grain: one row per `record_id` billed more than once)

| Column | Meaning |
|---|---|
| `record_id` | the usage record |
| `customer_id`, `usage_date` | from `fct_usage` |
| `times_billed` | number of bill lines, always ≥ 2 in this mart |

## Tests every build should run

- `unique` and `not_null` on every grain key (`record_id` in `fct_usage`, `bill_line_id` in `fct_billing`, `customer_id`, `product_code`, and the two-column grains of the marts).
- `relationships`: `fct_usage.customer_id` → `dim_customer`, `fct_usage.product_code` → `dim_product`, `fct_billing.record_id` → `fct_usage`.
- `accepted_values` on `dim_customer.segment` (`consumer`, `business`).
- Source freshness is optional here (the files are static), but worth adding when Airflow runs the loads.

## Done means

1. `python generate/generate.py` writes `data/`.
2. `dbt build` in `dbt/` runs every model and test with no failures.
3. `python check/acceptance.py` prints `PASS` for all three faults and all three controls, and reports zero unexplained flags.
