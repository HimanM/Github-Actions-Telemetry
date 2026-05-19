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

Because the inner workings of the Python polling logic are tightly wrapped in a single composite action, utilizing this from any arbitrary repository is incredibly simple. All you need is the token, and an optional initial delay.

```yaml
jobs:
  telemetry:
    runs-on: ubuntu-latest
    steps:
      # Use the centralized observer directly from this repository
      - name: Observer Telemetry Agent
        uses: HimanM/Github-Actions-Telemetry@main
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          initial_delay: '45' # Defaults to 60 if not specified
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
