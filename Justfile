default:
    just --list

run:
    uv run python prototype/arco_prototype.py

lint:
    uv run ruff check prototype/

fmt:
    uv run ruff format prototype/

typecheck:
    uv run ty check prototype/

check:
    just lint && just fmt && just typecheck

hooks:
    uv run pre-commit install

pre-commit:
    uv run pre-commit run --all-files