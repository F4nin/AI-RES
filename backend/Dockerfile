# AI RES backend image (S03). Pinned bases, lockfile-only install, non-root, no secrets in layers.
FROM ghcr.io/astral-sh/uv:0.11.0@sha256:e49fde5daf002023f0a2e2643861ce9ca8a8da5b73d0e6db83ef82ff99969baf AS uv

FROM python:3.13.18-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.13.18-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72 AS runtime
RUN groupadd --gid 10001 aires && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin aires \
 # No package installer at runtime: pip/setuptools of the base image vendor libraries (msgpack, urllib3, ...) flagged by the image scan, and nothing needs them.
 && rm -rf /usr/local/lib/python3.13/site-packages/pip* /usr/local/lib/python3.13/site-packages/setuptools* \
           /usr/local/lib/python3.13/site-packages/pkg_resources /usr/local/lib/python3.13/site-packages/wheel* /usr/local/bin/pip*
COPY --from=build /app/.venv /app/.venv
COPY alembic.ini /app/alembic.ini
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
USER 10001:10001
EXPOSE 8000
# The one-shot `migrate` Compose service runs `alembic upgrade head` from this same image; API startup never migrates (Blueprint §4.1).
# serve.py runs uvicorn with log_config=None so that redacting logging (platform.redaction) stays in force (ADR-037).
CMD ["python", "-m", "ai_res.api.serve"]
