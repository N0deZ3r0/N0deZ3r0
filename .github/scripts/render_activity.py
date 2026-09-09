#!/usr/bin/env python3
"""Draw the Activity cards as SVG files, from this account's own data.

The cards these replace came from free shared services that call the GitHub API
under one token for everybody using them. That token runs out, and when it does
the service answers with a picture that says ERROR -- served as HTTP 200, so
GitHub's image proxy caches it like any other image and the word ERROR can sit
on the profile after the service itself has recovered. Drawing the cards here
removes the whole failure mode: nothing is fetched when the page is viewed.

Three cards, each in a light and a dark variant, written to a directory the
workflow then force-pushes to a branch of its own:

    overview  contributions, commits, pull requests, repositories
    insight   which language each repository leads with, and the hours of the
              day the commits land in
    streak    total, current run of days, longest run of days

All three are the same width on purpose. The README column on a profile is
narrower than it looks -- 652px at an ordinary window size -- so cards built to
sit side by side do not, and drop into a row of their own at half the width of
their neighbours. Cards of one width scale together whatever the column does.

Everything comes from one GraphQL call plus one paginated call per repository,
using only the standard library, so the job needs no install step.

A note on what the numbers mean. The default job token sees public
contributions only, which is what a visitor to the profile sees as well, so the
cards agree with the page around them. A personal token with `read:user` in
ACTIVITY_TOKEN widens every count to include private work -- the same choice
pacman.yml offers, and it has to be made the same way in both places, or the
numbers and the board beneath them would be counting different years.
"""

import datetime
import json
import math
import os
import sys
import urllib.request

OWNER = os.environ.get("GITHUB_OWNER") or "N0deZ3r0"
TOKEN = os.environ.get("GITHUB_TOKEN")
OUT = os.environ.get("OUTPUT_DIR") or "dist"
# Hours are meaningless without a timezone and the runner is on UTC. This is
# the offset the card it replaces was configured with.
OFFSET = int(os.environ.get("UTC_OFFSET") or 3)
API = "https://api.github.com/graphql"

FONT = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, "
        "Helvetica, Arial, sans-serif")

# The palettes are the ones the README already asked the old services for, so
# the section keeps its colours through the swap.
THEMES = {
    "light": {"bg": "#FFFFFF", "border": "#D0D7DE", "text": "#1F2328",
              "muted": "#57606A", "accent": "#0969DA", "dim": "#B6D0F0",
              "track": "#E4E8EC"},
    "dark": {"bg": "#0D1117", "border": "#21262D", "text": "#C9D1D9",
             "muted": "#8B949E", "accent": "#58A6FF", "dim": "#26456E",
             "track": "#21262D"},
}

WIDE = (852, 168)
INSIGHT = (852, 200)

PROFILE = """
query($login: String!) {
  user(login: $login) {
    createdAt
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER,
                 privacy: PUBLIC, isFork: false) {
      totalCount
      nodes { name primaryLanguage { name color } }
    }
  }
}
"""

HISTORY = """
query($login: String!, $name: String!, $since: GitTimestamp!, $after: String) {
  repository(owner: $login, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100, since: $since, after: $after) {
            pageInfo { hasNextPage endCursor }
            nodes { committedDate author { user { login } } }
          }
        }
      }
    }
  }
}
"""


def graphql(query, variables):
    """POST a query. Stops the job on anything that is not a clean answer."""
    body = json.dumps({"query": query, "variables": variables}).encode()
    request = urllib.request.Request(API, data=body)
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "profile-activity-renderer")
    if TOKEN:
        request.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    # A GraphQL error arrives with HTTP 200 and an "errors" key. Left unchecked
    # it would reach the drawing code as missing data and be rendered as zeros,
    # which is the failure this file exists to avoid.
    if "errors" in payload:
        sys.exit("GraphQL: %s" % json.dumps(payload["errors"])[:400])
    return payload["data"]


