from __future__ import annotations

import csv
import html
import io
import json
import logging
import os
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from typing import Any

import pytest
from owl.api import collect_leaf_nodes

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

def _render_value_table(
    leaves: list[tuple[str, str]],
    values_by_point: dict[str, str],
    values_history_by_point: dict[str, list[Any]],
) -> str:
    def render_value(value: str, *, highlight: bool) -> str:
        escaped_value = html.escape(value)
        css_class = ' class="low-value"' if highlight else ""
        return f"<td{css_class}>{escaped_value}</td>"

    def render_history(history: list[Any]) -> str:
        history_text = ", ".join(str(item) for item in history) or "--"
        return render_value(history_text, highlight=history_text == "--")

    rows = []
    for meta_code, meta_name in leaves:
        energy_value = values_by_point.get(f"{meta_code}::Eptp_1D") or "--"
        power_value = values_by_point.get(f"{meta_code}::P_RT") or "--"
        energy_history = values_history_by_point.get(f"{meta_code}::Eptp_1D") or []
        power_history = values_history_by_point.get(f"{meta_code}::P_RT") or []
        try:
            low_energy_value = float(energy_value) < 10
        except ValueError:
            low_energy_value = False
        rows.append(
            "<tr>"
            f"<td>{html.escape(meta_name)}</td>"
            f"{render_value(energy_value, highlight=energy_value == '--' or low_energy_value)}"
            f"{render_history(energy_history)}"
            f"{render_value(power_value, highlight=power_value == '--')}"
            f"{render_history(power_history)}"
            "</tr>"
        )
    return (
        "<div class=\"table-wrap\"><table>"
        "<thead>"
        "<tr>"
        "<th rowspan=\"2\">metaName</th>"
        "<th colspan=\"2\" style=\"text-align:center\">Eptp_1D</th>"
        "<th colspan=\"2\" style=\"text-align:center\">P_RT</th>"
        "</tr>"
        "<tr>"
        "<th>current</th><th>history</th>"
        "<th>current</th><th>history</th>"
        "</tr>"
        "</thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )


def _render_tree_node(
    meta_code: str,
    node: dict[str, Any],
    depth: int,
    values_by_point: dict[str, str],
    values_history_by_point: dict[str, list[Any]],
) -> str:
    meta_name = node.get("metaName")
    if not isinstance(meta_name, str) or not meta_name:
        raise ValueError(f"Structure node {meta_code!r} has no metaName")

    children = node.get("children", [])
    if not isinstance(children, list):
        raise ValueError(f"Structure node {meta_code!r} has invalid children")
    if not children:
        return _render_value_table(
            [(meta_code, meta_name)], values_by_point, values_history_by_point
        )

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
                        values_history_by_point,
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
        _render_value_table(leaf_children, values_by_point, values_history_by_point)
        if leaf_children
        else ""
    )
    return (
        f"<details class=\"tree-node depth-{depth}\"{default_open}>"
        f"<summary><span class=\"heading heading-{heading_level}\">{title}</span></summary>"
        f"{leaf_table}{''.join(branch_children)}</details>"
    )


