from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import httpx
import pytest


def _write_csv_report(
    report_path: Path,
    *,
    headers: tuple[str, ...],
    rows: list[tuple[str, ...]],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8-sig") as report_file:
        writer = csv.writer(report_file)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"CSV report: {report_path}")


def _post_security_list(
    client: httpx.Client,
    *,
    endpoint: str,
    tenant_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    headers = client.headers.copy()
    headers["X-AUTH-TENANT"] = tenant_id
    response = client.post(endpoint, json=payload, headers=headers)

    print(f"\nRequest URL: {response.request.url}")
    print(f"Request body: {response.request.content.decode('utf-8')}")
    print(f"HTTP status: {response.status_code}")
    response.raise_for_status()

    body = response.json()
    if not isinstance(body, dict):
        raise ValueError(f"Expected an object response from {endpoint}")
    print(f"API code: {body.get('code')}")
    print(f"API message: {body.get('message')}")
    if body.get("code") != 200:
        pytest.fail(
            f"API request failed: {json.dumps(body, ensure_ascii=False)}"
        )
    return body

@pytest.mark.skip(reason="This test is for debugging and printing API responses, not for automated testing.")
@pytest.mark.sungrow
def test_user_list(sungrow_client: httpx.Client, sungrow_tenant_id: str) -> None:
    endpoint = "/security/account/page/list"
    page_num = 1
    account_rows: list[tuple[str, str, str]] = []

    while True:
        body = _post_security_list(
            sungrow_client,
            endpoint=endpoint,
            tenant_id=sungrow_tenant_id,
            payload={
                "pageNum": page_num,
                "pageSize": 10,
                "accountName": "",
            },
        )
        data = body.get("data")
        print(f"Page {page_num} data: {json.dumps(data, ensure_ascii=False)}")
        if not isinstance(data, dict):
            raise ValueError(f"Expected paginated data from {endpoint}")
        page_accounts = data.get("list")
        if not isinstance(page_accounts, list):
            raise ValueError(f"Expected an account list on page {page_num}")
        if not page_accounts:
            break

        for account in page_accounts:
            if not isinstance(account, dict):
                raise ValueError(
                    f"Invalid account on page {page_num}: {account!r}"
                )
            account_roles = account.get("accountRoleDetailList", [])
            if not isinstance(account_roles, list):
                raise ValueError(
                    f"Invalid accountRoleDetailList on page {page_num}"
                )
            role_names = []
            for role in account_roles:
                if not isinstance(role, dict):
                    raise ValueError(
                        f"Invalid account role on page {page_num}: {role!r}"
                    )
                if "roleName" in role:
                    role_names.append(str(role["roleName"]))
            account_rows.append(
                (
                    str(account.get("accountName", "")),
                    str(account.get("organizationName", "")),
                    ", ".join(role_names),
                )
            )
        page_num += 1

    headers = ("accountName", "organizationName", "roleName")
    widths = (
        max(len(headers[0]), *(len(row[0]) for row in account_rows)),
        max(len(headers[1]), *(len(row[1]) for row in account_rows)),
        max(len(headers[2]), *(len(row[2]) for row in account_rows)),
    )
    separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    print("\nUser list")
    print(separator)
    print(
        "| "
        + " | ".join(
            header.ljust(width) for header, width in zip(headers, widths)
        )
        + " |"
    )
    print(separator)
    for account_name, organization_name, role_names in account_rows:
        print(
            "| "
            + " | ".join(
                value.ljust(width)
                for value, width in zip(
                    (account_name, organization_name, role_names), widths
                )
            )
            + " |"
        )
    print(separator)
    print(f"Total users: {len(account_rows)}")
    report_path = (
        Path(__file__).resolve().parents[1]
        / "test_logs"
        / "test_security"
        / "users.csv"
    )
    _write_csv_report(
        report_path,
        headers=headers,
        rows=account_rows,
    )


@pytest.mark.sungrow
def test_role_list(sungrow_client: httpx.Client, sungrow_tenant_id: str) -> None:
    endpoint = "/security/role/page/list"
    page_num = 1
    role_rows: list[tuple[str, str]] = []

    while True:
        body = _post_security_list(
            sungrow_client,
            endpoint=endpoint,
            tenant_id=sungrow_tenant_id,
            payload={
                "pageNum": page_num,
                "pageSize": 10,
                "roleName": "",
            },
        )
        data = body.get("data")
        if not isinstance(data, dict):
            raise ValueError(f"Expected paginated data from {endpoint}")
        page_roles = data.get("list")
        if not isinstance(page_roles, list):
            raise ValueError(f"Expected a role list on page {page_num}")
        if not page_roles:
            break
        print (f"Page {page_num} roles: {json.dumps(page_roles, ensure_ascii=False)}")
        for role in page_roles:
            if not isinstance(role, dict):
                raise ValueError(f"Invalid role on page {page_num}: {role!r}")
            menu_details = role.get("menuDetailList", [])
            if not isinstance(menu_details, list):
                raise ValueError(f"Invalid menuDetailList on page {page_num}")
            titles = []
            for menu in menu_details:
                if not isinstance(menu, dict):
                    raise ValueError(f"Invalid menu detail on page {page_num}")
                if "title" in menu:
                    titles.append(str(menu["title"]))
            role_rows.append(
                (
                    str(role.get("roleName", "")),
                    ", ".join(titles),
                )
            )
        page_num += 1

    headers = ("roleName", "FunctionList")
    widths = (
        max(len(headers[0]), *(len(row[0]) for row in role_rows)),
        max(len(headers[1]), *(len(row[1]) for row in role_rows)),
    )
    separator = f"+-{'-' * widths[0]}-+-{'-' * widths[1]}-+"
    print("\nRole list")
    print(separator)
    print(f"| {headers[0]:<{widths[0]}} | {headers[1]:<{widths[1]}} |")
    print(separator)
    for role_name, function_list in role_rows:
        print(
            f"| {role_name:<{widths[0]}} | "
            f"{function_list:<{widths[1]}} |"
        )
    print(separator)
    print(f"Total roles: {len(role_rows)}")
    report_path = (
        Path(__file__).resolve().parents[1]
        / "test_logs"
        / "test_security"
        / "roles.csv"
    )
    _write_csv_report(
        report_path,
        headers=headers,
        rows=role_rows,
    )