def commit_hours(names, since):
    """Commits per local hour, this account's own, over the same window.

    Bots share these repositories -- the project list is redrawn by one -- so
    the author is checked rather than every commit being counted.
    """
    hours = [0] * 24
    total = 0
    for name in names:
        cursor = None
        while True:
            data = graphql(HISTORY, {"login": OWNER, "name": name,
                                     "since": since, "after": cursor})
            ref = (data["repository"] or {}).get("defaultBranchRef")
            if not ref:            # an empty repository has no default branch
                break
            history = ref["target"]["history"]
            for node in history["nodes"]:
                user = (node["author"] or {}).get("user") or {}
                if user.get("login") != OWNER:
                    continue
                stamp = datetime.datetime.strptime(
                    node["committedDate"], "%Y-%m-%dT%H:%M:%SZ")
                hours[(stamp + datetime.timedelta(hours=OFFSET)).hour] += 1
                total += 1
            if not history["pageInfo"]["hasNextPage"]:
                break
            cursor = history["pageInfo"]["endCursor"]
    return hours, total


def streaks(days, today):
    """Current and longest run of consecutive days with a contribution.

    Days after today exist in the calendar -- it comes back in whole weeks --
    and are dropped rather than counted as a break. A run is still current when
    today itself is empty: the day is not over, so ending the streak on it
    would report a loss that has not happened.
    """
    days = [day for day in days if day["date"] <= today]
    longest = run = 0
    longest_end = current_end = None
    for day in days:
        if day["contributionCount"] > 0:
            run += 1
            if run > longest:
                longest, longest_end = run, day["date"]
        else:
            run = 0
    current = 0
    for day in reversed(days):
        if day["contributionCount"] > 0:
            current += 1
            if current_end is None:
                current_end = day["date"]
        elif current or day["date"] != today:
            break
    return {"current": current, "current_end": current_end,
            "longest": longest, "longest_end": longest_end}


def pretty(date):
    """2026-09-08 -> 8 Sep. Short enough to sit under a number."""
    parsed = datetime.datetime.strptime(date, "%Y-%m-%d")
    return "%d %s" % (parsed.day, parsed.strftime("%b"))


def span(end, length):
    """The date range a run of `length` days ending on `end` covers."""
    if not end or not length:
        return ""
    parsed = datetime.datetime.strptime(end, "%Y-%m-%d")
    start = (parsed - datetime.timedelta(days=length - 1)).strftime("%Y-%m-%d")
    if start == end:
        return pretty(end)
    return "%s - %s" % (pretty(start), pretty(end))


def escape(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def text(x, y, body, size, colour, weight="400", anchor="middle"):
    return ('<text x="%s" y="%s" text-anchor="%s" font-size="%s" '
            'font-weight="%s" fill="%s">%s</text>'
            % (x, y, anchor, size, weight, colour, escape(body)))


def frame(size, theme, title, parts):
    """A card: rounded border, a title screen readers can reach, contents."""
    width, height = size
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d" role="img" aria-label="%s" '
            'font-family="%s">\n<title>%s</title>\n'
            '<rect x="0.5" y="0.5" width="%d" height="%d" rx="6" fill="%s" '
            'stroke="%s"/>\n%s\n</svg>\n'
            % (width, height, width, height, escape(title), FONT,
               escape(title), width - 1, height - 1, theme["bg"],
               theme["border"], "\n".join(parts)))


def grouped(value):
    """1234 -> 1 234. A thin gap reads faster than four digits run together."""
    return "{:,}".format(value).replace(",", " ")


def overview(summary, theme):
    stats = [(summary["contributions"], "Contributions"),
             (summary["commits"], "Commits"),
             (summary["pull_requests"], "Pull requests"),
             (summary["repositories"], "Repositories")]
    width = WIDE[0]
    parts = [text(28, 34, "Last 12 months", 13, theme["muted"], "600", "start")]
    for index, (value, label) in enumerate(stats):
        centre = width * (2 * index + 1) / 8.0
        parts.append(text(centre, 108, grouped(value), 40, theme["accent"],
                          "700"))
        parts.append(text(centre, 134, label, 13, theme["muted"]))
        if index:
            edge = width * index / 4.0
            parts.append('<line x1="%.1f" y1="56" x2="%.1f" y2="140" '
                         'stroke="%s"/>' % (edge, edge, theme["border"]))
    return frame(WIDE, theme, "Activity over the last 12 months", parts)


