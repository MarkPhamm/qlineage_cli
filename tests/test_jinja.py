from qlineage.jinja import display_name_for_placeholder, replace_dbt_refs


def test_replace_dbt_refs_and_sources():
    sql = "select * from {{ ref('orders') }} join {{ source('stripe', 'payments') }} using (id)"
    prepared = replace_dbt_refs(sql)
    assert "__dbt_ref__.orders" in prepared
    assert "__dbt_source__.stripe__payments" in prepared


def test_display_placeholder():
    assert display_name_for_placeholder("__dbt_ref__.orders") == "ref:orders"
    assert (
        display_name_for_placeholder("__dbt_source__.stripe__payments")
        == "source:stripe.payments"
    )
