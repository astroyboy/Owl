from __future__ import annotations

import json

import pytest


def _print_response_debug(label: str, response) -> None:
    safe_headers = {
        key: ("<redacted>" if key.lower() in {
            "authorization",
            "cookie",
            "x-auth-token",
            "set-cookie",
        } else value)
        for key, value in response.request.headers.items()
    }
    print(f"\n--- {label} request ---")
    print(f"{response.request.method} {response.request.url}")
    print(f"Request headers: {safe_headers}")
    print(f"Request body: {response.request.content.decode('utf-8', errors='replace')}")
    print(f"--- {label} response ---")
    print(f"HTTP status: {response.status_code}")
    safe_response_headers = {
        key: ("<redacted>" if key.lower() in {"authorization", "set-cookie"} else value)
        for key, value in response.headers.items()
    }
    print(f"Response headers: {safe_response_headers}")
    print(f"Response body: {response.text}")


@pytest.mark.sungrow
def test_prints_ledger_integration_detail(sungrow_client) -> None:
    ledger_list_response = sungrow_client.post(
        "/monitor/register/ledger/page/list",
        json={"pageNum": 1, "pageSize": 1},
        headers={"X-AUTH-TENANT": "900002"},
    )
    _print_response_debug("ledger list", ledger_list_response)
    assert ledger_list_response.is_success, ledger_list_response.text

    ledger_list_body = ledger_list_response.json()
    assert ledger_list_body.get("code") == 200, (
        f"Ledger list business error: {json.dumps(ledger_list_body, ensure_ascii=False)}"
    )

    ledger_list = ledger_list_body.get("data", {}).get("list", [])
    if not ledger_list:
        pytest.fail("SUNGROW returned no ledger records")

    ledger_id = ledger_list[0].get("ledgerId")
    if ledger_id is None:
        pytest.fail("The first SUNGROW ledger record has no ledgerId")

    print(f"Using ledger_id={ledger_id}")

    response = sungrow_client.get(
        "/monitor/register/ledger/integration/detail",
        params={"ledgerId": ledger_id},
        headers={"X-AUTH-TENANT": "900002"},
    )

    _print_response_debug("ledger detail", response)
    assert response.is_success, response.text
    detail_body = response.json()
    print(json.dumps(detail_body, ensure_ascii=False, indent=2))
    assert detail_body.get("code") == 200, (
        f"Ledger detail business error: {json.dumps(detail_body, ensure_ascii=False)}"
    )
