<div align="center">

<picture>
  <source media="(prefers-color-scheme: light)" srcset="assets/banner-light.svg" />
  <img src="assets/banner-dark.svg" width="100%" alt="N0deZ3r0 — privacy engineering · browser internals · automation" />
</picture>

**English** · [Русский](README.ru.md)

</div>

## About

I work on the parts of the web that identify you without asking — canvas, WebGL,
font metrics, timezone, screen geometry — and on making them report something
else, consistently enough to survive cross-checking. A spoof that contradicts
itself is worse than none: it makes you *more* distinctive, not less.

**Fingerprint resistance.** Coherent profiles rather than scattered `navigator`
overrides. Verified against CreepJS, BrowserLeaks, Pixelscan and AmIUnique.

**Patched Chromium and extensions.** When a flag is not enough, the patch series
is. Manifest V3, WebAssembly cores, isolated and main-world injection.

**Windows privacy tooling.** C# and PowerShell. Telemetry off — and still off
after the next feature update, because something has to keep watching.

**Automation.** Job applications, latency checks, and the browser workflows
worth writing down once.

Every repository below ships CI, a security policy, issue templates and
documentation in both English and Russian.

## Stack

<table>
<tr><td><b>Languages</b></td><td>JavaScript · TypeScript · C# · C++ · Python</td></tr>
<tr><td><b>Runtime and build</b></td><td>WebAssembly · Node.js · .NET Framework 4.8 · PowerShell · Bash</td></tr>
<tr><td><b>Targets</b></td><td>Chromium · Chrome extensions (Manifest V3) · Windows 10 and 11</td></tr>
<tr><td><b>Tooling</b></td><td>Git · GitHub Actions · Visual Studio · VS Code</td></tr>
</table>

## Selected work

<table>
<tr>
<td width="50%" valign="top">

#### [fingerprint-shield](https://github.com/N0deZ3r0/fingerprint-shield)

One coherent invented machine — the same one in the window, in every frame and in
every worker. A claim the layout can contradict produces a machine that cannot
exist, which is rarer than the one you started from. 40 suites, and a Limits
section naming the sixteen things it knowingly does not close.

