import html
import json
import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path


OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "Suvam-paul145")
TOKEN = os.environ.get("README_STATS_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
OUT_DIR = Path("profile")
OUT_DIR.mkdir(exist_ok=True)

BG = "#0d1117"
CARD = "#111827"
BORDER = "#243244"
TITLE = "#e5eef8"
TEXT = "#b9c7d6"
MUTED = "#8b9aab"
ACCENT = "#38bdf8"
GREEN = "#22c55e"
PURPLE = "#a78bfa"

FONT = "Segoe UI, Arial, sans-serif"

LANGUAGE_ICONS = {
    "JavaScript": ("JS", "#f7df1e", "#101820"),
    "TypeScript": ("TS", "#3178c6", "#ffffff"),
    "Python": ("Py", "#3776ab", "#ffffff"),
    "HTML": ("5", "#e34f26", "#ffffff"),
    "CSS": ("3", "#1572b6", "#ffffff"),
    "Java": ("J", "#f89820", "#111827"),
    "C": ("C", "#a8b9cc", "#111827"),
    "C++": ("C++", "#00599c", "#ffffff"),
    "C#": ("C#", "#68217a", "#ffffff"),
    "Go": ("Go", "#00add8", "#111827"),
    "Rust": ("Rs", "#dea584", "#111827"),
    "PHP": ("PHP", "#777bb4", "#ffffff"),
    "Ruby": ("Rb", "#cc342d", "#ffffff"),
    "Dart": ("D", "#0175c2", "#ffffff"),
    "Kotlin": ("Kt", "#7f52ff", "#ffffff"),
    "Swift": ("Sw", "#f05138", "#ffffff"),
    "Shell": ("$", "#89e051", "#111827"),
    "Dockerfile": ("D", "#2496ed", "#ffffff"),
    "Jupyter Notebook": ("Ip", "#f37626", "#ffffff"),
}


def request_json(url, data=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-readme-card-renderer",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def graphql(query, variables):
    if not TOKEN:
        raise RuntimeError("A GitHub token is required for GraphQL stats")
    result = request_json("https://api.github.com/graphql", {"query": query, "variables": variables})
    if result.get("errors"):
        raise RuntimeError(json.dumps(result["errors"]))
    return result["data"]


def esc(value):
    return html.escape(str(value), quote=True)


def fmt(value):
    if isinstance(value, str):
        return value
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(value)


def write_svg(path, width, height, content, label):
    svg = f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(label)}">
  <rect width="{width}" height="{height}" rx="14" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="13.5" fill="{CARD}" stroke="{BORDER}"/>
  {content}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def fallback_public_repos():
    repos = []
    page = 1
    while True:
        batch = request_json(
            f"https://api.github.com/users/{OWNER}/repos?per_page=100&page={page}&type=owner&sort=updated"
        )
        if not batch:
            break
        repos.extend([repo for repo in batch if not repo.get("fork")])
        page += 1
    return repos


def fetch_contribution_stats():
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
          }
          totalPullRequestContributions
          totalPullRequestReviewContributions
          commitContributionsByRepository(maxRepositories: 100) {
            repository { nameWithOwner }
          }
          pullRequestContributionsByRepository(maxRepositories: 100) {
            repository { nameWithOwner }
          }
          pullRequestReviewContributionsByRepository(maxRepositories: 100) {
            repository { nameWithOwner }
          }
          issueContributionsByRepository(maxRepositories: 100) {
            repository { nameWithOwner }
          }
        }
      }
    }
    """
    collection = graphql(query, {"login": OWNER})["user"]["contributionsCollection"]
    projects = set()
    for group in (
        "commitContributionsByRepository",
        "pullRequestContributionsByRepository",
        "pullRequestReviewContributionsByRepository",
        "issueContributionsByRepository",
    ):
        for item in collection.get(group, []):
            projects.add(item["repository"]["nameWithOwner"])

    return {
        "totalContributions": collection["contributionCalendar"]["totalContributions"],
        "pullRequests": collection["totalPullRequestContributions"],
        "contributedProjects": len(projects),
        "codeReviews": collection["totalPullRequestReviewContributions"],
    }


def fetch_languages_from_graphql():
    query = """
    query($login: String!, $after: String) {
      user(login: $login) {
        repositories(
          first: 100
          after: $after
          ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]
          orderBy: {field: UPDATED_AT, direction: DESC}
        ) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            isFork
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node {
                  name
                  color
                }
              }
            }
          }
        }
      }
    }
    """
    languages = {}
    after = None
    while True:
        repos = graphql(query, {"login": OWNER, "after": after})["user"]["repositories"]
        for repo in repos["nodes"]:
            if repo["isFork"]:
                continue
            for edge in repo["languages"]["edges"]:
                node = edge["node"]
                name = node["name"]
                current = languages.setdefault(name, {"size": 0, "color": node.get("color") or ACCENT})
                current["size"] += edge["size"]
        if not repos["pageInfo"]["hasNextPage"]:
            break
        after = repos["pageInfo"]["endCursor"]
    return languages


def fetch_languages_from_rest():
    languages = {}
    try:
        repos = fallback_public_repos()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return languages

    for repo in repos:
        try:
            repo_languages = request_json(repo["languages_url"])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            continue
        for name, size in repo_languages.items():
            current = languages.setdefault(name, {"size": 0, "color": None})
            current["size"] += size
    return languages


def render_stats(stats):
    items = [
        ("Total Contributions", stats["totalContributions"], ACCENT),
        ("Pull Requests", stats["pullRequests"], GREEN),
        ("Contributed Projects", stats["contributedProjects"], PURPLE),
        ("Code Reviews", stats["codeReviews"], "#f97316"),
    ]
    cards = []
    positions = [(24, 70), (240, 70), (24, 142), (240, 142)]
    for (label, value, color), (x, y) in zip(items, positions):
        cards.append(
            f'<rect x="{x}" y="{y}" width="186" height="52" rx="10" fill="#0f172a" stroke="#263449"/>'
            f'<circle cx="{x + 22}" cy="{y + 26}" r="8" fill="{color}"/>'
            f'<text x="{x + 42}" y="{y + 22}" fill="{TEXT}" font-family="{FONT}" font-size="12">{esc(label)}</text>'
            f'<text x="{x + 42}" y="{y + 42}" fill="{TITLE}" font-family="{FONT}" font-size="18" font-weight="700">{esc(fmt(value))}</text>'
        )

    content = f"""
  <text x="24" y="34" fill="{TITLE}" font-family="{FONT}" font-size="19" font-weight="700">GitHub Impact</text>
  <text x="24" y="53" fill="{MUTED}" font-family="{FONT}" font-size="12">Contribution-focused activity, updated by workflow</text>
  {''.join(cards)}
