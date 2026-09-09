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

That phase shift is also the reason a ghost needs a second transform of its
own. Its route animation is running on a clock offset from everybody else's,
so nothing written into those keyframes can be made to happen at a particular
moment of the loop -- and an energizer has to. The drift track is that second
transform, unshifted: while a fright is on it pulls a ghost further back along
the route it is already following, or, for the ones being eaten, exactly onto
Pac-Man at the instant he takes them. Both are computed here rather than
guessed, which is why the routes are linear -- an eased position cannot be
worked out from outside the browser.
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

LOOP = 36.0        # seconds end to end: sweep, then the ghosts catch him
MOVING = 0.80      # the share of the loop spent eating
CAUGHT = 0.865     # they have all arrived by here, and he dies
GONE = 0.915       # dead; the board sits empty until the loop restarts
JAWS = 0.34        # one open-and-shut

# Four energizers, spaced along the route rather than dropped in the corners
# the arcade uses: corners here would fire one at the very first cell and one
# at the very last, and the point of them is that the chase changes character
# four times over the run. Each is snapped to the nearest day with nothing on
# it, so no contribution square is overwritten to make room for one.
ENERGIZERS = (0.15, 0.38, 0.61, 0.84)
SCARED_FOR = 3.6   # seconds the ghosts stay blue after one is eaten
FLASH_FOR = 1.2    # the tail of that, spent flashing white
FLASH_EVERY = 0.3

# How far behind Pac-Man each ghost runs, in seconds. Deliberately uneven:
# evenly spaced trails read as one train rather than four things chasing him.
# The last of them has to arrive before CAUGHT, or a ghost would still be on
# its way in while he is already being eaten.
TRAILS = (0.45, 1.05, 1.65, 2.2)

# What a fright does to the chase. A fleeing ghost is pushed further back along
# the route it is already on -- expressed as extra seconds of lag rather than a
# distance, because at a corner a fixed vector points off the board while a
# second of lag simply puts it round the bend behind. Anything eaten lunges the
# wrong way into him instead, and the scores double the way the arcade doubles
# them within one energizer.
FLED_BY = 0.95     # seconds of extra lag while running away
FLINCH_BY = 0.28   # the shorter one, for a ghost that is about to be eaten
FLEE_IN = 0.7      # how long the running-away takes
EATEN_AT = (1.2, 1.7, 2.2, 2.7)   # seconds into the fright, nearest first
SCORES = (200, 400, 800, 1600)
SCORE_COLOUR = "#00E0E8"
SCORE_FONT = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif")
SCORE_FOR = 0.9    # how long the number hangs there
# Each ghost bobs on its own clock, so they never line up: seconds, then how
# far it rises, then a fixed nudge that keeps them from stacking into one
# shape when they all arrive at the last cell.
BOBS = ((1.05, 3.0, -3, 0), (1.35, 4.0, 3, -1), (0.90, 2.5, -1, 2),
        (1.50, 3.5, 4, 1))

# GitHub's own two palettes, so the graph looks like the graph it is drawn from.
THEMES = {
    "light": {"bg": "#FFFFFF", "empty": "#EBEDF0", "pellet": "#D8DEE4",
              "power": "#E09B54",
              "levels": ["#EBEDF0", "#9BE9A8", "#40C463", "#30A14E",
                         "#216E39"]},
    "dark": {"bg": "#0D1117", "empty": "#161B22", "pellet": "#30363D",
             "power": "#FFB897",
             "levels": ["#161B22", "#0E4429", "#006D32", "#26A641",
                        "#39D353"]},
}

PACMAN = "#FFD534"
# The arcade four, by their own colours: Blinky, Pinky, Inky, Clyde.
GHOSTS = ("#FF0000", "#FFB8FF", "#00FFFF", "#FFB852")
PUPIL = "#2121DE"
SCARED = "#2121DE"      # the blue they turn when an energizer goes
SCARED_TRIM = "#FFFFFF"
FLASHED = "#FFFFFF"     # and the white they blink before it wears off
FLASHED_TRIM = "#FF0000"

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


