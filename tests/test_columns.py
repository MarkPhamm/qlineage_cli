from qlineage.columns import trace_column


def _names(node):
    yield node.name
    for child in node.children:
        yield from _names(child)


def test_column_lineage_reaches_physical_column():
    sql = """
    with payments as (
      select order_id, amount from raw.stripe.payments
    )
    select sum(amount) as revenue from payments
    """
    root = trace_column(sql, "revenue", dialect="snowflake")
    names = set(_names(root))
    assert "revenue" in names
    assert any("amount" in name for name in names)
