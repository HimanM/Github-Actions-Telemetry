# GitHub Actions Centralized Telemetry Observer

This repository implements a Centralized Workflow Telemetry Collector (Observer) designed to securely monitor and measure all workflow activity tied to a specific Commit SHA, without interfering directly with the workloads being monitored.

## Repository Metadata

**Topics:** SVG generation, JSON output, CLI/API tooling, Visualization, Security masking, Developer tooling, Python

## Project Overview

Per the MVP design, this pattern removes the need to embed telemetry logic directly inside other workflow files. Instead, the centralized observer automatically initializes, discovers what is executing, waits for all executions to finish, and extracts their structural telemetry (including durations, job steps, and event metadata).

### Architecture

* **Observer Trigger**: Triggered automatically via `push`, `pull_request`, and `workflow_dispatch`. It is also configured via `workflow_run` to capture manual triggers.
* **Identifier**: Bound strictly to `github.sha`.
* **Stabilization Engine**: Listens to GitHub Action API responses until the number of reported workflow runs matching the trigger SHA stabilizes. This accounts for asynchronous creation and polling latency.
* **Metrics Collector**: Harvests workflow run metadata, resolves internal job details, and attaches precise timestamps alongside Git commit history.

## Installation

### Prerequisites

* Python 3.11

### Dependencies

The following dependencies are required to run the Python scripts locally or are handled automatically when run as a GitHub Action:

* `requests`

You can install dependencies locally using:

```bash
pip install requests
```

## Security Notes

The Action is designed to be secure by default.

* **Secret Masking:** Sensitive variables provided to the Action, specifically `api_url` and `api_key`, are explicitly masked from workflow logs using `::add-mask::` during execution.
* **Examples:** All examples provided in this documentation use `<MASKED_TOKEN>` or similar dummy values. These are masked/redacted values. You must supply your own valid secrets via GitHub Secrets (e.g., `${{ secrets.GITHUB_TOKEN }}`).
* **Safe Usage:** Ensure that any external webhook URLs or API keys you provide are stored securely as GitHub Actions Secrets and never hardcoded into your workflow YAML.

## Usage Guide

Because the core polling and visualization logic is tightly wrapped inside a Composite Action (`action.yml`), integrating this into any other GitHub repository is incredibly simple. Other users do not need to clone this repository; they only need to reference it directly using the `uses:` syntax.

There are two primary methods for generating output: JSON-only and SVG+JSON combined output.

### Method 1: JSON Only Output

By default, the Action generates a comprehensive JSON payload. This is ideal if you only need the raw telemetry metrics for downstream analysis.

In this workflow, the Action exports the metrics to a JSON file. The exact generated JSON path is exposed via the `json_path` output variable.

**Example Usage:**

```yaml
name: Global Telemetry Observer (JSON Only)

on:
  push:
  pull_request:

permissions:
  actions: read

jobs:
  telemetry:
    runs-on: ubuntu-latest
    steps:
      - name: Observer Telemetry Agent
        uses: HimanM/Github-Actions-Telemetry@main
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          generate_svg_report: 'false'

      - name: Upload JSON Telemetry Data
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: telemetry-test-jsons
          path: ${{ steps.observer.outputs.json_path }}
```

### Method 2: SVG + JSON Output

If you prefer a visual report in addition to the raw data, you can enable SVG generation. This method uses the metrics from the JSON payload to generate a timeline report (`workflow_status.svg`).

In this workflow, the `generate_svg_report: 'true'` option is set. The Action will generate the SVG file and expose its path via the `svg_path` output variable.

**Example Usage:**

```yaml
name: Global Telemetry Observer (SVG + JSON)

on:
  push:
  pull_request:

permissions:
  actions: read
  contents: write

jobs:
  telemetry:
    runs-on: ubuntu-latest
    steps:
      - name: Observer Telemetry Agent
        uses: HimanM/Github-Actions-Telemetry@main
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          generate_svg_report: 'true'

      - name: Upload SVG Timeline Report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: workflow-svg-report
          path: ${{ steps.observer.outputs.svg_path || 'workflow_status.svg' }}
```

### Examples with External Webhook

If you wish to POST the resulting JSON telemetry directly to your API, ensure you use GitHub Secrets to mask your credentials.

```yaml
      - name: Observer Telemetry Agent
        uses: HimanM/Github-Actions-Telemetry@main
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          api_url: 'https://api.yourdomain.com/v1/telemetry'
          api_key: ${{ secrets.TELEMETRY_API_KEY }} # Note: Always use Secrets! Example: <MASKED_TOKEN>
```

