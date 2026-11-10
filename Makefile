.PHONY: contracts-install contracts-check contracts-test contracts-baseline

contracts-install:
	cd contracts && uv sync --locked && npm ci --ignore-scripts --no-audit --no-fund

contracts-check:
	cd contracts && uv run --locked python tools/cli.py

contracts-test:
	cd contracts && uv run --locked pytest -q

# Accept the current contracts (base + overlays must already pass contracts-check) as the new compatibility baseline.
contracts-baseline:
	cd contracts && uv run --locked python tools/cli.py verify-mirror validate-openapi validate-asyncapi validate-jsonschema lint-openapi && \
	rm -rf baseline.new && mkdir -p baseline.new && cp -R openapi asyncapi json-schema baseline.new/ && \
	rm -rf baseline && mv baseline.new baseline

.PHONY: backend-install backend-check backend-test

backend-install:
	cd backend && uv sync --locked

backend-check:
	cd backend && uv run --locked ruff check . && uv run --locked mypy && uv run --locked lint-imports

backend-test:
	cd backend && uv run --locked pytest -q
