# GitHub Actions Centralized Telemetry Observer

This repository implements a Centralized Workflow Telemetry Collector (Observer) designed to securely monitor and measure all workflow activity tied to a specific Commit SHA, without interfering directly with the workloads being monitored.

Per the MVP design, this pattern removes the need to embed telemetry logic directly inside other workflow files. Instead, the centralized observer automatically initializes, discovers what is executing, waits for all executions to finish, and extracts their structural telemetry (including durations, job steps, and event metadata).

## Architecture

* **Observer Trigger**: Triggered automatically via `push`, `pull_request`, and `workflow_dispatch`. It is also configured via `workflow_run` to capture manual triggers.
* **Identifier**: Bound strictly to `github.sha`.
* **Stabilization Engine**: Listens to GitHub Action API responses until the number of reported workflow runs matching the trigger SHA stabilizes. This accounts for asynchronous creation and polling latency.
* **Metrics Collector**: Harvests workflow run metadata, resolves internal job details, and attaches precise timestamps alongside Git commit history.

## How It Works

1. A repository event occurs (e.g., a push, a pull request, or a manual trigger).
2. The `.github/workflows/observer.yml` workflow begins execution. It possesses native logic to ignore evaluating itself.
3. The observer utilizes a standardized composite action (`action.yml`) ensuring minimal setup in client workflows.
4. It polls the repository's action runs endpoints continuously until it confirms all workflows linked to the SHA have reached a terminal state.
5. It exports a comprehensive JSON payload to `test_jsons/main_{datetime}_{sha}.json`.
6. The payload is uploaded as a standard GitHub Action Artifact named `telemetry-test-jsons`.

### Integrating into other Repositories

Because the core polling and visualization logic is tightly wrapped inside a Composite Action (`action.yml`), integrating this into *any* other GitHub repository is incredibly simple. Other users do not need to clone this repository; they only need to reference it directly using the `uses:` syntax.

Here is a complete usage example to drop into any external repository:

```yaml
name: Global Telemetry Observer

on:
  push:
  pull_request:

permissions:
  actions: read   # Required to read workflow run statuses
  contents: read  # Required to grab commit metadata

jobs:
  telemetry:
    runs-on: ubuntu-latest
    steps:
      - name: Observer Telemetry Agent
        uses: HimanM/Github-Actions-Telemetry@main
        with:
          # Required: GitHub Token to securely authenticate with GitHub's REST API
          github_token: ${{ secrets.GITHUB_TOKEN }}
          
          # Optional Configuration (Defaults shown below)
          initial_delay: '60'               # Wait 60s before tracking starts to allow other jobs to queue
          max_timeout: '3600'               # Global timeout in seconds (1 hour) before giving up
          poll_interval: '15'               # Seconds between API polls for live jobs
          ignored_workflows: 'Observer,CodeQL,Dependabot' # Comma-separated list to prevent recursion
          
          # Optional: External webhook export
          # api_url: 'https://api.yourdomain.com/v1/telemetry'
          # api_key: ${{ secrets.TELEMETRY_API_KEY }}

          # Optional: Generate a visual SVG timeline report (Default: false)
          # generate_svg_report: 'true'

      # By default, the Action generates a comprehensive JSON payload.
      # You can upload this JSON data as an artifact to review the raw metrics.
      - name: Upload JSON Telemetry Data
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: telemetry-test-jsons
          # The Action exposes the exact generated JSON path for you!
          path: ${{ steps.observer.outputs.json_path }}

      # (Optional) If you set `generate_svg_report: 'true'` above, 
      # the Action also outputs the path to the SVG diagram so you can upload it!
      # - name: Upload SVG Timeline Report
      #   if: always()
      #   uses: actions/upload-artifact@v4
      #   with:
      #     name: workflow-svg-report
      #     path: ${{ steps.observer.outputs.svg_path || 'workflow_status.svg' }}
```

## Triggering on Manual Workflows

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

## Included Test Workflows

To ensure coverage, synthetic test workflows have been scaffolded to mimic active usage so the Observer can validate recording operations:
- `01 - Test Manual Trigger`
- `02 - Test Commit Trigger`
- `03 - Test Long Running` (Simulates heavy load taking 30+ seconds)
- `04 - Test Upstream Dependent`
- `05 - Test Downstream Dependent` (Only executes when 04 finishes successfully)

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
