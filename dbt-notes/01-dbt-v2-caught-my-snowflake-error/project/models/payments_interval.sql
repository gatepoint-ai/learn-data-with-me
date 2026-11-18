-- The version that broke on Snowflake.
-- DuckDB accepts "interval 3 day" with a bare number; Snowflake does not.
{{ config(materialized='incremental', unique_key='payment_id') }}

select payment_id, order_id, amount_cents, created_date
from {{ ref('payments') }}
{% if is_incremental() %}
where created_date >= (select max(created_date) - interval 3 day from {{ this }})
{% endif %}
