from __future__ import annotations

import json
import pytest
from typing import Any
from datetime import datetime
import logging
from owl.reporting import ReportTable

logger = logging.getLogger(__name__)

source_list = ["T0", "T1", "T2"]  #T0 - 总览， T1 - 习友园， T2 - 产业园区
trend_list = {
    "T0": [
        "/monitor/visual/dashboard/municipal/electricity/power/trend",   #市电功率
        "/monitor/visual/dashboard/photovoltaic/power/trend",  #光伏功率
        "/monitor/visual/dashboard/charge/power/trend", #充电桩功率
        "/monitor/visual/dashboard/storage/power/trend", #储能充电功率, 储能放电功率
    ],
    "T1": [
        "/monitor/visual/dashboard/municipal/electricity/power/trend",   #市电功率
        "/monitor/visual/dashboard/photovoltaic/power/trend",  #光伏功率
        "/monitor/visual/dashboard/charge/power/trend", #充电桩功率        
    ],
    "T2": [
        "/monitor/visual/dashboard/municipal/electricity/power/trend",   #市电功率
        "/monitor/visual/dashboard/photovoltaic/power/trend",  #光伏功率
        "/monitor/visual/dashboard/charge/power/trend", #充电桩功率
        "/monitor/visual/dashboard/storage/power/trend", #储能充电功率, 储能放电功率
    ],
}

def _normalize_data(data: list) -> dict[str, Any]:
    if not data:
        raise ValueError("data must contain at least one chart")

    if len(data) != 2:
        raise ValueError(f"Expected exactly 2 charts, got {len(data)}")

    chart1, chart2 = data

    # Start with the first chart's values for all other keys
    merged = chart1.copy()

    # Join chart titles and codes
    merged["chartTitle"] = f'{chart1["chartTitle"]} / {chart2["chartTitle"]}'
    merged["chartCode"] = f'{chart1["chartCode"]} / {chart2["chartCode"]}'

    # Merge ordinate: fill empty values in chart1 using chart2
    ordinate1 = chart1.get("ordinate", [])
    ordinate2 = chart2.get("ordinate", [])

    if len(ordinate1) != len(ordinate2):
        raise ValueError("The two charts have different ordinate lengths")

    merged["ordinate"] = [
        value1 if value1 != "" else value2
        for value1, value2 in zip(ordinate1, ordinate2)
    ]

    return merged

def _examine_trend_data(
    data: Any,
    now: datetime,
) -> list[tuple[str, list[Any]]]:
    
    missing_values: list[tuple[str, list[Any]]] = []
    if isinstance(data, list):
        data = _normalize_data(data)
    
    abscissa = data.get("abscissa") or []
    ordinate = data.get("ordinate") or []
    if not isinstance(abscissa, list) or not isinstance(ordinate, list):
        raise AssertionError(
            f"Trend data has invalid abscissa/ordinate: {data!r}"
        )
    if len(abscissa) != len(ordinate):
        raise AssertionError(
            f"Trend data length mismatch: abscissa={len(abscissa)}, "
            f"ordinate={len(ordinate)}, item={data!r}"
        )
    sample_index = 0
    for index, timestamp_str in enumerate(abscissa):
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError) as exc:
            raise AssertionError(
                f"Trend timestamp is invalid: {timestamp_str!r}, item={data!r}"
            ) from exc
        if timestamp > now:
            break
        sample_index = index + 1
    sample_time = abscissa[:sample_index]
    sample_value = ordinate[:sample_index]
    logger.debug(
        "Query time: %s, Sample time: %s, Sample value: %s",
        now,
        sample_time,
        sample_value,
    )
    missing_sample_values = [
        value for value in sample_value if value == ""
    ]
    if missing_sample_values:
        missing_values.append(
            (str(data.get("chartTitle", "")), missing_sample_values)
        )

    return missing_values


@pytest.mark.sungrow
@pytest.mark.hide_report_error
def test_electricity_power_trend(
    request: pytest.FixtureRequest,
    sungrow_client,
    sungrow_token: str,
    report_collector,
) -> None:
    now = datetime.now()
    report_rows: list[list[Any]] = []
    report_row_keys: set[str] = set()
    failures: list[str] = []

    for source in source_list:
        for endpoint in trend_list[source]:
            payload = {"source": source}
            response = sungrow_client.post(
                endpoint,
                json=payload,
                headers={"X-AUTH-TOKEN": sungrow_token
                         },
            )
            response.raise_for_status()

            body = response.json()
            assert body.get("code") == 200

            data = body.get("data")
            assert data is not None

            logger.info("Testing endpoint: %s, Source: %s", endpoint, source)
            missing_values = _examine_trend_data(data, now)
            for chart_title, sample_value in missing_values:
                item_name = f"{source}-{chart_title}"
                report_row = [item_name, sample_value]
                row_key = json.dumps(report_row, ensure_ascii=False, sort_keys=True)
                if row_key in report_row_keys:
                    continue
                report_row_keys.add(row_key)
                logger.info(
                    "Missing trend data: Item=%s, sample_value=%s",
                    item_name,
                    sample_value,
                )
                report_rows.append(report_row)
            if missing_values:
                failures.append(
                    f"source={source}, endpoint={endpoint}, "
                    f"sample_value={[values for _, values in missing_values]}"
                )

    logger.info("Trend test missing-data rows: %s", report_rows)
    if report_rows:
        report_collector.add_table(
            request.node.nodeid,
            ReportTable(
                title="趋势数据缺失",
                columns=["Item", "Sample value"],
                rows=report_rows,
            ),
        )
        pytest.fail("Trend validation found empty values:\n" + "\n".join(failures))
