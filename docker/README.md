# Docker

```bash
make docker-build       # build the image
make docker-up          # start (prints the MCP URL + Claude Code command)
make docker-logs        # follow logs
make docker-down        # stop
```

The one-shot `hgnc-data-init` service restores the image's pinned, digest-verified
`data-hgnc-*` data release (a GitHub release of this repository) into the
`hgnc-data` volume and exits; the server then mounts that volume **read-only**.
Nothing is downloaded from HGNC at boot and there is no refresh service: a new
data release arrives with a reviewed re-pin and a new image. See
[`../docs/data.md`](../docs/data.md#data-releases-external-reference) and
[`../docs/deployment.md`](../docs/deployment.md#operator-steps-fleet-host).

## Ports

The host port defaults to `8000`; override with `HGNC_LINK_HOST_PORT` (e.g. in
`docker/.env`). MCP endpoint: `http://127.0.0.1:<port>/mcp`. Health:
`http://127.0.0.1:<port>/health`.
