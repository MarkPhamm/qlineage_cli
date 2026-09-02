# Contributing

Contributions are welcome.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check .
```

## Scope

The project is intentionally local-first. Features should not require warehouse credentials unless they are optional and clearly separated from the core CLI.

Good contributions include:

- Snowflake and Redshift parser edge cases
- dbt manifest compatibility
- better column-lineage rendering
- tests for real-world SQL patterns
- terminal UX and export formats