def languages(ranked, theme, origin):
    """The left half of the insight card: a donut and its legend."""
    parts = [text(origin + 28, 36, "Top languages by repo", 13, theme["muted"],
                  "600", "start")]
    total = sum(count for _, count, _ in ranked) or 1
    cx, cy, radius = origin + 336, 122, 50
    # A donut is one circle per slice with a dashed stroke: each dash is as
    # long as that slice's share of the circumference, pushed round by
    # everything already drawn.
    circumference = 2 * math.pi * radius
    offset = 0.0
    for _, count, colour in ranked:
        length = circumference * count / total
        parts.append('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" '
                     'stroke-width="18" stroke-dasharray="%.2f %.2f" '
                     'stroke-dashoffset="%.2f" transform="rotate(-90 %d %d)"/>'
                     % (cx, cy, radius, colour or theme["accent"], length,
                        circumference - length, -offset, cx, cy))
        offset += length
    for index, (name, count, colour) in enumerate(ranked):
        y = 84 + index * 26
        parts.append('<rect x="%d" y="%d" width="11" height="11" rx="2" '
                     'fill="%s"/>'
                     % (origin + 28, y - 10, colour or theme["accent"]))
        parts.append(text(origin + 48, y, name, 14, theme["text"], "400",
                          "start"))
        parts.append(text(origin + 240, y,
                          "%d%%" % round(100.0 * count / total), 14,
                          theme["muted"], "400", "end"))
    return parts


def hours(counts, theme, origin):
    """The right half of the insight card: a bar per hour of the day."""
    label = "Commits by hour (UTC%+d)" % OFFSET
    parts = [text(origin + 28, 36, label, 13, theme["muted"], "600", "start")]
    peak = max(counts) or 1
    base, top = 170, 66
    left, right = origin + 30, origin + 398
    step = (right - left) / 24.0
    busiest = counts.index(max(counts))
    for hour, count in enumerate(counts):
        height = max((base - top) * count / float(peak), 1.5)
        parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                     'rx="2" fill="%s"/>'
                     % (left + hour * step, base - height, step - 4, height,
                        theme["accent"] if hour == busiest else theme["dim"]))
    for hour in (0, 6, 12, 18):
        parts.append(text(left + hour * step + (step - 4) / 2, 188,
                          "%02d" % hour, 11, theme["muted"]))
    return parts


def insight(ranked, counts, theme):
    """Languages and hours in one card.

    They were two cards until the profile was measured: the README column is
    652px wide there, so a pair of 420px cards will not sit side by side and
    drops into a second row, half the width of the cards above and below it.
    One wide card scales as a unit and lines up with them at any column width.
    """
    half = INSIGHT[0] / 2.0
    parts = languages(ranked, theme, 0) + hours(counts, theme, int(half))
    parts.append('<line x1="%.1f" y1="30" x2="%.1f" y2="172" stroke="%s"/>'
                 % (half, half, theme["border"]))
    return frame(INSIGHT, theme, "Top languages, and commits by hour", parts)


