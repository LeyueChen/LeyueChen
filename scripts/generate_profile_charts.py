#!/usr/bin/env python3
import datetime as dt
import html
import json
import math
import os
import pathlib
import urllib.request

USERNAME = os.environ.get("USERNAME", "LeyueChen")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
DATA = ROOT / "data"
ASSETS.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)


def request_json(url, payload=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "LeyueChen-profile-metrics",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def contribution_days(days=60):
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=days - 1)
    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        contributionsCollection(from:$from, to:$to) {
          contributionCalendar {
            weeks {
              contributionDays { date contributionCount }
            }
          }
        }
      }
    }
    """
    result = request_json(
        "https://api.github.com/graphql",
        {
            "query": query,
            "variables": {
                "login": USERNAME,
                "from": start.isoformat(),
                "to": end.isoformat(),
            },
        },
    )
    weeks = result["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    values = []
    for week in weeks:
        for day in week["contributionDays"]:
            date = dt.date.fromisoformat(day["date"])
            if date >= start.date():
                values.append((date, int(day["contributionCount"])))
    values.sort(key=lambda x: x[0])
    return values[-days:]


def owned_repositories():
    repos = []
    page = 1
    while True:
        batch = request_json(
            f"https://api.github.com/users/{USERNAME}/repos?type=owner&sort=updated&per_page=100&page={page}"
        )
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def svg_header(width, height, title):
    safe = html.escape(title)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{safe}">
<style>
  .bg {{ fill:#0d1117; }}
  .grid {{ stroke:#21262d; stroke-width:1; }}
  .axis {{ fill:#8b949e; font:12px -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif; }}
  .title {{ fill:#f0f6fc; font:600 18px -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif; }}
  .sub {{ fill:#8b949e; font:13px -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif; }}
  .value {{ fill:#58a6ff; font:600 14px -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif; }}
  .line {{ fill:none; stroke:#58a6ff; stroke-width:3; stroke-linejoin:round; stroke-linecap:round; }}
  .area {{ fill:#58a6ff; opacity:.12; }}
  .dot {{ fill:#79c0ff; }}
  .bar {{ fill:#238636; }}
</style>
<rect class="bg" x="0" y="0" width="{width}" height="{height}" rx="10"/>
<text class="title" x="24" y="32">{safe}</text>'''


def render_activity(values, path):
    width, height = 920, 270
    left, right, top, bottom = 48, 24, 58, 42
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_v = max([v for _, v in values] + [1])
    y_max = max(4, int(math.ceil(max_v / 4.0) * 4))

    def x(i):
        return left + (plot_w * i / max(1, len(values) - 1))

    def y(v):
        return top + plot_h - (plot_h * v / y_max)

    out = [svg_header(width, height, "60-Day Contribution Trend")]
    total = sum(v for _, v in values)
    active = sum(1 for _, v in values if v > 0)
    out.append(f'<text class="sub" x="24" y="52">{total} contributions · {active} active days · public profile activity</text>')

    for step in range(5):
        val = y_max * step / 4
        yy = y(val)
        out.append(f'<line class="grid" x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}"/>')
        out.append(f'<text class="axis" x="12" y="{yy+4:.1f}">{int(val)}</text>')

    pts = [(x(i), y(v)) for i, (_, v) in enumerate(values)]
    if pts:
        line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        area = f"{pts[0][0]:.1f},{top+plot_h:.1f} " + line + f" {pts[-1][0]:.1f},{top+plot_h:.1f}"
        out.append(f'<polygon class="area" points="{area}"/>')
        out.append(f'<polyline class="line" points="{line}"/>')
        for i, (px, py) in enumerate(pts):
            if i == len(pts)-1 or values[i][1] == max_v:
                out.append(f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" r="4"/>')

    if values:
        for idx in [0, len(values)//2, len(values)-1]:
            date = values[idx][0].strftime("%b %d")
            out.append(f'<text class="axis" x="{x(idx)-18:.1f}" y="{height-16}">{date}</text>')
    out.append('</svg>')
    path.write_text("\n".join(out), encoding="utf-8")


def render_star_growth(repos, path, history_path):
    today = dt.date.today().isoformat()
    total_stars = sum(int(r.get("stargazers_count", 0)) for r in repos if not r.get("fork"))
    history = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history = [p for p in history if p.get("date") != today]
    history.append({"date": today, "stars": total_stars})
    history = history[-365:]
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    width, height = 920, 250
    left, right, top, bottom = 58, 24, 64, 42
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [int(p["stars"]) for p in history]
    lo = min(values) if values else 0
    hi = max(values) if values else 1
    if hi == lo:
        hi = lo + 1

    def x(i):
        return left + plot_w * i / max(1, len(history)-1)

    def y(v):
        return top + plot_h - plot_h * (v-lo) / max(1, hi-lo)

    out = [svg_header(width, height, "Open Source Star Growth")]
    out.append(f'<text class="sub" x="24" y="52">Total stars across public, non-fork repositories: {total_stars}</text>')
    for step in range(4):
        val = lo + (hi-lo) * step / 3
        yy = y(val)
        out.append(f'<line class="grid" x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}"/>')
        out.append(f'<text class="axis" x="16" y="{yy+4:.1f}">{int(round(val))}</text>')

    pts = [(x(i), y(int(p["stars"]))) for i, p in enumerate(history)]
    if pts:
        if len(pts) == 1:
            px, py = pts[0]
            out.append(f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" r="5"/>')
            out.append(f'<text class="sub" x="{left}" y="{top+plot_h/2:.1f}">History collection starts today; this line will grow automatically each day.</text>')
        else:
            line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
            area = f"{pts[0][0]:.1f},{top+plot_h:.1f} " + line + f" {pts[-1][0]:.1f},{top+plot_h:.1f}"
            out.append(f'<polygon class="area" points="{area}"/>')
            out.append(f'<polyline class="line" points="{line}"/>')
            out.append(f'<circle class="dot" cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="4"/>')
        start_label = history[0]["date"][5:]
        end_label = history[-1]["date"][5:]
        out.append(f'<text class="axis" x="{left-10}" y="{height-16}">{start_label}</text>')
        out.append(f'<text class="axis" x="{width-right-34}" y="{height-16}">{end_label}</text>')
    out.append('</svg>')
    path.write_text("\n".join(out), encoding="utf-8")


def main():
    activity = contribution_days(60)
    repos = owned_repositories()
    render_activity(activity, ASSETS / "activity-trend.svg")
    render_star_growth(repos, ASSETS / "star-growth.svg", DATA / "star-history.json")
    print("Generated profile metrics")


if __name__ == "__main__":
    main()