"""
    write_svg(OUT_DIR / "stats.svg", 450, 220, content, "Suvam Paul's GitHub contribution stats")


def language_icon(name, color, x, y):
    icon_text, icon_bg, icon_fg = LANGUAGE_ICONS.get(name, (name[:2].title(), color or ACCENT, "#ffffff"))
    return (
        f'<rect x="{x}" y="{y}" width="25" height="25" rx="6" fill="{esc(icon_bg)}"/>'
        f'<text x="{x + 12.5}" y="{y + 17}" fill="{esc(icon_fg)}" font-family="{FONT}" font-size="9" font-weight="800" text-anchor="middle">{esc(icon_text)}</text>'
    )


def render_top_languages(languages):
    top = sorted(languages.items(), key=lambda item: item[1]["size"], reverse=True)[:6]
    total = sum(item["size"] for _, item in top) or 1
    rows = []
    y = 68
    for name, data in top:
        pct = data["size"] * 100 / total
        bar_width = max(6, round(230 * pct / 100))
        color = data.get("color") or LANGUAGE_ICONS.get(name, ("", ACCENT, ""))[1]
        rows.append(
            language_icon(name, color, 24, y - 17)
            + f'<text x="60" y="{y}" fill="{TITLE}" font-family="{FONT}" font-size="13" font-weight="600">{esc(name)}</text>'
            + f'<text x="382" y="{y}" fill="{TEXT}" font-family="{FONT}" font-size="12" text-anchor="end">{pct:.1f}%</text>'
            + f'<rect x="60" y="{y + 9}" width="230" height="7" rx="3.5" fill="#1f2937"/>'
            + f'<rect x="60" y="{y + 9}" width="{bar_width}" height="7" rx="3.5" fill="{esc(color)}"/>'
        )
        y += 29

    empty = f'<text x="24" y="95" fill="{TEXT}" font-family="{FONT}" font-size="14">Language data will appear after the workflow runs.</text>'
    content = f"""
  <text x="24" y="34" fill="{TITLE}" font-family="{FONT}" font-size="19" font-weight="700">Top Languages</text>
  <text x="24" y="53" fill="{MUTED}" font-family="{FONT}" font-size="12">Calculated from accessible repositories</text>
  {''.join(rows) if rows else empty}
