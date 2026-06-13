import html
import json
import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path


OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "Suvam-paul145")
OUT_DIR = Path("profile")
OUT_DIR.mkdir(exist_ok=True)

import sys
import re

def get_valid_token():
    for name in ["README_STATS_TOKEN", "GITHUB_TOKEN"]:
        token = os.environ.get(name)
        if token:
            req = urllib.request.Request(
                f"https://api.github.com/users/{OWNER}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "profile-readme-card-renderer",
                    "Authorization": f"Bearer {token}"
                }
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        return token
            except Exception as exc:
                print(f"Token from {name} is invalid or expired: {exc}", file=sys.stderr)
    return ""

TOKEN = get_valid_token()

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


class StatsUnavailable(RuntimeError):
    pass


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


def download_svg(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "profile-readme-card-renderer"})
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read()
    if b"<svg" not in body[:500]:
        raise StatsUnavailable(f"{url} did not return SVG content")
    path.write_bytes(body)


def has_svg(path):
    return path.exists() and "<svg" in path.read_text(encoding="utf-8", errors="ignore")


def update_stats_svg_file(path, stats):
    """Update numeric values in an existing stats.svg in-place, preserving structure.

    Returns True if any replacement was made.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False

    mapping = [
        ("Total Contributions", stats["totalContributions"]),
        ("Pull Requests", stats["pullRequests"]),
        ("Contributed Projects", stats["contributedProjects"]),
        ("Code Reviews", stats["codeReviews"]),
    ]
    changed = False
    for label, value in mapping:
        new_value = esc(fmt(value))
        pattern = re.compile(rf'({re.escape(label)}</text>\s*<text[^>]*>)([^<]*)(</text>)', re.DOTALL)
        new_text, n = pattern.subn(lambda m: m.group(1) + new_value + m.group(3), text, count=1)
        if n:
            text = new_text
            changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def update_streak_svg_file(path, stats):
    """Update numeric values in an existing streak.svg in-place, preserving structure.

    Stats dict expected keys: 'current', 'longest', 'total'
    Returns True if any replacement was made.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False

    replacements = [
        (r'(<!-- Total Contributions big number -->.*?<text[^>]*>)([^<]*)(</text>)', str(stats.get('total', ''))),
        (r'(<!-- Current Streak big number -->.*?<text[^>]*>)([^<]*)(</text>)', str(stats.get('current', ''))),
        (r'(<!-- Longest Streak big number -->.*?<text[^>]*>)([^<]*)(</text>)', str(stats.get('longest', ''))),
    ]
    changed = False
    for pattern, new_value in replacements:
        new_value = esc(fmt(new_value))
        new_text, n = re.subn(pattern, lambda m: m.group(1) + new_value + m.group(3), text, count=1, flags=re.DOTALL)
        if n:
            text = new_text
            changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


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
    if not TOKEN:
        raise StatsUnavailable("GITHUB_TOKEN or README_STATS_TOKEN is required for contribution stats")
    
    # Get user creation date to determine the range of years
    query_created = """
    query($login: String!) {
      user(login: $login) {
        createdAt
      }
    }
    """
    created_at_str = graphql(query_created, {"login": OWNER})["user"]["createdAt"]
    start_year = date.fromisoformat(created_at_str.split("T")[0]).year
    end_year = date.today().year

    query_year = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
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
    
    total_contributions = 0
    total_prs = 0
    total_reviews = 0
    projects = set()
    
    for year in range(start_year, end_year + 1):
        from_date = f"{year}-01-01T00:00:00Z"
        to_date = f"{year}-12-31T23:59:59Z"
        try:
            collection = graphql(query_year, {"login": OWNER, "from": from_date, "to": to_date})["user"]["contributionsCollection"]
            
            total_contributions += collection["contributionCalendar"]["totalContributions"]
            total_prs += collection["totalPullRequestContributions"]
            total_reviews += collection["totalPullRequestReviewContributions"]
            
            for group in (
                "commitContributionsByRepository",
                "pullRequestContributionsByRepository",
                "pullRequestReviewContributionsByRepository",
                "issueContributionsByRepository",
            ):
                for item in collection.get(group, []):
                    if item.get("repository"):
                        projects.add(item["repository"]["nameWithOwner"])
        except Exception as exc:
            print(f"Error fetching contribution stats for year {year}: {exc}", file=sys.stderr)

    return {
        "totalContributions": total_contributions,
        "pullRequests": total_prs,
        "contributedProjects": len(projects),
        "codeReviews": total_reviews,
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
    if not languages:
        raise StatsUnavailable("No language data available")
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

    content = f"""
  <text x="24" y="34" fill="{TITLE}" font-family="{FONT}" font-size="19" font-weight="700">Top Languages</text>
  <text x="24" y="53" fill="{MUTED}" font-family="{FONT}" font-size="12">Calculated from accessible repositories</text>
  {''.join(rows)}
"""
    write_svg(OUT_DIR / "top-langs.svg", 450, 250, content, "Suvam Paul's top programming languages")


def fetch_streak_stats():
    if not TOKEN:
        raise StatsUnavailable("GITHUB_TOKEN or README_STATS_TOKEN is required for streak stats")
    
    # Get user creation date to determine start year
    query_created = """
    query($login: String!) {
      user(login: $login) {
        createdAt
      }
    }
    """
    created_at_str = graphql(query_created, {"login": OWNER})["user"]["createdAt"]
    start_year = date.fromisoformat(created_at_str.split("T")[0]).year
    end_year = date.today().year

    query_year = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
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
    
    all_days = []
    total_contributions = 0
    
    for year in range(start_year, end_year + 1):
        from_date = f"{year}-01-01T00:00:00Z"
        to_date = f"{year}-12-31T23:59:59Z"
        try:
            calendar = graphql(query_year, {"login": OWNER, "from": from_date, "to": to_date})["user"]["contributionsCollection"]["contributionCalendar"]
            total_contributions += calendar["totalContributions"]
            for week in calendar["weeks"]:
                for day in week["contributionDays"]:
                    all_days.append(day)
        except Exception as exc:
            print(f"Error fetching streak calendar for year {year}: {exc}", file=sys.stderr)

    # Sort days by date to ensure chronological order
    all_days.sort(key=lambda d: d["date"])
    
    # Filter out future days
    days = [
        day
        for day in all_days
        if date.fromisoformat(day["date"]) <= date.today()
    ]
    
    current = 0
    for day in reversed(days):
        if day["contributionCount"] == 0:
            # If the current day is not finished, or it is today and they haven't committed yet, 
            # they might have committed yesterday, so don't break yet if we're on today's index
            # and they have a streak from yesterday.
            # However, standard streak calculation says if today is 0, we can check if yesterday is > 0.
            # Let's check: if we are at the very last element (today) and it is 0, we check if they committed yesterday.
            # If they did not commit today, but they committed yesterday, the streak is still active (it doesn't break).
            if len(days) - 1 - days.index(day) == 0:
                # This is today, and it's 0. Let's see if yesterday has contributions.
                continue
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
        "total": total_contributions,
    }


