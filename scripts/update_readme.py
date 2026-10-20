#!/usr/bin/env python3
"""Fill README.md marker blocks with live data from the GitHub API.

Blocks (replaced in place):
  <!--ACTIVITY:START--> ... <!--ACTIVITY:END-->   recent public activity
  <!--REPOS:START-->    ... <!--REPOS:END-->      most recently updated repositories

Usage: GITHUB_TOKEN=... python scripts/update_readme.py <username> [README.md]
Standard library only.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"


def get(path: str, token: str):
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def ago(iso: str) -> str:
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - then
    days = delta.days
    if days >= 30:
        return f"{days // 30} mo ago"
    if days >= 1:
        return f"{days} d ago"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours} h ago"
    return "just now"


def describe(event: dict) -> str | None:
    repo = event["repo"]["name"]
    link = f"[{repo}](https://github.com/{repo})"
    payload = event["payload"]
    kind = event["type"]
    if kind == "PushEvent":
        commits = payload.get("commits", [])
        if not commits:
            return None
        message = commits[-1]["message"].splitlines()[0][:72]
        count = payload.get("size", len(commits))
        noun = "commit" if count == 1 else "commits"
        return f"Pushed {count} {noun} to {link} – _{message}_"
    if kind == "PullRequestEvent":
        pr = payload["pull_request"]
        return f"{payload['action'].capitalize()} PR [#{pr['number']}]({pr['html_url']}) in {link} – _{pr['title'][:72]}_"
    if kind == "IssuesEvent":
        issue = payload["issue"]
        return f"{payload['action'].capitalize()} issue [#{issue['number']}]({issue['html_url']}) in {link}"
    if kind == "CreateEvent" and payload.get("ref_type") == "repository":
        return f"Created repository {link}"
    if kind == "ReleaseEvent":
        release = payload["release"]
        return f"Released [{release['tag_name']}]({release['html_url']}) in {link}"
    return None


def activity_block(user: str, token: str) -> str:
    events = get(f"/users/{user}/events/public?per_page=50", token)
    lines = []
    for event in events:
        text = describe(event)
        if text:
            lines.append(f"- {text} · <sub>{ago(event['created_at'])}</sub>")
        if len(lines) == 6:
            break
    return "\n".join(lines) if lines else "_No public activity yet._"


def repos_block(user: str, token: str) -> str:
    repos = get(f"/users/{user}/repos?sort=pushed&per_page=30&type=owner", token)
    rows = [
        "| Repository | Description | Language | ★ | Updated |",
        "| :-- | :-- | :-- | --: | :-- |",
    ]
    shown = 0
    for repo in repos:
        if repo["fork"] or repo["name"].lower() == user.lower():
            continue
        description = (repo["description"] or "–").replace("|", "/")
        rows.append(
            f"| [**{repo['name']}**]({repo['html_url']}) | {description} | "
            f"{repo['language'] or '–'} | {repo['stargazers_count']} | {ago(repo['pushed_at'])} |"
        )
        shown += 1
        if shown == 6:
            break
    return "\n".join(rows) if shown else "_No public repositories yet._"


def replace_block(text: str, name: str, content: str) -> str:
    pattern = re.compile(rf"(<!--{name}:START-->)(.*?)(<!--{name}:END-->)", re.DOTALL)
    if not pattern.search(text):
        raise SystemExit(f"marker {name} not found in README")
    return pattern.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(3)}", text)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: update_readme.py <username> [README.md]")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")
    user = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else "README.md"
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    text = replace_block(text, "ACTIVITY", activity_block(user, token))
    text = replace_block(text, "REPOS", repos_block(user, token))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"updated {path}")


if __name__ == "__main__":
    main()
