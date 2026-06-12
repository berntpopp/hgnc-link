#!/usr/bin/env bash
# Build the local HGNC index before serving so the request path never triggers
# a lazy build, then start the server. Refresh is handled by cron (see
# docs/deployment.md), not the in-app scheduler.
set -euo pipefail

echo "[entrypoint] Ensuring the local HGNC index is built/refreshed..."
if hgnc-link-data refresh; then
    echo "[entrypoint] HGNC index ready."
else
    echo "[entrypoint] WARN: build/refresh failed; the server will lazy-bootstrap on first use."
fi

exec python server.py \
    --transport "${HGNC_LINK_TRANSPORT:-unified}" \
    --host "${HGNC_LINK_HOST:-0.0.0.0}" \
    --port "${HGNC_LINK_PORT:-8000}"