def step_at(seconds, steps):
    """Where along the sweep a moment in the loop falls."""
    return max(0.0, min(float(steps), seconds / (MOVING * LOOP) * steps))


def place(step, corners):
    """The point the sweep is at, part way between two corners.

    The route keyframes only name the corners and let the browser interpolate.
    This is the same interpolation done here, which is what makes it possible
    to say where a ghost will be at a given moment -- and so to place one on
    top of Pac-Man exactly when he is meant to eat it.
    """
    for start, end in zip(corners, corners[1:]):
        if step <= end[0]:
            span = end[0] - start[0]
            share = 0.0 if span <= 0 else (step - start[0]) / float(span)
            share = max(0.0, min(1.0, share))
            ax, ay = centre(start[1], start[2])
            bx, by = centre(end[1], end[2])
            return (ax + (bx - ax) * share, ay + (by - ay) * share)
    return centre(corners[-1][1], corners[-1][2])


def whereis(seconds, corners, steps, trail=0.0):
    """A character's point at a moment of the loop, its own lag included."""
    return place(step_at(seconds - trail, steps), corners)


def lag(seconds, behind, corners, steps, trail):
    """The offset that puts a ghost `behind` seconds further back than it is.

    Following its own route backwards rather than shifting it by a fixed
    vector: at the end of a row a fixed vector would push it off the board,
    where extra lag simply places it round the corner it came from.
    """
    now = whereis(seconds, corners, steps, trail)
    then = whereis(seconds - behind, corners, steps, trail)
    return (then[0] - now[0], then[1] - now[1])


def held(segments, default):
    """Keyframes holding a value across each segment and `default` elsewhere.

    Every one of them ends at 100%. An absent final keyframe is not simply the
    last value carried over -- the browser fills one in from the property's own
    value, and the animation drifts back towards it across whatever is left of
    the loop.
    """
    frames = ["0%%{opacity:%d}" % default]
    for start, end, value in segments:
        frames.append("%.4f%%{opacity:%d}%.4f%%{opacity:%d}"
                      "%.4f%%{opacity:%d}%.4f%%{opacity:%d}"
                      % (max(start - 0.005, 0.0), default, start, value,
                         end, value, min(end + 0.005, 100.0), default))
    frames.append("100%%{opacity:%d}" % default)
    return "".join(frames)


def switching(intervals):
    """Keyframes for a value that only jumps, over a timeline with no gaps.

    Each interval is stated twice, at its start and just before the next one
    begins, so nothing is ever interpolated between two of them and the last
    reaches 100% -- where an absent keyframe would otherwise be invented from
    the property's own value.
    """
    frames = []
    for index, (start, end, value) in enumerate(intervals):
        tail = 100.0 if index == len(intervals) - 1 else end - 0.004
        frames.append("%.4f%%{opacity:%g}%.4f%%{opacity:%g}"
                      % (start, value, tail, value))
    return "".join(frames)


def hunts(powered, steps):
    """The fright windows, and who gets eaten in each.

    One more ghost goes with every energizer, nearest first, so the scores run
    200, 400, 800, 1600 the way they do inside a single arcade fright -- and so
    the last of the four is the one where the whole quartet disappears.
    """
    windows = []
    for index, step in enumerate(sorted(powered.values())):
        start = step / float(steps) * MOVING * LOOP
        windows.append({
            "start": start,
            "end": start + SCARED_FOR,
            "eats": [(ghost, start + EATEN_AT[ghost])
                     for ghost in range(min(index + 1, len(TRAILS)))],
        })
    return windows


def fright(windows):
    """The three states a ghost is in, as one set of shared keyframes.

    All four turn at once, so the timing is the same for every ghost and none
    of these carry the phase shift their routes do.
    """
    flash = FLASH_FOR / LOOP * 100.0
    beat = FLASH_EVERY / LOOP * 100.0

    windows = [(window["start"] / LOOP * 100.0, window["end"] / LOOP * 100.0)
               for window in windows]
    pulses = []
    for _, end in windows:
        moment, lit = end - flash, True
        while moment < end - 0.001:
            if lit:
                pulses.append((moment, min(moment + beat, end)))
            moment += beat
            lit = not lit

    return ("@keyframes calm{%s}@keyframes scared{%s}@keyframes blink{%s}"
            % (held([(start, end, 0) for start, end in windows], 1),
               held([(start, end, 1) for start, end in windows], 0),
               held([(start, end, 1) for start, end in pulses], 0)))


