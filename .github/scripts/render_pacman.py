#!/usr/bin/env python3
"""Draw the contribution calendar as a game of Pac-Man that plays itself.

The board is not a drawn maze. It is the calendar: a day with work on it is a
wall, an empty day is a corridor with a pellet in it. So the maze is a year of
this account's history and it rearranges itself as the year fills in, without
anyone designing a level.

Nobody is playing. Three whole lives are played out here, when the SVG is built
-- Pac-Man looking for the nearest pellet and backing off when something is
close, four ghosts with four different amounts of patience, energizers, a
chase, and the death that ends each life -- and what ships is the recording.
That is the only way it can work: GitHub renders README images inside <img>,
where scripts never run, so nothing can be decided in the browser. CSS
animation does run there, so every move leaves here as a @keyframes rule and
the browser only interpolates between positions settled long before.

Three lives rather than one, and the pellets stay eaten across them, so a loop
holds three different games on a board that is emptier each time instead of the
same death in the same corner forever. The seed is fresh on every build, so no
two rebuilds are the same match.
"""

import datetime
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
DEATH_FOR = 1.3    # the mouth opening all the way round
REST_FOR = 0.5     # a beat before the next life starts
PAUSE_FOR = 1.3    # and a longer one on the last, before the loop restarts

LIVES = 3
SHORTEST = 90      # a life below this is not worth watching
LONGEST = 150      # above this, three of them will not fit
BUDGET = 420       # total moves in a loop, which is most of the file size
TRIES = 40         # seeds to look through for a life that fits

FRIGHT_STEPS = 20  # how long an energizer lasts
GHOST_BACK = 9     # steps an eaten ghost spends away from the board
# How long they let him live. Measured against the window the search below is
# looking for: with these two, a third of the seeds end in a death somewhere
# between 90 and 150 moves, averaging around 117.
RELENTLESS = 45    # after this many moves of one life, they stop dawdling
SETTLE = 90.0      # and their wandering fades out over this many
SCORES = (200, 400, 800, 1600)
SCORE_FOR = 0.9

# How often each ghost wanders instead of closing in. Four ghosts all taking
# the shortest step converge into a single moving wall and a life is over in
# seconds; giving each its own patience is also what makes the arcade four feel
# like four characters rather than one.
WANDER = (0.12, 0.30, 0.45, 0.62)

