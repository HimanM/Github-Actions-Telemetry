import os
import sys
import time
import json
import requests
from datetime import datetime, timezone

# --- Constants & Config ---
TOKEN = os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPOSITORY")
SHA = os.environ.get("GITHUB_SHA")
REF = os.environ.get("GITHUB_REF_NAME")
EVENT = os.environ.get("GITHUB_EVENT_NAME")
INITIAL_DELAY = int(os.environ.get("INITIAL_DELAY", "60"))

API_BASE = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json"
}

OUTPUT_DIR = "test_jsons"

IGNORED_WORKFLOW_NAMES = [x.strip() for x in os.environ.get("IGNORED_WORKFLOWS", "Observer,CodeQL,Dependabot").split(",") if x.strip()]
NON_TERMINAL_STATES = ["queued", "waiting", "requested", "pending", "in_progress"]
MAX_TIMEOUT_SECONDS = int(os.environ.get("MAX_TIMEOUT", "3600"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "15"))

EXTERNAL_API_URL = os.environ.get("API_URL")
EXTERNAL_API_KEY = os.environ.get("API_KEY")

# --- Utils ---
def get_paged(url, params=None):
    results = []
    if params is None:
        params = {}
    params["per_page"] = 100
    
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    
    if "items" in resp.json():
        results.extend(resp.json()["items"])
    elif "workflow_runs" in resp.json():
        results.extend(resp.json()["workflow_runs"])
    elif "workflows" in resp.json():
        results.extend(resp.json()["workflows"])
    elif "jobs" in resp.json():
        results.extend(resp.json()["jobs"])
    else:
        return resp.json()
        
    while "next" in resp.links:
        resp = requests.get(resp.links["next"]["url"], headers=HEADERS)
        resp.raise_for_status()
        
        js = resp.json()
        if "items" in js:
            results.extend(js["items"])
        elif "workflow_runs" in js:
            results.extend(js["workflow_runs"])
        elif "workflows" in js:
            results.extend(js["workflows"])
        elif "jobs" in js:
            results.extend(js["jobs"])
            
    return results

def get_run_duration(started_at, completed_at):
    try:
        start = datetime.strptime(started_at.replace('Z', '+0000'), "%Y-%m-%dT%H:%M:%S%z")
        end = datetime.strptime(completed_at.replace('Z', '+0000'), "%Y-%m-%dT%H:%M:%S%z")
        return int((end - start).total_seconds())
    except Exception:
        return None

# --- Main Logic ---

