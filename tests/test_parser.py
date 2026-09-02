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
