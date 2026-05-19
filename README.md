# GitHub Actions Centralized Telemetry Observer 🚀

This repository implements a **Centralized Workflow Telemetry Collector** (Observer) designed to securely monitor and measure all workflow activity tied to a specific Commit SHA, without interfering directly with the workloads being monitored.

Per the MVP design, this pattern removes the need to embed telemetry logic directly inside other workflow files. Instead, the centralized observer automatically spins up, discovers what is executing, waits for all executions to finish, and extracts their structural telemetry (Durations, Job Steps, Event Metadata).

## 🛠️ Architecture

* **Observer Trigger**: Triggered automatically via `push`, `pull_request`, and `workflow_dispatch`.
* **Identifier**: Bound strictly to `github.sha`.
* **Stabilization Engine**: Listens heavily to GitHub Action API responses until the number of reported workflow runs matching the trigger SHA stabilizes (in case of asynchronous creation/polling latency).
* **Metrics Collector**: Harvests workflow run metadata, resolves internal job details, and attaches precise timestamps alongside Git commit history.

## 🚀 How it works
1. You push a commit or trigger a workflow manually.
2. The `.github/workflows/observer.yml` starts up automatically (ignoring itself natively).
3. The observer runs `scripts/observer.py` using `requests` utilizing the actions `GITHUB_TOKEN`.
4. It polls the repository's action runs endpoints continuously until it confirms all workflows linked to the SHA have completed.
5. It exports an exhaustively detailed `main_{datetime}_{sha}.json` payload inside `test_jsons/`.
6. Finally, the payload is uploaded as a standard GitHub Action Artifact named `telemetry-test-jsons`.

## 📂 Included Test Workflows

To ensure coverage, 5 synthetic test workflows have been scaffolded to mimic active usage so the Observer can successfully record them:
- `01 - Test Manual Trigger`
- `02 - Test Commit Trigger`
- `03 - Test Long Running` (Simulates heavy load taking 30+ seconds)
- `04 - Test Upstream Dependent`
- `05 - Test Downstream Dependent` (Only fires when 04 finishes successfully)