def main():
    if not all([TOKEN, REPO, SHA]):
        print("Missing required environment variables.")
        sys.exit(1)

    print(f"Observer started for {REPO} @ {SHA}")
    observer_started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Initial Delay
    print(f"Waiting {INITIAL_DELAY} seconds for initial workflow evaluations...")
    time.sleep(INITIAL_DELAY)

    # 2. Stabilization Loop
    print("Stabilizing workflow discovery...")
    start_time = time.time()
    last_run_count = -1
    stable_since = None

    while True:
        if time.time() - start_time > MAX_TIMEOUT_SECONDS:
            print("Timeout reached during stabilization phase.")
            break

        runs_url = f"{API_BASE}/repos/{REPO}/actions/runs"
        current_runs = get_paged(runs_url, params={"head_sha": SHA})
        
        # Exclude ignored
        current_runs = [r for r in current_runs if r["name"] not in IGNORED_WORKFLOW_NAMES]
        current_count = len(current_runs)
        
        if current_count != last_run_count:
            print(f"Run count changed from {last_run_count} to {current_count}. Resetting stable timer.")
            last_run_count = current_count
            stable_since = time.time()
        else:
            if stable_since and (time.time() - stable_since) >= 30:
                print(f"Workflow set stabilized with {current_count} runs.")
                break
        
        time.sleep(POLL_INTERVAL)

    # 3. Completion Detection Loop
    print("Waiting for all workflows to complete...")
    final_runs = []
    while True:
        if time.time() - start_time > MAX_TIMEOUT_SECONDS:
             print("Global timeout reached. Terminating wait loop.")
             final_runs = get_paged(f"{API_BASE}/repos/{REPO}/actions/runs", params={"head_sha": SHA})
             break

        runs = get_paged(f"{API_BASE}/repos/{REPO}/actions/runs", params={"head_sha": SHA})
        final_runs = [r for r in runs if r["name"] not in IGNORED_WORKFLOW_NAMES]

        non_terminal = [r for r in final_runs if r["status"] in NON_TERMINAL_STATES]
        
        if len(non_terminal) == 0:
            print("All monitored workflows have reached a terminal state.")
            break
        
        print(f"Waiting on {len(non_terminal)} workflows...")
        time.sleep(POLL_INTERVAL)

    # 4. Fetch All Valid Workflows (to detect what didn't run)
    all_workflows = get_paged(f"{API_BASE}/repos/{REPO}/actions/workflows")
    all_workflows = [w for w in all_workflows if w["name"] not in IGNORED_WORKFLOW_NAMES]

    # 5. Connect Runs and Calculate Job Metrics
    runs_by_wfid = {r["workflow_id"]: r for r in final_runs}
    workflows_ran = []
    workflows_not_triggered = []

    for wf in all_workflows:
        wf_id = wf["id"]
        if wf_id in runs_by_wfid:
            rn = runs_by_wfid[wf_id]
            jobs_url = f"{API_BASE}/repos/{REPO}/actions/runs/{rn['id']}/jobs"
            jobs_raw = get_paged(jobs_url)
            
            jobs = []
            for j in jobs_raw:
                steps = []
                for s in j.get("steps", []):
                    steps.append({
                        "number": s.get("number"),
                        "name": s.get("name"),
                        "status": s.get("status"),
                        "conclusion": s.get("conclusion"),
                        "started_at": s.get("started_at"),
                        "completed_at": s.get("completed_at")
                    })
                
                jobs.append({
                    "job_id": j["id"],
                    "name": j["name"],
                    "status": j["status"],
                    "conclusion": j["conclusion"],
                    "started_at": j["started_at"],
                    "completed_at": j["completed_at"],
                    "duration_seconds": get_run_duration(j.get("started_at",""), j.get("completed_at","")),
                    "runner_name": j.get("runner_name"),
                    "steps": steps
                })

            workflows_ran.append({
                "workflow_id": wf_id,
                "workflow_name": wf["name"],
                "run_id": rn["id"],
                "run_number": rn["run_number"],
                "head_sha": rn["head_sha"],
                "branch": rn.get("head_branch"),
                "event": rn.get("event"),
                "actor": rn.get("actor", {}).get("login"),
                "status": rn["status"],
                "conclusion": rn["conclusion"],
                "created_at": rn["created_at"],
                "started_at": rn.get("run_started_at"),
                "completed_at": rn["updated_at"], # updated_at approximates completed for terminal
                "duration_seconds": get_run_duration(rn.get("run_started_at", ""), rn.get("updated_at", "")),
                "html_url": rn["html_url"],
                "jobs": jobs,
                "exists": True,
                "ran": True
            })
        else:
            last_run_info = None
            try:
                lr_resp = requests.get(f"{API_BASE}/repos/{REPO}/actions/workflows/{wf_id}/runs", headers=HEADERS, params={"per_page": 1})
                if lr_resp.status_code == 200:
                    runs_list = lr_resp.json().get("workflow_runs", [])
                    if runs_list:
                        lr = runs_list[0]
                        last_run_info = {
                            "run_id": lr.get("id"),
                            "run_number": lr.get("run_number"),
                            "event": lr.get("event"),
                            "head_sha": lr.get("head_sha"),
                            "status": lr.get("status"),
                            "conclusion": lr.get("conclusion"),
                            "created_at": lr.get("created_at"),
                            "started_at": lr.get("run_started_at"),
                            "completed_at": lr.get("updated_at"),
                            "duration_seconds": get_run_duration(lr.get("run_started_at", ""), lr.get("updated_at", "")),
                            "html_url": lr.get("html_url")
                        }
            except Exception as e:
                print(f"Warning: Failed to fetch last run for workflow {wf_id}: {e}")

            workflows_not_triggered.append({
                "workflow_id": wf_id,
                "workflow_name": wf["name"],
                "head_sha": SHA,
                "exists": True,
                "ran": False,
                "last_run": last_run_info
            })

    # 6. Fetch Commit Metadata
    commit_data = {}
    try:
        commit_resp = requests.get(f"{API_BASE}/repos/{REPO}/commits/{SHA}", headers=HEADERS)
        if commit_resp.status_code == 200:
            cj = commit_resp.json()
            author_info = cj.get("commit", {}).get("author", {})
            commit_data = {
                "sha": SHA,
                "message": cj.get("commit", {}).get("message"),
                "author_name": author_info.get("name"),
                "author_email": author_info.get("email"),
                "timestamp": author_info.get("date")
            }
    except Exception as e:
        print(f"Warning: Failed to fetch commit info: {e}")

    observer_completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 7. Final JSON Assembly
    payload = {
        "repository": REPO,
        "telemetry_session": f"{REPO}@{SHA}",
        "head_sha": SHA,
        "trigger_sha": SHA,
        "branch": REF,
        "event": EVENT,
        "commit": commit_data,
        "observer_started_at": observer_started_at,
        "observer_completed_at": observer_completed_at,
        "total_workflows": len(all_workflows),
        "workflows_ran": len(workflows_ran),
        "workflows_not_triggered": len(workflows_not_triggered),
        "workflows": workflows_ran + workflows_not_triggered
    }

    print("Outputting telemetry payload...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    file_time = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short_sha = SHA[:7] if SHA else "unknown"
    file_name = f"main_{file_time}_{short_sha}.json"
    
    out_path = os.path.join(OUTPUT_DIR, file_name)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
        
    print(f"Telemetry saved successfully to {out_path}")
    
    # 8. External API Upload (Optional)
    if EXTERNAL_API_URL:
        print("Uploading telemetry to external API...")
        upload_headers = {"Content-Type": "application/json"}
        if EXTERNAL_API_KEY:
            upload_headers["Authorization"] = f"Bearer {EXTERNAL_API_KEY}"
            
        try:
            res = requests.post(EXTERNAL_API_URL, json=payload, headers=upload_headers)
            res.raise_for_status()
            print("Successfully uploaded telemetry payload.")
        except Exception as e:
            print(f"Failed to upload telemetry to external API: {e}")

if __name__ == "__main__":
    main()
