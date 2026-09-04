import html
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path


def load_dotenv(dotenv_path=Path(".env")):
    """Load variables from .env file into os.environ if present."""
    if not dotenv_path.exists():
        return
    try:
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


load_dotenv()


def is_enabled(name, default="1"):
    val = os.environ.get(name)
    if val is None or val == "":
        val = default
    return str(val).strip().lower() in ("1", "true", "yes", "on", "enable", "enabled")


OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "Suvam-paul145")
OUT_DIR = Path("profile")
OUT_DIR.mkdir(exist_ok=True)


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
GRID = "#1f2937"

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
    if path.exists():
        try:
            if path.read_text(encoding="utf-8").strip() == svg.strip():
                return
        except Exception:
            pass
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


def fetch_public_contributions():
    req = urllib.request.Request(
        f"https://github.com/users/{OWNER}/contributions",
        headers={"User-Agent": "profile-readme-card-renderer"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        html_content = resp.read().decode("utf-8")

    tooltip_map = {}
    for match in re.finditer(r'<tool-tip[^>]*for="([^"]+)"[^>]*>(.*?)</tool-tip>', html_content, re.DOTALL):
        comp_id, text = match.group(1), match.group(2)
        m = re.search(r'(\d+)\s+contribution', text)
        count = int(m.group(1)) if m else 0
        tooltip_map[comp_id] = count

    days_data = []
    for match in re.finditer(r'<td[^>]*data-date="([^"]+)"[^>]*id="(contribution-day-component-[^"]+)"', html_content):
        date_str, comp_id = match.group(1), match.group(2)
        count = tooltip_map.get(comp_id, 0)
        days_data.append({"date": date_str, "contributionCount": count})

    days_data.sort(key=lambda x: x["date"])
    return days_data


def fetch_streak_stats():
    all_days = []
    total_contributions = 0
    
    if TOKEN:
        query_created = """
        query($login: String!) {
          user(login: $login) {
            createdAt
          }
        }
        """
        try:
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
        except Exception as exc:
            print(f"GraphQL streak fetch failed, trying public calendar: {exc}", file=sys.stderr)

    if not all_days:
        try:
            all_days = fetch_public_contributions()
            total_contributions = sum(d["contributionCount"] for d in all_days)
            # When running without token, preserve all-time total from existing SVG if present
            stats_svg = OUT_DIR / "stats.svg"
            if stats_svg.exists():
                try:
                    s_text = stats_svg.read_text(encoding="utf-8")
                    m = re.search(r'Total Contributions</text>\s*<text[^>]*>([^<]+)</text>', s_text)
                    if m:
                        total_contributions = m.group(1)
                except Exception:
                    pass
        except Exception as exc:
            if not TOKEN:
                raise StatsUnavailable("GITHUB_TOKEN or README_STATS_TOKEN is required for streak stats") from exc
            raise

    all_days.sort(key=lambda d: d["date"])
    
    days = [
        day
        for day in all_days
        if date.fromisoformat(day["date"]) <= date.today()
    ]
    
    current = 0
    for idx, day in enumerate(reversed(days)):
        if day["contributionCount"] == 0:
            if idx == 0:
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
        "days": days,
    }


def render_streak(stats=None):
    if stats is None:
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


def render_activity_graph(days, width=840, height=280):
    if not days:
        raise StatsUnavailable("No contribution day data available for activity graph")

    total_contribs = sum(d["contributionCount"] for d in days)
    active_days = sum(1 for d in days if d["contributionCount"] > 0)
    max_day = max((d["contributionCount"] for d in days), default=0)

    reversed_days = list(reversed(days))
    weekly_chunks = []
    for i in range(0, min(52 * 7, len(reversed_days)), 7):
        chunk = reversed_days[i:i + 7]
        weekly_chunks.append(chunk)
    weekly_chunks.reverse()

    weeks = []
    for chunk in weekly_chunks:
        start_date = min(d["date"] for d in chunk)
        total = sum(d["contributionCount"] for d in chunk)
        weeks.append((start_date, total))

    if not weeks:
        return

    counts = [w[1] for w in weeks]
    max_val = max(counts) if counts else 1
    if max_val == 0:
        max_val = 1
    ceil_max = math.ceil(max_val / 10) * 10 or 10

    pad_left = 50
    pad_right = 35
    pad_top = 88
    pad_bottom = 45
    plot_width = width - pad_left - pad_right
    plot_height = height - pad_top - pad_bottom

    n = len(weeks)
    step_x = plot_width / max(1, n - 1)

    points = []
    for i, (date_str, val) in enumerate(weeks):
        x = pad_left + i * step_x
        y = pad_top + plot_height - (val / ceil_max) * plot_height
        points.append((x, y, val, date_str))

    def get_spline_path(pts):
        if len(pts) < 2:
            return ""
        path = [f"M {pts[0][0]:.1f},{pts[0][1]:.1f}"]
        for i in range(len(pts) - 1):
            p0 = pts[i - 1] if i > 0 else pts[i]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[i + 2] if i + 2 < len(pts) else p2

            cp1x = p1[0] + (p2[0] - p0[0]) / 6.0
            cp1y = p1[1] + (p2[1] - p0[1]) / 6.0
            cp2x = p2[0] - (p3[0] - p1[0]) / 6.0
            cp2y = p2[1] - (p3[1] - p1[1]) / 6.0

            cp1y = min(cp1y, pad_top + plot_height)
            cp2y = min(cp2y, pad_top + plot_height)

            path.append(f"C {cp1x:.1f},{cp1y:.1f} {cp2x:.1f},{cp2y:.1f} {p2[0]:.1f},{p2[1]:.1f}")
        return " ".join(path)

    line_d = get_spline_path(points)
    first_x = points[0][0]
    last_x = points[-1][0]
    base_y = pad_top + plot_height
    area_d = f"{line_d} L {last_x:.1f},{base_y:.1f} L {first_x:.1f},{base_y:.1f} Z"

    grid_svg = []
    for frac in [0.0, 0.33, 0.66, 1.0]:
        y_val = pad_top + plot_height - frac * plot_height
        label_val = int(round(frac * ceil_max))
        grid_svg.append(
            f'<line x1="{pad_left}" y1="{y_val:.1f}" x2="{width - pad_right}" y2="{y_val:.1f}" stroke="{GRID}" stroke-width="1" stroke-dasharray="3 3"/>'
            f'<text x="{pad_left - 10}" y="{y_val + 4:.1f}" fill="{MUTED}" font-family="{FONT}" font-size="10" text-anchor="end">{label_val}</text>'
        )

    month_svg = []
    last_month = None
    for x, y, val, date_str in points:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            m_str = dt.strftime("%b")
            if m_str != last_month:
                month_svg.append(
                    f'<text x="{x:.1f}" y="{base_y + 22}" fill="{MUTED}" font-family="{FONT}" font-size="11" text-anchor="middle">{m_str}</text>'
                )
                last_month = m_str
        except Exception:
            pass

    peak_points_svg = []
    max_week_val = max(counts)
    for x, y, val, date_str in points:
        if val == max_week_val and val > 0:
            peak_points_svg.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{ACCENT}" opacity="0.3"/>'
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#ffffff" stroke="{ACCENT}" stroke-width="2"/>'
                f'<text x="{x:.1f}" y="{y - 10:.1f}" fill="{TITLE}" font-family="{FONT}" font-size="11" font-weight="700" text-anchor="middle">{val}</text>'
            )

    total_str = f"{total_contribs:,}"
    pills_svg = f"""
    <!-- Total Pill -->
    <rect x="{width - 340}" y="26" width="98" height="34" rx="8" fill="#0f172a" stroke="{BORDER}"/>
    <circle cx="{width - 326}" cy="43" r="4" fill="{ACCENT}"/>
    <text x="{width - 314}" y="38" fill="{MUTED}" font-family="{FONT}" font-size="9">TOTAL</text>
    <text x="{width - 314}" y="52" fill="{TITLE}" font-family="{FONT}" font-size="13" font-weight="700">{total_str}</text>

    <!-- Peak Day Pill -->
    <rect x="{width - 232}" y="26" width="98" height="34" rx="8" fill="#0f172a" stroke="{BORDER}"/>
    <circle cx="{width - 218}" cy="43" r="4" fill="{GREEN}"/>
    <text x="{width - 206}" y="38" fill="{MUTED}" font-family="{FONT}" font-size="9">MAX DAY</text>
    <text x="{width - 206}" y="52" fill="{TITLE}" font-family="{FONT}" font-size="13" font-weight="700">{max_day} commits</text>

    <!-- Active Days Pill -->
    <rect x="{width - 124}" y="26" width="94" height="34" rx="8" fill="#0f172a" stroke="{BORDER}"/>
    <circle cx="{width - 110}" cy="43" r="4" fill="{PURPLE}"/>
    <text x="{width - 98}" y="38" fill="{MUTED}" font-family="{FONT}" font-size="9">ACTIVE</text>
    <text x="{width - 98}" y="52" fill="{TITLE}" font-family="{FONT}" font-size="13" font-weight="700">{active_days} days</text>
    """

    content = f"""
  <defs>
    <linearGradient id="act-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{ACCENT}" stop-opacity="0.32"/>
      <stop offset="70%" stop-color="{ACCENT}" stop-opacity="0.06"/>
      <stop offset="100%" stop-color="{ACCENT}" stop-opacity="0.0"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>

  <text x="28" y="42" fill="{TITLE}" font-family="{FONT}" font-size="20" font-weight="700">Activity Graph</text>
  <text x="28" y="62" fill="{MUTED}" font-family="{FONT}" font-size="12">Weekly contribution cadence &amp; rhythm across past 52 weeks</text>

  {pills_svg}

  <!-- Gridlines -->
  {''.join(grid_svg)}

  <!-- Area Fill -->
  <path d="{area_d}" fill="url(#act-grad)"/>

  <!-- Glowing Line -->
  <path d="{line_d}" stroke="{ACCENT}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)"/>

  <!-- Peaks -->
  {''.join(peak_points_svg)}

  <!-- Month labels -->
  {''.join(month_svg)}
"""
    write_svg(OUT_DIR / "activity-graph.svg", width, height, content, "Suvam Paul's contribution activity graph")


