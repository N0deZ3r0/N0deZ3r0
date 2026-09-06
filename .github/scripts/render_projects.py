#!/usr/bin/env python3
"""Redraw the project table in both READMEs from the public repositories.

The list itself comes from the API, so a new public repository shows up on its
own. What a card says comes from .github/profile/projects.json when that file
has an entry, and from the repository description when it does not, so anything
written up by hand keeps its write-up.

Only the block between the projects:start and projects:end markers is touched.
"""

import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.environ.get("GITHUB_WORKSPACE") or os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CONFIG = os.path.join(ROOT, ".github", "profile", "projects.json")
OWNER = os.environ.get("GITHUB_OWNER") or "N0deZ3r0"
API = "https://api.github.com"
WRAP = 80

READMES = {
    "en": os.path.join(ROOT, "README.md"),
    "ru": os.path.join(ROOT, "README.ru.md"),
}

# Badge wording per language. The label rides in the query string, so it has to
# be percent-encoded; the alt text does not. A None label leaves the shields
# default in place.
LABELS = {
    "en": {"ci": "CI", "build": "Build", "version": "Version",
           "release": "Release", "license": "License",
           "q_build": "build", "q_version": "version",
           "q_release": "release", "q_license": None},
    "ru": {"ci": "CI", "build": "Сборка", "version": "Версия",
           "release": "Релиз", "license": "Лицензия",
           "q_build": "сборка", "q_version": "версия",
           "q_release": "релиз", "q_license": "лицензия"},
}


def api(path, default=None):
    """GET a JSON endpoint. Returns the default on 404, so callers can probe."""
    request = urllib.request.Request(API + path)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", "profile-readme-renderer")
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return default
        raise


def repositories(exclude):
    """Every public, owned, unarchived repository, newest push first."""
    collected, page = [], 1
    while True:
        batch = api("/users/%s/repos?per_page=100&type=owner&sort=pushed&page=%d"
                    % (OWNER, page)) or []
        collected += batch
        if len(batch) < 100:
            break
        page += 1
    return [r for r in collected
            if not r["fork"] and not r["archived"] and not r["private"]
            and r["name"] not in exclude]


def badges(repo, language):
    """Two badges per card, picked from what the repository actually has.

    A repository with a ci.yml gets the workflow badge GitHub serves itself;
    anything else with a workflow gets a shields.io status badge for it. The
    second badge is the most specific version marker available: a manifest,
    failing that a release, failing that the licence.
    """
    words = LABELS[language]
    branch = repo["default_branch"]
    slug = "%s/%s" % (OWNER, repo["name"])
    out = []

    def quote(value):
        return urllib.parse.quote(value, safe="")

    workflows = api("/repos/%s/contents/.github/workflows" % slug, []) or []
    files = sorted(f["name"] for f in workflows
                   if f["name"].endswith((".yml", ".yaml")))
    chosen = "ci.yml" if "ci.yml" in files else (files[0] if files else None)
    if chosen == "ci.yml":
        out.append("[![%s](https://github.com/%s/actions/workflows/ci.yml/badge.svg)]"
                   "(https://github.com/%s/actions/workflows/ci.yml)"
                   % (words["ci"], slug, slug))
    elif chosen:
        out.append("[![%s](https://img.shields.io/github/actions/workflow/status/%s/%s"
                   "?branch=%s&labelColor=0d1117&label=%s)]"
                   "(https://github.com/%s/actions/workflows/%s)"
                   % (words["build"], slug, chosen, branch,
                      quote(words["q_build"]), slug, chosen))

    if api("/repos/%s/contents/manifest.json" % slug) is not None:
        out.append("[![%s](https://img.shields.io/github/manifest-json/v/%s"
                   "?label=%s&labelColor=0d1117&color=1f6feb)]"
                   "(https://github.com/%s/releases/latest)"
                   % (words["version"], slug, quote(words["q_version"]), slug))
    elif api("/repos/%s/releases/latest" % slug) is not None:
        out.append("[![%s](https://img.shields.io/github/v/release/%s"
                   "?label=%s&labelColor=0d1117&color=1f6feb)]"
                   "(https://github.com/%s/releases/latest)"
                   % (words["release"], slug, quote(words["q_release"]), slug))
    elif repo.get("license"):
        query = "?labelColor=0d1117&color=6e40c9"
        if words["q_license"]:
            query = "?label=%s&labelColor=0d1117&color=6e40c9" % quote(words["q_license"])
        out.append("[![%s](https://img.shields.io/github/license/%s%s)]"
                   "(https://github.com/%s/blob/%s/LICENSE)"
                   % (words["license"], slug, query, slug, branch))

    return out


def card(repo, language, written):
    slug = "%s/%s" % (OWNER, repo["name"])
    lines = ["#### [%s](https://github.com/%s)" % (repo["name"], slug)]

    blurb = (written.get(repo["name"]) or {}).get(language)
    if blurb is None and repo.get("description"):
        # Wrapped to the width the hand-written copy uses, so the README stays
        # readable as source and not only as a rendered page.
        blurb = "\n".join(textwrap.wrap(repo["description"].strip(), WRAP))
    if blurb:
        lines += ["", blurb]

    drawn = badges(repo, language)
    if drawn:
        lines += [""] + drawn
    return "\n".join(lines)


def table(repos, language, written):
    """Two cards to a row; a last card left on its own spans both columns."""
    rows = []
    for index in range(0, len(repos), 2):
        pair = repos[index:index + 2]
        cells = []
        for repo in pair:
            width = ' colspan="2"' if len(pair) == 1 else ' width="50%"'
            cells.append('<td%s valign="top">\n\n%s\n\n</td>'
                         % (width, card(repo, language, written)))
        rows.append("<tr>\n%s\n</tr>" % "\n".join(cells))
    return "<table>\n%s\n</table>" % "\n".join(rows)


def main():
    with open(CONFIG, encoding="utf-8") as handle:
        config = json.load(handle)
    written = config.get("projects", {})
    exclude = set(config.get("exclude", []))

    found = repositories(exclude)
    by_name = {r["name"]: r for r in found}
    # Hand-written entries first, in the order the file lists them; whatever is
    # left follows, most recently pushed first.
    ordered = [by_name[name] for name in written if name in by_name]
    ordered += [r for r in found if r["name"] not in written]
    if not ordered:
        sys.exit("no repositories to list, refusing to empty the section")

    for language, path in READMES.items():
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        block = "<!-- projects:start -->\n%s\n<!-- projects:end -->" % table(
            ordered, language, written)
        replaced, count = re.subn(
            r"<!-- projects:start -->.*?<!-- projects:end -->",
            lambda match: block, text, flags=re.S)
        if count != 1:
            sys.exit("%s: expected one projects block, found %d" % (path, count))
        if replaced == text:
            print("unchanged %s" % os.path.basename(path))
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(replaced)
        print("updated %s" % os.path.basename(path))

    print("listed: %s" % ", ".join(r["name"] for r in ordered))


if __name__ == "__main__":
    main()
