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

.PHONY: infra-install infra-check infra-test infra-verify-digests

infra-install:
	cd infra && uv sync --locked

# Static policy checks on the rendered Compose model for every profile combination (no containers started).
infra-check:
	cd infra && uv run --locked ruff check . && \
	uv run --locked python scripts/check_compose.py -f compose.yaml && \
	uv run --locked python scripts/check_compose.py -f compose.yaml -f compose.dev.yaml && \
	uv run --locked python scripts/check_compose.py -f compose.yaml -f compose.test.yaml

infra-test:
	cd infra && uv run --locked pytest -q

# Network-dependent: every pinned digest must still match the registry.
infra-verify-digests:
	cd infra && uv run --locked python scripts/verify_digests.py

.PHONY: secrets-dev secrets-clean up down reset backend-audit infra-test-runtime
secrets-dev:
	cd infra && uv run --locked python scripts/secrets_dev.py init

secrets-clean:
	cd infra && uv run --locked python scripts/secrets_dev.py clean

COMPOSE := docker compose -f infra/compose.yaml -f infra/compose.dev.yaml
up: secrets-dev infra-check
	$(COMPOSE) up -d --build --remove-orphans
	cd infra && uv run --locked python scripts/wait_stack.py

# Stops the stack and removes containers and networks; named data volumes (Postgres, MinIO) are KEPT.
down:
	$(COMPOSE) down --remove-orphans

# DESTRUCTIVE (DOC-015 §15): also deletes the named data volumes of the local stack. Requires explicit confirmation: make reset CONFIRM=yes
reset:
	@test "$(CONFIRM)" = "yes" || { echo "reset deletes the local Postgres/MinIO volumes; run: make reset CONFIRM=yes"; exit 1; }
	$(COMPOSE) down --volumes --remove-orphans

# Dependency audit of the locked runtime set (ADR-037 layer 1). Network-dependent (vulnerability database).
backend-audit:
	cd backend && uv export --locked --no-dev --no-emit-project --format requirements-txt | uvx pip-audit@2.10.1 -r /dev/stdin --disable-pip --no-deps

# Live-stack evidence (needs `make up`); skipped tests are NOT evidence.
infra-test-runtime:
	cd infra && AI_RES_REQUIRE_STACK=1 uv run --locked pytest tests/runtime -q -rs