def render_streak():
    stats = fetch_streak_stats()

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
    stats_path = OUT_DIR / "stats.svg"
    languages_path = OUT_DIR / "top-langs.svg"
    streak_path = OUT_DIR / "streak.svg"

    # Print which token is being used (present/absent only) to help debug CI runs
    try:
        token_source = 'README_STATS_TOKEN' if os.environ.get('README_STATS_TOKEN') else ('GITHUB_TOKEN' if os.environ.get('GITHUB_TOKEN') else 'none')
        print(f"Token source: {token_source}")
    except Exception:
        pass

    try:
        contribution_stats = fetch_contribution_stats()
        # If an existing stats.svg is present, attempt to update only the numeric values
        # to preserve the SVG structure/UI. Fall back to full render if updating fails.
        if stats_path.exists() and has_svg(stats_path):
            updated = update_stats_svg_file(stats_path, contribution_stats)
            if not updated:
                render_stats(contribution_stats)
        else:
            render_stats(contribution_stats)
    except Exception as exc:
        # Log the error to aid debugging in workflow logs, but don't print secret values
        print(f"Could not fetch contribution stats: {exc}", file=sys.stderr)
        # Preserve the existing stats.svg if present; only fail if nothing exists to show
        if not has_svg(stats_path):
            raise StatsUnavailable(f"Cannot generate {stats_path}: {exc}") from exc

    # Skip regenerating top-langs.svg by default to avoid changing its structure/UI.
    # To enable generation, set environment variable GENERATE_TOP_LANGS=1 in the workflow.
    if os.environ.get("GENERATE_TOP_LANGS") == "1":
        try:
            languages = fetch_languages_from_graphql()
        except Exception:
            languages = fetch_languages_from_rest()
        try:
            render_top_languages(languages)
        except Exception as exc:
            print(f"Could not render top languages: {exc}", file=sys.stderr)
            if not has_svg(languages_path):
                raise StatsUnavailable(f"Cannot generate {languages_path}: {exc}") from exc

    # Optionally generate streak.svg if explicitly requested (keeps file stable by default)
    if os.environ.get("GENERATE_STREAK") == "1":
        try:
            # Prefer updating existing streak.svg in-place (change numbers only) to preserve UI
            streak_stats = fetch_streak_stats()
            if streak_path.exists() and has_svg(streak_path):
                updated = update_streak_svg_file(streak_path, streak_stats)
                if not updated:
                    render_streak()
            else:
                render_streak()
        except Exception as exc:
            try:
                url = f"https://streak-stats.demolab.com?user={OWNER}&theme=github-dark-blue&hide_border=true"
                download_svg(url, streak_path)
            except Exception:
                print(f"Could not render streak: {exc}", file=sys.stderr)
                if not has_svg(streak_path):
                    raise StatsUnavailable(f"Cannot generate {streak_path}: {exc}") from exc


if __name__ == "__main__":
    main()
