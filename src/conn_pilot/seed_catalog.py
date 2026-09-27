from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SeedCatalog:
    """Versioned, searchable inventory of built-in CONN seed regions."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "conn_pilot_seed_catalog_v1":
            raise ValueError(f"Unsupported seed catalog schema: {self.path}")
        seeds = payload.get("seeds")
        if not isinstance(seeds, list) or not seeds:
            raise ValueError(f"Seed catalog is empty: {self.path}")
        self.metadata = {key: value for key, value in payload.items() if key != "seeds"}
        self.seeds = tuple(seeds)
        self.by_id = {str(item["id"]): item for item in self.seeds}
        if len(self.by_id) != len(self.seeds):
            raise ValueError(f"Seed catalog contains duplicate ids: {self.path}")

    def resolve(self, seed_ids: list[str]) -> list[dict[str, Any]]:
        selected = list(dict.fromkeys(str(value) for value in seed_ids))
        unknown = sorted(set(selected) - set(self.by_id))
        if unknown:
            raise ValueError(f"Unknown seed_ids: {', '.join(unknown)}")
        return [dict(self.by_id[value]) for value in selected]

    def search(
        self,
        *,
        query: str | None = None,
        collection: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        if not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be zero or greater")
        normalized_collection = collection.strip().lower() if collection else None
        collections = set(self.metadata.get("collections", {}))
        if normalized_collection and normalized_collection not in collections:
            raise ValueError(
                "Unknown seed collection: " + normalized_collection
                + ". Available: " + ", ".join(sorted(collections))
            )
        terms = query.casefold().split() if query and query.strip() else []
        matches = []
        for seed in self.seeds:
            if normalized_collection and seed["collection"] != normalized_collection:
                continue
            haystack = " ".join(
                str(seed.get(field, ""))
                for field in ("id", "label", "description", "collection")
            ).casefold()
            if terms and not all(term in haystack for term in terms):
                continue
            matches.append(seed)
        page = matches[offset : offset + limit]
        return {
            "catalog_version": self.metadata.get("catalog_version"),
            "conn_version": self.metadata.get("conn_version"),
            "collections": self.metadata.get("collections", {}),
            "query": query,
            "collection": normalized_collection,
            "total_count": len(matches),
            "offset": offset,
            "returned_count": len(page),
            "has_more": offset + len(page) < len(matches),
            "seeds": [dict(item) for item in page],
        }
