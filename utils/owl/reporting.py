from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ReportTable:
    title: str
    columns: list[str]
    rows: list[list[Any]]


@dataclass
class TestReport:
    nodeid: str
    outcome: str = "unknown"
    duration: float = 0.0
    tables: list[ReportTable] = field(default_factory=list)
    stdout: str = ""
    error: str | None = None


class ReportCollector:
    def __init__(self) -> None:
        self.tests: dict[str, TestReport] = {}

    def get_test(self, nodeid: str) -> TestReport:
        if nodeid not in self.tests:
            self.tests[nodeid] = TestReport(nodeid=nodeid)

        return self.tests[nodeid]

    def add_table(
        self,
        nodeid: str,
        table: ReportTable,
    ) -> None:
        self.get_test(nodeid).tables.append(table)

    def save_html(self, output_file: Path) -> None:
        total = len(self.tests)
        passed = sum(
            test.outcome == "passed"
            for test in self.tests.values()
        )
        failed = sum(
            test.outcome == "failed"
            for test in self.tests.values()
        )

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Owl Test Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 30px;
        }}

        table {{
            border-collapse: collapse;
            margin-bottom: 20px;
        }}

        th, td {{
            border: 1px solid #ccc;
            padding: 6px 10px;
        }}

        th {{
            background: #eee;
        }}

        .passed {{
            color: green;
        }}

        .failed {{
            color: red;
        }}
    </style>
</head>

<body>

<h1>Owl Test Report</h1>

<h2>Summary</h2>

<p>
Total: {total}<br>
Passed: <span class="passed">{passed}</span><br>
Failed: <span class="failed">{failed}</span>
</p>

<hr>

"""

        for test in self.tests.values():

            status_class = test.outcome

            html += f"""
<h2 class="{status_class}">
    {test.outcome.upper()} - {test.nodeid}
</h2>

<p>
Duration: {test.duration:.2f} seconds
</p>
"""

            for table in test.tables:

                html += f"""
<h3>{table.title}</h3>

<table>
<tr>
"""

                for column in table.columns:
                    html += f"<th>{column}</th>"

                html += "</tr>"

                for row in table.rows:
                    html += "<tr>"

                    for value in row:
                        html += f"<td>{value}</td>"

                    html += "</tr>"

                html += "</table>"

            if test.error:
                html += f"""
<h3>Error</h3>
<pre>{test.error}</pre>
"""

        html += """
</body>
</html>
"""

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_file.write_text(
            html,
            encoding="utf-8",
        )