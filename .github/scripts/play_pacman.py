#!/usr/bin/env python3
"""A game of Pac-Man that visitors play by commenting, on a maze of commits.

The board is not a drawn maze. It is the contribution calendar: a day with
work on it is a wall, an empty day is a corridor with a pellet in it. So the
maze is a year of this account's history, and it thickens on its own as the
year fills in -- nobody has to design a level.

One comment is one move. The direction is read out of the comment, Pac-Man
walks up to three cells that way until something stops him, then each ghost
takes one step of its own -- measured, not guessed: at two steps a competent
player was wiped out every 80 moves, at one every 300, and a move here costs
somebody a comment. The state that survives between comments is a
single JSON file on the `game` branch, next to the two SVGs the README shows.

Nothing here ever runs anything a commenter wrote. The comment arrives in an
environment variable and leaves this file as one of five values -- four
directions or nothing -- which is the whole reason a workflow with write
access can be triggered by a stranger typing into a text box.
"""

import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import render_pacman as art          # noqa: E402  (path set above)

STATE = "state.json"
PAC_STEPS = 3        # cells he covers per comment
GHOST_STEPS = 1      # slower than him, as they are in the arcade
FRIGHT_MOVES = 6     # comments a fright lasts
LIVES = 3
PELLET_WORTH = 10
POWER_WORTH = 50
GHOST_WORTH = (200, 400, 800, 1600)
ENERGIZERS = (0.15, 0.38, 0.61, 0.84)
# How often each ghost wanders instead of closing in, by index:
# Blinky hardly ever, Clyde most of the time.
WANDER = (0.15, 0.35, 0.5, 0.65)

TOP = 36             # room above the grid for the score line
BOTTOM = 20          # and below it for who moved last

# Everything a comment is allowed to mean. Whole words only, so a sentence
# mentioning "downstream" does not read as a move.
WORDS = {
    "up": "up", "u": "up", "w": "up", "вверх": "up", "верх": "up", "↑": "up",
    "down": "down", "d": "down", "s": "down", "вниз": "down", "низ": "down",
    "↓": "down",
    "left": "left", "l": "left", "a": "left", "влево": "left",
    "лево": "left", "←": "left",
    "right": "right", "r": "right", "вправо": "right", "право": "right",
    "→": "right",
}

STEPS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
ARROWS = {"up": "↑", "down": "↓", "left": "←", "right": "→"}


def wanted(comment):
    """The move a comment asks for, or None. The only thing read from it."""
    for word in re.findall(r"[\w←-↓]+", (comment or "").lower()):
        if word in WORDS:
            return WORDS[word]
    return None


def maze():
    """Walls, corridors and the shape of the board, from the calendar."""
    data = art.graphql(art.CALENDAR, {"login": art.OWNER})["user"]
    weeks = data["contributionsCollection"]["contributionCalendar"]["weeks"]
    if not weeks:
        sys.exit("the contribution calendar came back empty")
    level = {}
    for column, week in enumerate(weeks):
        for day in week["contributionDays"]:
            level[(column, day["weekday"])] = art.LEVELS.get(
                day["contributionLevel"], 0)
    return level, len(weeks)


def around(cell, columns):
    """The four neighbours, with the left and right edges joined up.

    A board 53 weeks wide and 7 days tall is nearly all corridor; without the
    wrap the two ends are dead ends and a ghost can trap you against them.
    """
    column, row = cell
    for dx, dy in STEPS.values():
        neighbour = ((column + dx) % columns, row + dy)
        if 0 <= neighbour[1] < art.ROWS:
            yield neighbour


def reachable(level, columns, start):
    """Corridor cells actually walkable from `start`.

    Pellets go only here. A pocket of corridor walled off by a busy week would
    otherwise hold pellets that can never be eaten, and the level could never
    be cleared.
    """
    if level.get(start, 1) != 0:
        start = nearest(level, columns, start)
    seen, stack = {start}, [start]
    while stack:
        for neighbour in around(stack.pop(), columns):
            if level.get(neighbour, 1) == 0 and neighbour not in seen:
                seen.add(neighbour)
                stack.append(neighbour)
    return seen


def nearest(level, columns, target):
    """The closest corridor cell to a point, for placing things."""
    corridors = [cell for cell, value in level.items() if value == 0]
    if not corridors:
        sys.exit("the whole calendar is walls, there is nowhere to play")
    return min(corridors,
               key=lambda cell: (abs(cell[0] - target[0]) % columns
                                 + abs(cell[1] - target[1])))


