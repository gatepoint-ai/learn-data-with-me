-- Which refresh mode does a dynamic table get when you leave it on AUTO?
-- About 5 minutes on an XSMALL warehouse. Nothing refreshes on a schedule
-- (target_lag = downstream with no consumer), and step 6 drops everything.
-- Run it one step at a time in a Snowsight worksheet and keep each result.

-- 1. Setup
use role sysadmin;
create warehouse if not exists dt_test_wh
  warehouse_size = xsmall auto_suspend = 60 initially_suspended = true;
use warehouse dt_test_wh;
create database if not exists dt_test;
create schema if not exists dt_test.lab;
use schema dt_test.lab;

create or replace table orders (
  order_id int, customer_id int, amount number(10,2), order_date date
) change_tracking = true;

insert into orders
select seq4(), uniform(1, 50, random()), uniform(10, 500, random()),
       dateadd(day, -uniform(0, 30, random()), current_date())
from table(generator(rowcount => 10000));

-- 2. Three dynamic tables over the same source
-- A: AUTO, current_date() in the SELECT list
create or replace dynamic table dt_auto_select_date
  target_lag = downstream warehouse = dt_test_wh refresh_mode = auto
as
select customer_id, sum(amount) as total, current_date() as as_of
from orders group by customer_id;

-- B: AUTO, current_date() only in the WHERE clause
create or replace dynamic table dt_auto_where_date
  target_lag = downstream warehouse = dt_test_wh refresh_mode = auto
as
select customer_id, sum(amount) as total
from orders where order_date >= dateadd(day, -7, current_date())
group by customer_id;

-- C: ADAPTIVE, no date function
create or replace dynamic table dt_adaptive
  target_lag = downstream warehouse = dt_test_wh refresh_mode = adaptive
as
select customer_id, sum(amount) as total
from orders group by customer_id;

-- 3. What did AUTO resolve to, and why?   (screenshot or copy this result)
show dynamic tables in schema dt_test.lab;
select "name", "refresh_mode", "refresh_mode_reason", "rows"
from table(result_scan(last_query_id()));

-- 4. New rows, then one manual refresh each
insert into orders
select 100000 + seq4(), uniform(1, 50, random()), uniform(10, 500, random()), current_date()
from table(generator(rowcount => 100));

alter dynamic table dt_auto_select_date refresh;
alter dynamic table dt_auto_where_date refresh;
alter dynamic table dt_adaptive refresh;

-- What each refresh actually did   (screenshot or copy this result)
select name, refresh_trigger, refresh_action, state, statistics,
       datediff('millisecond', refresh_start_time, refresh_end_time) as ms
from table(information_schema.dynamic_table_refresh_history())
where name in ('DT_AUTO_SELECT_DATE', 'DT_AUTO_WHERE_DATE', 'DT_ADAPTIVE')
order by name, refresh_start_time;

-- 5. Force INCREMENTAL on the query from A. Expected to FAIL: copy the error message.
create or replace dynamic table dt_incr_select_date
  target_lag = downstream warehouse = dt_test_wh refresh_mode = incremental
as
select customer_id, sum(amount) as total, current_date() as as_of
from orders group by customer_id;

-- 6. Cleanup (run even if a step above failed)
drop database if exists dt_test;
drop warehouse if exists dt_test_wh;
