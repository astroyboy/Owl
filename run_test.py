from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
TESTS_DIR = PROJECT_ROOT / "tests"
PYTEST_CONFIG = PROJECT_ROOT / "pyproject.toml"


def _resolve_test_file(value: str) -> Path:
    path = Path(value)
    candidates = (
        [path]
        if path.is_absolute()
        else [TESTS_DIR / path, PROJECT_ROOT / path]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_relative_to(TESTS_DIR) and resolved.is_file():
            if resolved.suffix != ".py":
                raise ValueError(f"Test path must point to a .py file: {value}")
            return resolved
    raise ValueError(f"Test file not found under {TESTS_DIR}: {value}")


def _read_config_files(config_path: str) -> list[Path]:
    path = Path(config_path)
    if not path.is_absolute():
        working_directory_path = path.resolve()
        project_path = (PROJECT_ROOT / path).resolve()
        path = (
            working_directory_path
            if working_directory_path.is_file()
            else project_path
        )
    if not path.is_file():
        raise ValueError(f"JSON config file not found: {config_path}")

    try:
        config: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in config file {path}: {exc}") from exc
    if not isinstance(config, list) or not config:
        raise ValueError("The JSON config must be a non-empty list of test file paths")
    if not all(isinstance(item, str) and item for item in config):
        raise ValueError("Every JSON config entry must be a non-empty file path")
    return [_resolve_test_file(item) for item in config]


class _TestNameFilter:
    def __init__(self, keyword: str) -> None:
        self.keyword = keyword.casefold()

    def pytest_collection_modifyitems(
        self,
        session: Any,
        config: Any,
        items: list[Any],
    ) -> None:
        selected = [
            item for item in items if self.keyword in item.name.casefold()
        ]
        deselected = [item for item in items if item not in selected]
        if deselected:
            config.hook.pytest_deselected(items=deselected)
        items[:] = selected


class _TestRunSummary:
    def __init__(self) -> None:
        self.tests: dict[str, dict[str, Any]] = {}

    def pytest_runtest_logreport(self, report: Any) -> None:
        record = self.tests.setdefault(
            report.nodeid,
            {
                "module": Path(report.location[0]).stem,
                "case": report.nodeid.rsplit("::", 1)[-1],
                "duration": 0.0,
                "outcomes": {},
                "log": self._log_path(report),
            },
        )
        record["duration"] += report.duration
        record["outcomes"][report.when] = report.outcome

    @staticmethod
    def _log_path(report: Any) -> Path:
        module = Path(report.location[0]).stem
        case = report.nodeid.rsplit("::", 1)[-1]
        safe_case = re.sub(r'[<>:"/\\|?*]+', "_", case)
        return PROJECT_ROOT / "test_logs" / module / f"{safe_case}.log"

    def print_summary(self) -> None:
        headers = ("Test module", "Test case", "Run time (s)", "Result", "Test log")
        rows = [
            (
                record["module"],
                record["case"],
                f"{record['duration']:.3f}",
                self._result(record["outcomes"]),
                str(record["log"]),
            )
            for record in self.tests.values()
        ]
        if not rows:
            print("\nNo test cases were run.")
            return

        widths = [
            max(len(header), *(len(row[index]) for row in rows))
            for index, header in enumerate(headers)
        ]
        separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"
        print("\nTest run summary")
        print(separator)
        print(
            "| "
            + " | ".join(
                header.ljust(width) for header, width in zip(headers, widths)
            )
            + " |"
        )
        print(separator)
        for row in rows:
            print(
                "| "
                + " | ".join(
                    value.ljust(width) for value, width in zip(row, widths)
                )
                + " |"
            )
        print(separator)

    @staticmethod
    def _result(outcomes: dict[str, str]) -> str:
        if "failed" in outcomes.values():
            return "FAILED"
        if "skipped" in outcomes.values():
            return "SKIPPED"
        if outcomes.get("call") == "passed":
            return "PASSED"
        return "UNKNOWN"


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Owl pytest cases using a JSON list, test file, or name keyword."
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "-f",
        "--file",
        dest="config_file",
        help="JSON file containing a list of test file paths",
    )
    selection.add_argument(
        "-m",
        "--module",
        dest="test_file",
        help="run all tests from one Python test file under tests/",
    )
    selection.add_argument(
        "-t",
        "--test-name",
        dest="test_keyword",
        help="run tests whose function names contain this keyword",
    )
    return parser


def main() -> int:
    parser = _argument_parser()
    arguments, pytest_arguments = parser.parse_known_args()

    try:
        if arguments.config_file:
            targets = _read_config_files(arguments.config_file)
        elif arguments.test_file:
            targets = [_resolve_test_file(arguments.test_file)]
        else:
            targets = [TESTS_DIR]
    except ValueError as exc:
        parser.error(str(exc))

    pytest_args = ["-c", str(PYTEST_CONFIG), "--run-sungrow", "-s"]
    pytest_args.extend(str(target) for target in targets)
    pytest_args.extend(pytest_arguments)

    import pytest

    summary = _TestRunSummary()
    plugins = [summary]
    if arguments.test_keyword:
        plugins.append(_TestNameFilter(arguments.test_keyword))
    result = pytest.main(pytest_args, plugins=plugins)
    summary.print_summary()
    return int(result)


if __name__ == "__main__":
    sys.exit(main())
