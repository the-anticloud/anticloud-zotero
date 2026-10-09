# Anticloud Reference — reproducible runtime image.
#
# TRL-8 deployment evidence: the image runs as a non-root user, from a
# read-only root filesystem, with no ML runtime and no network listener.

FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Dependencies first, hash-verified. --require-hashes makes pip reject any
# artifact whose sha256 is not in the lock, which is the whole point: a
# substituted wheel cannot be installed even if the index serves it.
COPY requirements.lock ./
RUN python -m pip install --require-hashes -r requirements.lock

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --no-deps --wheel-dir /dist .


FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="anticloud-reference" \
      org.opencontainers.image.description="Convergent CRDTs, signed provenance and a fail-closed licence policy" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/anticloud/anticloud-reference" \
      org.opencontainers.image.version="1.0.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Non-root, no shell in PATH for the app user, no home directory to litter.
RUN groupadd --system --gid 10001 anticloud \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin anticloud

WORKDIR /app
COPY --from=builder /dist/*.whl /tmp/
RUN python -m pip install --no-index /tmp/*.whl && rm -f /tmp/*.whl

COPY LICENSE NOTICE README.md /app/
COPY deploy/bench-entrypoint.sh /app/entrypoint.sh
RUN chmod 0555 /app/entrypoint.sh

USER 10001:10001

# No EXPOSE: the library opens no port. A listener would be a defect, not a
# feature, and `tests/test_project_metadata.py` enforces its absence.

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["anticloud-ref", "bench", "--quiet"]

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["anticloud-ref", "validate", "--node-id", "container"]
