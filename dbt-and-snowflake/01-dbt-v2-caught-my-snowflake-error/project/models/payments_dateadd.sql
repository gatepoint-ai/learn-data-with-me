-- The portable version: dbt.dateadd dispatches to each adapter's own date syntax.
{{ config(materialized='incremental', unique_key='payment_id') }}

select payment_id, order_id, amount_cents, created_date
from {{ ref('payments') }}
{% if is_incremental() %}
where created_date >= (select {{ dbt.dateadd('day', -3, 'max(created_date)') }} from {{ this }})
{% endif %}
