"""D1 (Tool-Schema Documentation v1.1): each tool's first sentence says what it returns.

ponytail: copied from genefoundry-router scripts/surface.py (lead_states_return); re-vendor
if the router's rule changes.
"""

from __future__ import annotations

import re
from typing import Any

_LEAD_VERBS = (  # noqa: SIM905 - kept identical to router surface.py
    "get fetch retrieve list look lookup search find resolve report read predict annotate "
    "compute calculate count summarize summarise map translate convert describe show check "
    "validate classify score rank query browse discover explain compare diff normalize normalise "
    "expand evaluate assess enumerate identify locate export download match suggest recommend "
    "inspect generate render estimate"
).split()
_VERB_LEAD = re.compile(
    rf"^(?:use this (?:tool )?to )?(?:{'|'.join(_LEAD_VERBS)})(?:s|es|ies)?\b", re.IGNORECASE
)
_RETURNS = re.compile(
    r"(?<!not )(?<!n't )(?<!n’t )(?<!never )\breturn(?:s|ed|ing)?\b(?!\s*[~<\d])|→|->",  # noqa: RUF001
    re.IGNORECASE,
)
_FIELD_LIST = re.compile(r"\w+\W+\w+[^:]*:\s+[^.;:]+,")
_SENTENCE_END = re.compile(r"(?<!e\.g\.)(?<!i\.e\.)(?<=[.!?])\s+")


def lead_states_return(description: str | None) -> bool:
    text = " ".join((description or "").split())
    lead = _SENTENCE_END.split(text, maxsplit=1)[0][:300]
    return bool(_VERB_LEAD.match(lead) or _RETURNS.search(lead) or _FIELD_LIST.search(lead))


async def test_every_description_lead_states_what_it_returns(facade: Any) -> None:
    failing = [t.name for t in await facade.list_tools() if not lead_states_return(t.description)]
    assert not failing, f"D1: first sentence must say what is returned: {failing}"
