"""Configuration management for hgnc-link.

Settings load from environment variables with the ``HGNC_LINK_`` prefix (nested
models use ``__``, e.g. ``HGNC_LINK_DATA__DB_FILENAME=hgnc.sqlite`` or
``HGNC_LINK_API__TIMEOUT=45``) and an optional ``.env`` file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hgnc_link import __version__

# Project root: <repo>/hgnc_link/config.py -> <repo>
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATA_DIR = _PROJECT_ROOT / "data"

# HGNC publishes the complete set + withdrawn list to a public GCS bucket.
# Note the doubled path segments (json/json, tsv/tsv) are correct, not typos.
_GCS = "https://storage.googleapis.com/public-download-files/hgnc"
DEFAULT_COMPLETE_SET_URL = f"{_GCS}/json/json/hgnc_complete_set.json"
DEFAULT_WITHDRAWN_URL = f"{_GCS}/tsv/tsv/withdrawn.txt"
DEFAULT_REST_BASE_URL = "https://rest.genenames.org"


class HgncDataConfig(BaseModel):
    """Local data store: bulk downloads -> built SQLite index."""

    data_dir: Path = Field(
        default=_DEFAULT_DATA_DIR,
        description="Directory holding the built SQLite database and download cache.",
    )
    db_filename: str = Field(
        default="hgnc.sqlite",
        description="SQLite database filename within data_dir.",
    )
    complete_set_url: str = Field(
        default=DEFAULT_COMPLETE_SET_URL,
        description="URL of the HGNC complete-set JSON dump.",
    )
    withdrawn_url: str = Field(
        default=DEFAULT_WITHDRAWN_URL,
        description="URL of the HGNC withdrawn.txt dump.",
    )
    download_timeout: int = Field(
        default=180,
        ge=5,
        le=900,
        description="HTTP timeout (seconds) for downloading the bulk HGNC dumps.",
    )
    max_download_bytes: int = Field(
        default=128 << 20,
        gt=0,
        description=(
            "Maximum bulk artifact size; measured below 64 MiB on 2026-07-10. "
            "Override for a larger approved HGNC export."
        ),
    )
    max_download_seconds: float = Field(
        default=900.0,
        gt=0,
        description=(
            "Maximum total bulk transfer time; measured below 450 seconds on 2026-07-10. "
            "Override for slower approved links."
        ),
    )
    user_agent: str = Field(
        default=f"hgnc-link/{__version__} (+https://github.com/berntpopp/hgnc-link)",
        description="User-Agent sent to genenames.org / GCS.",
    )
    auto_bootstrap: bool = Field(
        default=True,
        description="Build the database on first use by downloading the dumps if absent.",
    )
    refresh_enabled: bool = Field(
        default=False,
        description=(
            "Run an in-process scheduler (unified/http transports only) that "
            "conditionally refreshes the database on an interval. Default OFF: HGNC "
            "data is best refreshed by an external cron job (see docs/deployment.md)."
        ),
    )
    refresh_interval_hours: float = Field(
        default=24.0,
        ge=1.0,
        le=720.0,
        description=(
            "Hours between conditional refresh checks (when refresh_enabled). HGNC "
            "updates Tue/Fri; a daily check is cheap because unchanged dumps 304."
        ),
    )
    refresh_jitter_seconds: int = Field(
        default=300,
        ge=0,
        le=86400,
        description="Random jitter added to each refresh to avoid thundering herds.",
    )
    build_lock_timeout: int = Field(
        default=600,
        ge=1,
        le=3600,
        description="Seconds to wait for the cross-process build lock before giving up.",
    )
    cache_size: int = Field(
        default=1024,
        ge=0,
        le=65536,
        description="Max entries in the in-process query cache (0 disables).",
    )
    cache_ttl: int = Field(
        default=3600,
        ge=0,
        le=86400,
        description="Query cache TTL in seconds.",
    )

    @property
    def db_path(self) -> Path:
        """Absolute path to the SQLite database file."""
        return self.data_dir / self.db_filename

    @field_validator("data_dir")
    @classmethod
    def _expand_data_dir(cls, v: Path) -> Path:
        return Path(v).expanduser()


class HgncApiConfig(BaseModel):
    """Optional live REST fallback (rest.genenames.org)."""

    base_url: str = Field(
        default=DEFAULT_REST_BASE_URL,
        description="HGNC REST API base URL.",
    )
    contact_email: str = Field(
        default="bernt.popp@charite.de",
        description="Contact email embedded in the User-Agent for the REST API.",
    )
    timeout: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Per-request timeout (seconds) for the REST API.",
    )
    max_concurrency: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Max concurrent in-flight REST requests (HGNC asks for <=10 req/s).",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=6,
        description="Retry attempts for transient (429/5xx/network) REST failures.",
    )
    enable_live_fallback: bool = Field(
        default=False,
        description=(
            "Reserved for a live REST fallback when the local DB is unavailable "
            "(e.g. before the first build completes). Default OFF: the fallback is "
            "NOT yet wired into any tool (no service method calls the REST client), "
            "so enabling it only constructs an unused client. Keep OFF until the "
            "fallback path is implemented (see HgncService follow-up note)."
        ),
    )

    @property
    def user_agent(self) -> str:
        """User-Agent string with a contact mailbox, per HGNC etiquette."""
        return f"hgnc-link/{__version__} (mailto:{self.contact_email})"

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        """Normalise the endpoint URL (no trailing slash)."""
        return v.rstrip("/")


class ServerSettings(BaseSettings):
    """Top-level server settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="HGNC_LINK_",
        env_nested_delimiter="__",
    )

    host: str = Field(default="127.0.0.1", description="Server host.")
    port: int = Field(default=8000, ge=1024, le=65535, description="Server port.")
    reload: bool = Field(default=False, description="Enable auto-reload in development.")

    transport: Literal["unified", "http", "stdio"] = Field(
        default="unified",
        description="Server transport mode.",
    )
    mcp_path: str = Field(default="/mcp", description="MCP endpoint path.")
    allowed_hosts: list[str] = Field(
        default=["localhost", "127.0.0.1", "::1"],
        description="Exact Host header values accepted by the request guard.",
    )
    allowed_origins: list[str] = Field(
        default=[],
        description="Browser Origin values accepted by the request guard.",
    )

    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins.",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level.",
    )
    log_format: Literal["json", "console"] = Field(
        default="console",
        description="Log format.",
    )

    data: HgncDataConfig = Field(
        default_factory=HgncDataConfig,
        description="Local data store configuration.",
    )
    api: HgncApiConfig = Field(
        default_factory=HgncApiConfig,
        description="Live REST fallback configuration.",
    )

    @field_validator("mcp_path")
    @classmethod
    def validate_mcp_path(cls, v: str) -> str:
        """Ensure the MCP path starts with a forward slash."""
        return v if v.startswith("/") else f"/{v}"

    @field_validator("allowed_hosts", "allowed_origins", "cors_origins", mode="before")
    @classmethod
    def parse_string_list(cls, v: Any) -> list[str]:
        """Parse string lists from a comma-separated value or list."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return list(v) if v else []

    @field_validator("allowed_hosts", "allowed_origins")
    @classmethod
    def reject_wildcard_pattern(cls, v: list[str]) -> list[str]:
        """Require exact values; FastMCP otherwise interprets glob patterns."""
        if any(any(marker in value for marker in "*?[]") for value in v):
            raise ValueError("wildcard patterns are not allowed in security allowlists")
        return v


settings = ServerSettings()


def get_data_config() -> HgncDataConfig:
    """Return the active data-store configuration (used by the ingest CLI)."""
    return settings.data
