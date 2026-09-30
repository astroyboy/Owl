from __future__ import annotations

import json
import os
import time

import pytest

from owl.api import get_consumption_structure


def _category() -> str:
    return os.getenv(
        "SUNGROW_METRIC_CATEGORY",
        "49607e0284dd44b7b2807e0d103fbc55",   #能耗地图
    )


def _print_api_response(label: str, response, payload: dict | None = None) -> None:
    print(f"--- {label} ---")
    print(f"Request URL: {response.request.url}")
    if payload is not None:
        print(f"Request body: {json.dumps(payload, ensure_ascii=False)}")
    print(f"HTTP status: {response.status_code}")
    print("Response:")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))


@pytest.mark.skip(reason="This test is for debugging and printing API responses, not for automated testing.")
@pytest.mark.sungrow
def test_prints_scada_sensitive_history(sungrow_client, sungrow_token) -> None:
    tenant_id = os.getenv("SUNGROW_TENANT_ID", "900002")
    payload = {
        "deviceCode": os.getenv(
            "SUNGROW_DEVICE_CODE",
            "TD2_METE2076664110007668743",
        ),
        "pointCode": os.getenv("SUNGROW_POINT_CODE", "Eptp_1D"),
        "start": os.getenv("SUNGROW_HISTORY_START", "2026-09-17 16:31:36"),
        "end": os.getenv("SUNGROW_HISTORY_END", "2026-09-24 16:31:36"),
        "interval": os.getenv("SUNGROW_HISTORY_INTERVAL", "1h-last"),
    }
    response = sungrow_client.post(
        "https://ems.sungrow.cn/scada-service/private/history/query/sensitive",
        json=payload,
        headers={
            "Referer": "https://ems.sungrow.cn/scada",
            "X-ACCESS-TENANT": tenant_id,
            "X-ACCESS-TOKEN": sungrow_token,
            "X-AUTH-TENANT": tenant_id,
            "X-AUTH-TOKEN": sungrow_token,
            "X-AUTH-UUID": os.getenv("SUNGROW_AUTH_UUID", ""),
        },
    )
    _print_api_response("SCADA sensitive history", response, payload)
    response.raise_for_status()
    body = response.json()
    assert body.get("code") == 200, json.dumps(body, ensure_ascii=False)


@pytest.mark.skip(reason="This test is for debugging and printing API responses, not for automated testing.")
@pytest.mark.sungrow
def test_prints_metric_formula_results(sungrow_client) -> None:
    payload = {
        "category": _category(),
        "pageNum": 1,
        "pageSize": 100,
    }
    response = sungrow_client.post(
        "/monitor/topology/foundery/metric/result",
        json=payload,
        headers={"X-AUTH-TENANT": "900002"},
    )
    response.raise_for_status()
    body = response.json()
    assert body.get("code") == 200, json.dumps(body, ensure_ascii=False)

    data = body.get("data") or {}
    metrics = data.get("list", []) if isinstance(data, dict) else data
    code_header = "metaCode"
    name_header = "metaName"
    code_width = max(
        len(code_header),
        *(len(str(item.get("metaCode", ""))) for item in metrics),
    )
    name_width = max(
        len(name_header),
        *(len(str(item.get("metaName", ""))) for item in metrics),
    )
    separator = f"+-{'-' * code_width}-+-{'-' * name_width}-+"

    print(separator)
    print(f"| {code_header:<{code_width}} | {name_header:<{name_width}} |")
    print(separator)
    for item in metrics:
        print(
            f"| {str(item.get('metaCode', '')):<{code_width}} "
            f"| {str(item.get('metaName', '')):<{name_width}} |"
        )
    print(separator)

'''
--- vertical metric list ---
Request URL: https://ems.sungrow.cn/service/monitor/topology/vertical/foundery/metric/list
Request body: {"category": "49607e0284dd44b7b2807e0d103fbc55", "metaCode": "TD4_METE2092570319572914177"}
HTTP status: 200
Response:
{
  "code": 200,
  "message": "成功",
  "data": [
    {
      "category": "49607e0284dd44b7b2807e0d103fbc55",
      "metaCode": "TD4_METE2092570319572914177",
      "metaName": "M7组串1线",
      "metaType": "METE",
      "spaceCode": null,
      "spaceName": null,
      "metricCode": "Eptp",
      "metricUnit": "kWh",
      "scale": 1,
      "extensions": null,
      "evaluator": "3",
      "variables": null,
      "expression": "TD4_METE2075146610372931589_Eptp*1",
      "expressionTranslate": null,
      "remark": null
    }
  ]
}
'''
@pytest.mark.skip(reason="This test is for debugging and printing API responses, not for automated testing.")
@pytest.mark.sungrow
def test_prints_vertical_metric_list(sungrow_client) -> None:
    payload = {
        "category": _category(),
        "metaCode": os.getenv(
            "SUNGROW_METRIC_META_CODE",
            "TD4_METE2092570319572914177",
        ),
    }
    response = sungrow_client.post(
        "/monitor/topology/vertical/foundery/metric/list",
        json=payload,
        headers={"X-AUTH-TENANT": "900002"},
    )
    _print_api_response("vertical metric list", response, payload)
    response.raise_for_status()
    body = response.json()
    assert body.get("code") == 200, json.dumps(body, ensure_ascii=False)

'''
--- metric extension ---
Request URL: https://ems.sungrow.cn/service/monitor/topology/foundery/metric/extension?category=49607e0284dd44b7b2807e0d103fbc55
HTTP status: 200
Response:
{
  "code": 200,
  "message": "成功",
  "data": [
    {
      "title": "负荷",
      "value": "false",
      "code": "P_RT",
      "unit": null
    }
  ]
}
'''
@pytest.mark.skip(reason="This test is for debugging and printing API responses, not for automated testing.")
@pytest.mark.sungrow
def test_prints_metric_extension(sungrow_client) -> None:
    response = sungrow_client.get(
        "/monitor/topology/foundery/metric/extension",
        params={"category": _category()},
        headers={"X-AUTH-TENANT": "900002"},
    )
    _print_api_response("metric extension", response)
    response.raise_for_status()
    body = response.json()
    assert body.get("code") == 200, json.dumps(body, ensure_ascii=False)