def fresh(level, columns):
    """A new game: where everything starts and what is still on the board."""
    pac = nearest(level, columns, (columns // 2, 3))
    open_cells = reachable(level, columns, pac)
    powers = []
    for share in ENERGIZERS:
        spot = min((cell for cell in open_cells if cell not in powers),
                   key=lambda cell: (abs(cell[0] - int(columns * share))
                                     + abs(cell[1] - 3)))
        powers.append(spot)
    ghosts = [list(nearest(level, columns, (int(columns * share), row)))
              for share, row in ((0.2, 0), (0.4, 6), (0.6, 0), (0.8, 6))]
    return {"pac": list(pac), "dir": "left", "ghosts": ghosts,
            "eaten": [], "powers": ["%d,%d" % spot for spot in powers],
            "score": 0, "lives": LIVES, "level": 1, "fright": 0, "combo": 0,
            "moves": 0, "high": 0, "last": "", "by": "", "note": ""}


def load(path, level, columns):
    try:
        with open(path, encoding="utf-8") as handle:
            state = json.load(handle)
        if not isinstance(state.get("pac"), list):
            raise ValueError
    except (OSError, ValueError):
        return fresh(level, columns)
    start = fresh(level, columns)
    for key, value in start.items():
        state.setdefault(key, value)
    return state


def chase(index, ghost, pac, level, columns, fright, rng):
    """One ghost step: towards him, or away while it is frightened.

    Not all four the same. Four greedy ghosts on a board this open converge on
    one cell and the game is unplayable -- 60 deaths in 400 random moves when
    they all took the shortest step. So each has its own share of wandering,
    from Blinky who almost never does to Clyde who mostly does, which is the
    same thing that makes the arcade four feel like four characters.

    Ties are broken with a seeded shuffle rather than a fixed order, so the
    ones that do chase still do not walk in lockstep.
    """
    options = [cell for cell in around(tuple(ghost), columns)
               if level.get(cell, 1) == 0]
    if not options:
        return tuple(ghost)
    rng.shuffle(options)
    if rng.random() < WANDER[index % len(WANDER)]:
        return options[0]

    def apart(cell):
        across = abs(cell[0] - pac[0])
        return min(across, columns - across) + abs(cell[1] - pac[1])

    return max(options, key=apart) if fright else min(options, key=apart)


def collide(state, index, level, columns, rng):
    """A ghost and Pac-Man in the same cell. Somebody is eaten."""
    if state["fright"]:
        state["score"] += GHOST_WORTH[min(state["combo"],
                                          len(GHOST_WORTH) - 1)]
        state["combo"] += 1
        state["ghosts"][index] = list(nearest(level, columns,
                                              (columns // 2, 0)))
        state["note"] = "ghost eaten"
        return False
    state["lives"] -= 1
    state["note"] = "caught"
    if state["lives"] <= 0:
        state["high"] = max(state["high"], state["score"])
        state["note"] = "game over"
        keep = state["high"]
        state.update(fresh(level, columns))
        # After the reset, not before: fresh() carries an empty note and would
        # wipe the one thing this run had to report.
        state["high"], state["note"] = keep, "game over"
        return True
    start = fresh(level, columns)
    state["pac"], state["ghosts"] = start["pac"], start["ghosts"]
    state["fright"], state["combo"] = 0, 0
    return True


def play(state, move, player, level, columns):
    """Apply one comment to the game."""
    state["moves"] += 1
    state["dir"] = move
    state["last"] = move
    state["by"] = player
    state["note"] = ""
    rng = random.Random(state["moves"])
    eaten = set(state["eaten"])
    powers = set(state["powers"])
    dx, dy = STEPS[move]

    for _ in range(PAC_STEPS):
        column, row = state["pac"]
        step = ((column + dx) % columns, row + dy)
        if not (0 <= step[1] < art.ROWS) or level.get(step, 1) != 0:
            break
        state["pac"] = list(step)
        key = "%d,%d" % step
        if key not in eaten:
            eaten.add(key)
            if key in powers:
                state["score"] += POWER_WORTH
                state["fright"] = FRIGHT_MOVES
                state["combo"] = 0
            else:
                state["score"] += PELLET_WORTH
        for index, ghost in enumerate(state["ghosts"]):
            if tuple(ghost) == tuple(state["pac"]):
                if collide(state, index, level, columns, rng):
                    state["eaten"] = sorted(eaten)
                    return state
    state["eaten"] = sorted(eaten)

    # He does not move during this half, so a ghost can only reach him by
    # stepping onto his cell; there is no passing-through case to catch.
    # One step each, against his three: the margin is what makes the board
    # survivable for someone who is paying attention.
    for _ in range(GHOST_STEPS):
        for index, ghost in enumerate(state["ghosts"]):
            after = chase(index, ghost, state["pac"], level, columns,
                          state["fright"], rng)
            state["ghosts"][index] = list(after)
            if after == tuple(state["pac"]):
                if collide(state, index, level, columns, rng):
                    return state

    if state["fright"]:
        state["fright"] -= 1
        if not state["fright"]:
            state["combo"] = 0

    walkable = reachable(level, columns, tuple(state["pac"]))
    if walkable and all("%d,%d" % cell in eaten for cell in walkable):
        keep = (state["score"], state["lives"], state["high"],
                state["level"] + 1)
        state.update(fresh(level, columns))
        (state["score"], state["lives"], state["high"],
         state["level"]) = keep
        state["note"] = "level cleared"
    return state


def escape(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def spot(column, row):
    return (art.MARGIN + column * art.PITCH + art.CELL / 2.0,
            TOP + row * art.PITCH + art.CELL / 2.0)


def pac_sprite(x, y, facing):
    turn = {"right": 0, "down": 90, "left": 180, "up": 270}[facing]
    radius = 6.4
    top = "M0,0 L%.1f,0 A%.1f,%.1f 0 0 0 %.1f,0 Z" % (
        radius, radius, radius, -radius)
    bottom = "M0,0 L%.1f,0 A%.1f,%.1f 0 0 1 %.1f,0 Z" % (
        radius, radius, radius, -radius)
    return ('<g transform="translate(%.1f,%.1f) rotate(%d)">'
            '<path class="jaw" d="%s" fill="%s"/>'
            '<path class="jaw down" d="%s" fill="%s"/></g>'
            % (x, y, turn, top, art.PACMAN, bottom, art.PACMAN))


def ghost_sprite(x, y, colour, scared):
    if scared:
        inner = art.afraid(art.SCARED, art.SCARED_TRIM, "scared")
    else:
        inner = ('<path d="%s" fill="%s"/>'
                 '<circle cx="-2.4" cy="-1.2" r="2" fill="#FFFFFF"/>'
                 '<circle cx="2.4" cy="-1.2" r="2" fill="#FFFFFF"/>'
                 '<circle cx="-2.4" cy="-1.2" r="1" fill="%s"/>'
                 '<circle cx="2.4" cy="-1.2" r="1" fill="%s"/>'
                 % (art.GHOST_BODY, colour, art.PUPIL, art.PUPIL))
    return '<g transform="translate(%.1f,%.1f)">%s</g>' % (x, y, inner)


def render(state, level, columns, palette):
    width = art.MARGIN * 2 + columns * art.PITCH - art.GAP
    height = TOP + art.ROWS * art.PITCH - art.GAP + BOTTOM
    eaten = set(state["eaten"])
    powers = set(state["powers"])
    parts = []

    for cell, value in sorted(level.items()):
        x, y = spot(*cell)
        key = "%d,%d" % cell
        if value:
            parts.append('<rect x="%.1f" y="%.1f" width="%d" height="%d" '
                         'rx="2" fill="%s"/>'
                         % (x - art.CELL / 2.0, y - art.CELL / 2.0, art.CELL,
                            art.CELL, palette["levels"][value]))
        elif key in eaten:
            continue
        elif key in powers:
            parts.append('<circle class="power" cx="%.1f" cy="%.1f" r="3.4" '
                         'fill="%s"/>' % (x, y, palette["power"]))
        else:
            parts.append('<circle cx="%.1f" cy="%.1f" r="1.6" fill="%s"/>'
                         % (x, y, palette["pellet"]))

    for index, ghost in enumerate(state["ghosts"]):
        x, y = spot(*ghost)
        parts.append(ghost_sprite(x, y, art.GHOSTS[index], state["fright"]))
    parts.append(pac_sprite(*spot(*state["pac"]), facing=state["dir"]))

    hud = [text(art.MARGIN, 24, "SCORE %d" % state["score"], 13,
                palette["text"], "700", "start"),
           text(width / 2.0, 24, "LEVEL %d" % state["level"], 13,
                palette["muted"], "600"),
           text(width - art.MARGIN, 24,
                "BEST %d" % max(state["high"], state["score"]), 13,
                palette["muted"], "600", "end")]
    for life in range(state["lives"]):
        hud.append('<circle cx="%.1f" cy="19" r="4.5" fill="%s"/>'
                   % (width / 2.0 + 44 + life * 13, art.PACMAN))

    footer = height - 7
    if state["by"]:
        told = "%s %s by @%s" % (ARROWS.get(state["last"], ""),
                                 state["last"], state["by"])
    else:
        told = "comment up / down / left / right on the issue to play"
    if state["note"]:
        told += "  -  " + state["note"]
    hud.append(text(art.MARGIN, footer, told, 11, palette["muted"], "400",
                    "start"))
    hud.append(text(width - art.MARGIN, footer,
                    "%d pellets left" % pellets_left(state, level, columns),
                    11, palette["muted"], "400", "end"))

    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d" role="img" aria-label="%s" '
            'font-family="%s">\n<title>%s</title>\n<style>%s</style>\n'
            '<rect width="%d" height="%d" rx="6" fill="%s"/>\n%s\n%s\n</svg>\n'
            % (width, height, width, height,
               escape("Pac-Man on the contribution graph, score %d"
                      % state["score"]),
               art.SCORE_FONT,
               escape("Pac-Man on the contribution graph"),
               ".jaw{animation:chew .34s ease-in-out infinite;"
               "transform-box:view-box;transform-origin:0 0}"
               ".down{animation-name:chew-down}"
               "@keyframes chew{0%,100%{transform:rotate(0)}"
               "50%{transform:rotate(-32deg)}}"
               "@keyframes chew-down{0%,100%{transform:rotate(0)}"
               "50%{transform:rotate(32deg)}}"
               ".power{animation:pulse .5s steps(1,end) infinite}"
               "@keyframes pulse{0%,49%{opacity:1}50%,100%{opacity:.15}}",
               width, height, palette["bg"], "\n".join(parts),
               "\n".join(hud)))


def pellets_left(state, level, columns):
    walkable = reachable(level, columns, tuple(state["pac"]))
    eaten = set(state["eaten"])
    return sum(1 for cell in walkable if "%d,%d" % cell not in eaten)


def text(x, y, body, size, colour, weight="400", anchor="middle"):
    return ('<text x="%.1f" y="%d" text-anchor="%s" font-size="%d" '
            'font-weight="%s" fill="%s">%s</text>'
            % (x, y, anchor, size, weight, colour, escape(body)))


PALETTES = {
    "light": dict(art.THEMES["light"], text="#1F2328", muted="#57606A"),
    "dark": dict(art.THEMES["dark"], text="#C9D1D9", muted="#8B949E"),
}


def main():
    out = os.environ.get("OUTPUT_DIR") or "game"
    move = wanted(os.environ.get("MOVE"))
    player = re.sub(r"[^A-Za-z0-9_.-]", "", os.environ.get("PLAYER", ""))[:39]

    level, columns = maze()
    state = load(os.path.join(out, STATE), level, columns)

    # Anything standing in a wall after the calendar changed under it -- a day
    # that was empty yesterday and has a commit on it today -- is stood back up
    # on the nearest corridor rather than being left inside the scenery.
    if level.get(tuple(state["pac"]), 1) != 0:
        state["pac"] = list(nearest(level, columns, tuple(state["pac"])))
    for index, ghost in enumerate(state["ghosts"]):
        if level.get(tuple(ghost), 1) != 0:
            state["ghosts"][index] = list(nearest(level, columns,
                                                  tuple(ghost)))

    if move:
        state = play(state, move, player, level, columns)
    elif os.environ.get("REQUIRE_MOVE"):
        print("no direction in that comment, nothing to do")
        return

    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, STATE), "w", encoding="utf-8",
              newline="\n") as handle:
        json.dump(state, handle, indent=1, sort_keys=True)
        handle.write("\n")
    for name, palette in PALETTES.items():
        with open(os.path.join(out, "board-%s.svg" % name), "w",
                  encoding="utf-8", newline="\n") as handle:
            handle.write(render(state, level, columns, palette))
    print("move %s by %s | score %d, lives %d, level %d, %d pellets left%s"
          % (move or "-", player or "-", state["score"], state["lives"],
             state["level"], pellets_left(state, level, columns),
             ", " + state["note"] if state["note"] else ""))


if __name__ == "__main__":
    main()
