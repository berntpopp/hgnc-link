"""``docs/configuration.md`` must document every settable environment variable.

README.md routes operators to that page with the claim "every ``HGNC_LINK_*``
variable", and the page repeats it. A hand-maintained table cannot honour that
claim for long: the six settings this test was written for (the ``MAX_DOWNLOAD_*``
caps, ``USER_AGENT``, the two cache knobs and ``RELOAD``) were added to
``config.py`` and never reached the docs, so an operator hardening a deployment
could not find the download caps that exist.

So the claim is machine-checked, in both directions: every field of
``ServerSettings`` (recursing into the nested ``DATA__`` / ``API__`` models) must
appear on the page, and every ``HGNC_LINK_*`` name on the page must be a real
setting. Properties (``db_path``, ``HgncApiConfig.user_agent``) are not fields and
are correctly absent.

Also guards the README's federation identity line: ``serverInfo.name`` is what the
router's registry resolves against, so a rotted README claim there is load-bearing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from hgnc_link.config import ServerSettings

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DOC = ROOT / "docs/configuration.md"
README = ROOT / "README.md"

ENV_PREFIX = "HGNC_LINK_"
NESTED_DELIMITER = "__"

#: A backticked env-var name in prose or a table cell: ``| `HGNC_LINK_PORT` | … |``.
_DOCUMENTED_VAR = re.compile(r"`(HGNC_LINK_[A-Z0-9_]+)`")


def _settable_env_vars(model: type[BaseModel], prefix: str = ENV_PREFIX) -> set[str]:
    """Every env var pydantic-settings will actually read, from the live model."""
    names: set[str] = set()
    for field_name, field in model.model_fields.items():
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            nested = f"{prefix}{field_name.upper()}{NESTED_DELIMITER}"
            names |= _settable_env_vars(annotation, nested)
        else:
            names.add(f"{prefix}{field_name.upper()}")
    return names


def _documented_env_vars() -> set[str]:
    return set(_DOCUMENTED_VAR.findall(CONFIG_DOC.read_text(encoding="utf-8")))


def test_configuration_doc_documents_every_setting() -> None:
    undocumented = _settable_env_vars(ServerSettings) - _documented_env_vars()
    assert not undocumented, (
        "settings exist but docs/configuration.md does not document them: "
        f"{sorted(undocumented)}. Add a row, or drop the page's exhaustiveness claim "
        "(and README.md's 'every HGNC_LINK_* variable') to a scoped one."
    )


def test_configuration_doc_has_no_phantom_settings() -> None:
    phantom = _documented_env_vars() - _settable_env_vars(ServerSettings)
    assert not phantom, (
        "docs/configuration.md documents variables that no longer exist in "
        f"ServerSettings: {sorted(phantom)}. Setting them would do nothing."
    )


def test_readme_states_the_real_server_name(facade: Any) -> None:
    assert facade.name == "hgnc-link"
    readme = README.read_text(encoding="utf-8")
    assert f"`serverInfo.name` is `{facade.name}`" in readme, (
        "README.md must state the serverInfo.name the facade actually advertises "
        f"({facade.name!r}); the router registry resolves backends against it."
    )