def looking(corners, steps):
    """Ghost pupils lean the way the ghost is travelling."""
    frames = []
    for index in range(0, len(corners), 2):
        shift = 1.2 if corners[index][2] % 2 == 0 else -1.2
        frames.append("%.3f%%,%.3f%%{transform:translate(%.1fpx,0)}"
                      % (percent(corners[index][0], steps),
                         percent(corners[index + 1][0], steps), shift))
    frames.append("100%%{transform:translate(%.1fpx,0)}"
                  % (1.2 if (ROWS - 1) % 2 == 0 else -1.2))
    return "@keyframes looking{%s}" % "".join(frames)


def board(weeks):
    """Contribution level per (column, row); missing where the calendar has no
    such day, which happens at both ends because it arrives in whole weeks."""
    filled = {}
    for column, week in enumerate(weeks):
        for day in week["contributionDays"]:
            filled[(column, day["weekday"])] = LEVELS.get(
                day["contributionLevel"], 0)
    return filled


def energizers(order, filled):
    """Pick the four energizer cells, and say when each is eaten.

    Only days with nothing on them are eligible, so the graph keeps every one
    of its squares; an energizer replaces a pellet, never a contribution.
    """
    empty = [cell for cell in order if filled.get((cell[1], cell[2])) == 0]
    chosen = {}
    if not empty:
        return chosen
    last = order[-1][0]
    for fraction in ENERGIZERS:
        target = fraction * last
        pick = min(empty, key=lambda cell: abs(cell[0] - target))
        empty.remove(pick)
        chosen[(pick[1], pick[2])] = pick[0]
    return chosen


def cells(theme, steps, order, filled, powered):
    """The board, plus the keyframes that take each cell off it."""
    shapes = []
    rules = []
    for step, column, row in order:
        level = filled.get((column, row))
        if level is None:               # the calendar starts and ends mid-week
            continue
        x, y = centre(column, row)
        eaten = percent(step, steps)
        name = "e%d_%d" % (column, row)
        if (column, row) in powered:
            # The blink is on the circle and the eating is on the group around
            # it. Both are opacity, and one element can only be told once what
            # its opacity does -- the longer animation would simply overrule
            # the blink. Nested, the two multiply instead of competing.
            shapes.append('<g class="%s"><circle class="power" cx="%.1f" '
                          'cy="%.1f" r="3.4" fill="%s"/></g>'
                          % (name, x, y, theme["power"]))
        elif level:
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
        # of the loop. The keyframe at 100% is not decoration: without one the
        # browser fills in an implicit final keyframe from the property's own
        # value, which is opacity 1 -- every eaten cell would fade back in over
        # the remainder of the loop, and the board would refill behind him.
        rules.append(".%s{animation:%s %.1fs linear infinite}"
                     "@keyframes %s{0%%,%.3f%%{opacity:1}%.3f%%,100%%"
                     "{opacity:0}}"
                     % (name, name, LOOP, name, eaten, eaten + 0.45))
    return shapes, rules


def mover(name, corners, steps, trail, easing="linear"):
    """Position keyframes for one character, phase-shifted by `trail`."""
    frames = []
    for step, column, row in corners:
        x, y = centre(column, row)
        frames.append("%.3f%%{transform:translate(%.1fpx,%.1fpx)}"
                      % (percent(step, steps), x, y))
    # The sweep ends before the loop does; parking on the last corner is what
    # gathers the ghosts around him there, each arriving its own trail late.
    frames.append("100%%{transform:translate(%.1fpx,%.1fpx)}"
                  % centre(corners[-1][1], corners[-1][2]))
    rule = ".%s{animation:route %.1fs %s infinite" % (name, LOOP, easing)
    if trail:
        # A negative delay is a phase shift. Shifting by a whole loop minus the
        # trail puts the ghost behind Pac-Man instead of in front of him.
        rule += ";animation-delay:%.2fs" % -(LOOP - trail)
    return rule + "}", "@keyframes route{%s}" % "".join(frames)