def _render_report(
    structure: dict[str, dict[str, Any]],
    values_by_point: dict[str, str],
    values_history_by_point: dict[str, list[Any]],
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
            tree.append(
                _render_tree_node(
                    meta_code, node, 1, values_by_point, values_history_by_point
                )
            )
        else:
            meta_name = node.get("metaName")
            if not isinstance(meta_name, str) or not meta_name:
                raise ValueError(f"Structure node {meta_code!r} has no metaName")
            root_leaves.append((meta_code, meta_name))
    if root_leaves:
        tree.insert(
            0,
            _render_value_table(root_leaves, values_by_point, values_history_by_point),
        )

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


def _csv_leaf_row(
    meta_code: str,
    meta_name: str,
    values_by_point: dict[str, str],
    values_history_by_point: dict[str, list[Any]],
) -> list[str]:
    """Cell text for one leaf, identical to what the HTML table shows."""

    def history_text(point_code: str) -> str:
        history = values_history_by_point.get(f"{meta_code}::{point_code}") or []
        return ", ".join(str(item) for item in history) or "--"

    return [
        meta_name,
        values_by_point.get(f"{meta_code}::Eptp_1D") or "--",
        history_text("Eptp_1D"),
        values_by_point.get(f"{meta_code}::P_RT") or "--",
        history_text("P_RT"),
    ]


def _csv_node_rows(
    meta_code: str,
    node: dict[str, Any],
    titles: list[str],
    values_by_point: dict[str, str],
    values_history_by_point: dict[str, list[Any]],
) -> list[tuple[list[str], list[str]]]:
    """(titles, leaf row) pairs for one node, in the same order as the HTML."""
    meta_name = node.get("metaName")
    if not isinstance(meta_name, str) or not meta_name:
        raise ValueError(f"Structure node {meta_code!r} has no metaName")
    children = node.get("children", [])
    if not isinstance(children, list):
        raise ValueError(f"Structure node {meta_code!r} has invalid children")
    if not children:
        return [
            (
                titles,
                _csv_leaf_row(
                    meta_code, meta_name, values_by_point, values_history_by_point
                ),
            )
        ]

    node_titles = [*titles, meta_name]
    leaf_rows: list[tuple[list[str], list[str]]] = []
    branch_rows: list[tuple[list[str], list[str]]] = []
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
                branch_rows.extend(
                    _csv_node_rows(
                        child_code,
                        child_node,
                        node_titles,
                        values_by_point,
                        values_history_by_point,
                    )
                )
            else:
                child_name = child_node.get("metaName")
                if not isinstance(child_name, str) or not child_name:
                    raise ValueError(f"Structure node {child_code!r} has no metaName")
                leaf_rows.append(
                    (
                        node_titles,
                        _csv_leaf_row(
                            child_code,
                            child_name,
                            values_by_point,
                            values_history_by_point,
                        ),
                    )
                )
    return leaf_rows + branch_rows


def _render_csv(
    structure: dict[str, dict[str, Any]],
    values_by_point: dict[str, str],
    values_history_by_point: dict[str, list[Any]],
) -> str:
    """All report tables as one CSV: one column per title level, then the values."""
    root_leaf_rows: list[tuple[list[str], list[str]]] = []
    tree_rows: list[tuple[list[str], list[str]]] = []
    for meta_code, node in structure.items():
        rows = _csv_node_rows(
            meta_code, node, [], values_by_point, values_history_by_point
        )
        if node.get("children"):
            tree_rows.extend(rows)
        else:
            root_leaf_rows.extend(rows)
    all_rows = root_leaf_rows + tree_rows

    depth = max((len(titles) for titles, _ in all_rows), default=0)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [f"Level {level}" for level in range(1, depth + 1)]
        + [
            "metaName",
            "Eptp_1D (current)",
            "Eptp_1D (history)",
            "P_RT (current)",
            "P_RT (history)",
        ]
    )
    for titles, values in all_rows:
        writer.writerow(titles + [""] * (depth - len(titles)) + values)
    return output.getvalue()

