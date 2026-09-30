from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from owl.api import (
    get_all_tenants,
    get_consumption_structure,
    get_structure_categories,
)

CACHE_MAX_AGE = timedelta(days=3)
CACHE_SCHEMA_VERSION = 1
UTC = timezone.utc


def _cache_path(cache_dir: Path, tenant_id: str, category: str) -> Path:
    key = f"tenant_{quote(tenant_id, safe='')}_category_{quote(category, safe='')}"
    return cache_dir / f"{key}.json"


def _is_fresh(
    record: Any,
    *,
    tenant_id: str,
    category: str,
    now: datetime,
) -> bool:
    if not isinstance(record, dict):
        return False
    if (
        record.get("schema_version") != CACHE_SCHEMA_VERSION
        or record.get("tenant_id") != tenant_id
        or record.get("category") != category
    ):
        return False

    fetched_at = record.get("fetched_at")
    if not isinstance(fetched_at, str):
        return False
    try:
        timestamp = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if timestamp.tzinfo is None:
        return False

    data = record.get("data")
    return (
        now - timestamp.astimezone(UTC) < CACHE_MAX_AGE
        and isinstance(data, dict)
        and isinstance(data.get("tenants"), list)
        and isinstance(data.get("categories"), list)
        and isinstance(data.get("consumption_structure"), dict)
    )


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def get_cached_reference_data(
    client: httpx.Client,
    *,
    tenant_id: str,
    category: str,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    """Return cached tenant/category/structure data, refreshing it every 3 days."""
    selected_cache_dir = cache_dir or Path(
        os.getenv("OWL_CACHE_DIR", ".cache")
    )
    selected_cache_dir.mkdir(parents=True, exist_ok=True)
    latest_path = _cache_path(selected_cache_dir, tenant_id, category)
    now = datetime.now(UTC)

    if latest_path.exists():
        cache_text = latest_path.read_text(encoding="utf-8")
        try:
            previous_record = json.loads(cache_text)
        except json.JSONDecodeError:
            print(f"Cache file is invalid JSON and will be refreshed: {latest_path}")
        else:
            if _is_fresh(
                previous_record,
                tenant_id=tenant_id,
                category=category,
                now=now,
            ):
                print(f"Using cached reference data: {latest_path}")
                return previous_record["data"]
            print(f"Cached reference data is older than 3 days or invalid: {latest_path}")

    tenants = get_all_tenants(client, tenant_id=tenant_id)
    categories = get_structure_categories(client, tenant_id=tenant_id)
    structure = get_consumption_structure(
        client,
        category,
        tenant_id=tenant_id,
    )
    record = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "category": category,
        "fetched_at": now.isoformat(),
        "data": {
            "tenants": tenants,
            "categories": categories,
            "consumption_structure": structure,
        },
    }

    if latest_path.exists():
        archive_dir = selected_cache_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        timestamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
        archive_path = archive_dir / f"{latest_path.stem}_{timestamp}.json"
        shutil.copy2(latest_path, archive_path)
        print(f"Archived previous cache: {archive_path}")

    _atomic_write_json(latest_path, record)
    print(f"Saved refreshed reference data: {latest_path}")
    return record["data"]
