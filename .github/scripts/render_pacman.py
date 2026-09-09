#!/usr/bin/env python3
"""Draw the contribution calendar as a game of Pac-Man that plays itself.

The board is not a drawn maze. It is the calendar: a day with work on it is a
wall, an empty day is a corridor with a pellet in it. So the maze is a year of
this account's history and it rearranges itself as the year fills in, without
anyone designing a level.

Nobody is playing. A whole game is played out here, when the SVG is built --
Pac-Man looking for the nearest pellet and backing off when something is close,
four ghosts with four different amounts of patience, energizers, a chase, and
the death that ends the run -- and what ships is the recording. That is the
only way it can work: GitHub renders README images inside <img>, where scripts
never run, so nothing can be decided in the browser. CSS animation does run
there, so every move of the game leaves here as a @keyframes rule and the
browser only interpolates between positions that were settled long before.

Written here rather than taken from an action for the same reason the activity
cards are: a picture served from this account should not depend on somebody
else's service or somebody else's release.
"""

import json
import math
import os
import random
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

STEP = 0.15        # seconds to cross one cell
DEATH_FOR = 1.7    # the mouth opening all the way round
PAUSE_FOR = 1.3    # an empty board before the loop starts again
WANT_STEPS = 170   # a run at least this long is worth showing
CAP_STEPS = 260    # and no longer than this, or the loop drags
SEEDS = 40         # tries at finding one

FRIGHT_STEPS = 20  # how long an energizer lasts
GHOST_BACK = 9     # steps an eaten ghost spends away from the board
SCORES = (200, 400, 800, 1600)
SCORE_FOR = 0.9

# How often each ghost wanders instead of closing in. Four ghosts all taking
# the shortest step converge into a single moving wall and the run is over in
# seconds; giving each its own patience is also what makes the arcade four feel
# like four characters rather than one.
WANDER = (0.12, 0.30, 0.45, 0.62)

# GitHub's own two palettes, so the graph looks like the graph it is drawn from.
THEMES = {
    "light": {"bg": "#FFFFFF", "pellet": "#D8DEE4", "power": "#E09B54",
              "levels": ["#EBEDF0", "#9BE9A8", "#40C463", "#30A14E",
                         "#216E39"]},
    "dark": {"bg": "#0D1117", "pellet": "#30363D", "power": "#FFB897",
             "levels": ["#161B22", "#0E4429", "#006D32", "#26A641",
                        "#39D353"]},
}

PACMAN = "#FFD534"
# The arcade four, by their own colours: Blinky, Pinky, Inky, Clyde.
GHOSTS = ("#FF0000", "#FFB8FF", "#00FFFF", "#FFB852")
PUPIL = "#2121DE"
SCARED = "#2121DE"
SCARED_TRIM = "#FFFFFF"
FLASHED = "#FFFFFF"
FLASHED_TRIM = "#FF0000"
SCORE_COLOUR = "#00E0E8"
FONT = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, "
        "Helvetica, Arial, sans-serif")

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

STEPS = {"right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1)}

CALENDAR = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { weekday contributionLevel } }
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


def calendar():
    """Contribution level per (column, row), and how many weeks wide it is."""
    data = graphql(CALENDAR, {"login": OWNER})["user"]
    board = data["contributionsCollection"]["contributionCalendar"]
    if not board["weeks"]:
        sys.exit("the contribution calendar came back empty")
    # An empty year is what a throttled or unauthorised token looks like, and
    # it would publish as a picture of nothing happening.
    if board["totalContributions"] == 0:
        sys.exit("no contributions in the calendar, refusing to draw a board")
    level = {}
    for column, week in enumerate(board["weeks"]):
        for day in week["contributionDays"]:
            level[(column, day["weekday"])] = LEVELS.get(
                day["contributionLevel"], 0)
    return level, len(board["weeks"]), board["totalContributions"]


def centre(column, row):
    return (MARGIN + column * PITCH + CELL / 2.0,
            MARGIN + row * PITCH + CELL / 2.0)


def around(cell, columns):
    """The four neighbours, with the left and right edges joined up.

    Seven days tall and a year wide, the board is one long corridor; without
    the tunnel its two ends are dead ends to be cornered against.
    """
    column, row = cell
    for dx, dy in STEPS.values():
        step = ((column + dx) % columns, row + dy)
        if 0 <= step[1] < ROWS:
            yield step


