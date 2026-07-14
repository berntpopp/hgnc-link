# Data & provenance

`hgnc-link` is a **bulk-download-backed** server. It serves every query from a local
SQLite index built from HGNC's public dumps; there are **no per-request REST
round-trips** on the hot path. That is the whole reason resolution is fast enough to
sit in front of other tools.

## Sources

| File | Contents |
|------|----------|
| `hgnc_complete_set.json` | Every approved HGNC record — symbols, names, aliases, previous symbols, cross-references. |
| `withdrawn.txt` | Retired HGNC IDs and their successors, so a withdrawn symbol redirects instead of 404-ing. |

Both are published by [genenames.org](https://www.genenames.org/) to a public Google
Cloud Storage bucket (`DEFAULT_COMPLETE_SET_URL` / `DEFAULT_WITHDRAWN_URL` in
`hgnc_link/config.py`; override with `HGNC_LINK_DATA__COMPLETE_SET_URL` /
`__WITHDRAWN_URL`). No API key, no authentication. The complete set is roughly 33 MB;
a full build takes seconds.

## Building the index

`make data` is a **mandatory** first step — the server has no data until it runs.

```bash
make data           # uv run hgnc-link-data build   — force download + full rebuild
make data-refresh   # uv run hgnc-link-data refresh — conditional; rebuild only on change
make data-status    # uv run hgnc-link-data status  — print the loaded release + provenance
```

The `hgnc-link-data` CLI is the only data entry point:

- **`build`** — unconditional download and rebuild. Use it once on install.
- **`refresh`** — the **cron entry point**. Issues a conditional GET
  (ETag / `Last-Modified`); an unchanged dump returns `304 Not Modified`, so it costs
  one cheap request and skips both the download and the rebuild.
- **`status`** — prints the loaded release, record counts and build provenance. The
  same facts are available over MCP from `get_hgnc_diagnostics` and over HTTP from
  `/health`.

Builds are **atomic** — the CLI writes a temp database and `os.replace`s it into
place, and a `fcntl` lock serializes concurrent builds. It is therefore safe to
refresh while the server is serving.

## Freshness

HGNC publishes new data on **Tuesdays and Fridays**. A daily conditional refresh is
the recommended cadence and is nearly free on unchanged days. Refresh is
**cron-driven**: the in-process scheduler (`HGNC_LINK_DATA__REFRESH_ENABLED`) is
**off by default** because cron is the observable mechanism. See
[Deployment](deployment.md) for a crontab line, a systemd timer, and the Docker path.

## The live REST client

`rest.genenames.org` is **not** on the query path. A REST client exists in
`hgnc_link/api/`, but `HGNC_LINK_API__ENABLE_LIVE_FALLBACK` defaults to `false` and no
service method calls it — the fallback is reserved for a future "index not yet built"
path and is not implemented today. Enabling it constructs an unused client. See
[Configuration](configuration.md).

Note that the REST API is also *field-scoped* (`/fetch/{field}/{value}`), which is
precisely the deficiency the local index removes: it makes the caller decide up front
whether a string is a current symbol, a previous symbol, an alias or an ID.

## Licence

HGNC data is released with **no usage restrictions** (effectively public domain /
CC0). Attribution is **requested but not required**. This is unusually permissive —
do not copy a restrictive licence stanza from a sibling `-link` repo onto it.

The `hgnc-link` **code** is [MIT](../LICENSE).

## Citation

Paste verbatim; also served as the `hgnc://citation` resource and as the
`recommended_citation` field on responses:

> Seal RL, Braschi B, Gray K, Jones TEM, Tweedie S, Haim-Vilmovsky L, Bruford EA.
> Genenames.org: the HGNC resources in 2023. *Nucleic Acids Res.*
> 2023;51(D1):D1003-D1009. doi:10.1093/nar/gkac888. RRID:SCR_002827.
