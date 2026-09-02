from qlineage.parser import parse_sql_graph


def test_cte_lineage():
    sql = """
    with orders as (
        select order_id from raw.shop.orders
    ), final as (
        select order_id from orders
    )
    select * from final
    """
    graph = parse_sql_graph(sql, dialect="snowflake", root_name="fct_orders")
    assert graph.upstream("fct_orders") == ["cte:final"]
    assert graph.upstream("cte:final") == ["cte:orders"]
    assert graph.upstream("cte:orders") == ["table:raw.shop.orders"]
    orders_sql = graph.nodes["cte:orders"].sql or ""
    assert "order_id" in orders_sql
    assert "raw.shop.orders" in orders_sql
    assert "stripe" not in orders_sql
    assert "select * from final" not in orders_sql.lower()
    final_sql = graph.nodes["cte:final"].sql or ""
    assert "from orders" in final_sql.lower()
    assert "raw.shop.orders" not in final_sql
    output_sql = graph.nodes["fct_orders"].sql or ""
    assert "select" in output_sql.lower()
    assert "from final" in output_sql.lower()
    assert "raw.shop.orders" not in output_sql


def test_node_columns_types_and_join_metadata():
    sql = """
    with orders as (
        select order_id, customer_id from raw.shop.orders
    ), payments as (
        select order_id, amount from raw.stripe.payments
    ), final as (
        select o.customer_id, sum(p.amount) as revenue, count(*) as n
        from orders o join payments p using (order_id)
        group by 1
    )
    select * from final
    """
    graph = parse_sql_graph(sql, dialect="snowflake", root_name="customer_revenue")

    final = graph.nodes["cte:final"]
    assert [(column.name, column.type) for column in final.columns] == [
        ("customer_id", "UNKNOWN"),
        ("revenue", "DECIMAL"),
        ("n", "BIGINT"),
    ]
    assert final.join_count == 1

    # Upstream CTEs record the key they are joined on downstream.
    assert graph.nodes["cte:orders"].join_keys == ("order_id",)
    assert graph.nodes["cte:payments"].join_keys == ("order_id",)

    # Source tables expose only the columns the query actually reads.
    source = graph.nodes["table:raw.stripe.payments"]
    assert [column.name for column in source.columns] == ["order_id", "amount"]

    edge = next(e for e in graph.edges if e.source == "cte:final" and e.target == "cte:payments")
    assert set(edge.columns) == {"amount", "order_id"}


def test_cast_type_inference():
    graph = parse_sql_graph(
        "select cast(created_at as date) as day from raw.events",
        dialect="snowflake",
        root_name="daily",
    )
    assert graph.nodes["daily"].columns[0].type == "DATE"


def test_dbt_ref_fallback():
    graph = parse_sql_graph(
        "select * from {{ ref('stg_orders') }}",
        dialect="snowflake",
        root_name="orders",
    )
    table_id = graph.upstream("orders")[0]
    assert graph.nodes[table_id].label == "ref:stg_orders"


def test_relation_label_mapping():
    graph = parse_sql_graph(
        "select * from analytics.staging.stg_orders",
        dialect="snowflake",
        root_name="orders",
        relation_labels={"analytics.staging.stg_orders": "ref:stg_orders"},
    )
    table_id = graph.upstream("orders")[0]
    assert graph.nodes[table_id].label == "ref:stg_orders"
