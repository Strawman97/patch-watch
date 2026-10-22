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

- **Starts with 670+ projects** across the Super Famicom, Satellaview, Game Boy Advance, DS, 3DS, Wii, Switch, PS1, PS2, PS3, PSP, PS Vita, Saturn, Dreamcast and more, including about 170 undubs from swosho's Internet Archive uploads.
- **Filters** by label, coverage, status, platform, where the patch is hosted, extras and when it was last updated, plus a search across English titles, Japanese titles and group names.
- **Links** straight to the page hosting each patch or mod (GitHub, GameBrew, Romhack Plaza, Romhacking.net, GBAtemp, itch.io and so on), and to the download page and project site when that page names them.
- **List and grid views,** with box art from libretro-thumbnails, the LaunchBox Games Database (which picks the Japanese box for translations and the Western box for undubs), IGDB, VNDB, SteamGridDB, the patch page itself and Wikipedia. Japanese-only games listed under a romanized title are matched through IGDB's alternative names and VNDB's titles, and the English names those return are used to look the game up on SteamGridDB too. Covers made for the patched release's own platform (libretro, IGDB's entry for that platform, VNDB) come before SteamGridDB, which mostly has PC releases, so a console port such as a PS Vita *Evolution* edition shows its own box art. Every source has to match the title word for word apart from filler words and a series name before a colon, so *Trails in the Sky FC Evolution* never takes the cover of *Trails in the Sky SC* or of the PC release. Games with several patches (a translation and an undub, or two competing translations) are grouped into one entry with a tab for each, across platforms like Port Watch: an undub for the PS2 and 3DS releases of *Tales of the Abyss* is one entry. Remakes and other releases that share a name but are different games (*Tales of Phantasia*, *Star Ocean*, the *Dragon Quest* remakes and so on) stay apart per platform; any project can be switched either way in its edits, and the maintainer can share that as `separate`. **Group by game** turns grouping off.
- **Screenshots:** the patch itself, from its README or patch page, and the original game, from IGDB and libretro-thumbnails. Click one to enlarge it; the arrow keys page through them.
- **Follow list:** tap the heart on a project, then use **Check followed** to check only those.
- **Alerts** for new releases and versions, updated patch pages, newly listed projects and links that stop working.
- **New patches are added on their own:** every refresh looks for new English translations and undubs (Romhack Plaza, GameBrew, GitHub, the Internet Archive and the sources credited on CDRomance) and adds the ones that pass the checks below straight to the list. They show up like any other project, and the Activity tab says what was added.
- **Add project:** track anything else by its link. GitHub and GitLab links are checked straight away.
- **NSFW blur, on by default:** cover art and screenshots of games marked NSFW are blurred with an NSFW label. A game is marked when VNDB rates its cover suggestive or explicit, when IGDB lists it under its Erotic theme, when its README or patch page mentions adult content, or when you or the maintainer mark it. Click a blurred cover in a project's details to show it, set any project to "always blur" or "never blur" in its edits, or turn the blur off in **Settings**.
- **Uploads that hold several games** (for example one Internet Archive item with undubs for all four Professor Layton DS games) are listed as one entry per game, grouped under the upload with a tab for each game.
- **Malware-lure warnings** for GitHub repositories that look like malware disguised as patches.

## Getting started

1. Open the site. It syncs with Patch Watch's shared data (see below) straight away, and again every 30 minutes while it's open, so new releases, updated patch pages and newly found patches show up without clicking anything.
2. Follow the projects you're interested in with the heart.
3. **Check for updates** and **Check followed** are still there for checking GitHub projects you added yourself directly. **Settings > When I open Patch Watch** turns syncing off or adds direct checks.

Everything you do (follows, edits, settings) is saved in your own browser. Use **Settings > Export backup** to keep a copy or move it to another browser.

A GitHub token (**Settings > GitHub token**) is optional. It only helps with GitHub projects you added yourself, **Check this project now** and **Search GitHub here**. Create a fine-grained token with **Public repositories (read-only)** access. It's stored only in your browser and sent only to `api.github.com`.

