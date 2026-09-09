"""Outlet-level bias / factuality lookup.

Loads the hand-curated table in `newsfact/resources/outlet_bias.json` (see that
file's `_meta` block for provenance and caveats — it is a v2 approximation, not
a validated rating) and answers "what do we know about this domain?".

The fine-grained `bias` values (center-left / center-right / …) collapse to the
three coarse buckets the Bias/Blindspot Analyzer reports on via `coarse_side()`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

_COARSE = {
    "left": "left",
    "center-left": "left",
    "center": "center",
    "center-right": "right",
    "right": "right",
    "unknown": "unknown",
}


def coarse_side(bias: str) -> str:
    return _COARSE.get(bias, "unknown")


@dataclass(frozen=True)
class OutletRating:
    domain: str
    name: str
    bias: str          # fine-grained scale value
    factuality: str
    country: str

    @property
    def side(self) -> str:
        return coarse_side(self.bias)


_UNKNOWN_CACHE: dict[str, OutletRating] = {}


def _unknown(domain: str) -> OutletRating:
    return _UNKNOWN_CACHE.setdefault(
        domain, OutletRating(domain=domain, name=domain, bias="unknown", factuality="unknown", country="unknown")
    )


class BiasTable:
    def __init__(self, outlets: dict[str, dict[str, Any]]):
        self._outlets = {k.lower(): v for k, v in outlets.items()}

    @classmethod
    def load(cls, path: str | Path | None = None) -> "BiasTable":
        if path is not None:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        else:
            with resources.files("newsfact.resources").joinpath("outlet_bias.json").open(
                "r", encoding="utf-8"
            ) as fh:
                raw = json.load(fh)
        return cls(raw.get("outlets", {}))

    def __len__(self) -> int:
        return len(self._outlets)

    def items(self):
        """(domain, raw_row_dict) pairs — used by source identification to scan
        for a known outlet name appearing in an article's text."""
        return self._outlets.items()

    @staticmethod
    def _normalize(domain: str) -> str:
        d = (domain or "").strip().lower()
        if d.startswith("www."):
            d = d[4:]
        return d

    def lookup(self, domain: str) -> OutletRating:
        d = self._normalize(domain)
        row = self._outlets.get(d)
        if row is None and d.count(".") > 1:
            # try the registrable-ish parent (e.g. edition.cnn.com -> cnn.com)
            row = self._outlets.get(".".join(d.split(".")[-2:]))
        if row is None:
            return _unknown(d or "unknown")
        return OutletRating(
            domain=d,
            name=row.get("name", d),
            bias=row.get("bias", "unknown"),
            factuality=row.get("factuality", "unknown"),
            country=row.get("country", "unknown"),
        )
