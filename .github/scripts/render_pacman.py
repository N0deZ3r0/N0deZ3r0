#!/usr/bin/env python3
"""Draw the contribution calendar as a game of Pac-Man, as an animated SVG.

Written here rather than taken from an action for the same reason the activity
cards are: the picture on a profile should not depend on somebody else's
service or somebody else's release, and a generated SVG has to be trusted
completely -- it is served from this account and cannot be reviewed by whoever
looks at it.

How the animation survives being an image. GitHub serves README images through
its own proxy and renders them inside <img>, where scripts never run. CSS does,
so every moving part here is a @keyframes rule inside the SVG: Pac-Man's route,
his jaws, the ghosts, and the moment each cell is eaten. Nothing is computed in
the browser beyond interpolating between the keyframes written below.

The route is a boustrophedon sweep -- left to right along a row of weeks, drop
a day, right to left along the next -- which is what makes the grid readable as
corridors. A cell disappears at exactly the percentage of the loop at which
Pac-Man's centre reaches it, so the eating is the route rather than an effect
laid over it. Ghosts run the same keyframes with a negative animation-delay,
which is a phase shift: a delay of -(T - trail) puts a ghost `trail` seconds
behind rather than ahead.
"""

import json
import os
import sys
import urllib.request

OWNER = os.environ.get("GITHUB_OWNER") or "N0deZ3r0"
TOKEN = os.environ.get("GITHUB_TOKEN")
OUT = os.environ.get("OUTPUT_DIR") or "dist"
API = "https://api.github.com/graphql"

CELL = 10          # a contribution square, as GitHub draws it
GAP = 3
PITCH = CELL + GAP
MARGIN = 12
ROWS = 7

LOOP = 20.0        # seconds for one full sweep
MOVING = 0.93      # the tail of the loop is an empty board, before it refills
JAWS = 0.32        # one open-and-shut
TRAILS = (0.20, 0.40, 0.60, 0.80)   # how far behind Pac-Man each ghost runs

# GitHub's own two palettes, so the graph looks like the graph it is drawn from.
THEMES = {
    "light": {"bg": "#FFFFFF", "empty": "#EBEDF0", "pellet": "#D8DEE4",
              "levels": ["#EBEDF0", "#9BE9A8", "#40C463", "#30A14E",
                         "#216E39"]},
    "dark": {"bg": "#0D1117", "empty": "#161B22", "pellet": "#30363D",
             "levels": ["#161B22", "#0E4429", "#006D32", "#26A641",
                        "#39D353"]},
}

PACMAN = "#FFD534"
GHOSTS = ("#FF4B4B", "#FFB8DE", "#57DFFF", "#FFB852")

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