# GitHub's own two palettes, so the graph looks like the graph it is drawn from.
THEMES = {
    "light": {"bg": "#FFFFFF", "pellet": "#D8DEE4", "power": "#E09B54",
              "berry": "#E5484D", "stem": "#2EA043",
              "levels": ["#EBEDF0", "#9BE9A8", "#40C463", "#30A14E",
                         "#216E39"]},
    "dark": {"bg": "#0D1117", "pellet": "#30363D", "power": "#FFB897",
             "berry": "#FF6369", "stem": "#3FB950",
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
ANGLES = {"right": 0, "down": 90, "left": 180, "up": 270}

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


def apart(a, b, columns):
    """Distance ignoring walls -- near enough for deciding what is dangerous."""
    across = abs(a[0] - b[0])
    return min(across, columns - across) + abs(a[1] - b[1])


def opening(level, columns):
    """Where everything stands at the start of a life, and the energizers."""
    pac = nearest(level, columns, (columns // 2, 3))
    walkable = set(explore(level, columns, pac)[0])
    powers = []
    for share in (0.14, 0.38, 0.62, 0.86):
        powers.append(min((cell for cell in walkable if cell not in powers),
                          key=lambda cell: (abs(cell[0] - columns * share)
                                            + abs(cell[1] - 3))))
    ghosts = [nearest(level, columns, (int(columns * share), row))
              for share, row in ((0.18, 0), (0.38, 6), (0.62, 0), (0.82, 6))]
    return pac, walkable, set(powers), ghosts


def live(level, columns, seed, cleared):
    """Play one life out and write down everything that happened in it."""
    rng = random.Random(seed)
    pac, walkable, powers, ghosts = opening(level, columns)
    home = nearest(level, columns, (columns // 2, 0))

    life = {"pac": [pac], "dir": ["left"], "ghosts": [[g] for g in ghosts],
            "away": [[] for _ in ghosts], "ate": {}, "frights": [],
            "kills": [], "caught": False}
    eaten = set(cleared)
    facing, fright, combo = "left", 0, 0
    hidden = [0, 0, 0, 0]

    for tick in range(1, LONGEST + 1):
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
            near = [cell for cell in powers - eaten
                    if cell in distance and distance[cell] < 9]
            crowded = any(apart(pac, g, columns) < 5 for g in threats)
            wanted = (near if near and crowded
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
        # A step that walks straight into somebody is not worth a pellet: take
        # whichever option keeps the most room instead.
        if threats and min(apart(step, g, columns) for g in threats) <= 1:
            step = max(options, key=lambda cell: min(apart(cell, g, columns)
                                                     for g in threats))

        facing = next((name for name, (dx, dy) in STEPS.items()
                       if ((pac[0] + dx) % columns, pac[1] + dy) == step),
                      facing)
        pac = step
        if pac not in eaten:
            eaten.add(pac)
            life["ate"][pac] = tick
            if pac in powers:
                fright, combo = FRIGHT_STEPS, 0
                life["frights"].append([tick, tick + FRIGHT_STEPS])

        # Ghosts are slower than he is, and slower still while frightened.
        # They also stop dawdling the longer a life runs -- measured, not
        # guessed: without that escalation a life ran about 200 moves and three
        # of them would not fit in one loop; with it the median is 85.
        moving = ((True if tick > RELENTLESS else tick % 5 != 0)
                  if not fright else tick % 2 == 0)
        patience = max(0.15, 1 - tick / SETTLE)
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
            if rng.random() < WANDER[index] * patience:
                ghosts[index] = choices[0]
            elif fright:
                ghosts[index] = max(choices,
                                    key=lambda c: apart(c, pac, columns))
            else:
                ghosts[index] = min(choices,
                                    key=lambda c: apart(c, pac, columns))

        for index, ghost in enumerate(ghosts):
            if hidden[index] or ghost != pac:
                continue
            if fright:
                life["kills"].append((tick, SCORES[min(combo,
                                                       len(SCORES) - 1)], pac))
                combo += 1
                hidden[index] = GHOST_BACK
                life["away"][index].append([tick, tick + GHOST_BACK])
            else:
                life["caught"] = True

        if fright:
            fright -= 1
            if not fright:
                combo = 0

        life["pac"].append(pac)
        life["dir"].append(facing)
        for index, ghost in enumerate(ghosts):
            life["ghosts"][index].append(ghost)
        if life["caught"]:
            break
    return life, eaten


def compose(level, columns):
    """Three lives, back to back, laid out on one timeline.

    A life has to end in him actually being caught. One that merely ran out of
    moves would still be followed by the death animation, and he would die of
    nothing in an empty corridor with the ghosts somewhere else.
    """
    # Fresh randomness every time this runs, not a seed derived from the date.
    # A date gives the same three games all day however often it is rebuilt,
    # and the point of rebuilding is that the board is not the same recording
    # twice.
    base = random.SystemRandom().randrange(1 << 30)
    _, walkable, powers, _ = opening(level, columns)

    lives, cleared, spent = [], set(), 0
    for number in range(LIVES):
        chosen = None
        for attempt in range(TRIES):
            life, after = live(level, columns, base + number * 17 + attempt,
                               cleared)
            moves = len(life["pac"]) - 1
            fits = life["caught"] and SHORTEST <= moves <= LONGEST
            if fits and spent + moves <= BUDGET:
                chosen = (life, after)
                break
            if chosen is None or moves > len(chosen[0]["pac"]) - 1:
                chosen = (life, after)
        life, cleared = chosen
        lives.append(life)
        spent += len(life["pac"]) - 1
        if spent >= BUDGET:
            break

    at = 0.0
    for number, life in enumerate(lives):
        life["at"] = at
        life["moves"] = len(life["pac"]) - 1
        life["ends"] = at + life["moves"] * STEP
        life["gap"] = DEATH_FOR + (PAUSE_FOR if number == len(lives) - 1
                                   else REST_FOR)
        at = life["ends"] + life["gap"]
    return {"lives": lives, "loop": at, "walkable": walkable,
            "powers": powers}


def escape(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def condense(marks):
    """Drop every mark the browser would have arrived at by itself.

    Between two keyframes a transform is interpolated in a straight line at a
    constant rate, which is exactly what walking down a corridor is, so only
    the turns need saying. Five characters times three lives is most of the
    file, and this removes about half of it.
    """
    kept = [marks[0]]
    for index in range(1, len(marks) - 1):
        before, here, after = marks[index - 1], marks[index], marks[index + 1]
        first, second = here[0] - before[0], after[0] - here[0]
        # The test is equal velocity across the two neighbouring segments, and
        # it is made against the raw neighbours rather than the last mark kept.
        # Measuring from what survived lets a dropped point move the line the
        # next test is taken from, and the error walks: the path came out four
        # pixels away from the game that was actually played.
        if first > 1e-9 and second > 1e-9:
            if (abs((here[1] - before[1]) / first
                    - (after[1] - here[1]) / second) < 1e-6
                    and abs((here[2] - before[2]) / first
                            - (after[2] - here[2]) / second) < 1e-6):
                continue
        kept.append(here)
    kept.append(marks[-1])
    return kept


def trail(show, columns, index=None):
    """Every position a character holds, across all three lives.

    Two things have to be said out loud rather than left to interpolation. A
    walk through the tunnel leaves one edge and arrives at the other, which is
    not a slide back across the whole board; and a life ends where he died, so
    the position is held there through the death instead of drifting towards
    wherever the next life begins.
    """
    marks = []
    for life in show["lives"]:
        path = life["pac"] if index is None else life["ghosts"][index]
        for tick, cell in enumerate(path):
            when = life["at"] + tick * STEP
            x, y = centre(*cell)
            if tick:
                shift = cell[0] - path[tick - 1][0]
                if abs(shift) > 1:
                    heading = 1 if shift < 0 else -1
                    px, py = centre(*path[tick - 1])
                    marks.append((when - STEP * 0.5, px + heading * PITCH, py))
                    marks.append((when - STEP * 0.5 + 0.004,
                                  x - heading * PITCH, y))
            marks.append((when, x, y))
        held = centre(*path[-1])
        marks.append((life["ends"] + life["gap"] - 0.004, held[0], held[1]))
    return marks


def frames(marks, loop, shape="translate(%dpx,%dpx)"):
    # Four decimals, not three. A respawn is a jump of a whole board in four
    # milliseconds, and at three decimals one step of rounding is a tenth of
    # that jump -- the sprite is caught several pixels along the teleport.
    return "".join("%.4f%%{transform:%s}"
                   % (when / loop * 100.0, shape % (round(x), round(y)))
                   for when, x, y in condense(marks))


def turning(show, columns, index=None):
    """Which way a sprite points, as marks so the same condenser applies."""
    marks = []
    for life in show["lives"]:
        if index is None:
            names = life["dir"]
        else:
            names = ["left"]
            path = life["ghosts"][index]
            for tick in range(1, len(path)):
                shift = path[tick][0] - path[tick - 1][0]
                if abs(shift) > 1:
                    shift = 1 if shift < 0 else -1
                names.append(next((name for name, move in STEPS.items()
                                   if move == (shift, path[tick][1]
                                               - path[tick - 1][1])),
                                  names[-1]))
        for tick, name in enumerate(names):
            when = life["at"] + tick * STEP
            angle = ANGLES[name]
            if marks and marks[-1][1] == angle:
                continue
            # Two marks a hair apart, so a turn is a jump and not a spin.
            if marks:
                marks.append((when - 0.004, marks[-1][1], 0))
            marks.append((when, angle, 0))
        marks.append((life["ends"] + life["gap"] - 0.004, marks[-1][1], 0))
    return marks


def switching(intervals):
    """Keyframes for a value that only jumps, over a timeline with no gaps.

    Stated twice, at the start of each interval and just before the next, so
    nothing is interpolated between them -- and the last runs to 100%, where a
    missing keyframe would otherwise be invented from the property's own value
    and quietly undo the whole thing.
    """
    return "".join("%.3f%%{opacity:%g}%.3f%%{opacity:%g}"
                   % (start, value,
                      100.0 if index == len(intervals) - 1 else end - 0.004,
                      value)
                   for index, (start, end, value) in enumerate(intervals))


def windows(spans, loop, value, default):
    """Turn a list of second-ranges into the intervals `switching` wants.

    Overlapping ones are joined first. Two energizers eaten inside one fright,
    or a ghost caught twice in quick succession, would otherwise hand
    `switching` a timeline that runs backwards, and every keyframe after the
    overlap would land in the wrong order.
    """
    joined = []
    for start, end in sorted([float(a), float(b)] for a, b in spans):
        if joined and start <= joined[-1][1]:
            joined[-1][1] = max(joined[-1][1], end)
        else:
            joined.append([start, end])

    marks, edge = [], 0.0
    for start, end in joined:
        a = max(0.0, min(100.0, start / loop * 100.0))
        b = max(0.0, min(100.0, end / loop * 100.0))
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
    on the mouth. Two sprites also keeps the fast chew and the once-a-life
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


def cherry(theme):
    """The cherry that stands in for an energizer, four to a board.

    Described once in a defs block and pointed at by each of the four, which
    is also why it can be drawn properly: a fruit is a fiddly little thing to
    put in a ten-pixel cell, and the cost is paid once. Drawn around its own
    origin, because <use> places a copy by translating it.
    """
    return ('<defs><g id="ch">'
            '<path d="M-1.9,-0.4 Q-1.3,-3.3 0.2,-3.5 Q1.7,-3.3 1.9,-0.4" '
            'fill="none" stroke="%s" stroke-width="0.8" '
            'stroke-linecap="round"/>'
            '<circle cx="-1.9" cy="1.5" r="2.1" fill="%s"/>'
            '<circle cx="1.9" cy="1.5" r="2.1" fill="%s"/>'
            '<circle cx="-2.5" cy="0.9" r="0.6" fill="#FFFFFF" '
            'opacity=".5"/>'
            '<circle cx="1.3" cy="0.9" r="0.6" fill="#FFFFFF" '
            'opacity=".5"/></g></defs>'
            % (theme["stem"], theme["berry"], theme["berry"]))


def ghost(index, colour):
    return ('<g class="g%d"><g class="calm"><path d="%s" fill="%s"/>'
            '<circle cx="-2.4" cy="-1.2" r="2" fill="#FFFFFF"/>'
            '<circle cx="2.4" cy="-1.2" r="2" fill="#FFFFFF"/>'
            '<g class="look%d"><circle cx="-2.4" cy="-1.2" r="1" fill="%s"/>'
            '<circle cx="2.4" cy="-1.2" r="1" fill="%s"/></g></g>%s%s</g>'
            % (index, GHOST_BODY, colour, index, PUPIL, PUPIL,
               afraid(SCARED, SCARED_TRIM, "scared"),
               afraid(FLASHED, FLASHED_TRIM, "blink")))


def dying(show):
    """The death, once per life, on a disc that is eaten away to nothing."""
    loop = show["loop"]
    whole = "stroke-dasharray:%.2f 0;stroke-dashoffset:0" % RING
    nothing = "stroke-dasharray:0 %.2f;stroke-dashoffset:%.2f" % (RING,
                                                                  -RING / 2)
    parts = ["0%%{opacity:0;%s}" % whole]
    for life in show["lives"]:
        start = life["ends"] / loop * 100.0
        finish = (life["ends"] + DEATH_FOR) / loop * 100.0
        parts.append("%.3f%%{opacity:0;%s}%.3f%%{opacity:1;%s}"
                     % (start - 0.004, whole, start, whole))
        parts.append("%.3f%%{opacity:1;%s}%.3f%%{opacity:0;%s}"
                     % (finish, nothing, finish + 0.004, whole))
    parts.append("100%%{opacity:0;%s}" % whole)
    return "".join(parts)


def bursting(show):
    loop = show["loop"]
    parts = ["0%{opacity:0;transform:scale(.2)}"]
    for life in show["lives"]:
        pop = life["ends"] + DEATH_FOR
        parts.append("%.3f%%{opacity:0;transform:scale(.2)}"
                     % ((pop - 0.02) / loop * 100.0))
        parts.append("%.3f%%{opacity:1;transform:scale(.9)}"
                     % ((pop + 0.15) / loop * 100.0))
        parts.append("%.3f%%{opacity:0;transform:scale(1.8)}"
                     % ((pop + 0.6) / loop * 100.0))
    parts.append("100%{opacity:0;transform:scale(1.8)}")
    return "".join(parts)


def draw(show, level, columns, theme):
    loop = show["loop"]
    width = MARGIN * 2 + columns * PITCH - GAP
    height = MARGIN * 2 + ROWS * PITCH - GAP
    gaps = [[life["ends"], life["ends"] + life["gap"]]
            for life in show["lives"]]

    eaten_at = {}
    frights, kills, away = [], [], [[] for _ in GHOSTS]
    for life in show["lives"]:
        for cell, tick in life["ate"].items():
            eaten_at.setdefault(cell, life["at"] + tick * STEP)
        for start, end in life["frights"]:
            frights.append([life["at"] + start * STEP,
                            min(life["at"] + end * STEP, life["ends"])])
        for tick, points, cell in life["kills"]:
            kills.append((life["at"] + tick * STEP, points, cell))
        for index, spans in enumerate(life["away"]):
            for start, end in spans:
                away[index].append([life["at"] + start * STEP,
                                    min(life["at"] + end * STEP,
                                        life["ends"])])

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
        if cell not in show["walkable"]:
            continue
        if cell in show["powers"]:
            # The one worth crossing the board for. Two classes on two nested
            # elements because both are opacity: the cherry blinks where it
            # lies, the group around it is what takes it off the board when he
            # gets there, and one element cannot be told twice what its
            # opacity does.
            shapes.append('<g class="%s"><use class="power" href="#ch" '
                          'x="%d" y="%d"/></g>' % (name, round(x), round(y)))
        else:
            shapes.append('<circle class="%s" cx="%.1f" cy="%.1f" r="1.6" '
                          'fill="%s"/>' % (name, x, y, theme["pellet"]))
        when = eaten_at.get(cell)
        if when is None:
            continue
        at = when / loop * 100.0
        # The keyframe at 100% is not decoration: without one the browser
        # invents a final keyframe from the property's own value, and every
        # eaten pellet fades back in over the rest of the loop.
        rules.append(".%s{animation:%s %.2fs linear infinite}"
                     "@keyframes %s{0%%,%.3f%%{opacity:1}%.3f%%,100%%"
                     "{opacity:0}}" % (name, name, loop, name, at, at + 0.4))

    numbers = []
    for order, (when, points, cell) in enumerate(kills):
        x, y = centre(*cell)
        name = "s%d" % order
        numbers.append('<text class="%s" x="%.1f" y="%.1f" '
                       'text-anchor="middle" font-size="9" font-weight="700" '
                       'fill="%s">%d</text>'
                       % (name, x, y - 1, SCORE_COLOUR, points))
        at = when / loop * 100.0
        rules.append(
            ".%s{animation:%s %.2fs linear infinite}"
            "@keyframes %s{0%%,%.3f%%{opacity:0;transform:translate(0,0)}"
            "%.3f%%{opacity:1;transform:translate(0,-2px)}"
            "%.3f%%,100%%{opacity:0;transform:translate(0,-13px)}}"
            % (name, name, loop, name, at - 0.004, at,
               (when + SCORE_FOR) / loop * 100.0))

    style = [
        ".pac,.facing,.jaw,.burst,.g1,.g2,.g3,.g4,"
        ".look1,.look2,.look3,.look4"
        "{transform-box:view-box;transform-origin:0 0}",
        ".pac{animation:walk %.2fs linear infinite}" % loop,
        "@keyframes walk{%s}" % frames(trail(show, columns), loop),
        ".facing{animation:facing %.2fs linear infinite}" % loop,
        "@keyframes facing{%s}" % spin(turning(show, columns), loop),
        ".jaw{animation:chew .34s ease-in-out infinite}",
        ".down{animation-name:chew-down}",
        "@keyframes chew{0%,100%{transform:rotate(0)}"
        "50%{transform:rotate(-32deg)}}",
        "@keyframes chew-down{0%,100%{transform:rotate(0)}"
        "50%{transform:rotate(32deg)}}",
        ".power{animation:pulse .5s steps(1,end) infinite}",
        "@keyframes pulse{0%,49%{opacity:1}50%,100%{opacity:.15}}",
        ".alive{animation:alive %.2fs linear infinite}" % loop,
        "@keyframes alive{%s}" % windows(gaps, loop, 0, 1),
        ".death{animation:death %.2fs linear infinite}" % loop,
        "@keyframes death{%s}" % dying(show),
        ".burst{animation:burst %.2fs linear infinite}" % loop,
        "@keyframes burst{%s}" % bursting(show),
        ".calm{animation:calm %.2fs linear infinite}"
        ".scared{animation:scared %.2fs linear infinite}"
        ".blink{animation:blink %.2fs linear infinite}" % (loop, loop, loop),
        "@keyframes calm{%s}" % windows(frights, loop, 0, 1),
        "@keyframes scared{%s}" % windows(frights, loop, 1, 0),
        "@keyframes blink{%s}" % windows([[max(a, b - 1.05), b]
                                          for a, b in frights], loop, 1, 0),
    ]

    for index in range(len(GHOSTS)):
        style.append(".g%d{animation:w%d %.2fs linear infinite,"
                     "s%dseen %.2fs linear infinite}"
                     % (index + 1, index + 1, loop, index + 1, loop))
        style.append("@keyframes w%d{%s}"
                     % (index + 1,
                        frames(trail(show, columns, index), loop)))
        # Off the board twice over: while it is eaten, and through every death
        # -- four ghosts piled on the last cell would hide it entirely, and in
        # the arcade the screen clears for a death as well.
        style.append("@keyframes s%dseen{%s}"
                     % (index + 1,
                        windows(away[index] + gaps, loop, 0, 1)))
        style.append(".look%d{animation:look%d %.2fs linear infinite}"
                     % (index + 1, index + 1, loop))
        style.append("@keyframes look%d{%s}"
                     % (index + 1, eyes(turning(show, columns, index), loop)))

    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d" role="img" aria-label="%s" '
            'font-family="%s">\n<title>%s</title>\n<style>%s</style>\n%s\n'
            '<rect width="%d" height="%d" fill="%s"/>\n%s\n%s\n%s\n%s\n'
            '</svg>\n'
            % (width, height, width, height,
               escape("Three lives of Pac-Man played out on the contribution "
                      "graph"), FONT,
               escape("Three lives of Pac-Man played out on the contribution "
                      "graph"),
               "\n".join(style + rules), cherry(theme), width, height,
               theme["bg"],
               "\n".join(shapes),
               "\n".join(ghost(index + 1, colour)
                         for index, colour in enumerate(GHOSTS)),
               sprite(), "\n".join(numbers)))


def spin(marks, loop):
    """Angle marks as rotations."""
    return "".join("%.4f%%{transform:rotate(%ddeg)}"
                   % (when / loop * 100.0, angle)
                   for when, angle, _ in marks)


def eyes(marks, loop):
    """The same marks, as the small lean of a pupil."""
    lean = {0: (1.2, 0), 90: (0, 1.2), 180: (-1.2, 0), 270: (0, -1.2)}
    return "".join("%.4f%%{transform:translate(%.1fpx,%.1fpx)}"
                   % ((when / loop * 100.0,) + lean[angle])
                   for when, angle, _ in marks)


def main():
    level, columns, total = calendar()
    show = compose(level, columns)
    if not show["lives"]:
        sys.exit("no life of any length was possible on this board")

    os.makedirs(OUT, exist_ok=True)
    for name, theme in THEMES.items():
        path = os.path.join(OUT, "pacman-%s.svg" % name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(draw(show, level, columns, theme))
    walls = sum(1 for value in level.values() if value)
    print("%d weeks, %d contributions, %d walls | loop %.1fs"
          % (columns, total, walls, show["loop"]))
    for number, life in enumerate(show["lives"], 1):
        print("  life %d: %3d moves, %3d pellets, %d ghosts caught, %s"
              % (number, life["moves"], len(life["ate"]), len(life["kills"]),
                 "died" if life["caught"] else "ran out"))
    print("wrote pacman-light.svg and pacman-dark.svg to %s/" % OUT)


if __name__ == "__main__":
    main()
