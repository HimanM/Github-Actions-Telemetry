import os
import json
import glob
import sys
from datetime import datetime

# Read IO paths from environment or fallback to old defaults for testing
JSON_PATH = os.environ.get("JSON_PATH")
OUTPUT_SVG = os.environ.get("OUTPUT_SVG", "workflow_status.svg")

def get_status_color(status):
    if status == "success":
        return "#238636" # GitHub green
    elif status in ["failure", "timed_out", "startup_failure"]:
        return "#da3633" # GitHub red
    elif status in ["cancelled", "skipped", "skipped/not run", "not run"]:
        return "#6e7681" # Gray
    return "#d29922" # Yellow for pending/others

def generate_svg(json_path, output_path):
    print(f"Reading JSON from: {json_path}")
    with open(json_path, "r") as f:
        data = json.load(f)

    workflows = data.get("workflows", [])
    
    # Calculate dynamic height
    width = 650
    row_height = 65 # Increased to fit the new timestamp and pill design
    header_height = 70
    padding = 20
    
    total_height = header_height + (len(workflows) * row_height) + padding

    sha = data.get("head_sha", "Unknown")[:7]
    display_date = data.get("observer_started_at", datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
    
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_height}" viewBox="0 0 {width} {total_height}">',
        f'<style>',
        f'  .bg {{ fill: #ffffff; }}',
        f'  .card {{ fill: #f6f8fa; stroke: #d0d7de; stroke-width: 1px; rx: 6px; }}',
        f'  .text {{ font-family: "Google Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; fill: #24292f; }}',
        f'  .title {{ font-size: 20px; font-weight: 600; fill: #000000; }}',
        f'  .subtitle {{ font-size: 13px; fill: #57606a; }}',
        f'  .wf-name {{ font-size: 14px; font-weight: 500; }}',
        f'  .wf-meta {{ font-size: 13px; font-weight: 600; text-anchor: end; }}',
        f'  .timestamp {{ font-size: 11px; fill: #57606a; }}',
        f'</style>',
        f'<rect class="bg" width="{width}" height="{total_height}" rx="10" ry="10"/>',
        
        # Header
        f'<text x="25" y="35" class="text title">Workflow Execution Report</text>',
        f'<text x="25" y="55" class="text subtitle">Commit: {sha} • Triggered: {display_date.replace("T", " ").replace("Z", "")}</text>',
    ]

    y_offset = header_height

    for idx, wf in enumerate(workflows):
        name = wf.get("workflow_name", "Unknown")
        ran = wf.get("ran", False)
        
        # Gathering steps if available
        steps = []
        if ran:
            status = wf.get("conclusion", wf.get("status", "unknown"))
            duration = wf.get("duration_seconds", 0)
            time_str = f"{duration}s"
            timestamp = wf.get("started_at", "Unknown").replace("T", " ").replace("Z", "")
            event_type = wf.get("event", "unknown")
            timestamp_desc = f"{timestamp} • trigger: {event_type}"
            
            for j in wf.get("jobs", []):
                for s in j.get("steps", []):
                    steps.append(s)
        else:
            last_run = wf.get("last_run")
            if last_run:
                status = last_run.get("conclusion", "skipped/not run")
                time_str = f"Last: {last_run.get('duration_seconds', 0)}s"
                timestamp = last_run.get("started_at", "Unknown").replace("T", " ").replace("Z", "")
                event_type = last_run.get("event", "historical")
                timestamp_desc = f"{timestamp} • prev trigger: {event_type}"
                # We typically don't have historical steps for non-triggered runs in our simple JSON payload
            else:
                status = "not run"
                time_str = "N/A"
                timestamp_desc = "No history"

        color = get_status_color(status)
        
        # Row Background Card
        svg.append(f'<rect x="20" y="{y_offset}" width="{width-40}" height="55" class="card" />')
        
        # Status dot
        svg.append(f'<circle cx="35" cy="{y_offset + 25}" r="6" fill="{color}" />')
        
        # Workflow Name and Timestamp underneath
        svg.append(f'<text x="50" y="{y_offset + 25}" class="text wf-name">{name}</text>')
        svg.append(f'<text x="50" y="{y_offset + 42}" class="text timestamp">{timestamp_desc}</text>')
        
        # Step visualization 'Pill'
        pill_width = 160
        pill_height = 8
        pill_x = width - 35 - pill_width
        pill_y = y_offset + 35
        
        if steps:
            step_width = pill_width / len(steps)
            
            # Setup a clipPath to make the group of rectangles strictly rounded like a pill
            clip_id = f"pill-clip-{idx}"
            svg.append(f'<clipPath id="{clip_id}"><rect x="{pill_x}" y="{pill_y}" width="{pill_width}" height="{pill_height}" rx="4" ry="4" /></clipPath>')
            svg.append(f'<g clip-path="url(#{clip_id})">')
            
            # Base background for safety in case of math rounding
            svg.append(f'<rect x="{pill_x}" y="{pill_y}" width="{pill_width}" height="{pill_height}" fill="#ebecf0" />')
            
            for i, step in enumerate(steps):
                step_conc = step.get("conclusion", step.get("status", ""))
                step_color = get_status_color(step_conc)
                s_x = pill_x + (i * step_width)
                svg.append(f'<rect x="{s_x}" y="{pill_y}" width="{step_width}" height="{pill_height}" fill="{step_color}" />')
                
                # Add gap line between steps if there's more than 1
                if i < len(steps) - 1:
                    svg.append(f'<line x1="{s_x + step_width}" y1="{pill_y}" x2="{s_x + step_width}" y2="{pill_y + pill_height}" stroke="#ffffff" stroke-width="1.5" />')
            
            svg.append('</g>')
        else:
            # Solid color pill for historical runs with no granular steps
            pill_color = "#ebecf0" if status == "not run" else get_status_color(status)
            svg.append(f'<rect x="{pill_x}" y="{pill_y}" width="{pill_width}" height="{pill_height}" rx="4" ry="4" fill="{pill_color}" />')

        # Status and Time (placed upper right)
        display_text = f"{status.upper()} ({time_str})"
        svg.append(f'<text x="{width - 35}" y="{y_offset + 25}" class="text wf-meta" fill="{color}">{display_text}</text>')

        y_offset += row_height

    svg.append('</svg>')

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg))
    print(f"Successfully generated SVG at: {output_path}")

def main():
    if JSON_PATH and os.path.exists(JSON_PATH):
        target_json = JSON_PATH
    else:
        # Fallback for local testing if env vars aren't set
        input_dir = "test_jsons"
        if not os.path.exists(input_dir):
            print(f"Directory {input_dir} does not exist and JSON_PATH not set.")
            sys.exit(1)

        # Automatically find the most recent JSON file in the directory
        json_files = glob.glob(os.path.join(input_dir, "*.json"))
        if not json_files:
            print(f"No JSON files found in {input_dir}.")
            sys.exit(1)
            
        target_json = max(json_files, key=os.path.getctime)
        
    generate_svg(target_json, OUTPUT_SVG)

if __name__ == "__main__":
    main()