CALENDAR = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { weekday contributionLevel }
        }
      }
    }
  }
}
"""


def graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    request = urllib.request.Request(API, data=body)
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "profile-pacman-renderer")
    if TOKEN:
        request.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    # A GraphQL error arrives with HTTP 200 and an "errors" key; unchecked it
    # would reach the drawing code as an empty board.
    if "errors" in payload:
        sys.exit("GraphQL: %s" % json.dumps(payload["errors"])[:400])
    return payload["data"]


def route(columns):
    """Every cell in sweep order, and the corners the sweep turns at.

    Returns the ordered list of (column, row) the mouth passes over, and the
    list of (step, column, row) where direction changes -- the second is what
    the position keyframes are written from, since travel between corners is
    linear and needs no keyframe of its own.
    """
    order = []
    corners = []
    step = 0
    for row in range(ROWS):
        columns_in_row = range(columns) if row % 2 == 0 else \
            range(columns - 1, -1, -1)
        columns_in_row = list(columns_in_row)
        corners.append((step, columns_in_row[0], row))
        for index, column in enumerate(columns_in_row):
            order.append((step + index, column, row))
        step += columns - 1
        corners.append((step, columns_in_row[-1], row))
        if row != ROWS - 1:
            step += 1                       # the drop to the next day
    return order, corners, step


def centre(column, row):
    return (MARGIN + column * PITCH + CELL / 2.0,
            MARGIN + row * PITCH + CELL / 2.0)


def percent(step, steps):
    """A step of the sweep as a percentage of the whole loop."""
    return step / float(steps) * MOVING * 100.0


def cells(weeks, theme, steps, order):
    """The board, plus the keyframes that take each cell off it."""
    filled = {}
    for column, week in enumerate(weeks):
        for day in week["contributionDays"]:
            filled[(column, day["weekday"])] = LEVELS.get(
                day["contributionLevel"], 0)

    shapes = []
    rules = []
    for step, column, row in order:
        level = filled.get((column, row))
        if level is None:               # the calendar starts and ends mid-week
            continue
        x, y = centre(column, row)
        eaten = percent(step, steps)
        name = "e%d_%d" % (column, row)
        if level:
            shapes.append('<rect class="%s" x="%.1f" y="%.1f" width="%d" '
                          'height="%d" rx="2" fill="%s"/>'
                          % (name, x - CELL / 2.0, y - CELL / 2.0, CELL, CELL,
                             theme["levels"][level]))
        else:
            # An empty day is a pellet rather than a blank: the sweep should
            # look like a corridor being cleared, not like it skips the gaps.
            shapes.append('<circle class="%s" cx="%.1f" cy="%.1f" r="1.6" '
                          'fill="%s"/>' % (name, x, y, theme["pellet"]))
        # Held at full opacity until the mouth arrives, then gone for the rest
        # of the loop -- the final keyframe value persists to 100%.
        rules.append(".%s{animation:%s %.1fs linear infinite}"
                     "@keyframes %s{0%%,%.3f%%{opacity:1}%.3f%%{opacity:0}}"
                     % (name, name, LOOP, name, eaten, eaten + 0.45))
    return shapes, rules


def mover(name, corners, steps, trail):
    """Position keyframes for one character, phase-shifted by `trail`."""
    frames = []
    for step, column, row in corners:
        x, y = centre(column, row)
        frames.append("%.3f%%{transform:translate(%.1fpx,%.1fpx)}"
                      % (percent(step, steps), x, y))
    # The sweep ends before the loop does; parking the character on the last
    # corner keeps it still while the board sits empty.
    frames.append("100%%{transform:translate(%.1fpx,%.1fpx)}"
                  % centre(corners[-1][1], corners[-1][2]))
    rule = ".%s{animation:route %.1fs linear infinite" % (name, LOOP)
    if trail:
        # A negative delay is a phase shift. Shifting by a whole loop minus the
        # trail puts the ghost behind Pac-Man instead of in front of him.
        rule += ";animation-delay:%.2fs" % -(LOOP - trail)
    return rule + "}", "@keyframes route{%s}" % "".join(frames)


def facing(corners, steps):
    """Which way the mouth points: rows alternate, so the sprite flips."""
    frames = []
    for index in range(0, len(corners), 2):
        start = percent(corners[index][0], steps)
        angle = 0 if corners[index][2] % 2 == 0 else 180
        # Two keyframes a hair apart make the flip a jump rather than a spin.
        frames.append("%.3f%%,%.3f%%{transform:rotate(%ddeg)}"
                      % (start, percent(corners[index + 1][0], steps), angle))
    return "@keyframes facing{%s}" % "".join(frames)


def sprite():
    """Pac-Man as two jaws, so the mouth is a rotation and nothing else.

    A wedge cut out of a circle cannot be drawn with plain shapes, but two half
    discs hinged at the centre make the same silhouette and only need a
    rotation each -- which CSS animates reliably inside an <img>.
    """
    radius = 6.4
    top = ("M0,0 L%.1f,0 A%.1f,%.1f 0 0 0 %.1f,0 Z"
           % (radius, radius, radius, -radius))
    bottom = ("M0,0 L%.1f,0 A%.1f,%.1f 0 0 1 %.1f,0 Z"
              % (radius, radius, radius, -radius))
    return ('<g class="pac"><g class="facing">'
            '<path class="jaw top" d="%s" fill="%s"/>'
            '<path class="jaw bottom" d="%s" fill="%s"/>'
            '</g></g>' % (top, PACMAN, bottom, PACMAN))


def ghost(index, colour):
    """A ghost: domed head, four-scallop skirt, eyes that keep looking ahead."""
    body = ("M-6,3 L-6,-1 A6,6 0 0 1 6,-1 L6,3 "
            "L4.5,4.5 L3,3 L1.5,4.5 L0,3 L-1.5,4.5 L-3,3 L-4.5,4.5 Z")
    return ('<g class="g%d"><path d="%s" fill="%s"/>'
            '<circle cx="-2.4" cy="-1.2" r="2" fill="#FFFFFF"/>'
            '<circle cx="2.4" cy="-1.2" r="2" fill="#FFFFFF"/>'
            '<circle cx="-1.7" cy="-1.2" r="1" fill="#2B3A55"/>'
            '<circle cx="3.1" cy="-1.2" r="1" fill="#2B3A55"/></g>'
            % (index, body, colour))


def draw(weeks, theme):
    columns = len(weeks)
    order, corners, steps = route(columns)
    shapes, rules = cells(weeks, theme, steps, order)

    width = MARGIN * 2 + columns * PITCH - GAP
    height = MARGIN * 2 + ROWS * PITCH - GAP

    pac_rule, route_frames = mover("pac", corners, steps, 0)
    ghost_rules = [mover("g%d" % (index + 1), corners, steps, trail)[0]
                   for index, trail in enumerate(TRAILS)]

    style = [
        # Every animated group is positioned by transform, so they all need the
        # same origin: the sprite is drawn around 0,0 and moved to the cell.
        ".pac,.facing,.jaw,.g1,.g2,.g3,.g4"
        "{transform-box:view-box;transform-origin:0 0}",
        pac_rule,
        route_frames,
        "\n".join(ghost_rules),
        ".facing{animation:facing %.1fs linear infinite}" % LOOP,
        facing(corners, steps),
        ".jaw{animation:chew %.2fs ease-in-out infinite}" % JAWS,
        ".bottom{animation-name:chew-down}",
        "@keyframes chew{0%,100%{transform:rotate(0)}"
        "50%{transform:rotate(-32deg)}}",
        "@keyframes chew-down{0%,100%{transform:rotate(0)}"
        "50%{transform:rotate(32deg)}}",
        "\n".join(rules),
    ]

    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d" role="img" '
            'aria-label="Contribution graph as a game of Pac-Man">\n'
            '<title>Contribution graph as a game of Pac-Man</title>\n'
            '<style>%s</style>\n'
            '<rect width="%d" height="%d" fill="%s"/>\n%s\n%s\n%s\n</svg>\n'
            % (width, height, width, height, "\n".join(style), width, height,
               theme["bg"], "\n".join(shapes),
               "\n".join(ghost(index + 1, colour)
                         for index, colour in enumerate(GHOSTS)),
               sprite()))


def main():
    data = graphql(CALENDAR, {"login": OWNER})["user"]
    calendar = data["contributionsCollection"]["contributionCalendar"]
    weeks = calendar["weeks"]
    if not weeks:
        sys.exit("the contribution calendar came back empty")
    # An all-empty board is what a throttled or unauthorised token looks like,
    # and it would publish as a picture of nothing being eaten.
    if calendar["totalContributions"] == 0:
        sys.exit("no contributions in the calendar, refusing to draw a board")

    os.makedirs(OUT, exist_ok=True)
    for name, theme in THEMES.items():
        path = os.path.join(OUT, "pacman-%s.svg" % name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(draw(weeks, theme))
    print("%d weeks, %d contributions, wrote pacman-light.svg and "
          "pacman-dark.svg to %s/"
          % (len(weeks), calendar["totalContributions"], OUT))


if __name__ == "__main__":
    main()