## Shared data refreshed by this repository

Most patch pages can't be read from a web page, so a scheduled GitHub Actions workflow in this repository reads them every three hours and saves the results in `data/`. Every visitor gets them automatically.

| File | What it holds |
| --- | --- |
| `data/status.json` | Every tracked GitHub and GitLab project's latest release, last activity, README screenshots and what its README says about labels, coverage and extras |
| `data/pages.json` | Every other patch page (Internet Archive items are read through archive.org's metadata API): whether it still exists, its version, last-updated date, status, download and project links, screenshots and coverage hints. Up to 150 pages are read per run, oldest first, so every page is re-read every few runs |
| `data/discover.json` | English translations and undubs that Patch Watch doesn't list yet, found on Romhack Plaza's newest translations, GameBrew's translation lists, GitHub (topics such as `undub` and `fan-translation`, keywords such as "english patch" and "localize", and every repository of the watched accounts) and the Internet Archive (everything from the watched uploaders, plus items titled as undubs or English patches). Internet Archive items that hold game files (ROMs or disc images) instead of just a patch are never listed. Also the credited sources of CDRomance's newest English translations and undubs (see below). Kept as working data for the refresh (nothing on the page reads it) |
| `data/found.json` | The patches the refresh found and added to the list by itself. Rebuilt every run: an entry drops out on its own once it's built in, added by hand, hidden or ignored |
| `data/itch.json` | The latest devlog posts of projects hosted on itch.io |
| `data/covers.json` | SteamGridDB covers for games without libretro box art, looked up by the title, the Japanese title and the English names IGDB and VNDB matched (needs the `SGDB_API_KEY` secret) |
| `data/launchbox.json` | Box art matched in the [LaunchBox Games Database](https://gamesdb.launchbox-app.com), by title, Japanese title and the English names IGDB and VNDB found. The database is one large download, kept between runs in the workflow's cache and downloaded again weekly |
| `data/nsfw.json` | Each game's VNDB match, its cover (used when no other cover is found) and how that cover is rated (safe, suggestive or explicit), used for the NSFW blur. Up to 150 games are looked up per run and re-checked every 60 days |
| `data/screens.json` | Each game's IGDB match: its cover, screenshots of the original game and whether IGDB lists it as erotic. Games are matched by title on their platform, then by romanized or Japanese alternative names, then by an exact title on any platform (needs the `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET` secrets) |

What the refresh reads from a README or patch page (machine translation mentioned, coverage, extras) is a hint. Coverage is read sentence by sentence: sentences about other or older patches ("there are partial patches by others") are ignored, and a clear "completely translates the game" outranks a passing "partial". The built-in list and the maintainer's shared fixes always win, and each project's details say where every value came from.

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
- [swosho's uploads on the Internet Archive](https://archive.org/details/@swosho): undub patches
- [Life Bottle Productions](https://github.com/lifebottle): Tales series translations and undubs
- [VNDB](https://vndb.org): cover art ratings for the NSFW blur
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

**Cover links on ROM sites** (romsfun, cdromance, ziperto and similar) show for you, but **Export fixes for everyone** leaves them out, so the shared file never points visitors at those sites.

**Fixing or adding a project for everyone:**

1. In Patch Watch, correct the project as usual (title, Japanese title, cover, platform, labels, coverage, percentage, what's covered, status, extras), or add one with **Add project**.
2. Open **Settings > Export fixes for everyone**. This downloads a complete `overrides.json`: the current shared fixes plus your own.
3. Upload it to the repository, replacing the old file. Visitors see the fixes on their next visit, and the refresh reads newly added pages within minutes.

`overrides.json` has three sections:

- **`projects`**, keyed by the GitHub repository (`owner/repo`) or by `link:` plus the patch page's link. Fields: `title`, `jp`, `cover`, `platform`, `labels` (any of `Human translation`, `Machine translation`, `Undub`), `coverage` (`Complete`, `Story only`, `Partial`, `Menus only`, `Not stated`), `coverageNote`, `pct`, `status` (`Released`, `Partial release`, `In progress`, `Abandoned`, `Unknown`), `extras` (`retrans`, `port`, `subs`, `restore`, `uncensor`, `fixes`, `gameplay`, `gfx`, `dual`), `nsfw` (`true` always blurs the art, `false` never does), `separate` (`true` keeps the project apart from same-named games on other platforms, `false` groups it with them), `hideScreens`, `screens`, `hide` (removes the project) and `note`.
- **`added`**, projects added for everyone, with `link`, `title`, `jp`, `platform`, `labels`, `coverage`, `coverageNote`, `status`, `extras`, `cover` and `description`.
- **`ignoreFound`**, links of found patches that shouldn't be added automatically. Removing an automatically added project in its edits panel (then **Export fixes for everyone**) does the same through `hide`.
- **`watch`**, the accounts the refresh checks in full, beyond its keyword searches. Anything here adds to the built-in lists:

  ```json
  "watch": {
    "archiveCreators": ["swosho"],
    "githubOwners": ["lifebottle", "SymphoniaLauren", "AGTTeam", "Kaisaan", "Arks-Layer", "blashy101", "Supper", "pleonex"]
  }
  ```

  `archiveCreators` are Internet Archive uploaders (the name after `@` in their profile link); `githubOwners` are GitHub users or organisations. Their repositories don't need topics or particular words in their names: any repository whose name or description mentions translating, localizing, an English patch, voices or an undub is picked up. Add an account here whenever you find a group whose projects were missed. This file is edited by hand; **Export fixes for everyone** keeps whatever is already in it.

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

## CDRomance as a discovery signal

CDRomance's translation and undub sections are updated often, and each post names the patch author and a **Source:** link. The refresh reads the newest posts (3 listing pages per section, about 60 posts) and lists **only that credited source**: the Romhacking.net or Romhack Plaza page, GitHub repository, GBAtemp thread and so on. Rules:

- No CDRomance page is ever linked, shown or saved. Posts already read are remembered in `data/discover.json` (`cdromanceSeen`) by a hash of their path only.
- Posts without a credited source, or whose only source is another ROM site, are skipped.
- Posts that aren't English or undubs, PC titles, and Romhacking.net *hacks* (gameplay hacks rather than translations, unless they are undubs) are skipped.
- A credited Internet Archive item gets the usual check, and is never listed if it holds game files.
- If CDRomance blocks the runner (for example with a browser check), the step is skipped for that run and everything else carries on.

Older posts are read on their own: each run also walks further back through the listing pages, as far as it can read that run (up to 120 new posts), and remembers where it stopped, until the whole back catalogue is done. The log's **CDRomance back catalogue** line shows how far it has got. The *CDRomance listing pages* box under **Run workflow** isn't needed any more.



## What gets added automatically

A found patch is added to the list only if:

- it has a console or handheld platform (patches whose platform can't be worked out are left out, which drops most stray GitHub results);
- its link is a patch page or project, not a social post, store page, download host or ROM site;
- it's English (Spanish, Portuguese, French and other translations are left out);
- a GitHub or GitLab repository is a translation or undub for one game: translation tools, AI translation kits, data-only repositories, strategy guides, ports and repositories covering several games are left out, and a repository credited on CDRomance has to share words with the game it was credited for;
- it isn't for another language (Spanish, Portuguese, Farsi, Latin and so on, including repositories ending in `-es`, `-pt` and similar);
- it isn't a gameplay hack;
- the same game isn't already listed on the same platform with the same label (the same patch posted on another site). When two finds are the same game, the one on Romhacking.net, Romhack Plaza, romhack.ing or GitHub is kept.

The refresh log's **added to the list** line counts what was added and why the rest wasn't.

Names: a game found through CDRomance takes the post's **Game Name** (usually the English title) and **Original Title** (the Japanese title, which helps the cover lookups); this also renames a GitHub project when CDRomance credits it. A GitHub repository otherwise takes the game's name from its description ("English translation of Ys III: Wanderers From Ys on PS2"), and only falls back to the repository's name when the description doesn't name the game. Anything still wrong can be fixed in the project's edits panel.
