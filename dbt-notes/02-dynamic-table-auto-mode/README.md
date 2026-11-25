# dbt notes 02 · AUTO picked FULL: a dynamic table's refresh mode

One `current_date()` in the SELECT list, and a Snowflake dynamic table on `refresh_mode = AUTO` picked FULL
refresh. Snowflake says so once, in the CREATE status message. After that, the reason lives in one column of
`SHOW DYNAMIC TABLES`.

## The test

Three dynamic tables over the same source, 10,000 random orders for 50 customers, X-Small warehouse:

| Table | Refresh mode asked for | Query |
|---|---|---|
| `DT_AUTO_SELECT_DATE` | `AUTO` | `sum(amount)` per customer, plus `current_date() as as_of` in the **SELECT list** |
| `DT_AUTO_WHERE_DATE` | `AUTO` | `sum(amount)` per customer, `current_date()` only in the **WHERE** clause |
| `DT_ADAPTIVE` | `ADAPTIVE` | `sum(amount)` per customer, no date function |

All three use `target_lag = downstream` with no consumer, so nothing refreshes on a schedule: every refresh in the
log is either the creation or a manual `alter dynamic table … refresh`.

## What CREATE said

| Table | Status returned by CREATE |
|---|---|
| DT_AUTO_SELECT_DATE | Dynamic table DT_AUTO_SELECT_DATE successfully created. **FULL refresh mode was selected because:** Query contains the function 'CURRENT_DATE', but change tracking is not supported on queries with non-deterministic functions. … |
| DT_AUTO_WHERE_DATE | Dynamic table DT_AUTO_WHERE_DATE successfully created. |
| DT_ADAPTIVE | Dynamic table DT_ADAPTIVE successfully created. |

The CREATE message names the mode only when AUTO falls back to FULL. It's one line, easy to miss when a tool
runs the CREATE for you.

## What AUTO resolved to

```sql
show dynamic tables in schema dt_test.lab;
select "name", "refresh_mode", "refresh_mode_reason", "rows"
from table(result_scan(last_query_id()));
```

| name | refresh_mode | refresh_mode_reason |
|---|---|---|
| DT_ADAPTIVE | ADAPTIVE | *(null)* |
| DT_AUTO_SELECT_DATE | **FULL** | Query contains the function 'CURRENT_DATE', but change tracking is not supported on queries with non-deterministic functions. … |
| DT_AUTO_WHERE_DATE | **ADAPTIVE** | *(null)* |

- `current_date()` in the SELECT list made AUTO fall back to FULL. After the CREATE message, the reason is a
  full sentence in `refresh_mode_reason`, a column that `SHOW DYNAMIC TABLES` returns.
- The same function in the WHERE clause didn't block incremental refresh. AUTO resolved to **ADAPTIVE** there,
  not INCREMENTAL.

## What each refresh did

100 new orders dated today, then one manual refresh per table
(`information_schema.dynamic_table_refresh_history()`):

| Table | refresh_action | deleted | inserted | copied | total time | of which compilation |
|---|---|---|---|---|---|---|
| DT_AUTO_SELECT_DATE | FULL | 50 | 50 | 0 | 0.67 s | 0.35 s |
| DT_AUTO_WHERE_DATE | INCREMENTAL | 43 | 43 | 7 | 2.00 s | 1.66 s |
| DT_ADAPTIVE | INCREMENTAL | 43 | 43 | 7 | 2.37 s | 2.22 s |

- The FULL table rewrote every row. The incremental ones rewrote only the 43 customers with new orders and copied
  the other 7.
- On 50 rows incremental was **slower**, and almost all of the difference is compilation; execution was about
  0.36–0.38 s for all three. Incremental pays off when the table is big and the change is small.

## Forcing INCREMENTAL fails at creation

The query from `DT_AUTO_SELECT_DATE` with `refresh_mode = incremental`:

```
SQL compilation error: line 4 at position 42:
Query contains the function 'CURRENT_DATE', but change tracking is not supported on queries with non-deterministic functions. …
```

That's the behavior you want: the mistake shows up when you deploy, not later in the refresh history.

## What I do now

- Set `refresh_mode` explicitly (`INCREMENTAL`, `ADAPTIVE` or `FULL`); Snowflake's docs recommend the same.
- Keep `current_date()` / `current_timestamp()` out of the SELECT list of an incremental dynamic table. In
  WHERE / HAVING / QUALIFY they're allowed.
- Read the CREATE status, and after creating a dynamic table check `refresh_mode` and `refresh_mode_reason` in `SHOW DYNAMIC TABLES`, and
  `refresh_action` in the refresh history.
- In dbt, the `dynamic_table` materialization in dbt-snowflake has the same `refresh_mode` config.

## Try it

[`run-logs/test-auto-refresh-mode.sql`](run-logs/test-auto-refresh-mode.sql): about 5 minutes on an X-Small
warehouse, its own database and warehouse, dropped at the end. Run it one step at a time; step 5 is expected to
fail. Values are random, so your row counts can differ slightly.

## Files in this folder

| File | What |
|---|---|
| `run-logs/test-auto-refresh-mode.sql` | the test script |
| `run-logs/results.md` | the raw outputs of my run: the CREATE status messages, SHOW DYNAMIC TABLES, refresh history with the statistics JSON, the compile error, cleanup |

## Go deeper

- [Dynamic table refresh modes](https://docs.snowflake.com/en/user-guide/dynamic-tables/refresh-modes): AUTO, INCREMENTAL, ADAPTIVE, FULL.
- [Supported queries](https://docs.snowflake.com/en/user-guide/dynamic-tables/supported-queries): which functions and constructs block incremental refresh.
- [CREATE DYNAMIC TABLE](https://docs.snowflake.com/en/sql-reference/sql/create-dynamic-table)
- [Dynamic tables in dbt-snowflake](https://docs.getdbt.com/reference/resource-configs/snowflake-configs#dynamic-tables)

*Tested on Snowflake 10.42.104, 24 Nov 2026.*

---

📣 LinkedIn post: 25 Nov 2026 · Previous: [dbt notes 01](../01-dbt-v2-caught-my-snowflake-error/)
