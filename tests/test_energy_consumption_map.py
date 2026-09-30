from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

logger = logging.getLogger(__name__)


def _power_statistics_payload(
    structure: dict[str, dict[str, Any]],
    tenants: list[dict[str, Any]],
) -> list[tuple[str, dict[str, str]]]:
    tenant_name_aliases = {"储能南区": "阳光储能园区"}
    tenant_by_name: dict[str, dict[str, Any]] = {}
    for tenant in tenants:
        tenant_name = tenant.get("tenantName")
        if isinstance(tenant_name, str) and tenant_name:
            tenant_by_name[tenant_name] = tenant

    payloads: list[tuple[str, dict[str, str]]] = []

    def collect_level_three(
        nodes: dict[str, dict[str, Any]],
        level: int,
        parent_name: str | None = None,
    ) -> None:
        for node in nodes.values():
            meta_name = node.get("metaName")
            children = node.get("children", [])
            if not isinstance(children, list):
                raise ValueError("Structure node has invalid children")

            if (
                level == 3
                and isinstance(meta_name, str)
                and meta_name.endswith("能耗地图")
            ):
                if not isinstance(parent_name, str) or not parent_name.endswith(
                    "能耗地图"
                ):
                    raise ValueError(
                        f"Level-3 map {meta_name!r} has no valid level-2 parent"
                    )
                tenant_name = parent_name.replace("能耗地图", "").strip()
                tenant_name = tenant_name_aliases.get(tenant_name, tenant_name)
                tenant = tenant_by_name.get(tenant_name)
                if tenant is None:
                    normalized_name = tenant_name.removesuffix("区")
                    tenant = next(
                        (
                            candidate
                            for name, candidate in tenant_by_name.items()
                            if name.removesuffix("区") == normalized_name
                        ),
                        None,
                    )
                if tenant is None:
                    raise ValueError(
                        f"No cached tenant matches level-2 map parent "
                        f"{parent_name!r} (looked up as {tenant_name!r})"
                    )
                tenant_id = tenant.get("tenantId")
                if not isinstance(tenant_id, (str, int)):
                    raise ValueError(
                        f"Cached tenant {tenant_name!r} has no valid tenantId"
                    )
                payloads.append(
                    (
                        str(tenant_id),
                        {
                            "metaCode": meta_name.replace("能耗地图", ""),
                            "chronoUnit": "DAYS",
                            "temporal": date.today().isoformat(),
                        },
                    )
                )

            for child in children:
                if not isinstance(child, dict):
                    raise ValueError("Structure contains an invalid child node")
                collect_level_three(
                    child,
                    level + 1,
                    meta_name if isinstance(meta_name, str) else None,
                )

    collect_level_three(structure, 1)
    if not payloads:
        raise ValueError("No level-3 nodes ending in '能耗地图' found in structure")
    return payloads


def _collect_leaf_nodes(
    nodes: dict[str, dict[str, Any]],
) -> list[tuple[str, str]]:
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


