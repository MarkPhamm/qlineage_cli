with orders as (
    select order_id, customer_id from {{ ref('stg_orders') }}
),
payments as (
    select order_id, amount from {{ source('stripe', 'payments') }}
)
select o.customer_id, sum(p.amount) as revenue
from orders o
join payments p using (order_id)
group by 1