@pytest.mark.sungrow
def test_energy_consumption_map(
    request: pytest.FixtureRequest,
    sungrow_reference_data: dict[str, Any],
    sungrow_history_data: dict[str, Any],
    sungrow_client,
    sungrow_token: str,
    sungrow_tenant_id: str,
) -> None:
    
    structure = sungrow_reference_data["consumption_structure"]
    leaf_nodes = collect_leaf_nodes(structure)
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
    history_data = sungrow_history_data['data']
    values_history_by_point: dict[str, list[Any]] = {}
    for item in result_data:
        if not isinstance(item, dict):
            pytest.fail(f"Unexpected SCADA batch item: {item!r}")
        point_key = item.get("p")
        if not isinstance(point_key, str):
            pytest.fail(f"SCADA batch item has no string 'p' key: {item!r}")
        value = item.get("v")
        values_by_point[point_key] = "" if value is None else str(value)
        values_history_by_point[point_key] = history_data.get(point_key, [])

    report = _render_report(
        structure=structure,
        values_by_point=values_by_point,
        values_history_by_point=values_history_by_point,
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

    csv_path = report_path.with_suffix(".csv")
    # utf-8-sig adds a BOM so Excel shows the Chinese titles correctly.
    csv_path.write_text(
        _render_csv(structure, values_by_point, values_history_by_point),
        encoding="utf-8-sig",
    )
    logger.debug("CSV report: %s", csv_path)

def _display_width(text: str) -> int:
    """Terminal width of ``text``; CJK characters take two columns."""
    return sum(
        2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text
    )


def _table_cell(value: Any) -> tuple[str, bool]:
    """Return (text, is_number) for one table cell."""
    if value is None:
        return "", False
    if isinstance(value, bool):
        return ("true" if value else "false"), False
    if isinstance(value, (int, float)):
        return str(value), True
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")), False
    return str(value).replace("\r", " ").replace("\n", " "), False


def _format_table(columns: list[str], rows: list[list[Any]]) -> str:
    cells = [[_table_cell(value) for value in row] for row in rows]
    widths = [
        max(
            [_display_width(column)]
            + [_display_width(row[index][0]) for row in cells]
        )
        for index, column in enumerate(columns)
    ]

    def pad(text: str, width: int, *, right: bool = False) -> str:
        padding = " " * (width - _display_width(text))
        return padding + text if right else text + padding

    separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    lines = [
        separator,
        "| " + " | ".join(pad(c, w) for c, w in zip(columns, widths)) + " |",
        separator,
    ]
    for row in cells:
        lines.append(
            "| "
            + " | ".join(
                pad(text, width, right=is_number)
                for (text, is_number), width in zip(row, widths)
            )
            + " |"
        )
    lines.append(separator)
    return "\n".join(lines)


POWER_STATISTICS_COLUMNS = ["metaCode", "code", "offline", "online", "alarm"]


def _find_field(data: Any, name: str) -> Any:
    """Value stored under ``name`` in an object, looking into nested objects.

    A list is only searched when it holds exactly one item; with several items
    there is no single right value to pick, so nothing is returned.
    """
    if isinstance(data, dict):
        if name in data:
            return data[name]
        for value in data.values():
            found = _find_field(value, name)
            if found is not None:
                return found
    elif isinstance(data, list) and len(data) == 1:
        return _find_field(data[0], name)
    return None


def _power_statistics_row(meta_code: str, response: Any) -> list[Any]:
    """One table row: metaCode, response code, then offline/online/alarm."""
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return [meta_code, f"HTTP {response.status_code}", "--", "--", "--"]

    data = body.get("data")
    values = [_find_field(data, name) for name in POWER_STATISTICS_COLUMNS[2:]]
    return [
        meta_code,
        body.get("code", f"HTTP {response.status_code}"),
        *("--" if value is None else value for value in values),
    ]


def _emit_table(text: str) -> None:
    """Show ``text`` on screen and in the per-test log.

    ``print`` reaches the screen when pytest runs with ``-s`` (run_test.py does).
    Log records are always captured into the test log, even with ``-s``.
    The leading newline keeps the table aligned after the log prefix.
    """
    print(text)
    logger.info("\n%s", text)


def _print_power_statistics(
    sungrow_client: Any,
    structure: dict[str, dict[str, Any]],
    tenants: list[dict[str, Any]],
    path: str,
) -> None:
    rows: list[list[Any]] = []
    for tenant_id, payload in _power_statistics_payload(structure, tenants):
        headers = sungrow_client.headers.copy()
        headers["X-AUTH-TENANT"] = tenant_id
        response = sungrow_client.post(path, json=payload, headers=headers)
        # The full response goes to the test log only, so nothing is lost.
        logger.debug(
            "metaCode=%s tenant=%s HTTP %s: %s",
            payload["metaCode"],
            tenant_id,
            response.status_code,
            response.text,
        )
        rows.append(_power_statistics_row(payload["metaCode"], response))
    _emit_table(f"POST {path}\n" + _format_table(POWER_STATISTICS_COLUMNS, rows))


@pytest.mark.sungrow
def test_room_power_statistics(
    sungrow_client,
    sungrow_reference_data: dict[str, Any],
) -> None:
    _print_power_statistics(
        sungrow_client,
        sungrow_reference_data["consumption_structure"],
        sungrow_reference_data["tenants"],
        "/monitor/consumption/map/statistics/power/room",
    )


@pytest.mark.sungrow
def test_cabinet_power_statistics(
    sungrow_client,
    sungrow_reference_data: dict[str, Any],
) -> None:
    _print_power_statistics(
        sungrow_client,
        sungrow_reference_data["consumption_structure"],
        sungrow_reference_data["tenants"],
        "/monitor/consumption/map/statistics/power/cabinet",
    )
