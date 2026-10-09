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
    ],
    "T1": [
        "/monitor/visual/dashboard/municipal/electricity/power/trend",   #市电功率
        "/monitor/visual/dashboard/photovoltaic/power/trend",  #光伏功率
        "/monitor/visual/dashboard/storage/power/trend", #储能功率
        "/monitor/visual/dashboard/charge/power/trend", #充电桩功率
        "/monitor/visual/dashboard/storage/power/trend", #储能充电功率, 储能放电功率
    ],
    "T2": [
        "/monitor/visual/dashboard/municipal/electricity/power/trend",   #市电功率
        "/monitor/visual/dashboard/photovoltaic/power/trend",  #光伏功率
        "/monitor/visual/dashboard/storage/power/trend", #储能功率
        "/monitor/visual/dashboard/charge/power/trend", #充电桩功率
        "/monitor/visual/dashboard/storage/power/trend", #储能充电功率, 储能放电功率
    ],
}

def _normalize_data(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return [data]

    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return data

    return []

def _examine_trend_data(
    data: Any,
    now: datetime,
) -> list[tuple[str, list[Any]]]:
    normalized_data = _normalize_data(data)
    if not normalized_data:
        raise AssertionError(f"Trend data is empty or not a list/dict: {data!r}")

    missing_values: list[tuple[str, list[Any]]] = []
    for item in normalized_data:
        abscissa = item.get("abscissa") or []
        ordinate = item.get("ordinate") or []
        if not isinstance(abscissa, list) or not isinstance(ordinate, list):
            raise AssertionError(
                f"Trend data has invalid abscissa/ordinate: {item!r}"
            )

        if len(abscissa) != len(ordinate):
            raise AssertionError(
                f"Trend data length mismatch: abscissa={len(abscissa)}, "
                f"ordinate={len(ordinate)}, item={item!r}"
            )

        sample_index = 0
        for index, timestamp_str in enumerate(abscissa):
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError) as exc:
                raise AssertionError(
                    f"Trend timestamp is invalid: {timestamp_str!r}, item={item!r}"
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
                (str(item.get("chartTitle", "")), missing_sample_values)
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
                title="Missing visual trend data",
                columns=["Item", "Sample value"],
                rows=report_rows,
            ),
        )
        #pytest.fail("Trend validation found empty values:\n" + "\n".join(failures))
