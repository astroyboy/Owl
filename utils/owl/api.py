from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from owl.auth import Settings, SungrowAuthenticator

'''
 [
  {
    "tenantId": 900001,
    "tenantName": "总部园区",
    "tenantCode": "T2077217710983905281"
  },
  {
    "tenantId": 900002,
    "tenantName": "产业园区",
    "tenantCode": "T2077217710983905282"
  },
  {
    "tenantId": 900003,
    "tenantName": "阳光储能园区",
    "tenantCode": "T2077217710983905283"
  },
  {
    "tenantId": 900004,
    "tenantName": "阳光智源园区",
    "tenantCode": "T2084916314376122370"
  },
  {
    "tenantId": 900005,
    "tenantName": "阳光氢能园区",
    "tenantCode": "T2094596259345276929"
  },
  {
    "tenantId": 900006,
    "tenantName": "恒钧检测园区",
    "tenantCode": "T2094596295181410305"
  }
]
'''
def get_all_tenants(
    client: httpx.Client,
    *,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """Fetch, print, and return all tenants visible to the authenticated user."""
    page_num = 1
    tenants: list[dict[str, Any]] = []

    while True:
        response = client.post(
            "/security/tenant/page/list",
            json={"pageNum": page_num, "pageSize": page_size},
        )
        print("--- tenants ---")
        print(f"Request URL: {response.request.url}")
        print(f"HTTP status: {response.status_code}")
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 200:
            raise RuntimeError(
                f"Tenant list API returned an error: "
                f"{json.dumps(body, ensure_ascii=False)}"
            )

        data = body.get("data") or {}
        tenants.extend(data.get("list") or [])
        if not data.get("hasNextPage", False):
            break
        page_num += 1

    print(json.dumps(tenants, ensure_ascii=False, indent=2))
    print(f"Total tenants: {len(tenants)}")
    return tenants

'''
Request URL: https://ems.sungrow.cn/service/monitor/topology/foundery/consumption/category
HTTP status: 200
+----------------------------------+--------------+
| categoryCode                     | categoryName |
+----------------------------------+--------------+
| 918e6d6d3bd4424ca4314602581c23f3 | 建筑能耗用电  |
| df8ef9052ebf45ac8c685534089ccf08 | 生产能耗用电  |
| adb9756e593043cf9d9515d3c1557d8b | 能耗电费用电  |
| e8a353a305da489caad0b18d63fa2410 | 光储充用电    |
| 49607e0284dd44b7b2807e0d103fbc55 | 能耗地图     l|
| 2237304cb5684b76acd7cb4fdd0508e5 | 建筑公辅用电  |
| 53ec2fcbf76349f1b1bb7cdf5af45356 | 总部配电分析  |
| b90c9a4701b14bd5ae62a85ed77df80a | 用水         |
| ef7971547d044126ad3515e098c30681 | 用气         |
| 7ef5f051d8554f63830608bb089b577d | 公辅能效      |
| 3ac50793154e47af97b3a29a62abc449 | 公辅冷量      |
| c2858a18bf994855b28d4c2bab0b519e | 公辅用电      |
| c7b733ffdfd447e88ffb6af15a1fe670 | 公辅用气      |
+----------------------------------+--------------+
'''
def get_structure_categories(
    client: httpx.Client,
) -> list[dict[str, Any]]:
    """Fetch, print as a table, and return energy structure categories."""
    response = client.get(
        "/monitor/topology/foundery/consumption/category",
    )
    print("--- structure categories ---")
    print(f"Request URL: {response.request.url}")
    print(f"HTTP status: {response.status_code}")
    response.raise_for_status()

    body = response.json()
    if body.get("code") != 200:
        raise RuntimeError(
            f"Structure category API returned an error: "
            f"{json.dumps(body, ensure_ascii=False)}"
        )
    categories = body.get("data") or []

    code_header = "categoryCode"
    name_header = "categoryName"
    code_width = max(
        len(code_header),
        *(len(str(item.get("categoryCode", ""))) for item in categories),
    )
    name_width = max(
        len(name_header),
        *(len(str(item.get("categoryName", ""))) for item in categories),
    )
    separator = f"+-{'-' * code_width}-+-{'-' * name_width}-+"
    print(separator)
    print(f"| {code_header:<{code_width}} | {name_header:<{name_width}} |")
    print(separator)
    for item in categories:
        print(
            f"| {str(item.get('categoryCode', '')):<{code_width}} "
            f"| {str(item.get('categoryName', '')):<{name_width}} |"
        )
    print(separator)
    return categories


def _project_structure_nodes(
    nodes: list[dict[str, Any]],
) -> list[dict[str, dict[str, Any]]]:
    projected: list[dict[str, dict[str, Any]]] = []
    seen_meta_codes: set[str] = set()
    for node in nodes:
        meta_code = node.get("metaCode")
        if not isinstance(meta_code, str) or not meta_code:
            raise ValueError(f"Structure node has no valid metaCode: {node!r}")
        if meta_code in seen_meta_codes:
            raise ValueError(f"Duplicate metaCode in structure: {meta_code!r}")
        seen_meta_codes.add(meta_code)

        children = node.get("children") or []
        if not isinstance(children, list):
            raise ValueError(
                f"Unexpected children value for {meta_code!r}: {children!r}"
            )
        if any(not isinstance(child, dict) for child in children):
            raise ValueError(f"Unexpected child node under {meta_code!r}")

        projected.append(
            {
                meta_code: {
                    "metaName": node.get("metaName"),
                    "children": _project_structure_nodes(children),
                }
            }
        )
    return projected


def get_consumption_structure(
    client: httpx.Client,
    category: str,
) -> dict[str, dict[str, Any]]:
    """Fetch, print, and return the projected consumption topology tree."""
    response = client.get(
        "/monitor/topology/foundery/consumption/structure",
        params={"category": category},
    )
    print("--- consumption structure ---")
    print(f"Request URL: {response.request.url}")
    print(f"HTTP status: {response.status_code}")
    response.raise_for_status()

    body = response.json()
    if body.get("code") != 200:
        raise RuntimeError(
            f"Consumption structure API returned an error: "
            f"{json.dumps(body, ensure_ascii=False)}"
        )
    data = body.get("data") or []
    if not isinstance(data, list):
        raise ValueError(
            f"Expected structure data to be a list, got {type(data).__name__}"
        )

    if any(not isinstance(node, dict) for node in data):
        raise ValueError("Unexpected non-object node in consumption structure")
    projected_roots = _project_structure_nodes(data)
    structure = {
        meta_code: node
        for projected_root in projected_roots
        for meta_code, node in projected_root.items()
    }

    print(json.dumps(structure, ensure_ascii=False, indent=2))
    return structure


def get_structure_by_meta_name(
    structure: dict[str, dict[str, Any]],
    meta_name: str,
) -> dict[str, dict[str, Any]]:
    """Return matching nodes keyed by metaCode, retaining each matched subtree."""
    if not meta_name:
        raise ValueError("meta_name must not be empty")

    matches: dict[str, dict[str, Any]] = {}

    def collect(nodes: dict[str, dict[str, Any]]) -> None:
        for meta_code, node in nodes.items():
            if node.get("metaName") == meta_name:
                if meta_code in matches:
                    raise ValueError(
                        f"Duplicate metaCode while selecting structure: {meta_code!r}"
                    )
                matches[meta_code] = node
                continue

            children = node.get("children", [])
            if not isinstance(children, list):
                raise ValueError(
                    f"Unexpected children value for {meta_code!r}: {children!r}"
                )
            for child in children:
                if not isinstance(child, dict):
                    raise ValueError(f"Unexpected child node under {meta_code!r}")
                collect(child)

    collect(structure)
    return matches


def collect_leaf_nodes(
    nodes: dict[str, dict[str, Any]],
) -> list[tuple[str, str]]:
    """Return (metaCode, metaName) for every leaf of a projected structure."""
    leaves: list[tuple[str, str]] = []

    def visit(meta_code: str, node: dict[str, Any]) -> None:
        meta_name = node.get("metaName")
        if not isinstance(meta_name, str) or not meta_name:
            raise ValueError(f"Structure node {meta_code!r} has no metaName")

        children = node.get("children", [])
        if not isinstance(children, list):
            raise ValueError(f"Structure node {meta_code!r} has invalid children")
        if not children:
            leaves.append((meta_code, meta_name))
            return

        for child in children:
            if not isinstance(child, dict):
                raise ValueError(f"Structure node {meta_code!r} has an invalid child")
            for child_code, child_node in child.items():
                if not isinstance(child_node, dict):
                    raise ValueError(
                        f"Structure node {meta_code!r} has an invalid child node"
                    )
                visit(child_code, child_node)

    for meta_code, node in nodes.items():
        visit(meta_code, node)
    return leaves

def get_history_data(
    client: httpx.Client,
    *,
    device_code: str,
    start: str,
    end: str,
    interval: str = "1d-last",
    token: str | None = None,
    history_data: dict[str, Any] | None = None,
) -> Any:
    """Fetch SCADA history for one device. ``start``/``end``: ``YYYY-MM-DD HH:MM:SS``."""
    selected_token = token or client.headers.get("X-AUTH-TOKEN", "")
    for point_code in ["Eptp_1D", "P_RT"]:
        response = client.post(
            "https://ems.sungrow.cn/scada-service/private/history/query/sensitive",
            json={
                "deviceCode": device_code,
                "pointCode": point_code,
                "start": start,
                "end": end,
                "interval": interval,
            },
            headers={
                "Referer": "https://ems.sungrow.cn/scada",
                "X-ACCESS-TOKEN": selected_token,
                "X-AUTH-TOKEN": selected_token,
                "X-AUTH-UUID": os.getenv("SUNGROW_AUTH_UUID", ""),
            },
        )
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 200:
            raise RuntimeError(
                f"History API returned an error for {device_code!r}: "
                f"{json.dumps(body, ensure_ascii=False)}"
            )
        data = body.get("data")
        history_data[f"{data['deviceCode']}::{data['pointCode']}"] = list(data['dps'].values())
    return history_data


def main() -> dict[str, Any]:
    """Authenticate and run all read-only API helpers for manual debugging."""
    settings = Settings.from_env()
    token = SungrowAuthenticator(settings).login()
    category = os.getenv(
        "SUNGROW_METRIC_CATEGORY",
        "49607e0284dd44b7b2807e0d103fbc55",
    )
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://ems.sungrow.cn",
        "Referer": "https://ems.sungrow.cn/",
        "X-AUTH-CLIENT": "web",
        "X-AUTH-SCOPE": "",
        "X-AUTH-TOKEN": token,
        "X-LOCALE": "zh_CN",
        "Cookie": "locale=zh_CN",
    }

    with httpx.Client(
        base_url=settings.base_url,
        headers=headers,
        timeout=settings.timeout,
    ) as client:
        from owl.cache import get_cached_reference_data

        reference_data = get_cached_reference_data(
            client,
            category=category,
        )
        tenants = reference_data["tenants"]
        categories = reference_data["categories"]
        structure = reference_data["consumption_structure"]

    def print_structure_names(
        nodes: dict[str, dict[str, Any]],
        depth: int = 0,
    ) -> None:
        indentation = "\t" * depth
        for node in nodes.values():
            print(f"{indentation}{node.get('metaName', '')}")
            for child in node.get("children", []):
                print_structure_names(child, depth + 1)

    print("=== Consumption structure names ===")
    print_structure_names(structure)

    return {
        "tenants": tenants,
        "categories": categories,
        "consumption_structure": structure,
    }


if __name__ == "__main__":
    main()