def main():
    stats_path = OUT_DIR / "stats.svg"
    languages_path = OUT_DIR / "top-langs.svg"
    streak_path = OUT_DIR / "streak.svg"
    activity_path = OUT_DIR / "activity-graph.svg"

    try:
        token_source = 'README_STATS_TOKEN' if os.environ.get('README_STATS_TOKEN') else ('GITHUB_TOKEN' if os.environ.get('GITHUB_TOKEN') else 'none')
        print(f"Token source: {token_source}")
    except Exception:
        pass

    try:
        contribution_stats = fetch_contribution_stats()
        if stats_path.exists() and has_svg(stats_path):
            updated = update_stats_svg_file(stats_path, contribution_stats)
            if not updated:
                render_stats(contribution_stats)
        else:
            render_stats(contribution_stats)
    except Exception as exc:
        print(f"Could not fetch contribution stats: {exc}", file=sys.stderr)
        if not has_svg(stats_path):
            raise StatsUnavailable(f"Cannot generate {stats_path}: {exc}") from exc

    if is_enabled("GENERATE_TOP_LANGS"):
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

    streak_stats = None
    if is_enabled("GENERATE_STREAK") or is_enabled("GENERATE_ACTIVITY_GRAPH"):
        try:
            streak_stats = fetch_streak_stats()
            if is_enabled("GENERATE_STREAK"):
                render_streak(streak_stats)
        except Exception as exc:
            print(f"Could not render streak: {exc}", file=sys.stderr)
            if not has_svg(streak_path):
                raise StatsUnavailable(f"Cannot generate {streak_path}: {exc}") from exc

    if is_enabled("GENERATE_ACTIVITY_GRAPH"):
        try:
            days = streak_stats["days"] if streak_stats and "days" in streak_stats else fetch_public_contributions()
            render_activity_graph(days)
        except Exception as exc:
            print(f"Could not render activity graph: {exc}", file=sys.stderr)
            if not has_svg(activity_path):
                raise StatsUnavailable(f"Cannot generate {activity_path}: {exc}") from exc


if __name__ == "__main__":
    main()