def explore(level, columns, start):
    """Breadth-first over the corridors: how far, and which way to set off."""
    distance = {start: 0}
    first = {start: None}
    queue = [start]
    while queue:
        cell = queue.pop(0)
        for step in around(cell, columns):
            if level.get(step, 1) == 0 and step not in distance:
                distance[step] = distance[cell] + 1
                first[step] = first[cell] or step
                queue.append(step)
    return distance, first


def nearest(level, columns, target):
    corridors = [cell for cell, value in level.items() if value == 0]
    if not corridors:
        sys.exit("the whole calendar is walls, there is nowhere to play")
    return min(corridors, key=lambda cell: (abs(cell[0] - target[0])
                                            + abs(cell[1] - target[1])))


def gap(a, b, columns):
    """Distance ignoring walls -- near enough for deciding what is dangerous."""
    across = abs(a[0] - b[0])
    return min(across, columns - across) + abs(a[1] - b[1])


def simulate(level, columns, seed):
    """Play one life out and write down everything that happened."""
    rng = random.Random(seed)
    pac = nearest(level, columns, (columns // 2, 3))
    walkable = set(explore(level, columns, pac)[0])
    powers = []
    for share in (0.14, 0.38, 0.62, 0.86):
        powers.append(min((cell for cell in walkable if cell not in powers),
                          key=lambda cell: (abs(cell[0] - columns * share)
                                            + abs(cell[1] - 3))))
    powers = set(powers)
    home = nearest(level, columns, (columns // 2, 0))
    ghosts = [nearest(level, columns, (int(columns * share), row))
              for share, row in ((0.18, 0), (0.38, 6), (0.62, 0), (0.82, 6))]

    run = {"pac": [pac], "dir": ["left"], "ghosts": [[g] for g in ghosts],
           "away": [[] for _ in ghosts], "eaten": {}, "frights": [],
           "kills": [], "powers": powers, "walkable": walkable,
           "caught": False}
    facing = "left"
    hidden = [0, 0, 0, 0]
    fright = 0
    combo = 0
    eaten = set()

    for tick in range(1, CAP_STEPS + 1):
        distance, first = explore(level, columns, pac)
        threats = [g for index, g in enumerate(ghosts)
                   if not hidden[index] and not fright]

        target = None
        if fright:
            prey = [g for index, g in enumerate(ghosts)
                    if not hidden[index] and g in distance]
            if prey:
                target = min(prey, key=lambda g: distance[g])
        if target is None:
            close = [cell for cell in powers - eaten if cell in distance
                     and distance[cell] < 9]
            crowded = any(gap(pac, g, columns) < 5 for g in threats)
            wanted = (close if close and crowded
                      else [cell for cell in walkable - eaten
                            if cell in distance])
            if wanted:
                target = min(wanted, key=lambda cell: distance[cell])

        options = [cell for cell in around(pac, columns)
                   if level.get(cell, 1) == 0]
        if not options:
            break
        step = first.get(target) if target else None
        if step not in options:
            step = rng.choice(options)
        # A step that walks into somebody is not worth a pellet: if the chosen
        # one is that, take whichever option keeps the most room instead.
        if threats and min(gap(step, g, columns) for g in threats) <= 1:
            step = max(options,
                       key=lambda cell: min(gap(cell, g, columns)
                                            for g in threats))

        facing = next((name for name, (dx, dy) in STEPS.items()
                       if ((pac[0] + dx) % columns, pac[1] + dy) == step),
                      facing)
        pac = step
        if pac not in eaten:
            eaten.add(pac)
            run["eaten"][pac] = tick
            if pac in powers:
                fright = FRIGHT_STEPS
                combo = 0
                run["frights"].append([tick, tick + FRIGHT_STEPS])

        # Ghosts are slower than he is, and slower still while frightened --
        # four steps in five, one in two. Measured rather than guessed: at two
        # in three he outlived the recording in half the runs and the loop had
        # to end with a death nothing had caused, at four in five he is caught
        # in eleven runs out of twelve, after about 220 moves.
        moving = tick % 5 != 0 if not fright else tick % 2 == 0
        for index, ghost in enumerate(ghosts):
            if hidden[index]:
                hidden[index] -= 1
                if not hidden[index]:
                    ghosts[index] = home
                continue
            if not moving:
                continue
            choices = [cell for cell in around(ghost, columns)
                       if level.get(cell, 1) == 0]
            if not choices:
                continue
            rng.shuffle(choices)
            if rng.random() < WANDER[index]:
                ghosts[index] = choices[0]
            elif fright:
                ghosts[index] = max(choices,
                                    key=lambda c: gap(c, pac, columns))
            else:
                ghosts[index] = min(choices,
                                    key=lambda c: gap(c, pac, columns))

        for index, ghost in enumerate(ghosts):
            if hidden[index] or ghost != pac:
                continue
            if fright:
                run["kills"].append((tick, index,
                                     SCORES[min(combo, len(SCORES) - 1)], pac))
                combo += 1
                hidden[index] = GHOST_BACK
                run["away"][index].append([tick, tick + GHOST_BACK])
            else:
                run["caught"] = True

        if fright:
            fright -= 1
            if not fright:
                combo = 0

        run["pac"].append(pac)
        run["dir"].append(facing)
        for index, ghost in enumerate(ghosts):
            run["ghosts"][index].append(ghost)
        if run["caught"]:
            break
    return run


def best_run(level, columns):
    """A run long enough to watch that ends in him actually being caught.

    The ending matters more than the length. A run that simply reached the cap
    would still have to finish with the death animation, and he would die of
    nothing in an empty corridor with the ghosts elsewhere.
    """
    longest = None
    for seed in range(SEEDS):
        run = simulate(level, columns, seed)
        if longest is None or len(run["pac"]) > len(longest["pac"]):
            longest = run
        if run["caught"] and len(run["pac"]) >= WANT_STEPS:
            return run, seed
    return longest, -1


def escape(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def motion(path, columns, loop):
    """Position keyframes: one at every turn, and a tunnel where it wraps.

    Between two of them the browser interpolates in a straight line at a
    constant rate, which is exactly what walking down a corridor is, so the
    steps in between need saying only where the direction changes.
    """
    marks = []

    def add(when, x, y):
        if marks and abs(when - marks[-1][0]) < 1e-9:
            marks[-1] = (when, x, y)
        else:
            marks.append((when, x, y))

    for index, cell in enumerate(path):
        x, y = centre(*cell)
        if index == 0 or index == len(path) - 1:
            add(index * STEP, x, y)
            continue
        before, after = path[index - 1], path[index + 1]
        shift = cell[0] - before[0]
        if abs(shift) > 1:
            # Through the tunnel: out past one edge and in past the other,
            # rather than sliding the whole width of the board backwards.
            heading = 1 if shift < 0 else -1
            px, py = centre(*before)
            add((index - 1) * STEP, px, py)
            add((index - 0.5) * STEP, px + heading * PITCH, py)
            add((index - 0.5) * STEP + 0.004, x - heading * PITCH, y)
            add(index * STEP, x, y)
            continue
        if (cell[0] - before[0], cell[1] - before[1]) != \
                (after[0] - cell[0], after[1] - cell[1]):
            add(index * STEP, x, y)

    # The run ends before the loop does, and a track that stops early does not
    # simply hold its last value: the browser fills in a final keyframe from
    # the property's own transform, which is none at all, and everything slides
    # off to the top-left corner while he is supposed to be dying on the spot.
    last = centre(*path[-1])
    add(loop, last[0], last[1])
    # Written short on purpose: five sprites turning a few hundred times each
    # is most of the file, and the cell centres are whole numbers anyway.
    return "".join("%.3f%%{transform:translate(%dpx,%dpx)}"
                   % (when / loop * 100.0, round(x), round(y))
                   for when, x, y in marks)


def facing_frames(headings, loop):
    """Which way a sprite points, changing only when it turns."""
    angles = {"right": 0, "down": 90, "left": 180, "up": 270}
    frames = []
    last = None
    for index, name in enumerate(headings):
        angle = angles[name]
        if angle != last:
            when = index * STEP / loop * 100.0
            if last is not None:
                frames.append("%.4f%%{transform:rotate(%ddeg)}"
                              % (max(when - 0.004, 0.0), last))
            frames.append("%.4f%%{transform:rotate(%ddeg)}" % (when, angle))
            last = angle
    frames.append("100%%{transform:rotate(%ddeg)}" % last)
    return "".join(frames)


def headings_of(path, columns):
    """The direction walked into each cell, for the ghosts' eyes."""
    names = ["left"]
    for index in range(1, len(path)):
        before, cell = path[index - 1], path[index]
        shift = cell[0] - before[0]
        if abs(shift) > 1:
            shift = 1 if shift < 0 else -1
        found = None
        for name, (dx, dy) in STEPS.items():
            if (shift, cell[1] - before[1]) == (dx, dy):
                found = name
        names.append(found or names[-1])
    return names


def switching(intervals):
    """Keyframes for a value that only jumps, over a timeline with no gaps.

    Stated twice, at the start of each interval and just before the next, so
    nothing is interpolated between them -- and the last runs to 100%, where a
    missing keyframe would otherwise be invented from the property's own value
    and quietly undo the whole thing.
    """
    frames = []
    for index, (start, end, value) in enumerate(intervals):
        tail = 100.0 if index == len(intervals) - 1 else end - 0.004
        frames.append("%.4f%%{opacity:%g}%.4f%%{opacity:%g}"
                      % (start, value, tail, value))
    return "".join(frames)


def windows(spans, loop, ended, value, default):
    """Turn step ranges into the intervals `switching` wants.

    Overlapping ones are joined first. Two energizers eaten inside one fright,
    or a ghost caught twice in quick succession, would otherwise hand
    `switching` a timeline that runs backwards, and every keyframe after the
    overlap would land in the wrong order.
    """
    joined = []
    for start, end in sorted(tuple(span) for span in spans):
        if joined and start <= joined[-1][1]:
            joined[-1][1] = max(joined[-1][1], end)
        else:
            joined.append([start, min(end, ended)])

    marks = []
    edge = 0.0
    for start, end in joined:
        a = max(0.0, min(100.0, start * STEP / loop * 100.0))
        b = max(0.0, min(100.0, min(end, ended) * STEP / loop * 100.0))
        if b <= a:
            continue
        if a > edge:
            marks.append((edge, a, default))
        marks.append((a, b, value))
        edge = b
    if edge < 100.0:
        marks.append((edge, 100.0, default))
    return switching(marks)


GHOST_BODY = ("M-6,3 L-6,-1 A6,6 0 0 1 6,-1 L6,3 "
              "L4.5,4.5 L3,3 L1.5,4.5 L0,3 L-1.5,4.5 L-3,3 L-4.5,4.5 Z")
RADIUS = 6.4
RING = 2 * math.pi * (RADIUS / 2)


def afraid(fill, trim, name):
    """Square eyes and a zigzag mouth: at this size that pair is the whole
    difference between a ghost chasing and a ghost running away."""
    return ('<g class="%s"><path d="%s" fill="%s"/>'
            '<rect x="-3.1" y="-2.2" width="1.8" height="1.8" fill="%s"/>'
            '<rect x="1.3" y="-2.2" width="1.8" height="1.8" fill="%s"/>'
            '<path d="M-3.6,2 L-2.4,0.9 L-1.2,2 L0,0.9 L1.2,2 L2.4,0.9 '
            'L3.6,2" fill="none" stroke="%s" stroke-width="0.9"/></g>'
            % (name, GHOST_BODY, fill, trim, trim, trim))


def sprite():
    """Pac-Man twice: the one that chews, and the one that dies.

    Chewing is two half discs hinged at the centre. The arcade death cannot be
    those two halves -- swing them a full 180 degrees and they have merely
    swapped places and closed up again -- so the dying one is a disc drawn as a
    thick stroke whose dasharray shrinks away to nothing, with the gap centred
    on the mouth. Two sprites also keeps the fast chew and the once-a-loop
    death off the same property, where the longer would simply overrule the
    shorter.
    """
    top = "M0,0 L%.1f,0 A%.1f,%.1f 0 0 0 %.1f,0 Z" % (
        RADIUS, RADIUS, RADIUS, -RADIUS)
    bottom = "M0,0 L%.1f,0 A%.1f,%.1f 0 0 1 %.1f,0 Z" % (
        RADIUS, RADIUS, RADIUS, -RADIUS)
    spokes = "".join(
        '<line x1="0" y1="-3.4" x2="0" y2="-8.4" transform="rotate(%d)"/>'
        % angle for angle in range(0, 360, 60))
    return ('<g class="pac"><g class="facing">'
            '<g class="alive"><path class="jaw" d="%s" fill="%s"/>'
            '<path class="jaw down" d="%s" fill="%s"/></g>'
            '<circle class="death" cx="0" cy="0" r="%.2f" fill="none" '
            'stroke="%s" stroke-width="%.1f"/>'
            '<g class="burst" stroke="%s" stroke-width="1.6" '
            'stroke-linecap="round">%s</g></g></g>'
            % (top, PACMAN, bottom, PACMAN, RADIUS / 2, PACMAN, RADIUS,
               PACMAN, spokes))


def ghost(index, colour):
    return ('<g class="g%d"><g class="calm"><path d="%s" fill="%s"/>'
            '<circle cx="-2.4" cy="-1.2" r="2" fill="#FFFFFF"/>'
            '<circle cx="2.4" cy="-1.2" r="2" fill="#FFFFFF"/>'
            '<g class="look%d"><circle cx="-2.4" cy="-1.2" r="1" fill="%s"/>'
            '<circle cx="2.4" cy="-1.2" r="1" fill="%s"/></g></g>%s%s</g>'
            % (index, GHOST_BODY, colour, index, PUPIL, PUPIL,
               afraid(SCARED, SCARED_TRIM, "scared"),
               afraid(FLASHED, FLASHED_TRIM, "blink")))


def draw(run, level, columns, theme):
    ended = len(run["pac"]) - 1
    played = ended * STEP
    loop = played + DEATH_FOR + PAUSE_FOR
    caught = played / loop * 100.0
    gone = (played + DEATH_FOR) / loop * 100.0

    width = MARGIN * 2 + columns * PITCH - GAP
    height = MARGIN * 2 + ROWS * PITCH - GAP

    shapes, rules = [], []
    for cell, value in sorted(level.items()):
        x, y = centre(*cell)
        name = "e%d_%d" % cell
        if value:
            shapes.append('<rect x="%.1f" y="%.1f" width="%d" height="%d" '
                          'rx="2" fill="%s"/>'
                          % (x - CELL / 2.0, y - CELL / 2.0, CELL, CELL,
                             theme["levels"][value]))
            continue
        if cell not in run["walkable"]:
            continue
        if cell in run["powers"]:
            shapes.append('<g class="%s"><circle class="power" cx="%.1f" '
                          'cy="%.1f" r="3.4" fill="%s"/></g>'
                          % (name, x, y, theme["power"]))
        else:
            shapes.append('<circle class="%s" cx="%.1f" cy="%.1f" r="1.6" '
                          'fill="%s"/>' % (name, x, y, theme["pellet"]))
        when = run["eaten"].get(cell)
        if when is None:
            continue
        at = when * STEP / loop * 100.0
        # The keyframe at 100% is not decoration: without one the browser
        # invents a final keyframe from the property's own value, and every
        # eaten pellet fades back in over the rest of the loop.
        rules.append(".%s{animation:%s %.2fs linear infinite}"
                     "@keyframes %s{0%%,%.4f%%{opacity:1}%.4f%%,100%%"
                     "{opacity:0}}" % (name, name, loop, name, at, at + 0.4))

    numbers = []
    for tick, _, points, cell in run["kills"]:
        x, y = centre(*cell)
        name = "s%d" % tick
        numbers.append('<text class="%s" x="%.1f" y="%.1f" '
                       'text-anchor="middle" font-size="9" font-weight="700" '
                       'fill="%s">%d</text>' % (name, x, y - 1,
                                                SCORE_COLOUR, points))
        at = tick * STEP / loop * 100.0
        rules.append(
            ".%s{animation:%s %.2fs linear infinite}"
            "@keyframes %s{0%%,%.4f%%{opacity:0;transform:translate(0,0)}"
            "%.4f%%{opacity:1;transform:translate(0,-2px)}"
            "%.4f%%,100%%{opacity:0;transform:translate(0,-13px)}}"
            % (name, name, loop, name, at - 0.004, at,
               (tick * STEP + SCORE_FOR) / loop * 100.0))

    style = [
        ".pac,.facing,.jaw,.burst,.g1,.g2,.g3,.g4,"
        ".look1,.look2,.look3,.look4"
        "{transform-box:view-box;transform-origin:0 0}",
        ".pac{animation:pacpath %.2fs linear infinite}" % loop,
        "@keyframes pacpath{%s}" % motion(run["pac"], columns, loop),
        ".facing{animation:facing %.2fs linear infinite}" % loop,
        "@keyframes facing{%s}" % facing_frames(run["dir"], loop),
        ".jaw{animation:chew .34s ease-in-out infinite}",
        ".down{animation-name:chew-down}",
        "@keyframes chew{0%,100%{transform:rotate(0)}"
        "50%{transform:rotate(-32deg)}}",
        "@keyframes chew-down{0%,100%{transform:rotate(0)}"
        "50%{transform:rotate(32deg)}}",
        ".power{animation:pulse .5s steps(1,end) infinite}",
        "@keyframes pulse{0%,49%{opacity:1}50%,100%{opacity:.15}}",
        # Caught, and the mouth keeps opening until the disc is gone.
        ".alive{animation:alive %.2fs linear infinite}" % loop,
        "@keyframes alive{0%%,%.4f%%{opacity:1}%.4f%%,100%%{opacity:0}}"
        % (caught - 0.1, caught),
        ".death{animation:death %.2fs linear infinite}" % loop,
        "@keyframes death{0%%,%.4f%%{stroke-dasharray:%.2f 0;"
        "stroke-dashoffset:0;opacity:0}"
        "%.4f%%{stroke-dasharray:%.2f 0;stroke-dashoffset:0;opacity:1}"
        "%.4f%%,100%%{stroke-dasharray:0 %.2f;stroke-dashoffset:%.2f;"
        "opacity:1}}" % (caught - 0.1, RING, caught, RING, gone, RING,
                         -RING / 2),
        ".burst{animation:burst %.2fs linear infinite}" % loop,
        "@keyframes burst{0%%,%.4f%%{opacity:0;transform:scale(.2)}"
        "%.4f%%{opacity:1;transform:scale(.9)}"
        "%.4f%%,100%%{opacity:0;transform:scale(1.8)}}"
        % (gone - 0.1, gone + 0.6, gone + 2.4),
        ".calm{animation:calm %.2fs linear infinite}"
        ".scared{animation:scared %.2fs linear infinite}"
        ".blink{animation:blink %.2fs linear infinite}" % (loop, loop, loop),
        "@keyframes calm{%s}" % windows(run["frights"], loop, ended, 0, 1),
        "@keyframes scared{%s}" % windows(run["frights"], loop, ended, 1, 0),
        "@keyframes blink{%s}" % windows(
            [[max(a, b - 7), b] for a, b in run["frights"]], loop, ended, 1,
            0),
    ]

    for index in range(len(GHOSTS)):
        path = run["ghosts"][index]
        style.append(".g%d{animation:g%dpath %.2fs linear infinite,"
                     "g%dseen %.2fs linear infinite}"
                     % (index + 1, index + 1, loop, index + 1, loop))
        style.append("@keyframes g%dpath{%s}"
                     % (index + 1, motion(path, columns, loop)))
        # Off the board twice over: while it is eaten, and once he is dead --
        # four ghosts piled on the last cell would hide the death entirely, and
        # in the arcade the screen clears for it too.
        style.append("@keyframes g%dseen{%s}"
                     % (index + 1,
                        windows(run["away"][index] + [[ended, ended + 999]],
                                loop, 10 ** 9, 0, 1)))
        style.append(".look%d{animation:look%d %.2fs linear infinite}"
                     % (index + 1, index + 1, loop))
        style.append("@keyframes look%d{%s}"
                     % (index + 1,
                        facing_frames(headings_of(path, columns), loop)
                        .replace("rotate(0deg)", "translate(1.2px,0)")
                        .replace("rotate(180deg)", "translate(-1.2px,0)")
                        .replace("rotate(90deg)", "translate(0,1.2px)")
                        .replace("rotate(270deg)", "translate(0,-1.2px)")))

    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d" role="img" aria-label="%s" '
            'font-family="%s">\n<title>%s</title>\n<style>%s</style>\n'
            '<rect width="%d" height="%d" fill="%s"/>\n%s\n%s\n%s\n%s\n'
            '</svg>\n'
            % (width, height, width, height,
               escape("A game of Pac-Man played out on the contribution "
                      "graph"), FONT,
               escape("A game of Pac-Man played out on the contribution "
                      "graph"),
               "\n".join(style + rules), width, height, theme["bg"],
               "\n".join(shapes),
               "\n".join(ghost(index + 1, colour)
                         for index, colour in enumerate(GHOSTS)),
               sprite(), "\n".join(numbers)))


def main():
    level, columns, total = calendar()
    run, seed = best_run(level, columns)
    if len(run["pac"]) < 20:
        sys.exit("no run of any length was possible on this board")

    os.makedirs(OUT, exist_ok=True)
    for name, theme in THEMES.items():
        path = os.path.join(OUT, "pacman-%s.svg" % name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(draw(run, level, columns, theme))
    walls = sum(1 for value in level.values() if value)
    print("%d weeks, %d contributions, %d walls | run of %d moves (seed %s), "
          "%d pellets eaten, %d ghosts caught, %s"
          % (columns, total, walls, len(run["pac"]) - 1, seed,
             len(run["eaten"]), len(run["kills"]),
             "died at the end" if run["caught"] else "ran out of moves"))
    print("wrote pacman-light.svg and pacman-dark.svg to %s/" % OUT)


if __name__ == "__main__":
    main()
