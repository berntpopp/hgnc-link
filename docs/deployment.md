# Deployment & data refresh

`hgnc-link` serves from a **local SQLite index** built from the HGNC bulk dumps.
**Containers** (the fleet deploy) serve one pinned, digest-verified **data
release** restored at startup and never download from HGNC (see "Docker" below
and [Data](data.md#data-releases-external-reference)). The cron/systemd
`hgnc-link-data refresh` options below are for a **source checkout** (bare VM /
local) only. HGNC publishes new data Tuesdays and Fridays; a daily refresh is
cheap because an unchanged dump returns `304 Not Modified` (no re-download, no
rebuild).

## The refresh command

```bash
hgnc-link-data build     # force download + full rebuild (first install)
hgnc-link-data refresh   # conditional: rebuild ONLY if the dump changed (cron)
hgnc-link-data status    # print the loaded release + provenance
```

`refresh` downloads the complete set + withdrawn list with conditional GET, and
rebuilds the index atomically (temp file + `os.replace`) only on change. It is
safe to run concurrently with the server (a cross-process build lock serializes
builds; the server hot-reloads the swapped file).

## Option A — host crontab

```cron
# Refresh the HGNC index every day at 03:17. Logs to syslog.
17 3 * * *  cd /opt/hgnc-link && /opt/hgnc-link/.venv/bin/hgnc-link-data refresh >> /var/log/hgnc-link-refresh.log 2>&1
```

(With `uv`: `cd /opt/hgnc-link && uv run hgnc-link-data refresh`.)

## Option B — systemd timer (recommended for servers)

`/etc/systemd/system/hgnc-link-refresh.service`:

```ini
[Unit]
Description=Refresh the hgnc-link HGNC index
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=hgnc
WorkingDirectory=/opt/hgnc-link
Environment=HGNC_LINK_DATA__DATA_DIR=/var/lib/hgnc-link
ExecStart=/opt/hgnc-link/.venv/bin/hgnc-link-data refresh
```

`/etc/systemd/system/hgnc-link-refresh.timer`:

```ini
[Unit]
Description=Daily hgnc-link index refresh

[Timer]
OnCalendar=*-*-* 03:17:00
RandomizedDelaySec=600
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hgnc-link-refresh.timer
systemctl list-timers hgnc-link-refresh.timer
```

## Docker (pinned data release)

- A one-shot **`hgnc-data-init`** service runs `hgnc-link-data materialize-data`
  before the server starts. It downloads the image's pinned `data-hgnc-*` GitHub
  release asset of this repository (`github.com` /
  `release-assets.githubusercontent.com` only), verifies the compressed and
  expanded SHA-256 and the schema, writes `/data/<digest>/hgnc.sqlite`, and
  atomically points `/data/current` at it. A restart re-verifies the existing
  snapshot without downloading.
- The **server mounts the volume read-only** and serves
  `/data/current/hgnc.sqlite`; `/health` reports `release_identity.data_identity`
  (`expected` from the pin, `actual` re-proved from the served bytes). No in-app
  refresh, no upstream download, no `refresh` service.

### Operator steps (fleet host)

1. Pull the released image by digest and set `HGNC_LINK_IMAGE` as before.
2. `docker compose -f docker/docker-compose.npm.yml --env-file .env.docker up -d`.
   Compose starts `hgnc-data-init` first (outbound HTTPS to `github.com` and
   `release-assets.githubusercontent.com`), waits for exit `0`, then starts the
   server. No manual staging is required.
3. Verify: `docker compose -f docker/docker-compose.npm.yml logs hgnc-data-init`
   shows `Materialized HGNC data release data-hgnc-…`, and `/health`
   `release_identity` shows `expected == actual` with the tag/digest from
   `container-release.json`.
4. Optional cleanup: the old files in the existing `hgnc-data` volume
   (`hgnc.sqlite`, the dumps, `download_cache.json`, `.build.lock`) are no longer
   read and may be deleted; the restore writes only `<digest>/` and `current`.
5. Remove any host cron line that ran `docker compose ... run --rm refresh`; that
   service no longer exists.

## Fleet deploy contract (strato_v6_docker_npm)

`docker/docker-compose.npm.yml` is the overlay the fleet controller repo
(`strato_v6_docker_npm`) actually deploys and validates — it pulls the
released, attested `ghcr.io/berntpopp/hgnc-link` image at a pinned digest and
never builds from source. Every service in that file must declare a numeric
`user: "<uid>:<gid>"` (currently `999:999`, this image's own uid:gid from
`docker/Dockerfile`) because the controller's runtime observer proves the
effective uid from `/proc`. The release Compose files named in
`container-release.json` (`docker/docker-compose.yml`,
`docker/docker-compose.prod.yml`) must **not** declare `user` — the shared
release gate (`container_release.py validate-compose`) forbids it there.
`tests/unit/test_deploy_overlay_user.py` guards both rules.

Release checklist enforced by this repo: bump `pyproject.toml`, run `uv lock`,
add a `CHANGELOG.md` heading `## [x.y.z] - YYYY-MM-DD`, bump `CITATION.cff`
`version:` (generated file; `date-released` is regenerated externally by
`genefoundry-router`'s `make citation-write`, not by this repo's release),
tag `vx.y.z`, then approve the `release` environment gate:
`gh api repos/berntpopp/hgnc-link/actions/runs/<id>/pending_deployments`
(`status: waiting` marks the gate; may need approving twice).

Self-check that the overlay still projects cleanly for the fleet controller:

```bash
HGNC_LINK_IMAGE="ghcr.io/berntpopp/hgnc-link@sha256:<64 hex>" docker compose -f docker/docker-compose.npm.yml config --format json > /tmp/r.json
# from strato_v6_docker_npm:
uv run python -c "import sys,json; sys.path.insert(0,'scripts'); from utils.deployment_preflight import canonical_projection; canonical_projection(json.load(open('/tmp/r.json')), project='hgnc-link'); print('PROJECTION OK')"
```

## Verifying

```bash
hgnc-link-data status          # loaded release + counts
curl localhost:8000/health     # liveness + build provenance
# Through MCP: call get_hgnc_diagnostics
```