"""
    write_svg(OUT_DIR / "top-langs.svg", 450, 250, content, "Suvam Paul's top programming languages")


def fetch_streak_stats():
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    calendar = graphql(query, {"login": OWNER})["user"]["contributionsCollection"]["contributionCalendar"]
    days = [
        day
        for week in calendar["weeks"]
        for day in week["contributionDays"]
        if date.fromisoformat(day["date"]) <= date.today()
    ]
    current = 0
    for day in reversed(days):
        if day["contributionCount"] == 0:
            break
        current += 1
    longest = 0
    running = 0
    for day in days:
        running = running + 1 if day["contributionCount"] else 0
        longest = max(longest, running)
    return {
        "current": current,
        "longest": longest,
        "total": calendar["totalContributions"],
    }


def render_streak():
    try:
        stats = fetch_streak_stats()
    except Exception:
        stats = {"current": "Run workflow", "longest": "Run workflow", "total": "Run workflow"}

    content = f"""
  <text x="28" y="42" fill="{TITLE}" font-family="{FONT}" font-size="21" font-weight="700">Contribution Streak</text>
  <text x="28" y="67" fill="{MUTED}" font-family="{FONT}" font-size="12">Current year contribution rhythm</text>
  <rect x="28" y="88" width="144" height="78" rx="12" fill="#0f172a" stroke="#263449"/>
  <rect x="188" y="88" width="144" height="78" rx="12" fill="#0f172a" stroke="#263449"/>
  <rect x="348" y="88" width="144" height="78" rx="12" fill="#0f172a" stroke="#263449"/>
  <text x="100" y="122" fill="{ACCENT}" font-family="{FONT}" font-size="24" font-weight="800" text-anchor="middle">{esc(fmt(stats["current"]))}</text>
  <text x="260" y="122" fill="{GREEN}" font-family="{FONT}" font-size="24" font-weight="800" text-anchor="middle">{esc(fmt(stats["longest"]))}</text>
  <text x="420" y="122" fill="{PURPLE}" font-family="{FONT}" font-size="24" font-weight="800" text-anchor="middle">{esc(fmt(stats["total"]))}</text>
  <text x="100" y="147" fill="{TEXT}" font-family="{FONT}" font-size="12" text-anchor="middle">Current</text>
  <text x="260" y="147" fill="{TEXT}" font-family="{FONT}" font-size="12" text-anchor="middle">Longest</text>
  <text x="420" y="147" fill="{TEXT}" font-family="{FONT}" font-size="12" text-anchor="middle">Total</text>
"""
    write_svg(OUT_DIR / "streak.svg", 520, 196, content, "Suvam Paul's contribution streak")


def main():
    try:
        contribution_stats = fetch_contribution_stats()
    except Exception:
        contribution_stats = {
            "totalContributions": "--",
            "pullRequests": "--",
            "contributedProjects": "--",
            "codeReviews": "--",
        }

    try:
        languages = fetch_languages_from_graphql()
    except Exception:
        languages = fetch_languages_from_rest()

    render_stats(contribution_stats)
    render_top_languages(languages)
    render_streak()


if __name__ == "__main__":
    main()
