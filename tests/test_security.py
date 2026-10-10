from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from owl.menu_reporter import export_overall_menu_csv
import re


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
    #tenant_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    headers = client.headers.copy()
    #headers["X-AUTH-TENANT"] = tenant_id
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
            #tenant_id=sungrow_tenant_id,
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
def test_role_list(
    sungrow_client: httpx.Client,
) -> None:
    """Fetch all roles and export one overall menu permission report."""

    endpoint = "/security/role/page/list"
    endpoint_detail = "/security/role/menu/tree"

    page_num = 1
    page_size = 10

    # Store each role's menu tree, keyed by role name.
    menus_by_role: dict[str, list[dict]] = {}

    while True:
        # Fetch one page of roles.
        body = _post_security_list(
            sungrow_client,
            endpoint=endpoint,
            payload={
                "pageNum": page_num,
                "pageSize": page_size,
                "roleName": "",
            },
        )

        data = body.get("data")
        if not isinstance(data, dict):
            raise ValueError(
                f"Expected paginated data from {endpoint}, "
                f"page {page_num}"
            )

        page_roles = data.get("list")
        if not isinstance(page_roles, list):
            raise ValueError(
                f"Expected role list on page {page_num}"
            )

        # No more roles: finish pagination.
        if not page_roles:
            break

        print(
            f"[Owl] Processing page {page_num}, "
            f"roles: {len(page_roles)}"
        )

        for role in page_roles:
            if not isinstance(role, dict):
                raise ValueError(
                    f"Invalid role on page {page_num}: {role!r}"
                )

            role_id = role.get("roleId", "")
            role_name = str(role.get("roleName", "")).strip()

            if not role_id:
                raise ValueError(
                    f"Missing roleId for role {role_name!r}"
                )

            if not role_name:
                raise ValueError(
                    f"Missing roleName for roleId {role_id!r}"
                )

            if role_name in menus_by_role:
                raise ValueError(
                    f"Duplicate roleName encountered: {role_name!r}"
                )

            # Fetch this role's menu tree.
            role_details = _post_security_list(
                sungrow_client,
                endpoint=endpoint_detail,
                payload={"roleId": role_id},
            )

            menus = role_details.get("data")
            if not isinstance(menus, list):
                raise ValueError(
                    f"Expected menu tree list for role "
                    f"{role_name!r}, got {type(menus).__name__}"
                )

            # Keep the complete tree for the overall comparison.
            menus_by_role[role_name] = menus

            print(
                f"[Owl] Retrieved menu tree for role: "
                f"{role_name}"
            )

        page_num += 1

    if not menus_by_role:
        raise ValueError("No roles were retrieved; no report generated.")

    # Generate one overall CSV after all roles have been collected.
    report_path = (
            Path(__file__).resolve().parents[1]
            / "test_logs"
            / "test_security"
            / "test_role_list"
        )
    report_path.mkdir(parents=True, exist_ok=True)
    output_file = report_path / "overall_menu_comparison.csv"

    export_overall_menu_csv(
        menus_by_role,
        output_file=output_file,
    )

    print(
        f"[Owl] Completed. Retrieved {len(menus_by_role)} roles. "
        f"Overall report: {output_file}"
    )