# Patch Watch

A single-page tracker for English fan translations and undubs of Japanese console games. A sister site to [Port Watch](https://strawman97.github.io/port-watch/): the same look, the same way of following projects and getting told when they change.

**Live site:** https://strawman97.github.io/patch-watch/

> Patch Watch links to patch pages and code projects only. It does not host, link to or include game files, ROMs or disc images. Every patch it lists needs your own legally obtained copy of the game.

## What it covers

- **English translations** of Japanese games, labelled **Human translation** or **Machine translation** (machine translation or AI, edited or not).
- **Undubs:** patches and mods that restore the Japanese voices to a game whose English release only had an English dub. **Undub** is its own label; a patch can carry more than one label.
- **What each patch covers:**
  - **Complete (100%)**: everything is translated (for an undub, every voice is restored).
  - **Story only**: the main story is translated, but some side content is still in Japanese.
  - **Partial**: only part of the game is translated so far (with a percentage when the project gives one).
  - **Menus only**: menus and interface are translated; the story is still in Japanese.
  - **Not stated**: the project doesn't say.

  Each project can also carry a free-text note about what is and isn't covered.
- **Status:** Released, Partial release, In progress, Abandoned or Unknown.
- **Extras** the same patch includes: retranslation of an official script, port of an existing translation, subtitles added, restored content, uncensored, bug fixes, gameplay changes, graphics changes and dual audio.

**Out of scope:** ROM hacks that only change gameplay, balance or visuals; translations into languages other than English; and texture packs. A patch that changes gameplay or graphics *and* translates or undubs the game is covered, with the extra changes noted.

## What it does

- **Starts with 490+ projects** across the Super Famicom, Satellaview, Game Boy Advance, DS, 3DS, Wii, Switch, PS1, PS2, PS3, PSP, PS Vita, Saturn, Dreamcast and more.
- **Filters** by label, coverage, status, platform, where the patch is hosted, extras and when it was last updated, plus a search across English titles, Japanese titles and group names.
- **Links** straight to the page hosting each patch or mod (GitHub, GameBrew, Romhack Plaza, Romhacking.net, GBAtemp, itch.io and so on), and to the download page and project site when that page names them.
- **List and grid views,** with box art from libretro-thumbnails, SteamGridDB and Wikipedia. Games with several patches (a translation and an undub, or two competing translations) are grouped into one entry with a tab for each. **Group by game** turns this off.
- **Screenshots:** the patch itself, from its README or patch page, and the original game, from IGDB and libretro-thumbnails. Click one to enlarge it.
- **Follow list:** tap the heart on a project, then use **Check followed** to check only those.
- **Alerts** for new releases and versions, updated patch pages, newly listed projects and links that stop working.
- **Find a game:** search Patch Watch's list, see newly found patches that aren't listed yet, search GitHub from the page, or jump to Romhack Plaza, Romhacking.net, GameBrew, GitHub, r/fantranslation or the web with the game's name filled in.
- **Add project:** track anything else by its link. GitHub and GitLab links are checked straight away.
- **Malware-lure warnings** for GitHub repositories that look like malware disguised as patches.

## Getting started

1. Open the site. It starts with a built-in list and doesn't check anything until you ask.
2. Follow the projects you're interested in with the heart.
3. Click **Check for updates**, or **Check followed** to refresh just those. Both use Patch Watch's shared data (see below), so no account or token is needed.

Everything you do (follows, edits, settings) is saved in your own browser. Use **Settings > Export backup** to keep a copy or move it to another browser.

A GitHub token (**Settings > GitHub token**) is optional. It only helps with GitHub projects you added yourself, **Check this project now** and **Search GitHub here**. Create a fine-grained token with **Public repositories (read-only)** access. It's stored only in your browser and sent only to `api.github.com`.

## Shared data refreshed by this repository

Most patch pages can't be read from a web page, so a scheduled GitHub Actions workflow in this repository reads them every three hours and saves the results in `data/`. Every visitor gets them automatically.

| File | What it holds |
| --- | --- |
| `data/status.json` | Every tracked GitHub and GitLab project's latest release, last activity, README screenshots and what its README says about labels, coverage and extras |
| `data/pages.json` | Every other patch page: whether it still exists, its version, last-updated date, status, download and project links, screenshots and coverage hints. Up to 150 pages are read per run, oldest first, so every page is re-read every few runs |
| `data/discover.json` | English translations and undubs found on Romhack Plaza's newest translations, GameBrew's translation lists and GitHub (topics such as `undub` and `fan-translation`, and keywords such as "english patch") that Patch Watch doesn't list yet. They show in **Find a game** |
| `data/itch.json` | The latest devlog posts of projects hosted on itch.io |
| `data/covers.json` | SteamGridDB covers for games without libretro box art (needs the `SGDB_API_KEY` secret) |
| `data/screens.json` | IGDB screenshots of the original games (needs the `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET` secrets) |

What the refresh reads from a README or patch page (machine translation mentioned, coverage, extras) is a hint. The built-in list and the maintainer's shared fixes always win, and each project's details say where every value came from.

## Privacy

Patch Watch has no server, accounts or analytics. Your data never leaves your browser except for these requests, which only fetch public information:

| Destination | Why |
| --- | --- |
| `raw.githubusercontent.com` | This repository's shared data and fixes, README screenshots, and libretro box art |
| `api.github.com`, `gitlab.com` | Projects you added yourself, **Check this project now**, **Search GitHub here**, and cover lookups |
| `cdn2.steamgriddb.com`, `images.igdb.com` | Covers and screenshots |
| Image hosts of patch pages (GameBrew, Romhack Plaza, GitHub and others) | Screenshots of patches, only when you open a project |
| `en.wikipedia.org`, `upload.wikimedia.org` | Fallback cover art |
| `fonts.googleapis.com`, `fonts.gstatic.com` | Fonts |
| `api.rss2json.com`, `api.allorigins.win` | itch.io devlogs, only if you turn on the relay and the shared copy is missing |

## Data sources and credits

- [Romhack Archive](https://github.com/videogame-archive/romhack-archive): the Super Famicom and Satellaview translations and their Romhacking.net links
- [GameBrew](https://www.gamebrew.org): the PSP, PS Vita, DS, 3DS, Wii, Switch and GBA translation and undub lists
- [GBAtemp's list of English fan translations and translation ports](https://gbatemp.net/threads/list-of-english-fantranslations-and-translation-ports.612951/): the Switch projects
- [Romhack Plaza](https://romhackplaza.org) and [Romhacking.net](https://www.romhacking.net): patch pages
- [libretro-thumbnails](https://github.com/libretro-thumbnails): box art and original-game screenshots
- [SteamGridDB](https://www.steamgriddb.com) and [IGDB](https://www.igdb.com): covers and screenshots
- Every translator, hacker and undubber whose work is tracked here

All game titles, trademarks and box art belong to their respective owners. Patch Watch is an unofficial fan project and isn't affiliated with any game publisher, platform holder or listed project.

## Known limitations

- **Coverage and labels are only as good as their source.** Many entries start as **Not stated** until the refresh reads the page, and what it reads is a hint. Correct anything with your own edits, then share the fix (see below).
- **Some sites block automated reads.** When a page can't be read, its previous data is kept and its details say so. Open the link to check by hand.
- **Romhacking.net no longer takes submissions,** so newer patches are found through Romhack Plaza, GameBrew, GitHub and **Add project**.

## Maintaining the site

| Path | What it is |
| --- | --- |
| `index.html` | The whole site, served by GitHub Pages from the `main` branch |
| `scripts/refresh_data.py` | Refreshes everything in `data/` (standard library only). Run single steps with `python3 scripts/refresh_data.py pages discover` |
| `scripts/patch_analysis.py` | The label, coverage, extras, screenshot and malware-lure rules, ported from the page, and the readers for patch pages and lists |
| `scripts/sgdb_covers.py` | Optional helper for adding SteamGridDB covers to your own browser copy |
| `.github/workflows/refresh-data.yml` | Runs the refresh every three hours and after `overrides.json`, `index.html` or the scripts change, and commits `data/` |
| `data/` | Written by the workflow; don't edit by hand |
| `overrides.json` | Shared fixes and added projects (see below) |

**Updating the page:** save the new version as `index.html`, then choose **Add file > Upload files** in this repository and click **Commit changes**. GitHub Pages republishes within a minute or two.

**Secrets** (**Settings > Secrets and variables > Actions**): `SGDB_API_KEY` for covers, `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET` for screenshots (the same Twitch app Port Watch uses works here too). All are optional; the workflow skips what it has no key for. The status checks use the workflow's own `GITHUB_TOKEN`; add a read-only fine-grained token as `PW_GH_TOKEN` only if GitHub ever limits it.

**Fixing or adding a project for everyone:**

1. In Patch Watch, correct the project as usual (title, Japanese title, cover, platform, labels, coverage, percentage, what's covered, status, extras), or add one with **Add project** or **Add…** in Find a game.
2. Open **Settings > Export fixes for everyone**. This downloads a complete `overrides.json`: the current shared fixes plus your own.
3. Upload it to the repository, replacing the old file. Visitors see the fixes on their next visit, and the refresh reads newly added pages within minutes.

`overrides.json` has three sections:

- **`projects`**, keyed by the GitHub repository (`owner/repo`) or by `link:` plus the patch page's link. Fields: `title`, `jp`, `cover`, `platform`, `labels` (any of `Human translation`, `Machine translation`, `Undub`), `coverage` (`Complete`, `Story only`, `Partial`, `Menus only`, `Not stated`), `coverageNote`, `pct`, `status` (`Released`, `Partial release`, `In progress`, `Abandoned`, `Unknown`), `extras` (`retrans`, `port`, `subs`, `restore`, `uncensor`, `fixes`, `gameplay`, `gfx`, `dual`), `hideScreens`, `screens`, `hide` (removes the project) and `note`.
- **`added`**, projects added for everyone, with `link`, `title`, `jp`, `platform`, `labels`, `coverage`, `coverageNote`, `status`, `extras`, `cover` and `description`.
- **`ignoreFound`**, links of newly found patches that aren't relevant, so they stop showing in Find a game.

```json
"added": {
  "link:https://romhackplaza.org/translations/chaindive-english-translation-playstation-2": {
    "link": "https://romhackplaza.org/translations/chaindive-english-translation-playstation-2",
    "title": "ChainDive",
    "platform": "PS2",
    "labels": ["Human translation"],
    "coverage": "Complete",
    "status": "Released"
  }
}
```

**When refreshes run:** every three hours, and a few minutes after `overrides.json`, `index.html` or the scripts change. To run one by hand, open **Actions > Refresh data > Run workflow**. GitHub pauses scheduled workflows in public repositories after 60 days without activity; re-enable it from the **Actions** tab.

If this repository is renamed or moved, update `DATA_REPO` near the top of the script in `index.html`.

Never commit API keys or tokens to this repository.

## Suggesting a project or a fix

Open an issue with the patch's link, the game and its platform, or describe what's wrong with an existing entry.

## Licence

Patch Watch's own code (`index.html` and the scripts in `scripts/`) is released under the [MIT Licence](LICENSE). The licence doesn't cover the third-party data and images the site displays; those belong to their respective owners and sources.
