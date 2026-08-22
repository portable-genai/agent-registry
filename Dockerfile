# A3 Agent Registry & Governance — container image for Cloud Run.
#
# Two stages. The builder carries the build toolchain (git, needed only while pip resolves the
# git+https commons pin) and produces a self-contained virtualenv at /opt/venv. The runtime
# stage starts from the same digest-pinned slim base, copies only that virtualenv plus the
# application source, runs as a dedicated non-root uid and carries no build toolchain.
#
# The image selects the SECURE profile explicitly (HRZ_REGISTRY_PROFILE=gcp): a shipped image
# must not fall back to the no-auth SQLite laptop profile if the deployment forgets an env var.
# The offline 'local' profile is a developer/test convention, driven from the Makefile.

FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

# Locked, reproducible install: the committed lockfile pins every transitive dep; the package
# itself installs with --no-deps so the lock stays authoritative (matches CI and pip-audit).
COPY pyproject.toml README.md ./
COPY requirements-gcp.lock ./
COPY src ./src
COPY config ./config

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && python -m venv "$VIRTUAL_ENV" \
 && pip install -r requirements-gcp.lock \
 && pip install --no-deps . \
 && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------------------- #
# Runtime stage: slim base, virtualenv only, no compiler and no git.
# --------------------------------------------------------------------------------------- #
FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PORT=8083 \
    HRZ_REGISTRY_PROFILE=gcp

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
# Source and config are copied verbatim as well: the package resolves settings.yaml relative
# to the repo layout, so /app keeps the same shape the builder saw.
COPY src ./src
COPY config ./config

# Drop privileges: dedicated non-root uid/gid 10001 (not a recycled system id).
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid 10001 --home-dir /app app \
 && chown -R 10001:10001 /app
USER 10001

EXPOSE 8083

# Liveness: the API's own /healthz, hit over loopback with the interpreter already in the
# image (no curl/wget added to the runtime stage just to probe).
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8083')+'/healthz', timeout=2).status == 200 else 1)"]

# Cloud Run sets $PORT; default to 8083 to match C1's HRZ_REGISTRY_URL default.
CMD ["sh", "-c", "exec uvicorn agent_registry.api.app:app --host 0.0.0.0 --port ${PORT:-8083}"]