def _render_value_table(
    leaves: list[tuple[str, str]],
    values_by_point: dict[str, str],
) -> str:
    def render_value(value: str, *, highlight: bool) -> str:
        escaped_value = html.escape(value)
        css_class = ' class="low-value"' if highlight else ""
        return f"<td{css_class}>{escaped_value}</td>"

    rows = []
    for meta_code, meta_name in leaves:
        energy_value = values_by_point.get(f"{meta_code}::Eptp_1D") or "--"
        power_value = values_by_point.get(f"{meta_code}::P_RT") or "--"
        try:
            low_energy_value = float(energy_value) < 10
        except ValueError:
            low_energy_value = False
        rows.append(
            "<tr>"
            f"<td>{html.escape(meta_name)}</td>"
            f"{render_value(energy_value, highlight=energy_value == '--' or low_energy_value)}"
            f"{render_value(power_value, highlight=power_value == '--')}"
            "</tr>"
        )
    return (
        "<div class=\"table-wrap\"><table>"
        "<thead><tr><th>metaName</th><th>Eptp_1D</th><th>P_RT</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )


def _render_tree_node(
    meta_code: str,
    node: dict[str, Any],
    depth: int,
    values_by_point: dict[str, str],
) -> str:
    meta_name = node.get("metaName")
    if not isinstance(meta_name, str) or not meta_name:
        raise ValueError(f"Structure node {meta_code!r} has no metaName")

    children = node.get("children", [])
    if not isinstance(children, list):
        raise ValueError(f"Structure node {meta_code!r} has invalid children")
    if not children:
        return _render_value_table([(meta_code, meta_name)], values_by_point)

    leaf_children: list[tuple[str, str]] = []
    branch_children: list[str] = []
    for child in children:
        if not isinstance(child, dict):
            raise ValueError(f"Structure node {meta_code!r} has an invalid child")
        for child_code, child_node in child.items():
            if not isinstance(child_node, dict):
                raise ValueError(
                    f"Structure node {meta_code!r} has an invalid child node"
                )
            grand_children = child_node.get("children", [])
            if not isinstance(grand_children, list):
                raise ValueError(f"Structure node {child_code!r} has invalid children")
            if grand_children:
                branch_children.append(
                    _render_tree_node(
                        child_code,
                        child_node,
                        depth + 1,
                        values_by_point,
                    )
                )
            else:
                child_name = child_node.get("metaName")
                if not isinstance(child_name, str) or not child_name:
                    raise ValueError(f"Structure node {child_code!r} has no metaName")
                leaf_children.append((child_code, child_name))

    heading_level = min(depth + 1, 6)
    title = html.escape(meta_name)
    default_open = ' open' if depth == 1 and meta_name == "阳光电源能耗地图" else ""
    leaf_table = (
        _render_value_table(leaf_children, values_by_point) if leaf_children else ""
    )
    return (
        f"<details class=\"tree-node depth-{depth}\"{default_open}>"
        f"<summary><span class=\"heading heading-{heading_level}\">{title}</span></summary>"
        f"{leaf_table}{''.join(branch_children)}</details>"
    )


def _render_report(
    structure: dict[str, dict[str, Any]],
    values_by_point: dict[str, str],
    request_url: str,
    point_keys: list[str],
    http_status: int,
) -> str:
    captured_at = datetime.now().astimezone().isoformat(timespec="seconds")
    tree = []
    root_leaves: list[tuple[str, str]] = []
    for meta_code, node in structure.items():
        children = node.get("children", [])
        if not isinstance(children, list):
            raise ValueError(f"Structure node {meta_code!r} has invalid children")
        if children:
            tree.append(_render_tree_node(meta_code, node, 1, values_by_point))
        else:
            meta_name = node.get("metaName")
            if not isinstance(meta_name, str) or not meta_name:
                raise ValueError(f"Structure node {meta_code!r} has no metaName")
            root_leaves.append((meta_code, meta_name))
    if root_leaves:
        tree.insert(0, _render_value_table(root_leaves, values_by_point))

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>能耗地图 captured at {captured_at}</title>
  <style>
    :root {{ color-scheme: light; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }}
    body {{ margin: 0; padding: 24px; color: #1f2937; background: #f3f6fa; }}
    main {{ max-width: 1400px; margin: 0 auto; }}
    h1 {{ margin: 0 0 20px; color: #123b63; }}
    h2, h3, h4, h5, h6 {{ margin: 18px 0 10px; color: #174f7a; }}
    .tree-node {{ margin: 12px 0 12px 16px; padding: 8px 0 0 16px; border-left: 2px solid #c8d8e8; }}
    .depth-1 {{ margin-left: 0; padding-left: 0; border-left: 0; }}
    summary {{ cursor: pointer; list-style: none; }}
    summary::-webkit-details-marker {{ display: none; }}
    summary::before {{ content: "▶"; display: inline-block; margin-right: 8px; color: #52738f; font-size: .75em; transition: transform .15s ease; }}
    details[open] > summary::before {{ transform: rotate(90deg); }}
    .heading {{ color: #174f7a; font-weight: 650; }}
    .heading-2 {{ font-size: 1.35em; }}
    .heading-3 {{ font-size: 1.2em; }}
    .heading-4 {{ font-size: 1.08em; }}
    .table-wrap {{ overflow-x: auto; margin: 10px 0 16px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px #00000012; }}
    th, td {{ padding: 9px 12px; border: 1px solid #d9e2ec; text-align: left; }}
    th {{ color: #123b63; background: #e8f1f8; }}
    td.low-value {{ background: #fecaca; }}
    tbody tr:nth-child(even) {{ background: #f8fafc; }}
    code {{ font-size: .9em; overflow-wrap: anywhere; }}
    details:not(.tree-node) {{ margin-top: 24px; padding: 12px; background: white; border: 1px solid #d9e2ec; border-radius: 6px; }}
    summary {{ cursor: pointer; font-weight: 600; }}
    pre {{ overflow-x: auto; padding: 12px; background: #f8fafc; }}
    .request-info {{ color: #526273; }}
  </style>
</head>
<body>
<main>
  <h1>能耗地图 captured at {captured_at}</h1>
  <p class="request-info">HTTP status: {http_status}<br>
  Request URL: {html.escape(request_url)}<br>
  Requested points: {len(point_keys)}</p>
  {''.join(tree)}
</main>
</body>
</html>
"""


@pytest.mark.sungrow
def test_energy_consumption_map(
    request: pytest.FixtureRequest,
    sungrow_reference_data: dict[str, Any],
    sungrow_client,
    sungrow_token: str,
    sungrow_tenant_id: str,
) -> None:
    structure = sungrow_reference_data["consumption_structure"]
    leaf_nodes = _collect_leaf_nodes(structure)
    assert leaf_nodes, "Consumption structure has no leaf nodes"

    point_codes = ("Eptp_1D", "P_RT")
    point_keys = [
        f"{meta_code}::{point_code}"
        for meta_code, _ in leaf_nodes
        for point_code in point_codes
    ]
    tenant_id = sungrow_tenant_id
    response = sungrow_client.post(
        "https://ems.sungrow.cn/scada-service/calculate/real/query/batch",
        json=point_keys,
        headers={
            "Referer": "https://ems.sungrow.cn/scada",
            "X-ACCESS-TENANT": tenant_id,
            "X-ACCESS-TOKEN": sungrow_token,
            "X-AUTH-TENANT": tenant_id,
            "X-AUTH-TOKEN": sungrow_token,
            "X-AUTH-UUID": os.getenv("SUNGROW_AUTH_UUID", ""),
        },
    )
    response.raise_for_status()
    body = response.json()
    assert body.get("code") == 200, json.dumps(body, ensure_ascii=False)
    result_data = body.get("data")
    if not isinstance(result_data, list):
        pytest.fail(
            "Expected SCADA batch response data to be a list, got "
            f"{type(result_data).__name__}"
        )

    values_by_point: dict[str, str] = {}
    for item in result_data:
        if not isinstance(item, dict):
            pytest.fail(f"Unexpected SCADA batch item: {item!r}")
        point_key = item.get("p")
        if not isinstance(point_key, str):
            pytest.fail(f"SCADA batch item has no string 'p' key: {item!r}")
        value = item.get("v")
        values_by_point[point_key] = "" if value is None else str(value)

    report = _render_report(
        structure=structure,
        values_by_point=values_by_point,
        request_url=str(response.request.url),
        point_keys=point_keys,
        http_status=response.status_code,
    )
    test_file = Path(str(request.node.path)).stem
    safe_test_name = re.sub(r'[<>:"/\\|?*]+', "_", request.node.name)
    report_path = (
        Path(request.config.rootpath)
        / "test_logs"
        / test_file
        / f"{safe_test_name}.html"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    logger.debug("HTML report: %s", report_path)


@pytest.mark.sungrow
def test_energy_consumption_map_history(
    sungrow_client,
    sungrow_reference_data: dict[str, Any],
    sungrow_token: str,
    sungrow_tenant_id: str,
) -> None:
    structure = sungrow_reference_data["consumption_structure"]
    leaf_nodes = _collect_leaf_nodes(structure)
    assert leaf_nodes, "Consumption structure has no leaf nodes"

    end = datetime.now()
    start = end - timedelta(days=5)
    tenant_id = sungrow_tenant_id
    for meta_code, meta_name in leaf_nodes:
        payload = {
            "deviceCode": meta_code,
            "pointCode": os.getenv("SUNGROW_POINT_CODE", "Eptp_1D"),
            "start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end": end.strftime("%Y-%m-%d %H:%M:%S"),
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
        response.raise_for_status()
        body = response.json()
        assert body.get("code") == 200, json.dumps(body, ensure_ascii=False)
        print(
            f"metaCode={meta_code} metaName={meta_name}: "
            f"{json.dumps(body.get('data'), ensure_ascii=False)}"
        )


@pytest.mark.sungrow
def test_prints_room_power_statistics(
    sungrow_client,
    sungrow_reference_data: dict[str, Any],
) -> None:
    structure = sungrow_reference_data["consumption_structure"]
    tenants = sungrow_reference_data["tenants"]
    for tenant_id, payload in _power_statistics_payload(structure, tenants):
        headers = sungrow_client.headers.copy()
        headers["X-AUTH-TENANT"] = tenant_id
        response = sungrow_client.post(
            "/monitor/consumption/map/statistics/power/room",
            json=payload,
            headers=headers,
        )
        print(f"metaCode={payload['metaCode']}: {response.text}")
        
@pytest.mark.sungrow
def test_prints_cabinet_power_statistics(
    sungrow_client,
    sungrow_reference_data: dict[str, Any],
) -> None:
    structure = sungrow_reference_data["consumption_structure"]
    tenants = sungrow_reference_data["tenants"]
    for tenant_id, payload in _power_statistics_payload(structure, tenants):
        headers = sungrow_client.headers.copy()
        headers["X-AUTH-TENANT"] = tenant_id
        response = sungrow_client.post(
            "/monitor/consumption/map/statistics/power/cabinet",
            json=payload,
            headers=headers,
        )
        print(f"metaCode={payload['metaCode']}: {response.text}")

