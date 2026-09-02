with orders as (
    select order_id, customer_id
    from raw.shop.orders
),
payments as (
    select order_id, amount
    from raw.stripe.payments
),
final as (
    select
        o.customer_id,
        sum(p.amount) as revenue
    from orders o
    join payments p using (order_id)
    group by 1
)
select * from final
