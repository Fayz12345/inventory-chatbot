"""
Create Azure DevOps Epics and User Stories from User_Stories.md.

Usage: python scripts/create_ado_stories.py
"""

import re
import requests
import base64
import time
import sys
import os

ORG = "https://dev.azure.com/bridgewireless"
PROJECT = "BW Digital Transformation"
PAT = os.getenv("AZURE_DEVOPS_PAT")
API_VERSION = "7.1"

if not PAT:
    print("Missing AZURE_DEVOPS_PAT environment variable.")
    sys.exit(1)

AUTH = base64.b64encode(f":{PAT}".encode()).decode()
HEADERS = {
    "Authorization": f"Basic {AUTH}",
    "Content-Type": "application/json-patch+json",
}

BASE_URL = f"{ORG}/{PROJECT}/_apis/wit/workitems"


def create_work_item(work_item_type, title, description="", acceptance_criteria="", parent_id=None):
    """Create a work item in Azure DevOps and return its ID."""
    url = f"{BASE_URL}/${work_item_type}?api-version={API_VERSION}"

    body = [
        {"op": "add", "path": "/fields/System.Title", "value": title},
    ]

    if description:
        body.append({"op": "add", "path": "/fields/System.Description", "value": description})

    if acceptance_criteria:
        body.append({
            "op": "add",
            "path": "/fields/Microsoft.VSTS.Common.AcceptanceCriteria",
            "value": acceptance_criteria,
        })

    if parent_id:
        body.append({
            "op": "add",
            "path": "/relations/-",
            "value": {
                "rel": "System.LinkTypes.Hierarchy-Reverse",
                "url": f"{ORG}/{PROJECT}/_apis/wit/workItems/{parent_id}",
            },
        })

    resp = requests.post(url, headers=HEADERS, json=body)
    if resp.status_code in (200, 201):
        item = resp.json()
        return item["id"]
    else:
        print(f"  ERROR ({resp.status_code}): {resp.text[:200]}")
        return None


def parse_stories(filepath):
    """Parse User_Stories.md into structured epics and stories."""
    with open(filepath, "r") as f:
        content = f.read()

    epics = []
    current_epic = None
    current_story = None

    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # Epic header: ## Epic 0: Title or ## Epic 1A: Title
        epic_match = re.match(r'^## Epic (\S+?)[:] (.+)', line)
        if epic_match:
            if current_story and current_epic:
                current_epic["stories"].append(current_story)
                current_story = None
            current_epic = {
                "id": epic_match.group(1),
                "title": epic_match.group(2).strip(),
                "description": "",
                "stories": [],
            }
            epics.append(current_epic)
            # Grab the blockquote description if present
            i += 1
            desc_lines = []
            while i < len(lines) and (lines[i].startswith(">") or lines[i].strip() == ""):
                if lines[i].startswith(">"):
                    desc_lines.append(lines[i].lstrip("> ").strip())
                i += 1
            if desc_lines:
                current_epic["description"] = " ".join(desc_lines)
            continue

        # Story header: ### 0.1 — Title or ### 1A.1 — Title
        story_match = re.match(r'^### (\S+) \S+ (.+)', line)
        if story_match and current_epic:
            if current_story:
                current_epic["stories"].append(current_story)
            current_story = {
                "id": story_match.group(1),
                "title": story_match.group(2).strip(),
                "description_lines": [],
                "ac_lines": [],
            }
            i += 1
            continue

        # Inside a story — collect description and acceptance criteria
        if current_story:
            if line.strip().startswith("**Acceptance Criteria:**"):
                # Collect AC lines
                i += 1
                while i < len(lines):
                    ac_line = lines[i]
                    if ac_line.strip().startswith("- ["):
                        current_story["ac_lines"].append(ac_line.strip().lstrip("- [ ] ").lstrip("- [x] "))
                    elif ac_line.strip() == "" and i + 1 < len(lines) and not lines[i + 1].strip().startswith("- ["):
                        break
                    elif not ac_line.strip().startswith("- [") and ac_line.strip() != "":
                        break
                    i += 1
                continue
            else:
                if line.strip():
                    current_story["description_lines"].append(line.strip())

        i += 1

    # Don't forget the last story
    if current_story and current_epic:
        current_epic["stories"].append(current_story)

    return epics


def build_description(story):
    """Build HTML description from story lines."""
    raw = " ".join(story["description_lines"])

    # Extract As a / I want / So that
    as_match = re.search(r'\*\*As an?\*\*\s*(.+?)(?:,|\s*\*\*)', raw)
    want_match = re.search(r'\*\*I want\*\*\s*(.+?)(?:,|\s*\*\*)', raw)
    so_match = re.search(r'\*\*so that\*\*\s*(.+?)(?:\.|$)', raw)

    parts = []
    if as_match:
        parts.append(f"<b>As a</b> {as_match.group(1).strip()}")
    if want_match:
        parts.append(f"<b>I want</b> {want_match.group(1).strip()}")
    if so_match:
        parts.append(f"<b>so that</b> {so_match.group(1).strip()}.")

    return "<br>".join(parts) if parts else raw.replace("**", "")


def build_acceptance_criteria(story):
    """Build HTML acceptance criteria list."""
    if not story["ac_lines"]:
        return ""
    items = "".join(f"<li>{ac}</li>" for ac in story["ac_lines"])
    return f"<ul>{items}</ul>"


def main():
    filepath = "User_Stories.md"
    print(f"Parsing {filepath}...")
    epics = parse_stories(filepath)

    total_epics = len(epics)
    total_stories = sum(len(e["stories"]) for e in epics)
    print(f"Found {total_epics} epics with {total_stories} stories total.\n")

    # Test connection first
    print("Testing Azure DevOps connection...")
    test_url = f"{ORG}/_apis/projects?api-version={API_VERSION}"
    test_headers = {"Authorization": f"Basic {AUTH}"}
    resp = requests.get(test_url, headers=test_headers)
    if resp.status_code != 200:
        print(f"Connection failed ({resp.status_code}): {resp.text[:200]}")
        sys.exit(1)
    print("Connected successfully.\n")

    created = {"epics": 0, "stories": 0, "errors": 0}

    for epic in epics:
        epic_title = f"Epic {epic['id']}: {epic['title']}"
        print(f"Creating Epic: {epic_title}")
        epic_ado_id = create_work_item("Epic", epic_title, description=epic.get("description", ""))

        if not epic_ado_id:
            print(f"  FAILED to create epic — skipping its stories")
            created["errors"] += 1
            continue

        print(f"  Created Epic #{epic_ado_id}")
        created["epics"] += 1
        time.sleep(0.3)

        for story in epic["stories"]:
            story_title = f"{story['id']} — {story['title']}"
            description = build_description(story)
            ac = build_acceptance_criteria(story)

            print(f"  Creating Story: {story_title}")
            story_id = create_work_item("User Story", story_title, description, ac, parent_id=epic_ado_id)

            if story_id:
                print(f"    Created Story #{story_id}")
                created["stories"] += 1
            else:
                print(f"    FAILED")
                created["errors"] += 1

            time.sleep(0.3)

        print()

    print("=" * 50)
    print(f"Done! Created {created['epics']} epics and {created['stories']} stories. Errors: {created['errors']}")
    print(f"\nView your board: {ORG}/{PROJECT}/_backlogs")


if __name__ == "__main__":
    main()