def drifting(index, trail, corners, steps, windows):
    """What a fright pulls this ghost away from the chase to do.

    Its place in the queue behind Pac-Man is the route animation, which is
    phase-shifted and so cannot say anything about a moment of the loop. This
    is the second, unshifted transform on top of it: fleeing is extra lag, and
    being eaten is the offset that lands it exactly where Pac-Man is at the
    instant he takes it.
    """
    marks = [(0.0, 0.0, 0.0)]
    for window in windows:
        start, end = window["start"], window["end"]
        eaten = dict(window["eats"]).get(index)
        marks.append((start, 0.0, 0.0))
        if eaten is None:
            moment = start + FLEE_IN
            while moment < end - 0.5:
                marks.append((moment,) + lag(moment, FLED_BY, corners, steps,
                                             trail))
                moment += 0.4
        else:
            flinch = start + 0.32
            marks.append((flinch,) + lag(flinch, FLINCH_BY, corners, steps,
                                         trail))
            him = whereis(eaten, corners, steps)
            mine = whereis(eaten, corners, steps, trail)
            marks.append((eaten, him[0] - mine[0], him[1] - mine[1]))
            # Back to nothing the moment it is gone, while it cannot be seen
            # doing it, so it returns at the end of the fright in its own place.
            marks.append((eaten + 0.02, 0.0, 0.0))
        marks.append((end, 0.0, 0.0))
    marks.append((LOOP, 0.0, 0.0))
    return ("".join([
        ".drift%d{animation:drift%d %.1fs linear infinite}"
        % (index + 1, index + 1, LOOP),
        "@keyframes drift%d{%s}"
        % (index + 1,
           "".join("%.4f%%{transform:translate(%.1fpx,%.1fpx)}"
                   % (moment / LOOP * 100.0, dx, dy)
                   for moment, dx, dy in marks)),
    ]))


def haunting(index, trail, windows):
    """A ghost's bob, and the windows it is on the board at all.

    Two reasons it is not: until its phase wraps it is still parked at the end
    of the last sweep, which would show as a ghost sitting at the finish while
    Pac-Man sets off; and once eaten it stays gone until the fright it was
    eaten in runs out.
    """
    period, rise, dx, dy = BOBS[index]
    appears = trail / LOOP * 100.0
    spans = [(0.0, appears, 0)]
    for window in windows:
        eaten = dict(window["eats"]).get(index)
        if eaten is not None:
            spans.append((eaten / LOOP * 100.0, window["end"] / LOOP * 100.0,
                          0))
    spans.append((CAUGHT * 100.0, 100.0, 0))

    intervals = []
    edge = 0.0
    for start, end, value in spans:
        if start > edge:
            intervals.append((edge, start, 1))
        intervals.append((start, end, value))
        edge = end
    if edge < 100.0:
        intervals.append((edge, 100.0, 1))

    return ("".join([
        ".bob%d{animation:bob%d %.2fs ease-in-out infinite,"
        "haunt%d %.1fs linear infinite}" % (index + 1, index + 1, period,
                                            index + 1, LOOP),
        "@keyframes bob%d{0%%,100%%{transform:translate(%dpx,%dpx)}"
        "50%%{transform:translate(%dpx,%.1fpx)}}"
        % (index + 1, dx, dy, dx, dy - rise),
        # Gone the instant they have him at the end, too. Four ghosts piled on
        # the last cell cover him completely, and the death is the thing worth
        # watching -- in the arcade the screen clears and he dies alone as well.
        "@keyframes haunt%d{%s}" % (index + 1, switching(intervals)),
    ]))


