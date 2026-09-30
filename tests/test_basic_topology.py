from __future__ import annotations

import json
import os

import pytest


@pytest.mark.sungrow
def test_prints_structure_target_metrics(sungrow_client) -> None:
    category = os.getenv(
        "SUNGROW_METRIC_CATEGORY",
        "49607e0284dd44b7b2807e0d103fbc55",
    )
    print(f"Using category: {category}")

    response = sungrow_client.get(
        "/monitor/topology/foundery/structure/target/metric",
        params={"category": category},
        headers={"X-AUTH-TENANT": "900002"},
    )

    print(f"Request URL: {response.request.url}")
    print(f"HTTP status: {response.status_code}")
    print("Response:")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))

    response.raise_for_status()
    body = response.json()
    assert body.get("code") == 200, json.dumps(body, ensure_ascii=False)

    metrics = body.get("data") or []
    meta_code_header = "metaCode"
    meta_name_header = "metaName"
    meta_code_width = max(
        len(meta_code_header),
        *(len(str(item.get("metaCode", ""))) for item in metrics),
    )
    meta_name_width = max(
        len(meta_name_header),
        *(len(str(item.get("metaName", ""))) for item in metrics),
    )
    separator = f"+-{'-' * meta_code_width}-+-{'-' * meta_name_width}-+"
    print("--- metrics under selected category ---")
    print(separator)
    print(
        f"| {meta_code_header:<{meta_code_width}} "
        f"| {meta_name_header:<{meta_name_width}} |"
    )
    print(separator)
    for item in metrics:
        print(
            f"| {str(item.get('metaCode', '')):<{meta_code_width}} "
            f"| {str(item.get('metaName', '')):<{meta_name_width}} |"
        )
    print(separator)
