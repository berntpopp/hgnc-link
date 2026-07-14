# Configuration

Every setting is an environment variable with the `HGNC_LINK_` prefix. Nested
config uses a **double underscore**, e.g. `HGNC_LINK_DATA__DB_FILENAME`. Copy
[`.env.example`](../.env.example) to `.env` to start; everything below is optional
and shown with the default that `hgnc_link/config.py` actually sets.

## Server

| Variable | Default | Purpose |
|----------|---------|---------|
| `HGNC_LINK_HOST` | `127.0.0.1` | Bind address. |
| `HGNC_LINK_PORT` | `8000` | Bind port (1024–65535). |
| `HGNC_LINK_TRANSPORT` | `unified` | `unified` \| `http` \| `stdio`. |
| `HGNC_LINK_MCP_PATH` | `/mcp` | MCP endpoint path. |
| `HGNC_LINK_ALLOWED_HOSTS` | `["localhost","127.0.0.1","::1"]` | JSON list of **exact** `Host` values admitted. |
| `HGNC_LINK_ALLOWED_ORIGINS` | `[]` | JSON list of **exact** browser `Origin` values admitted. |
| `HGNC_LINK_CORS_ORIGINS` | `["http://localhost:3000","http://127.0.0.1:3000"]` | JSON list of origins that receive CORS response headers. |
| `HGNC_LINK_LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` \| `CRITICAL`. |
| `HGNC_LINK_LOG_FORMAT` | `console` | `console` \| `json`. |

## Local data store

The bulk downloads are built into a SQLite index — see [Data](data.md).

| Variable | Default | Purpose |
|----------|---------|---------|
| `HGNC_LINK_DATA__DATA_DIR` | `./data` | Holds the built index and the download cache. |
| `HGNC_LINK_DATA__DB_FILENAME` | `hgnc.sqlite` | Index filename within `DATA_DIR`. |
| `HGNC_LINK_DATA__COMPLETE_SET_URL` | HGNC GCS bucket | `hgnc_complete_set.json` dump URL. |
| `HGNC_LINK_DATA__WITHDRAWN_URL` | HGNC GCS bucket | `withdrawn.txt` dump URL. |
| `HGNC_LINK_DATA__DOWNLOAD_TIMEOUT` | `180` | HTTP timeout (s) for a bulk download. |
| `HGNC_LINK_DATA__AUTO_BOOTSTRAP` | `true` | Build the index on first use if it is absent. |
| `HGNC_LINK_DATA__REFRESH_ENABLED` | `false` | In-process refresh scheduler (`unified`/`http` only). **Off by default — cron owns refresh** ([Deployment](deployment.md)). |
| `HGNC_LINK_DATA__REFRESH_INTERVAL_HOURS` | `24.0` | Interval for the in-process loop when enabled (1–720). |
| `HGNC_LINK_DATA__REFRESH_JITTER_SECONDS` | `300` | Random jitter per refresh, to avoid thundering herds. |
| `HGNC_LINK_DATA__BUILD_LOCK_TIMEOUT` | see `config.py` | Cross-process build-lock timeout (s). |

## Live REST client (`rest.genenames.org`)

> [!NOTE]
> The REST fallback is **reserved, not wired**. `enable_live_fallback` defaults to
> `false`, and no service method calls the REST client today — turning it on only
> constructs an unused client. The local index is the sole query path. Leave it off
> until the fallback is implemented.

| Variable | Default | Purpose |
|----------|---------|---------|
| `HGNC_LINK_API__ENABLE_LIVE_FALLBACK` | `false` | Reserved (see the note above). |
| `HGNC_LINK_API__BASE_URL` | `https://rest.genenames.org` | REST base URL. |
| `HGNC_LINK_API__CONTACT_EMAIL` | maintainer address | Embedded in the `User-Agent` (genenames.org etiquette). |
| `HGNC_LINK_API__TIMEOUT` | `30` | Per-request timeout (s), 1–120. |
| `HGNC_LINK_API__MAX_CONCURRENCY` | `5` | Max in-flight REST requests. **HGNC asks for ≤10 req/s** — do not raise this casually. |
| `HGNC_LINK_API__MAX_RETRIES` | `3` | Retries on transient 429/5xx/network failures. |

## The Host / Origin / CORS boundary

HTTP deployments enforce **exact** `Host` and `Origin` allowlists on every route.
Wildcards are not accepted. Three rules that are easy to get wrong:

1. **Add the public hostname.** `HGNC_LINK_ALLOWED_HOSTS` must contain the exact
   public reverse-proxy hostname *in addition to* the loopback defaults, or every
   proxied request is rejected.
2. **`HGNC_LINK_ALLOWED_ORIGINS` defaults to `[]`, which admits requests that carry
   no `Origin` header at all** — that is what lets non-browser MCP clients (Claude
   Code, `curl`) work out of the box. It does *not* mean "allow any origin".
3. **Request validation and CORS are separate policies, and neither widens the
   other.** A browser deployment must list its origin in **both**
   `HGNC_LINK_ALLOWED_ORIGINS` (admission) and `HGNC_LINK_CORS_ORIGINS` (response
   headers). Note their defaults differ: admission is empty, CORS ships with the
   two localhost:3000 dev origins.

## Transports

- **`unified`** (default) — FastAPI `/health` plus the MCP endpoint at `/mcp` on one
  port. `make dev`.
- **`http`** — HTTP transport without the unified REST host.
- **`stdio`** — `make mcp-serve` (`uv run python mcp_server.py`), used by Claude
  Desktop; see [`claude-desktop-config.json`](../claude-desktop-config.json). On stdio
  **stdout is reserved for the protocol** — logs go to stderr.

Register the HTTP server with Claude Code:

```bash
claude mcp add --transport http hgnc-link --scope user http://127.0.0.1:8000/mcp
```