def streak_card(run, total, first_day, theme):
    width = WIDE[0]
    left, middle, right = width / 6.0, width / 2.0, width * 5 / 6.0
    parts = [text(left, 86, grouped(total), 38, theme["text"], "700"),
             text(left, 112, "Total contributions", 13, theme["muted"]),
             text(left, 134, "%s - now" % pretty(first_day), 11,
                  theme["muted"])]

    radius = 46
    parts.append('<circle cx="%.1f" cy="76" r="%d" fill="none" stroke="%s" '
                 'stroke-width="5"/>' % (middle, radius, theme["track"]))
    # The ring is a gauge against the personal best, not decoration: a current
    # streak that matches the record closes the circle.
    portion = min(1.0, run["current"] / float(run["longest"] or 1))
    circumference = 2 * math.pi * radius
    parts.append('<circle cx="%.1f" cy="76" r="%d" fill="none" stroke="%s" '
                 'stroke-width="5" stroke-linecap="round" '
                 'stroke-dasharray="%.2f %.2f" '
                 'transform="rotate(-90 %.1f 76)"/>'
                 % (middle, radius, theme["accent"], circumference * portion,
                    circumference, middle))
    parts.append(text(middle, 89, str(run["current"]), 34, theme["text"],
                      "700"))
    parts.append(text(middle, 142, "Current streak", 13, theme["accent"],
                      "600"))
    parts.append(text(middle, 158, span(run["current_end"], run["current"]),
                      11, theme["muted"]))

    parts.append(text(right, 86, str(run["longest"]), 38, theme["text"], "700"))
    parts.append(text(right, 112, "Longest streak", 13, theme["muted"]))
    parts.append(text(right, 134, span(run["longest_end"], run["longest"]), 11,
                      theme["muted"]))
    for edge in (width / 3.0, width * 2 / 3.0):
        parts.append('<line x1="%.1f" y1="34" x2="%.1f" y2="134" stroke="%s"/>'
                     % (edge, edge, theme["border"]))
    return frame(WIDE, theme, "Contribution streak", parts)


def main():
    data = graphql(PROFILE, {"login": OWNER})["user"]
    collection = data["contributionsCollection"]
    calendar = collection["contributionCalendar"]
    days = [day for week in calendar["weeks"]
            for day in week["contributionDays"]]
    if not days:
        sys.exit("the contribution calendar came back empty")
    # Zero contributions is what a throttled or unauthorised token looks like.
    # Publishing that would put a card of noughts on the profile, which is the
    # same lie as the ERROR card, so the job stops instead of drawing it.
    if calendar["totalContributions"] == 0:
        sys.exit("no contributions in the calendar, refusing to draw a card")

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    repositories = data["repositories"]
    names = [repo["name"] for repo in repositories["nodes"]]
    by_hour, counted = commit_hours(names,
                                    days[0]["date"] + "T00:00:00Z")
    if not counted:
        sys.exit("no commits found in the window, refusing to draw a card")

    tally = {}
    for repo in repositories["nodes"]:
        language = repo["primaryLanguage"]
        if language:
            tally.setdefault(language["name"], [0, language["color"]])
            tally[language["name"]][0] += 1
    if not tally:
        sys.exit("no repository has a language, refusing to draw a card")
    ranked = sorted(((name, count, colour)
                     for name, (count, colour) in tally.items()),
                    key=lambda row: (-row[1], row[0]))[:4]

    summary = {"contributions": calendar["totalContributions"],
               "commits": collection["totalCommitContributions"],
               "pull_requests": collection["totalPullRequestContributions"],
               "repositories": repositories["totalCount"]}
    run = streaks(days, today)
    # The window is a rolling year, but an account younger than that has no
    # history before it existed, and dating the total from a day the account
    # did not exist would be a small lie on a card about dates.
    first = max(days[0]["date"], data["createdAt"][:10])

    os.makedirs(OUT, exist_ok=True)
    for name, theme in THEMES.items():
        cards = {"overview": overview(summary, theme),
                 "insight": insight(ranked, by_hour, theme),
                 "streak": streak_card(run, calendar["totalContributions"],
                                       first, theme)}
        for card, svg in cards.items():
            path = os.path.join(OUT, "%s-%s.svg" % (card, name))
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(svg)
    print("contributions %d, commits %d, streak %d (best %d), %d commits placed"
          % (calendar["totalContributions"],
             collection["totalCommitContributions"], run["current"],
             run["longest"], counted))
    print("wrote 6 files to %s/" % OUT)


if __name__ == "__main__":
    main()
