# Deployment & data refresh (cron)

`hgnc-link` serves from a **local SQLite index** built from the HGNC bulk dumps.
For speed there are no per-request REST calls — instead the index is kept fresh
by a **cron job** that runs the `hgnc-link-data refresh` CLI. HGNC publishes new
data Tuesdays and Fridays; a daily refresh is cheap because an unchanged dump
returns `304 Not Modified` (no re-download, no rebuild).

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

## Option C — Docker

The container entrypoint builds the index on first start; the named volume
persists it across restarts. Refresh the running container from host cron:

```cron
17 3 * * *  docker compose -f /opt/hgnc-link/docker/docker-compose.yml run --rm refresh
```

(The `refresh` service in `docker-compose.yml` is under the `tools` profile, so
it never starts with `docker compose up` — only when invoked explicitly.)

## In-process scheduler (alternative to cron)

If you cannot use cron, set `HGNC_LINK_DATA__REFRESH_ENABLED=true` and the server
runs an internal daily conditional refresh (unified/http transports only). It is
**off by default** because cron is the recommended, observable mechanism.

## Verifying

```bash
hgnc-link-data status          # loaded release + counts
curl localhost:8000/health     # liveness + build provenance
# Through MCP: call get_hgnc_diagnostics
```
