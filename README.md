# Owl

Small SUNGROW authentication client. The first version only logs in and
returns the token needed by later API calls.

## Setup

```powershell
cd C:\workspace\Owl
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

Copy `.env.example` to `.env` or set the variables in the shell:

```powershell
$env:SUNGROW_USERNAME = "your-username"
$env:SUNGROW_PASSWORD = "your-password"
```

## Generate a token

```powershell
python -m owl
```

The default endpoint is `https://ems.sungrow.cn/service/security/auth/login`. If the
SUNGROW deployment uses a different login route, override
`SUNGROW_LOGIN_PATH`.

The login request uses the documented JSON fields `accountCode` and `password`.
Following the website request, Owl sends the lowercase MD5 hash of the password
in the `password` field and includes the required web client headers.

Installing with `pip install -e .` makes `python -m owl` use the current source
code. Alternatively, set `PYTHONPATH` to `C:\workspace\Owl\utils` before running.

The token is printed only to standard output. Do not commit `.env` or share
the token.

## Run tests

```powershell
pytest
```

Use `run_test.py` to select tests. It enables live SUNGROW tests and disables
output capture by default, so tests marked `sungrow` run and their output is
shown in the console. Set `SUNGROW_USERNAME` and `SUNGROW_PASSWORD` before
running tests that require SUNGROW. The `-f` option reads a JSON array of test file paths
(paths may be relative to the project root or `tests/`):

```json
[
  "test_basic_api.py",
  "test_energy_consumption_map.py"
]
```

```powershell
python run_test.py -f tests-to-run.json
python run_test.py -m test_energy_consumption_map.py
python run_test.py -t cabinet_power_statistics
```

After pytest completes, the wrapper prints a per-case summary with the module,
case name, combined setup/call/teardown runtime, result, and test log path.
Extra pytest options can be passed through, for example:

```powershell
python run_test.py -m test_energy_consumption_map.py -k cabinet
```

Pytest automatically writes a separate log for each test case under
`test_logs/<test-file>/<test-name>.log`. The log contains the test outcome,
failures, and captured stdout/stderr/logging output. These generated logs are
ignored by Git.

The shared live-test fixtures are defined in `tests/conftest.py`. A test that
uses these fixtures authenticates once per pytest session:

- `sungrow_token`: one login token for the entire test session
- `sungrow_headers`: authenticated SUNGROW request headers
- `sungrow_client`: reusable authenticated `httpx.Client`

For manual debugging, run all reusable tenant/category/structure API functions
from the library module:

```powershell
python -m owl.api
```

This authenticates using `SUNGROW_USERNAME` and `SUNGROW_PASSWORD`, then fetches
tenants, structure categories, and the consumption structure. The structure
category defaults to `49607e0284dd44b7b2807e0d103fbc55`; override it with
`SUNGROW_METRIC_CATEGORY`. The returned values are also collected in the
`main()` result for callers importing the function.

During live pytest runs, tenant, category, and consumption-structure data are
loaded from `.cache/` before test cases run. The cache is keyed by tenant and
category and refreshes after three days. Each refreshed cache replaces its
latest JSON file, while the prior file is retained under `.cache/archive/`.
Set `OWL_CACHE_DIR` to use a different cache directory.

Tests can reuse the cached values by requesting the session-scoped
`sungrow_reference_data` fixture:

```python
def test_page_structure(sungrow_reference_data):
    structure = sungrow_reference_data["consumption_structure"]
```

The default tenant is `900002` (`产业园区`). Set `SUNGROW_TENANT_ID` to use
another tenant.

To print the complete response from the device ledger detail API, provide a
ledger ID and explicitly enable live tests:

```powershell
$env:SUNGROW_USERNAME = "your-account-code"
$env:SUNGROW_PASSWORD = "your-real-password"
$env:SUNGROW_LEDGER_ID = "your-ledger-id"
pytest -s --run-sungrow tests/test_basic_api.py
```

The endpoint is a GET request:

```text
/monitor/register/ledger/integration/detail?ledgerId=<ledger-id>
```

To print structure target metric points, the test first calls the category
discovery API and uses the first enabled category automatically:

```powershell
pytest -s --run-sungrow tests/test_basic_topology.py
```

The discovery request is:

```text
GET /monitor/topology/foundery/consumption/category
```

If you want to select a specific category instead, set
`SUNGROW_METRIC_CATEGORY` to its `categoryCode`:

```powershell
$env:SUNGROW_METRIC_CATEGORY = "your-category-code"
pytest -s --run-sungrow tests/test_basic_topology.py
```

The test calls:

```text
GET /monitor/topology/foundery/structure/target/metric?category=<category>
```

To print the formula/detail configuration for one metric, run:

```powershell
$env:SUNGROW_METRIC_CATEGORY = "49607e0284dd44b7b2807e0d103fbc55"
pytest -s --run-sungrow tests/test_basic_metric_detail.py
```

The test first calls the metric list API to get the first available `metaCode`:

```text
GET /monitor/topology/foundery/structure/target/metric?category=<category>
```

To request a specific metric instead, set `SUNGROW_METRIC_META_CODE` to a
value returned by that API.

This calls:

```text
POST /monitor/topology/foundery/metric/detail
```

with:

```json
{
  "category": "<category>",
  "metaCode": "<meta-code>"
}
```
