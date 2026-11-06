#!/usr/bin/env python3
"""Generate self-hosted GitHub stats SVG cards for the profile README.

Runs in GitHub Actions with GITHUB_TOKEN, so the profile does not depend on
third-party stats services. Usage: generate_stats.py <login> <out_dir>
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape

API = "https://api.github.com/graphql"

# Theme (matches the README banner)
BG = "#0d1117"
BORDER = "#30363d"
TITLE = "#38bdf8"
TEXT = "#c9d1d9"
MUTED = "#8b949e"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"

# Languages whose bytes are mostly data or boilerplate rather than code
IGNORED_LANGS = {"Roff", "TeX", "Rich Text Format"}


def gql(query, variables, token):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


USER_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes {
        name
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection { contributionYears }
  }
}
"""

YEAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def collect(login, token):
    user = gql(USER_QUERY, {"login": login}, token)["user"]
    repos = user["repositories"]["nodes"]

    langs = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name in IGNORED_LANGS:
                continue
            entry = langs.setdefault(name, {"size": 0, "color": edge["node"]["color"] or MUTED})
            entry["size"] += edge["size"]

    commits = 0
    days = {}
    for year in sorted(user["contributionsCollection"]["contributionYears"]):
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        cc = gql(YEAR_QUERY, {"login": login, "from": start.isoformat(), "to": end.isoformat()}, token)[
            "user"]["contributionsCollection"]
        commits += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        for week in cc["contributionCalendar"]["weeks"]:
            for d in week["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    return {
        "stars": sum(r["stargazerCount"] for r in repos),
        "repos": user["repositories"]["totalCount"],
        "commits": commits,
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "followers": user["followers"]["totalCount"],
        "contributions": sum(days.values()),
        "active_days": sum(1 for c in days.values() if c),
        "longest_streak": longest_streak(days),
        "since": user["createdAt"][:4],
        "languages": langs,
    }


def longest_streak(days):
    best = run = 0
    prev = None
    for ds in sorted(days):
        d = date.fromisoformat(ds)
        if days[ds]:
            run = run + 1 if prev and d - prev == timedelta(days=1) else 1
            prev = d
            best = max(best, run)
        else:
            run, prev = 0, None
    return best


def fmt(n):
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


# Simple 16px octicon-style paths
ICONS = {
    "star": "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z",
    "commit": "M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z",
    "repo": "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.087a.249.249 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z",
    "pr": "M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354ZM3.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z",
    "calendar": "M4.75 0a.75.75 0 0 1 .75.75V2h5V.75a.75.75 0 0 1 1.5 0V2h1.25c.966 0 1.75.784 1.75 1.75v10.5A1.75 1.75 0 0 1 13.25 16H2.75A1.75 1.75 0 0 1 1 14.25V3.75C1 2.784 1.784 2 2.75 2H4V.75A.75.75 0 0 1 4.75 0ZM2.5 7.5v6.75c0 .138.112.25.25.25h10.5a.25.25 0 0 0 .25-.25V7.5Zm10.75-4H2.75a.25.25 0 0 0-.25.25V6h11V3.75a.25.25 0 0 0-.25-.25Z",
    "flame": "M9.533.753V.752c.217 2.385 1.463 3.626 2.653 4.81C13.37 6.74 14.498 7.863 14.498 10c0 3.5-3 6-6.5 6S1.5 13.512 1.5 10c0-1.298.536-2.56 1.425-3.286.376-.308.862 0 1.035.454C4.46 8.487 5.18 9 5.998 9c.716 0 1.27-.4 1.27-1.25 0-.637-.35-1.248-.776-1.981C5.703 4.412 4.75 2.77 6.17.27A.501.501 0 0 1 6.613 0c1.09.023 2.623.243 2.92.753Z",
}


def card(width, height, title, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <style>
    .t {{ font: 600 18px {FONT}; fill: {TITLE}; }}
    .l {{ font: 400 14px {FONT}; fill: {TEXT}; }}
    .v {{ font: 700 14px {FONT}; fill: #ffffff; }}
    .m {{ font: 400 12px {FONT}; fill: {MUTED}; }}
    .row {{ opacity: 0; animation: in .5s ease-out forwards; }}
    @keyframes in {{ from {{ opacity: 0; transform: translateX(-6px); }} to {{ opacity: 1; transform: none; }} }}
  </style>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="{BG}" stroke="{BORDER}"/>
  <text x="25" y="38" class="t">{escape(title)}</text>
{body}
</svg>
"""


def stats_svg(s):
    rows = [
        ("star", "Total stars", fmt(s["stars"])),
        ("commit", "Total commits", fmt(s["commits"])),
        ("repo", "Public repositories", fmt(s["repos"])),
        ("calendar", "Contributions", fmt(s["contributions"])),
        ("flame", "Longest streak", f'{s["longest_streak"]} days'),
    ]
    body = []
    for i, (icon, label, value) in enumerate(rows):
        y = 70 + i * 26
        body.append(
            f'  <g class="row" style="animation-delay:{150 + i * 120}ms">'
            f'<path transform="translate(25,{y - 13})" fill="{TITLE}" d="{ICONS[icon]}"/>'
            f'<text x="52" y="{y}" class="l">{label}</text>'
            f'<text x="300" y="{y}" class="v" text-anchor="end">{value}</text></g>'
        )
    body.append(f'  <text x="25" y="{70 + len(rows) * 26 + 4}" class="m">On GitHub since {s["since"]}</text>')
    return card(330, 225, "GitHub Stats", "\n".join(body))


def langs_svg(s, top=6):
    langs = sorted(s["languages"].items(), key=lambda kv: kv[1]["size"], reverse=True)[:top]
    total = sum(v["size"] for _, v in langs) or 1
    bar_w = 280
    body = ['  <mask id="bar"><rect x="25" y="55" width="280" height="8" rx="4" fill="#fff"/></mask>', '  <g mask="url(#bar)">']
    x = 25.0
    for name, v in langs:
        w = bar_w * v["size"] / total
        body.append(f'    <rect x="{x:.2f}" y="55" width="{w + 0.5:.2f}" height="8" fill="{v["color"]}"/>')
        x += w
    body.append("  </g>")
    for i, (name, v) in enumerate(langs):
        col, row = i % 2, i // 2
        cx, cy = 25 + col * 145, 92 + row * 26
        pct = 100 * v["size"] / total
        body.append(
            f'  <g class="row" style="animation-delay:{150 + i * 100}ms">'
            f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{v["color"]}"/>'
            f'<text x="{cx + 16}" y="{cy}" class="l">{escape(name)}</text>'
            f'<text x="{cx + 16 + len(name) * 7.6 + 6:.0f}" y="{cy}" class="m">{pct:.1f}%</text></g>'
        )
    return card(330, 225, "Most Used Languages", "\n".join(body))


def main():
    login, out_dir = sys.argv[1], sys.argv[2]
    if os.environ.get("STATS_FIXTURE"):
        with open(os.environ["STATS_FIXTURE"]) as f:
            s = json.load(f)
    else:
        s = collect(login, os.environ["GITHUB_TOKEN"])
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "stats.svg"), "w") as f:
        f.write(stats_svg(s))
    with open(os.path.join(out_dir, "top-langs.svg"), "w") as f:
        f.write(langs_svg(s))
    with open(os.path.join(out_dir, "stats.json"), "w") as f:
        json.dump(s, f, indent=2)
    print(json.dumps({k: v for k, v in s.items() if k != "languages"}, indent=2))


if __name__ == "__main__":
    main()