def scoreboard(windows, corners, steps):
    """The number that hangs in the air where a ghost was eaten."""
    shapes, rules = [], []
    for index, window in enumerate(windows):
        for order, (_, when) in enumerate(window["eats"]):
            x, y = whereis(when, corners, steps)
            name = "s%d_%d" % (index, order)
            shapes.append('<text class="%s" x="%.1f" y="%.1f" '
                          'text-anchor="middle" font-size="9" '
                          'font-weight="700" fill="%s" font-family="%s">'
                          '%d</text>'
                          % (name, x, y - 1, SCORE_COLOUR, SCORE_FONT,
                             SCORES[order]))
            begins = when / LOOP * 100.0
            rules.append(
                ".%s{animation:%s %.1fs linear infinite}"
                "@keyframes %s{0%%,%.4f%%{opacity:0;transform:translate(0,0)}"
                "%.4f%%{opacity:1;transform:translate(0,-2px)}"
                "%.4f%%,100%%{opacity:0;transform:translate(0,-13px)}}"
                % (name, name, LOOP, name, begins - 0.004, begins,
                   (when + SCORE_FOR) / LOOP * 100.0))
    return shapes, rules


def facing(corners, steps):
    """Which way the mouth points: rows alternate, so the sprite flips."""
    frames = []
    for index in range(0, len(corners), 2):
        start = percent(corners[index][0], steps)
        angle = 0 if corners[index][2] % 2 == 0 else 180
        # Two keyframes a hair apart make the flip a jump rather than a spin.
        frames.append("%.3f%%,%.3f%%{transform:rotate(%ddeg)}"
                      % (start, percent(corners[index + 1][0], steps), angle))
    # Cornered, he turns to face up, which is the position the arcade death is
    # drawn from. Holding the angle to 100% afterwards matters for the same
    # reason the cells hold their opacity: an absent final keyframe is filled
    # in from the property's own value, and he would swing back to facing right
    # while being eaten.
    last = 0 if (ROWS - 1) % 2 == 0 else 180
    frames.append("%.3f%%{transform:rotate(%ddeg)}"
                  % (CAUGHT * 100 - 1.2, last))
    frames.append("%.3f%%,100%%{transform:rotate(-90deg)}" % (CAUGHT * 100))
    return "@keyframes facing{%s}" % "".join(frames)


RADIUS = 6.4
# A circle stroked with a width equal to its diameter reads as a disc, and then
# stroke-dasharray can take angular bites out of it. Drawn on a path of half
# the radius so the stroke spans the whole of it.
RING = 2 * 3.141592653589793 * (RADIUS / 2)


def sprite():
    """Pac-Man twice: the one that chews, and the one that dies.

    Chewing is two half discs hinged at the centre -- a wedge cut from a circle
    is not a shape CSS can animate, but two halves swung apart leave exactly
    that silhouette and need only a rotation each.

    The arcade death is a different problem: the mouth opens past a half circle
    and keeps going until nothing is left, which those two halves cannot do --
    swing them a full 180 degrees and they have merely swapped places and
    closed up again. So the dying Pac-Man is a second sprite, a disc drawn as a
    thick stroke whose dasharray shrinks to nothing, with the gap centred on
    the mouth. Two sprites rather than one also keeps the fast chew and the
    once-a-loop death off the same property, where the longer animation would
    simply overrule the shorter one.
    """
    top = ("M0,0 L%.1f,0 A%.1f,%.1f 0 0 0 %.1f,0 Z"
           % (RADIUS, RADIUS, RADIUS, -RADIUS))
    bottom = ("M0,0 L%.1f,0 A%.1f,%.1f 0 0 1 %.1f,0 Z"
              % (RADIUS, RADIUS, RADIUS, -RADIUS))
    spokes = "".join(
        '<line x1="0" y1="-3.4" x2="0" y2="-8.4" transform="rotate(%d)"/>'
        % (angle,) for angle in range(0, 360, 60))
    return ('<g class="pac"><g class="facing">'
            '<g class="alive">'
            '<path class="jaw top" d="%s" fill="%s"/>'
            '<path class="jaw bottom" d="%s" fill="%s"/></g>'
            '<circle class="death" cx="0" cy="0" r="%.2f" fill="none" '
            'stroke="%s" stroke-width="%.1f"/>'
            '<g class="burst" stroke="%s" stroke-width="1.6" '
            'stroke-linecap="round">%s</g>'
            '</g></g>'
            % (top, PACMAN, bottom, PACMAN, RADIUS / 2, PACMAN, RADIUS,
               PACMAN, spokes))