[![CI](https://github.com/N0deZ3r0/fingerprint-shield/actions/workflows/ci.yml/badge.svg)](https://github.com/N0deZ3r0/fingerprint-shield/actions/workflows/ci.yml)
[![Version](https://img.shields.io/github/manifest-json/v/N0deZ3r0/fingerprint-shield?label=version&labelColor=0d1117&color=1f6feb)](https://github.com/N0deZ3r0/fingerprint-shield/releases/latest)

</td>
<td width="50%" valign="top">

#### [Win11Privacy](https://github.com/N0deZ3r0/Win11Privacy)

Disables Microsoft's data collection, shows what has already been collected
about this machine, and keeps checking on a schedule — because feature updates
quietly restore what you turned off.

[![Build](https://img.shields.io/github/actions/workflow/status/N0deZ3r0/Win11Privacy/build.yml?branch=main&labelColor=0d1117&label=build)](https://github.com/N0deZ3r0/Win11Privacy/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/N0deZ3r0/Win11Privacy?label=release&labelColor=0d1117&color=1f6feb)](https://github.com/N0deZ3r0/Win11Privacy/releases/latest)

</td>
</tr>
<tr>
<td width="50%" valign="top">

#### [hh-ru-job-automation-bot](https://github.com/N0deZ3r0/hh-ru-job-automation-bot)

Applies to hh.ru vacancies behind five layers of defence — 26 WebAssembly
functions, 32 blocked trackers, 11 intercepted APIs — so the site cannot profile
the machine doing it.

[![CI](https://github.com/N0deZ3r0/hh-ru-job-automation-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/N0deZ3r0/hh-ru-job-automation-bot/actions/workflows/ci.yml)
[![Version](https://img.shields.io/github/manifest-json/v/N0deZ3r0/hh-ru-job-automation-bot?label=version&labelColor=0d1117&color=1f6feb)](https://github.com/N0deZ3r0/hh-ru-job-automation-bot/releases/latest)

</td>
<td width="50%" valign="top">

#### [AutoSend-Letters-HH.RU](https://github.com/N0deZ3r0/AutoSend-Letters-HH.RU)

The same idea without an extension: one injected script that checks what you
have already applied to, fills in the cover letter and turns the pages.

[![CI](https://github.com/N0deZ3r0/AutoSend-Letters-HH.RU/actions/workflows/ci.yml/badge.svg)](https://github.com/N0deZ3r0/AutoSend-Letters-HH.RU/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/N0deZ3r0/AutoSend-Letters-HH.RU?labelColor=0d1117&color=6e40c9)](https://github.com/N0deZ3r0/AutoSend-Letters-HH.RU/blob/main/LICENSE)

</td>
</tr>
<tr>
<td colspan="2" valign="top">

#### [Quick-Ping-Chrome-Extension](https://github.com/N0deZ3r0/Quick-Ping-Chrome-Extension)

Response time for any site from the Chrome toolbar. Type an address, get
milliseconds. No account, no configuration, and `ERROR` instead of an invented
number when a host is unreachable.

[![CI](https://github.com/N0deZ3r0/Quick-Ping-Chrome-Extension/actions/workflows/ci.yml/badge.svg)](https://github.com/N0deZ3r0/Quick-Ping-Chrome-Extension/actions/workflows/ci.yml)
[![Version](https://img.shields.io/github/manifest-json/v/N0deZ3r0/Quick-Ping-Chrome-Extension?label=version&labelColor=0d1117&color=1f6feb)](https://github.com/N0deZ3r0/Quick-Ping-Chrome-Extension/releases/latest)

</td>
</tr>
</table>

## Activity

<div align="center">

<picture>
  <source media="(prefers-color-scheme: light)" srcset="https://github-profile-summary-cards.vercel.app/api/cards/profile-details?username=N0deZ3r0&theme=default" />
  <img src="https://github-profile-summary-cards.vercel.app/api/cards/profile-details?username=N0deZ3r0&theme=github_dark" alt="profile summary" />
</picture>

<br/>

<picture>
  <source media="(prefers-color-scheme: light)" srcset="https://github-profile-summary-cards.vercel.app/api/cards/repos-per-language?username=N0deZ3r0&theme=default" />
  <img src="https://github-profile-summary-cards.vercel.app/api/cards/repos-per-language?username=N0deZ3r0&theme=github_dark" alt="repos per language" />
</picture>
<picture>
  <source media="(prefers-color-scheme: light)" srcset="https://github-profile-summary-cards.vercel.app/api/cards/productive-time?username=N0deZ3r0&theme=default&utcOffset=3" />
  <img src="https://github-profile-summary-cards.vercel.app/api/cards/productive-time?username=N0deZ3r0&theme=github_dark&utcOffset=3" alt="productive time" />
</picture>

<br/>

<picture>
  <source media="(prefers-color-scheme: light)" srcset="https://streak-stats.demolab.com?user=N0deZ3r0&hide_border=true&background=FFFFFF&stroke=D0D7DE&ring=0969DA&fire=8250DF&currStreakLabel=0969DA&sideLabels=57606A&dates=6E7681&currStreakNum=1F2328&sideNums=1F2328" />
  <img src="https://streak-stats.demolab.com?user=N0deZ3r0&hide_border=true&background=0D1117&stroke=21262D&ring=58A6FF&fire=8957E5&currStreakLabel=58A6FF&sideLabels=8B949E&dates=6E7681&currStreakNum=C9D1D9&sideNums=C9D1D9" alt="streak" />
</picture>

<br/>

<picture>
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/N0deZ3r0/N0deZ3r0/output/snake-light.svg" />
  <img src="https://raw.githubusercontent.com/N0deZ3r0/N0deZ3r0/output/snake-dark.svg" alt="contribution graph" />
</picture>

</div>

---

<div align="center">

Privacy isn't a setting. It's an engineering budget.

<img src="assets/footer.svg" width="100%" alt="" />

</div>
