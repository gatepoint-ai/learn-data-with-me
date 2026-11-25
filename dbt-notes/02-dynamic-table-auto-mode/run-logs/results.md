# Run log: which refresh mode does AUTO pick?

- **Date:** 2026-11-24 (run at 20:14 UTC)
- **Snowflake version:** 10.42.104 (`select current_version()`)
- **Script:** `test-auto-refresh-mode.sql` in this folder, run unchanged, one step at a time, on my account with an
  X-Small warehouse. The script needed no changes: every column name it uses exists in this version.
- **Data:** 10,000 random orders for 50 customers, then 100 more orders dated today (step 4). Values are random,
  so row counts in another run can differ slightly.

## Step 2: CREATE output

The `status` each `create or replace dynamic table` returned, word for word (saved by the runner during the same
run; nothing was re-run):

| table | status returned by CREATE |
|---|---|
| DT_AUTO_SELECT_DATE | Dynamic table DT_AUTO_SELECT_DATE successfully created. FULL refresh mode was selected because: Query contains the function 'CURRENT_DATE', but change tracking is not supported on queries with non-deterministic functions. For more information, see https://docs.snowflake.com/user-guide/dynamic-tables-supported-queries#supported-non-deterministic-functions. |
| DT_AUTO_WHERE_DATE | Dynamic table DT_AUTO_WHERE_DATE successfully created. |
| DT_ADAPTIVE | Dynamic table DT_ADAPTIVE successfully created. |

The CREATE message names the FULL mode and the reason only when AUTO fell back to FULL. When AUTO chose ADAPTIVE,
the message says only that the table was created and doesn't name the mode.

## Step 3: what AUTO resolved to

Output of `show dynamic tables`, filtered to four columns:

| name | refresh_mode | refresh_mode_reason | rows |
|---|---|---|---|
| DT_ADAPTIVE | ADAPTIVE | *(null)* | 50 |
| DT_AUTO_SELECT_DATE | FULL | Query contains the function 'CURRENT_DATE', but change tracking is not supported on queries with non-deterministic functions. For more information, see https://docs.snowflake.com/user-guide/dynamic-tables-supported-queries#supported-non-deterministic-functions. | 50 |
| DT_AUTO_WHERE_DATE | ADAPTIVE | *(null)* | 50 |

## Step 4: what each refresh did

Output of `information_schema.dynamic_table_refresh_history()` after inserting 100 rows and running one manual refresh
per table. `ms` = `refresh_end_time - refresh_start_time`. The `statistics` JSON is the raw value, put on one line.

| name | refresh_trigger | refresh_action | state | statistics | ms |
|---|---|---|---|---|---|
| DT_ADAPTIVE | CREATION | INCREMENTAL | SUCCEEDED | `{"compilationTimeMs":446,"executionTimeMs":338,"numAddedPartitions":1,"numCopiedRows":0,"numDeletedRows":0,"numInsertedRows":50,"numRemovedPartitions":0,"queuedTimeMs":0}` | 747 |
| DT_ADAPTIVE | MANUAL | INCREMENTAL | SUCCEEDED | `{"compilationTimeMs":2218,"executionTimeMs":362,"numAddedPartitions":2,"numCopiedRows":7,"numDeletedRows":43,"numInsertedRows":43,"numRemovedPartitions":1,"queuedTimeMs":0}` | 2370 |
| DT_AUTO_SELECT_DATE | CREATION | FULL | SUCCEEDED | `{"compilationTimeMs":556,"executionTimeMs":393,"numAddedPartitions":1,"numCopiedRows":0,"numDeletedRows":0,"numInsertedRows":50,"numRemovedPartitions":0,"queuedTimeMs":0}` | 903 |
| DT_AUTO_SELECT_DATE | MANUAL | FULL | SUCCEEDED | `{"compilationTimeMs":351,"executionTimeMs":363,"numAddedPartitions":1,"numCopiedRows":0,"numDeletedRows":50,"numInsertedRows":50,"numRemovedPartitions":1,"queuedTimeMs":0}` | 673 |
| DT_AUTO_WHERE_DATE | CREATION | INCREMENTAL | SUCCEEDED | `{"compilationTimeMs":615,"executionTimeMs":413,"numAddedPartitions":1,"numCopiedRows":0,"numDeletedRows":0,"numInsertedRows":50,"numRemovedPartitions":0,"queuedTimeMs":0}` | 986 |
| DT_AUTO_WHERE_DATE | MANUAL | INCREMENTAL | SUCCEEDED | `{"compilationTimeMs":1659,"executionTimeMs":383,"numAddedPartitions":2,"numCopiedRows":7,"numDeletedRows":43,"numInsertedRows":43,"numRemovedPartitions":1,"queuedTimeMs":0}` | 2004 |

The `alter dynamic table ... refresh` statements also return a summary row each:

| table | statistics returned by ALTER ... REFRESH |
|---|---|
| DT_AUTO_SELECT_DATE | `{"insertedRows":50,"copiedRows":0,"deletedRows":50}` |
| DT_AUTO_WHERE_DATE | `{"insertedRows":43,"copiedRows":7,"deletedRows":43}` |
| DT_ADAPTIVE | `{"insertedRows":43,"copiedRows":7,"deletedRows":43}` |

## Step 5: forcing INCREMENTAL on query A (expected to fail)

```
SQL compilation error: line 4 at position 42:
Query contains the function 'CURRENT_DATE', but change tracking is not supported on queries with non-deterministic functions. For more information, see https://docs.snowflake.com/user-guide/dynamic-tables-supported-queries#supported-non-deterministic-functions.
```

Error code 91912, SQLSTATE `0A000` (feature not supported).

## Step 6: cleanup

Both statements succeeded. Afterwards `show databases like 'DT_TEST'` and `show warehouses like 'DT_TEST_WH'` returned
no rows: the test database and warehouse are gone.

## What the numbers show

1. **`CURRENT_DATE()` in the SELECT list:** AUTO chose **FULL**. It says so once, in the CREATE status message
   (step 2). After that, the place to see the mode and the reason is `SHOW DYNAMIC TABLES` (`refresh_mode`,
   `refresh_mode_reason`). Forcing INCREMENTAL on the same query fails at creation (step 5).
2. **`CURRENT_DATE()` only in the WHERE clause:** the same function didn't block incremental refresh. AUTO chose
   **ADAPTIVE**, not INCREMENTAL, and the refreshes ran as INCREMENTAL.
3. **The FULL table rewrote everything:** 50 rows deleted and 50 inserted for 100 new orders. The incremental tables
   touched only the 43 customers who had new orders and copied the other 7.
4. **On data this small, incremental was slower:** 2.0–2.4 s against 0.7 s for FULL. Almost all of the difference is
   compilation time (1.7–2.2 s against 0.35 s), not execution time (about 0.36–0.38 s for all three). Incremental
   pays off when the table is big and the change is small, not on 50 rows.