GHOST_BODY = ("M-6,3 L-6,-1 A6,6 0 0 1 6,-1 L6,3 "
              "L4.5,4.5 L3,3 L1.5,4.5 L0,3 L-1.5,4.5 L-3,3 L-4.5,4.5 Z")


def afraid(fill, trim, name):
    """The blue ghost, and the white one it blinks into as the fright runs out.

    Square eyes and a zigzag for a mouth: at this size that pair is the whole
    difference between a ghost that is chasing and a ghost that is running, and
    it is the difference the arcade draws too.
    """
    return ('<g class="%s"><path d="%s" fill="%s"/>'
            '<rect x="-3.1" y="-2.2" width="1.8" height="1.8" fill="%s"/>'
            '<rect x="1.3" y="-2.2" width="1.8" height="1.8" fill="%s"/>'
            '<path d="M-3.6,2 L-2.4,0.9 L-1.2,2 L0,0.9 L1.2,2 L2.4,0.9 '
            'L3.6,2" fill="none" stroke="%s" stroke-width="0.9"/></g>'
            % (name, GHOST_BODY, fill, trim, trim, trim))


def ghost(index, colour):
    """A ghost, in its three states, stacked and cross-faded by opacity.

    Three sprites rather than one recoloured sprite: a ghost that is merely
    tinted blue still has round eyes looking where it is going, which is the
    opposite of what a frightened one does.
    """
    return ('<g class="g%d"><g class="drift%d"><g class="bob%d">'
            '<g class="calm"><path d="%s" fill="%s"/>'
            '<circle cx="-2.4" cy="-1.2" r="2" fill="#FFFFFF"/>'
            '<circle cx="2.4" cy="-1.2" r="2" fill="#FFFFFF"/>'
            '<g class="look%d">'
            '<circle cx="-2.4" cy="-1.2" r="1" fill="%s"/>'
            '<circle cx="2.4" cy="-1.2" r="1" fill="%s"/></g></g>'
            '%s%s</g></g></g>'
            % (index, index, index, GHOST_BODY, colour, index, PUPIL, PUPIL,
               afraid(SCARED, SCARED_TRIM, "scared"),
               afraid(FLASHED, FLASHED_TRIM, "blink")))


