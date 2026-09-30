from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from owl.auth import Settings, SungrowAuthenticator
from owl.cache import get_cached_reference_data


def _test_log_path(item: pytest.Item) -> Path:
    logs_root = Path(item.config.rootpath) / "test_logs"
    test_file_dir = logs_root / Path(str(item.path)).stem
    safe_test_name = re.sub(r'[<>:"/\\|?*]+', "_", item.name)
    return test_file_dir / f"{safe_test_name}.log"


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    log_path = _test_log_path(item)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"Test: {item.nodeid}\n",
        encoding="utf-8",
    )
    setattr(item, "_owl_test_log_path", log_path)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item,
    call: pytest.CallInfo[Any],
):
    outcome = yield
    report = outcome.get_result()
    log_path = getattr(item, "_owl_test_log_path", None)
    if log_path is None:
        log_path = _test_log_path(item)
    logged_sections = getattr(item, "_owl_logged_sections", set())

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(
            f"\n[{report.when.upper()}] {report.outcome}"
            f" (duration: {report.duration:.3f}s)\n"
        )
        if report.failed and report.longrepr:
            log_file.write(f"{report.longrepr}\n")
        for section_name, content in report.sections:
            section_key = (section_name, content)
            if section_key in logged_sections:
                continue
            log_file.write(f"\n--- {section_name} ---\n")
            log_file.write(f"{content}\n")
            logged_sections.add(section_key)
    setattr(item, "_owl_logged_sections", logged_sections)


def _run_live_tests(config: pytest.Config) -> bool:
    return config.getoption("--run-sungrow") or os.getenv(
        "OWL_RUN_SUNGROW", ""
    ).lower() in {"1", "true", "yes"}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-sungrow",
        action="store_true",
        default=False,
        help="run tests that contact the live SUNGROW service",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "sungrow: test requires the live SUNGROW service",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if _run_live_tests(config):
        return

    skip = pytest.mark.skip(reason="pass --run-sungrow to enable live SUNGROW tests")
    for item in items:
        if "sungrow" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def sungrow_settings() -> Settings:
    """Load the one set of credentials shared by live tests."""
    settings = Settings.from_env()
    if not settings.username or not settings.password:
        pytest.fail(
            "SUNGROW_USERNAME and SUNGROW_PASSWORD are required for live tests"
        )
    return settings


@pytest.fixture(scope="session")
def sungrow_token(sungrow_settings: Settings) -> str:
    """Authenticate once per test session and share the returned token."""
    return SungrowAuthenticator(sungrow_settings).login()


@pytest.fixture(scope="session")
def sungrow_tenant_id() -> str:
    """Return the tenant selected for this test session."""
    return os.getenv("SUNGROW_TENANT_ID", "900002")


@pytest.fixture(scope="session")
def sungrow_metric_category() -> str:
    """Return the consumption category selected for this test session."""
    return os.getenv(
        "SUNGROW_METRIC_CATEGORY",
        "49607e0284dd44b7b2807e0d103fbc55",
    )


@pytest.fixture(scope="session")
def sungrow_headers(
    sungrow_token: str,
) -> dict[str, str]:
    """Build headers used by subsequent SUNGROW API requests."""
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://ems.sungrow.cn",
        "Referer": "https://ems.sungrow.cn/",
        "X-AUTH-CLIENT": "web",
        "X-AUTH-SCOPE": "",
        "X-AUTH-TOKEN": sungrow_token,
        "X-LOCALE": "zh_CN",
        "Cookie": "locale=zh_CN",
    }


@pytest.fixture(scope="session")
def sungrow_client(
    sungrow_headers: dict[str, str],
    sungrow_settings: Settings,
) -> Iterator[httpx.Client]:
    """Provide one authenticated HTTP client for the whole test session."""
    with httpx.Client(
        base_url=sungrow_settings.base_url,
        headers=sungrow_headers,
        timeout=sungrow_settings.timeout,
    ) as client:
        yield client


@pytest.fixture(scope="session")
def sungrow_reference_data(
    sungrow_client: httpx.Client,
    sungrow_tenant_id: str,
    sungrow_metric_category: str,
) -> dict[str, Any]:
    """Load tenant/category/structure data from the 3-day local JSON cache."""
    return get_cached_reference_data(
        sungrow_client,
        tenant_id=sungrow_tenant_id,
        category=sungrow_metric_category,
    )
