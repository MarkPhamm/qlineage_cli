from qlineage.jinja import display_name_for_placeholder, replace_dbt_refs
from qlineage.parser import parse_sql_graph

MODEL_SQL = """{{
    config(
        materialized='table',
        unique_key='tv_display_spend_key',
        enabled=true
    )
}}

{%- set id_cols = ['transaction_on_est', 'ad_network', 'campaign_id'] %}

with ttd_display_pull as (
    select
        'tradedesk'::varchar(32) as ad_network,
        date(transaction_on_est) as transaction_on_est,
        campaign_id::varchar(64),
        sum(spend) as spend
    from {{ ref('tradedesk_spend') }}
    where inventory_channel = 'Display'
    {{ dbt_utils.group_by(n=3) }}
)

select
    {{ dbt_utils.generate_surrogate_key(id_cols) }} as tv_display_spend_key,
    *
from ttd_display_pull
"""


def test_replace_dbt_refs_and_sources():
    sql = "select * from {{ ref('orders') }} join {{ source('stripe', 'payments') }} using (id)"
    prepared = replace_dbt_refs(sql)
    assert "__dbt_ref__.orders" in prepared
    assert "__dbt_source__.stripe__payments" in prepared


def test_display_placeholder():
    assert display_name_for_placeholder("__dbt_ref__.orders") == "ref:orders"
    assert (
        display_name_for_placeholder("__dbt_source__.stripe__payments") == "source:stripe.payments"
    )


def test_config_with_nested_quotes_and_comments_are_dropped():
    sql = """{{ config(materialized='incremental', tags=['a', 'b']) }}
    {# only the comment goes away #}
    select id from {{ ref('orders') }} where id > (select max(id) from {{ this }})"""
    prepared = replace_dbt_refs(sql)
    assert "config" not in prepared
    assert "comment" not in prepared
    assert "__dbt_this__" in prepared
    assert display_name_for_placeholder("__dbt_this__") == "this"


def test_statement_tags_and_known_macros_expand():
    prepared = replace_dbt_refs(MODEL_SQL)
    assert "{%" not in prepared
    assert "{{" not in prepared
    assert "group by 1, 2, 3" in prepared
    assert "md5(concat_ws('-', transaction_on_est, ad_network, campaign_id))" in prepared


def test_model_with_statement_tags_parses():
    graph = parse_sql_graph(MODEL_SQL, dialect="snowflake", root_name="tv_display_spend")
    assert graph.upstream("tv_display_spend") == ["cte:ttd_display_pull"]
    assert graph.upstream("cte:ttd_display_pull") == ["table:__dbt_ref__.tradedesk_spend"]
    surrogate_inputs = graph.edges[-1].columns
    assert "transaction_on_est" in surrogate_inputs
    assert "campaign_id" in surrogate_inputs


def test_unknown_macro_kept_as_placeholder_in_expressions():
    sql = "select id, {{ audit_columns() }} from {{ ref('orders') }}"
    prepared = replace_dbt_refs(sql)
    assert "__dbt_jinja__" in prepared
    assert display_name_for_placeholder("__dbt_jinja__") == "unresolved jinja"
    graph = parse_sql_graph(prepared, dialect="snowflake", root_name="model")
    assert graph.upstream("model") == ["table:__dbt_ref__.orders"]


def test_unknown_clause_macro_is_dropped():
    sql = """select id, sum(spend) as spend
    from {{ ref('orders') }}
    where id is not null
    {{ my_grouping_macro() }}"""
    prepared = replace_dbt_refs(sql)
    assert "__dbt_jinja__" not in prepared
    graph = parse_sql_graph(prepared, dialect="snowflake", root_name="model")
    assert graph.upstream("model") == ["table:__dbt_ref__.orders"]


def test_star_and_incremental_block():
    sql = """select {{ dbt_utils.star(from=ref('orders')) }}
    from {{ ref('orders') }}
    {% if is_incremental() %}
    where updated_at > (select max(updated_at) from {{ this }})
    {% endif %}"""
    prepared = replace_dbt_refs(sql)
    assert "select *" in prepared
    assert "where updated_at" in prepared