def draw(weeks, theme):
    columns = len(weeks)
    order, corners, steps = route(columns)
    filled = board(weeks)
    powered = energizers(order, filled)
    shapes, rules = cells(theme, steps, order, filled, powered)

    width = MARGIN * 2 + columns * PITCH - GAP
    height = MARGIN * 2 + ROWS * PITCH - GAP

    windows = hunts(powered, steps)
    numbers, number_rules = scoreboard(windows, corners, steps)

    pac_rule, route_frames = mover("pac", corners, steps, 0)
    # Every route is linear now. It was eased for two of them, which wove them
    # about nicely, but an eased position cannot be worked out from the outside
    # -- and being able to say exactly where a ghost is at a given instant is
    # what lets one be put under Pac-Man's mouth at the moment he eats it. The
    # weaving is paid for by the frights instead, which scatter them four times
    # a lap.
    ghost_rules = [mover("g%d" % (index + 1), corners, steps, trail)[0]
                   for index, trail in enumerate(TRAILS)]
    ghost_rules += [haunting(index, trail, windows)
                    for index, trail in enumerate(TRAILS)]
    ghost_rules += [drifting(index, trail, corners, steps, windows)
                    for index, trail in enumerate(TRAILS)]

    style = [
        # Every animated group is positioned by transform, so they all need the
        # same origin: the sprite is drawn around 0,0 and moved to the cell.
        ".pac,.facing,.jaw,.burst,.g1,.g2,.g3,.g4,.bob1,.bob2,.bob3,.bob4,"
        ".look1,.look2,.look3,.look4,.drift1,.drift2,.drift3,.drift4"
        "{transform-box:view-box;transform-origin:0 0}",
        pac_rule,
        route_frames,
        "\n".join(ghost_rules),
        # Caught at the last cell, with every ghost piled on top of him: the
        # chewing sprite is swapped for the dying one, and the mouth keeps
        # opening until the disc has been eaten away entirely.
        ".alive{animation:alive %.1fs linear infinite}" % LOOP,
        "@keyframes alive{0%%,%.2f%%{opacity:1}%.2f%%,100%%{opacity:0}}"
        % (CAUGHT * 100 - 0.1, CAUGHT * 100),
        ".death{animation:death %.1fs linear infinite}" % LOOP,
        "@keyframes death{0%%,%.2f%%{stroke-dasharray:%.2f 0;"
        "stroke-dashoffset:0;opacity:0}"
        "%.2f%%{stroke-dasharray:%.2f 0;stroke-dashoffset:0;opacity:1}"
        "%.1f%%,100%%{stroke-dasharray:0 %.2f;stroke-dashoffset:%.2f;"
        "opacity:1}}"
        % (CAUGHT * 100 - 0.1, RING, CAUGHT * 100, RING, GONE * 100, RING,
           -RING / 2),
        ".burst{animation:burst %.1fs linear infinite}" % LOOP,
        "@keyframes burst{0%%,%.1f%%{opacity:0;transform:scale(0.2)}"
        "%.1f%%{opacity:1;transform:scale(0.9)}"
        "%.1f%%,100%%{opacity:0;transform:scale(1.8)}}"
        % (GONE * 100 - 0.1, GONE * 100 + 0.6, GONE * 100 + 2.6),
        ".facing{animation:facing %.1fs linear infinite}" % LOOP,
        facing(corners, steps),
        ".jaw{animation:chew %.2fs ease-in-out infinite}" % JAWS,
        ".bottom{animation-name:chew-down}",
        "@keyframes chew{0%,100%{transform:rotate(0)}"
        "50%{transform:rotate(-32deg)}}",
        "@keyframes chew-down{0%,100%{transform:rotate(0)}"
        "50%{transform:rotate(32deg)}}",
        # An energizer goes, and for a few seconds the ghosts are the ones
        # being chased: blue, then blinking white as it wears off.
        ".calm{animation:calm %.1fs linear infinite}"
        ".scared{animation:scared %.1fs linear infinite}"
        ".blink{animation:blink %.1fs linear infinite}" % (LOOP, LOOP, LOOP),
        fright(windows),
        # steps(1,end) rather than a fade: an energizer in the arcade is on or
        # it is off, and a pellet that breathes reads as a glow instead.
        ".power{animation:pulse 0.5s steps(1,end) infinite}",
        "@keyframes pulse{0%,49%{opacity:1}50%,100%{opacity:0.15}}",
        "\n".join(".look%d{animation:looking %.1fs linear infinite;"
                  "animation-delay:%.2fs}" % (index + 1, LOOP,
                                              -(LOOP - trail))
                  for index, trail in enumerate(TRAILS)),
        looking(corners, steps),
        "\n".join(number_rules),
        "\n".join(rules),
    ]

    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d" role="img" '
            'aria-label="Contribution graph as a game of Pac-Man">\n'
            '<title>Contribution graph as a game of Pac-Man</title>\n'
            '<style>%s</style>\n'
            '<rect width="%d" height="%d" fill="%s"/>\n%s\n%s\n%s\n%s\n'
            '</svg>\n'
            % (width, height, width, height, "\n".join(style), width, height,
               theme["bg"], "\n".join(shapes),
               "\n".join(ghost(index + 1, colour)
                         for index, colour in enumerate(GHOSTS)),
               sprite(), "\n".join(numbers)))


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