## Configuration

The composite action (`action.yml`) accepts the following inputs:

* `github_token` (Required): GitHub token for API access.
* `initial_delay` (Optional): Initial wait time (in seconds) before tracking starts. Default: `60`.
* `max_timeout` (Optional): Global timeout (in seconds) before giving up. Default: `3600`.
* `poll_interval` (Optional): Seconds to wait between API polls. Default: `15`.
* `ignored_workflows` (Optional): Comma separated list of workflow names to ignore. Default: `Observer,CodeQL,Dependabot`.
* `api_url` (Optional): Optional URL to POST the JSON payload to.
* `api_key` (Optional): Optional Auth Bearer token/key for the API Upload.
* `generate_svg_report` (Optional): Generate an SVG visual report from the metrics. Default: `false`.

## Troubleshooting

### Triggering on Manual Workflows

GitHub Actions handles manual triggers (`workflow_dispatch`) as targeted events. When a user manually triggers a workflow, GitHub does not broadcast a generic event to the rest of the repository, meaning the Observer would not automatically start. 

To solve this, the Observer utilizes the `workflow_run` trigger listening for the `requested` type. 

**Important Configuration Note:** 
To ensure the Observer starts when specific manual workflows are executed, you must explicitly list those workflow names in the `.github/workflows/observer.yml` file under the `workflow_run.workflows` array. 

Example:
```yaml
  workflow_run:
    workflows: 
      - "01 - Test Manual Trigger"
      - "My Custom Manual Workflow"
    types:
      - requested
```

## Developer Section

If you would like to test or modify the scripts locally:

1.  **Clone the repository.**
2.  **Ensure Python 3.11 is installed.**
3.  **Install dependencies:** `pip install requests`.
4.  **Local Execution:**
    *   To run the observer script, supply the required environment variables:
        `GITHUB_TOKEN=<MASKED_TOKEN> GITHUB_REPOSITORY=owner/repo GITHUB_SHA=abc123 python scripts/observer.py`
    *   To test SVG generation locally, place a sample JSON file in the `test_jsons` directory and run:
        `python scripts/generate_svg.py`


## Included Test Workflows

To ensure coverage, synthetic test workflows have been scaffolded to mimic active usage so the Observer can validate recording operations:
- `01 - Test Manual Trigger`
- `02 - Test Commit Trigger`
- `03 - Test Long Running` (Simulates heavy load taking 30+ seconds)
- `04 - Test Upstream Dependent`
- `05 - Test Downstream Dependent` (Only executes when 04 finishes successfully)
- `06 - Test Failed Action`

## Data Fields Output

The observer generates a `.json` object containing several key pieces of information regarding the workflow session. 

### Global Keys (Always Present)
These fields are consistently outputted every time the observer completes:

| Field | Description | Example |
|---|---|---|
| `repository` | The full name of the repository in the format owner/repo. | `octocat/Hello-World` |
| `telemetry_session` | Canonical session ID using repo and SHA. | `octocat/Hello-World@abc123` |
| `head_sha` / `trigger_sha`| The commit SHA that triggered the workflow session. | `abc123...` |
| `event` | The name of the webhook event that triggered the observer. | `push`, `workflow_dispatch` |
| `commit` | Object containing commit metadata (author, message, timestamp). | `{"message": "fix auth issue"}` |
| `observer_started_at` | The exact UTC timestamp when the observer began evaluation. | `2024-05-19T10:15:30Z` |
| `total_workflows` | Total number of workflow definitions existing in the repository. | `6` |
| `workflows_ran` | Count of workflows that actually executed. | `3` |
| `workflows` | Array containing detailed objects of every workflow (ran or not). | `[{...}, {...}]` |

### Conditional Keys
These fields depend on the type of event or whether a specific workflow actually executed:

| Field | Description | Condition |
|---|---|---|
| `branch` | The branch or tag ref that triggered the session. | Usually present, but may differ during scheduled runs or PRs. |
| Workflow `jobs` | Array of detailed job and step metrics within a workflow. | Only populated for workflows where `ran` is `true`. Workflows that didn't trigger will only show `{ "ran": false }` and basic IDs. |
| Workflow `run_id` / `run_number` | Execution identifiers for the workflow run. | Only present if the workflow actually ran. |
| Workflow `duration_seconds` | Calculated duration of the run. | Only present if the workflow completed (requires `started_at` and `updated_at`). |
| Workflow `last_run` | Object containing metadata about the most recent historical execution. | Only populated for workflows where `ran` is `false`. |
