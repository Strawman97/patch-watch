#!/usr/bin/env python3
"""Refresh Patch Watch's shared data files. Runs in GitHub Actions (see .github/workflows/refresh-data.yml).

- data/status.json    every tracked GitHub/GitLab project's latest release, activity, README hints (label, coverage, extras)
                      and README screenshots (uses the workflow's GITHUB_TOKEN)
- data/pages.json     every other tracked patch page (GameBrew, Romhack Plaza, Romhacking.net, GBAtemp, websites): whether it
                      still exists, its version, last-updated date, download and project links, screenshots and coverage hints
- data/discover.json  English translations and undubs found on Romhack Plaza, GameBrew and GitHub that aren't tracked yet
- data/itch.json      the latest devlog posts of projects hosted on itch.io
- data/covers.json    SteamGridDB covers for games without libretro box art (needs the SGDB_API_KEY secret)
- data/screens.json   IGDB screenshots of the original games (needs the IGDB_CLIENT_ID and IGDB_CLIENT_SECRET secrets)

Only the Python standard library is used. Files are rewritten only when their contents change.
"""
import datetime, difflib, json, os, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_analysis as A

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
INDEX = os.path.join(ROOT, "index.html")
SGDB_BASE = os.environ.get("SGDB_BASE", "https://www.steamgriddb.com/api/v2")
ITCH_BASE = os.environ.get("PW_ITCH_BASE", "https://{user}.itch.io")
MAX_LOOKUPS = int(os.environ.get("PW_MAX_LOOKUPS", "250"))              # SteamGridDB lookups per run
MAX_PAGES = int(os.environ.get("PW_MAX_PAGES", "150"))                  # patch pages read per run (oldest first)
PAGE_DELAY = float(os.environ.get("PW_PAGE_DELAY", "1.5"))              # seconds between requests to the same site
RETRY_MISSES_DAYS = 14
UA = "Mozilla/5.0 (compatible; patch-watch-refresh/1.0; +https://github.com/strawman97/patch-watch)"
NOW = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

# ---------------------------------------------------------------- helpers
def log(*a): print(*a, flush=True)

class HttpStatus(Exception):
    def __init__(self, code): super().__init__(f"HTTP {code}"); self.code = code

def http_get(url, headers=None, tries=3, missing_ok=True):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en", **(headers or {})})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise
            if e.code in (404, 410):
                if missing_ok:
                    return None
                raise HttpStatus(e.code)
            if e.code == 429 and attempt < tries - 1:
                time.sleep(min(60, int(e.headers.get("Retry-After", "10") or 10)))
                continue
            if attempt == tries - 1:
                raise HttpStatus(e.code)
        except urllib.error.URLError:
            if attempt == tries - 1:
                raise
        time.sleep(2 * (attempt + 1))
    return None

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default

def write_json_if_changed(path, obj, compare_without=("generated",)):
    old = load_json(path, None)
    strip = lambda o: {k: v for k, v in (o or {}).items() if k not in compare_without} if isinstance(o, dict) else o
    if old is not None and strip(old) == strip(obj):
        log(f"  {os.path.relpath(path, ROOT)}: unchanged")
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    log(f"  {os.path.relpath(path, ROOT)}: updated")
    return True

def norm(t):
    t = "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c)).lower().replace("&", " and ")
    t = re.sub(r"[’'`]", "", t)
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return re.sub(r"^the ", "", t)

ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
def numbers(t): return sorted(ROMAN.get(w, w) for w in t.split() if w.isdigit() or w in ROMAN)

def strip_parens(t):
    prev = None
    while prev != t:
        prev, t = t, re.sub(r"\s*\((?!\d{4}\))[^()]*\)\s*$", "", t).strip()
    return t

def norm_link(u):
    return re.sub(r"/+$", "", re.sub(r"#.*$", "", (u or "").strip()))

def link_key(url):
    m = re.match(r"^https?://(?:www\.)?github\.com/([^/#?]+/[^/#?]+)", url or "", re.I)
    if m:
        return re.sub(r"\.git$", "", m.group(1).lower())
    m = re.match(r"^https?://(?:www\.)?gitlab\.com/([^#?]+?)(?:/-/.*)?/?$", url or "", re.I)
    if m:
        return "gitlab.com/" + m.group(1).lower()
    m = re.match(r"^https?://([a-z0-9-]+)\.itch\.io/([a-z0-9_-]+)", url or "", re.I)
    if m:
        return f"itch.io/{m.group(1).lower()}/{m.group(2).lower()}"
    return None

# ---------------------------------------------------------------- what Patch Watch tracks
def seed_projects():
    html = open(INDEX, encoding="utf-8").read()
    m = re.search(r"const SEED = (\[.*?\]);\nconst BUILT", html, re.S)
    if not m:
        sys.exit("Couldn't find Patch Watch's built-in list in index.html.")
    return json.loads(m.group(1).replace("<\\/", "</"))

def load_overrides():
    return load_json(os.path.join(ROOT, "overrides.json"), {}) or {}

def fix_for(p, fixes):
    return fixes.get(p.get("k") or "") or fixes.get(p["id"]) or fixes.get("link:" + norm_link(p.get("l"))) or {}

def load_added(over):
    """Projects the maintainer added for everyone (the "added" section of overrides.json)."""
    out = []
    for key, e in (over.get("added") or {}).items():
        if not isinstance(e, dict):
            continue
        link = e.get("link") or ""
        k = None if key.startswith("link:") else key.lower()
        out.append({"id": "shared:" + (k or norm_link(link)), "k": k, "l": link or ("https://github.com/" + k if k else ""), "g": e.get("title") or (k or link),
                    "jp": e.get("jp") or "", "p": e.get("platform") or "Unknown", "cover": e.get("cover") or ""})
    return out

def all_projects(seed, over):
    fixes = over.get("projects") or {}
    links = {norm_link(p.get("l")) for p in seed} | {p.get("k") for p in seed if p.get("k")}
    added = [p for p in load_added(over) if not (p["k"] in links or norm_link(p["l"]) in links)]
    out = []
    for p in seed + added:
        f = fix_for(p, fixes)
        if f.get("hide"):
            continue
        out.append({**p, "g": f.get("title") or p.get("g", ""), "jp": f.get("jp") or p.get("jp", ""), "p": f.get("platform") or p.get("p", ""),
                    "pinnedCover": f.get("cover") or p.get("cover") or ""})
    return out

# ---------------------------------------------------------------- SteamGridDB covers
def sgdb_lookup(title, key):
    res = http_get(SGDB_BASE + "/search/autocomplete/" + urllib.parse.quote(title, safe=""), {"Authorization": "Bearer " + key})
    hits = (json.loads(res).get("data") if res else None) or []
    q, best = norm(title), None
    for h in hits:
        n = norm(h.get("name", ""))
        score = 1.0 if n == q else difflib.SequenceMatcher(None, q, n).ratio()
        if numbers(q) != numbers(n):
            score -= 0.3
        if best is None or score > best[0]:
            best = (score, h)
    if not best or best[0] < 0.85:
        return None
    score, hit = best
    time.sleep(0.25)
    res = http_get(f"{SGDB_BASE}/grids/game/{hit['id']}?dimensions=600x900,342x482,660x930&types=static&nsfw=false&humor=false&epilepsy=false",
                   {"Authorization": "Bearer " + key})
    imgs = (json.loads(res).get("data") if res else None) or []
    if not imgs:
        return None
    return {"url": imgs[0].get("url"), "thumb": imgs[0].get("thumb"), "name": hit.get("name"), "match": round(score, 3)}

def refresh_covers(projects):
    key = os.environ.get("SGDB_API_KEY", "").strip()
    path = os.path.join(DATA, "covers.json")
    data = load_json(path, {"format": "patch-watch-covers", "version": 1, "covers": {}, "misses": {}})
    covers, misses = data.setdefault("covers", {}), data.setdefault("misses", {})
    if not key:
        log("  SGDB_API_KEY isn't set; skipping covers")
        return False
    todo, seen = [], set()
    for p in projects:
        ck = p.get("k") or p["id"]
        if p.get("pinnedCover"):
            covers.pop(ck, None)          # the maintainer pinned a cover: nothing to look up
            continue
        if p.get("cv") or ck in seen:
            continue                      # already has libretro box art
        seen.add(ck)
        title = strip_parens(p.get("g", ""))
        if ck in covers:
            if covers[ck].get("title") in (title, strip_parens(p.get("jp") or "")):
                continue
            covers.pop(ck, None); misses.pop(ck, None)      # the title was corrected: look it up again
        miss = misses.get(ck)
        if miss and (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(miss.replace("Z", "+00:00"))).days < RETRY_MISSES_DAYS:
            continue
        if title:
            todo.append((ck, title, strip_parens(p.get("jp") or "")))
    log(f"  {len(todo)} games need a cover lookup (max {MAX_LOOKUPS} this run)")
    for ck, title, jp in todo[:MAX_LOOKUPS]:
        hit, used = None, title
        try:
            for t in [title, jp]:
                if not t:
                    continue
                hit, used = sgdb_lookup(t, key), t
                time.sleep(0.25)
                if hit:
                    break
        except urllib.error.HTTPError as e:
            if e.code == 401:
                log("  SteamGridDB rejected the API key (401); stopping cover lookups")
                break
            continue
        except Exception as e:
            log(f"  {title}: {e}")
            continue
        if hit and hit.get("url"):
            covers[ck] = {**hit, "title": used, "added": NOW}
            misses.pop(ck, None)
            log(f"  + {used} -> {hit['name']} ({hit['match']})")
        else:
            misses[ck] = NOW
    data["generated"] = NOW
    return write_json_if_changed(path, data)

# ---------------------------------------------------------------- itch.io devlogs
def refresh_itch(projects):
    path = os.path.join(DATA, "itch.json")
    data = load_json(path, {"format": "patch-watch-itch", "version": 1, "feeds": {}})
    feeds = data.setdefault("feeds", {})
    for p in projects:
        k = p.get("k") or ""
        if not k.startswith("itch.io/"):
            continue
        _, user, game = k.split("/", 2)
        url = ITCH_BASE.format(user=user) + f"/{game}/devlog.rss"
        try:
            raw = http_get(url)
            if not raw:
                raise ValueError("no feed")
            items = []
            for it in ET.fromstring(raw).iter("item"):
                pub = (it.findtext("pubDate") or "").strip()
                try:
                    pub = datetime.datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=datetime.timezone.utc).isoformat().replace("+00:00", "Z")
                except ValueError:
                    pass
                items.append({"t": (it.findtext("title") or "").strip(), "d": pub, "u": (it.findtext("link") or "").strip()})
            items = items[:10]
            if items != (feeds.get(k) or {}).get("items"):
                feeds[k] = {"items": items, "fetched": NOW}
        except Exception as e:
            log(f"  {k}: couldn't read the devlog ({e}); keeping the previous copy")
    data["generated"] = NOW
    return write_json_if_changed(path, data)

# ---------------------------------------------------------------- GitHub / GitLab status
GQL_URL = os.environ.get("PW_GQL_URL", "https://api.github.com/graphql")
GITLAB_API = os.environ.get("PW_GITLAB_API", "https://gitlab.com/api/v4")
README_NAMES = ["README.md", "readme.md", "Readme.md", "README.MD", "README", "README.markdown", "README.rst", "README.txt"]
RELEASE_FIELDS = "tagName publishedAt createdAt isPrerelease url releaseAssets(first: 40) { nodes { name } }"

def gql(query, token):
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(GQL_URL, data=body, headers={"Authorization": "bearer " + token, "Content-Type": "application/json", "User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (502, 503, 504) and attempt < 2:
                time.sleep(5 * (attempt + 1)); continue
            raise
        except urllib.error.URLError:
            if attempt < 2:
                time.sleep(5 * (attempt + 1)); continue
            raise

def not_found_aliases(resp):
    return {e["path"][0] for e in (resp.get("errors") or []) if e.get("type") == "NOT_FOUND" and e.get("path")}

def repo_ref(k):
    owner, name = k.split("/", 1)
    return "repository(owner: %s, name: %s)" % (json.dumps(owner), json.dumps(name))

def meta_batch(keys, token):
    parts = ["r%d: %s { nameWithOwner pushedAt stargazerCount isArchived description diskUsage createdAt primaryLanguage { name } "
             "releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) { nodes { %s } } }" % (i, repo_ref(k), RELEASE_FIELDS) for i, k in enumerate(keys)]
    resp = gql("query {\n" + "\n".join(parts) + "\n}", token)
    data, missing = resp.get("data") or {}, not_found_aliases(resp)
    out = {}
    for i, k in enumerate(keys):
        a = "r%d" % i
        if a in missing:
            out[k] = {"notFound": True}; continue
        r = data.get(a)
        if not r:
            continue
        rel = ((r.get("releases") or {}).get("nodes") or [None])[0]
        e = {"repo": {"pushed": r.get("pushedAt"), "stars": r.get("stargazerCount"), "archived": bool(r.get("isArchived")), "full": r.get("nameWithOwner"),
                      "desc": r.get("description") or "", "size": r.get("diskUsage"), "lang": (r.get("primaryLanguage") or {}).get("name"), "created": r.get("createdAt")}}
        if rel:
            e["release"] = {"tag": rel.get("tagName"), "date": rel.get("publishedAt") or rel.get("createdAt"), "pre": bool(rel.get("isPrerelease")), "url": rel.get("url")}
            names = [n["name"] for n in ((rel.get("releaseAssets") or {}).get("nodes") or [])]
            e["assetOs"] = {"Windows": True} if any(re.search(r"\.(exe|msi)$", n, re.I) for n in names) else {}
        else:
            e["noRelease"] = True
        out[k] = e
    return out

def readme_batch(keys, token, full_names):
    parts = []
    for i, k in enumerate(keys):
        files = " ".join('f%d: object(expression: %s) { ... on Blob { text } }' % (j, json.dumps("HEAD:" + n)) for j, n in enumerate(README_NAMES))
        parts.append("r%d: %s { %s }" % (i, repo_ref(k), files))
    data = gql("query {\n" + "\n".join(parts) + "\n}", token).get("data") or {}
    out = {}
    for i, k in enumerate(keys):
        r = data.get("r%d" % i)
        if not r:
            continue
        text = next(((r.get("f%d" % j) or {}).get("text") for j in range(len(README_NAMES)) if (r.get("f%d" % j) or {}).get("text")), None)
        out[k] = {"readme": A.readme_analysis(text) if text else {"none": True, "patch": {"ex": {}}},
                  "readmeLure": A.lure_signals(text) if text else [], "shots": A.readme_shots(text, full_names.get(k) or k) if text else []}
    return out

def gitlab_status(k, prev):
    base = "%s/projects/%s" % (GITLAB_API, urllib.parse.quote(k[len("gitlab.com/"):], safe=""))
    raw = http_get(base)
    if raw is None:
        return {"notFound": True}
    d = json.loads(raw)
    e = {"repo": {"pushed": d.get("last_activity_at"), "stars": d.get("star_count"), "archived": bool(d.get("archived")), "full": d.get("path_with_namespace"), "desc": d.get("description") or ""}}
    rel = json.loads(http_get(base + "/releases?per_page=1") or b"[]")
    if rel:
        r = rel[0]
        e["release"] = {"tag": r.get("tag_name"), "date": r.get("released_at") or r.get("created_at"), "pre": bool(r.get("upcoming_release")), "url": (d.get("web_url") or "") + "/-/releases"}
    else:
        e["noRelease"] = True
    if (prev.get("repo") or {}).get("pushed") == e["repo"]["pushed"] and "readme" in prev:
        e["readme"] = prev.get("readme")
    else:
        text, branch = None, urllib.parse.quote(d.get("default_branch") or "main", safe="")
        for f in README_NAMES:
            t = http_get("%s/repository/files/%s/raw?ref=%s" % (base, urllib.parse.quote(f, safe=""), branch))
            if t:
                text = t.decode("utf-8", "replace"); break
        e["readme"] = A.readme_analysis(text) if text else {"none": True, "patch": {"ex": {}}}
    return e

def refresh_status(projects):
    token = (os.environ.get("PW_GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    path = os.path.join(DATA, "status.json")
    data = load_json(path, {"format": "patch-watch-status", "version": 1, "repos": {}})
    repos = data.setdefault("repos", {})
    keys = sorted({p["k"] for p in projects if p.get("k") and not p["k"].startswith("itch.io/")})
    gh_keys = [k for k in keys if not k.startswith("gitlab.com/")]
    gl_keys = [k for k in keys if k.startswith("gitlab.com/")]
    if not token:
        log("  No GitHub token available; skipping GitHub projects"); gh_keys = []
    fresh, changed = {}, []
    for i in range(0, len(gh_keys), 40):
        batch = gh_keys[i:i + 40]
        try:
            res = meta_batch(batch, token)
        except Exception as e:
            log("  GitHub batch %d failed (%s); keeping previous results for it" % (i // 40 + 1, e)); continue
        for k, e in res.items():
            prev = repos.get(k) or {}
            fresh[k] = e
            if e.get("notFound"):
                continue
            if (prev.get("repo") or {}).get("pushed") != e["repo"]["pushed"] or "readme" not in prev:
                changed.append(k)
            else:
                e["readme"], e["readmeLure"], e["shots"] = prev.get("readme"), prev.get("readmeLure", []), prev.get("shots", [])
        time.sleep(0.5)
    for i in range(0, len(changed), 15):
        batch = changed[i:i + 15]
        try:
            res = readme_batch(batch, token, {k: (fresh.get(k, {}).get("repo") or {}).get("full") or k for k in batch})
        except Exception as e:
            log("  README batch failed (%s); keeping previous README results" % e); res = {}
        for k in batch:
            if k in res:
                fresh[k].update(res[k])
            elif "readme" in (repos.get(k) or {}):
                for f in ("readme", "readmeLure", "shots"):
                    if f in repos[k]:
                        fresh[k][f] = repos[k][f]
        time.sleep(0.5)
    for k in gl_keys:
        try:
            fresh[k] = gitlab_status(k, repos.get(k) or {})
        except Exception as e:
            log("  %s: GitLab couldn't be read (%s); keeping the previous result" % (k, e))
    for k, e in fresh.items():
        repos[k] = {x: v for x, v in e.items() if v is not None}
    for k in [k for k in repos if k not in set(keys)]:
        del repos[k]
    log("  GitHub/GitLab: %d projects in status.json (%d not found)" % (len(repos), sum(1 for e in repos.values() if e.get("notFound"))))
    data["generated"] = NOW
    return write_json_if_changed(path, data)

# ---------------------------------------------------------------- patch pages that aren't code repositories
def refresh_pages(projects):
    path = os.path.join(DATA, "pages.json")
    data = load_json(path, {"format": "patch-watch-pages", "version": 1, "pages": {}})
    pages = data.setdefault("pages", {})
    links = {}
    for p in projects:
        if p.get("k") or not re.match(r"^https?://", p.get("l") or ""):
            continue
        links[norm_link(p["l"])] = p["l"]
    for u in [u for u in pages if u not in links]:
        del pages[u]                                         # no longer tracked
    todo = sorted(links, key=lambda u: (pages.get(u) or {}).get("checked", ""))[:MAX_PAGES]
    log(f"  {len(links)} patch pages tracked; reading {len(todo)} this run (oldest first)")
    last_hit = {}
    ok = gone = failed = 0
    for u in todo:
        host = A.host_of(u)
        wait = PAGE_DELAY - (time.time() - last_hit.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        last_hit[host] = time.time()
        prev = pages.get(u) or {}
        try:
            raw = http_get(links[u], {"Accept": "text/html,application/xhtml+xml"}, tries=2, missing_ok=False)
            h = (raw or b"").decode("utf-8", "replace")
            info = A.parse_page(links[u], h)
            e = {k: v for k, v in info.items() if v not in (None, "", [], {})}
            e["checked"] = NOW
            pages[u] = e
            ok += 1
        except HttpStatus as ex:
            e = {**prev, "checked": NOW, "http": ex.code}
            if ex.code in (404, 410):
                e["misses"] = prev.get("misses", 0) + 1
                if e["misses"] >= 2:
                    e["gone"] = True
                gone += 1
            else:
                failed += 1                                  # blocked or a server error: keep what we had
            pages[u] = e
        except Exception as ex:
            pages[u] = {**prev, "checked": NOW, "err": str(ex)[:120]}
            failed += 1
    log(f"  pages: {ok} read, {gone} missing, {failed} couldn't be read (kept the previous data)")
    data["generated"] = NOW
    return write_json_if_changed(path, data)

# ---------------------------------------------------------------- newly found patches
GH_QUERIES = ["topic:undub", "topic:fan-translation", "topic:english-translation", "topic:translation-patch", "topic:english-patch",
              "undub in:name,description", '"english patch" in:name,description', '"english translation" in:name,description',
              '"fan translation" in:name,description', '"translation patch" in:name,description']
NON_ENGLISH = re.compile(r"\b(spanish|espa[nñ]ol|portugu[eê]s|portuguese|brazilian|pt-?br|french|fran[cç]ais|german|deutsch|italian|italiano|russian|chinese|korean|vietnamese|indonesian|polish|turkish|arabic|ukrainian|thai|traduc|traduz|übersetzung|перевод)\b", re.I)
GAMEY = re.compile(r"\b(game|rpg|visual novel|vn|rom|iso|patch|undub|xdelta|ips|bps|ppf|japanese|japan|famicom|nintendo|sega|playstation|ps[1-5p]|psx|vita|nds|3ds|gba|snes|sfc|n64|gamecube|wii|switch|saturn|dreamcast|pc ?engine|mega ?drive|genesis)\b", re.I)
TOOLISH = re.compile(r"\b(tool|toolkit|library|framework|sdk|editor|extractor|unpacker|compressor|plugin|api|bot|website|font)\b", re.I)
GAMEBREW_LISTS = {"PSP": "List_of_PSP_Rom_Hacks", "PS Vita": "List_of_Vita_Rom_Hacks", "DS": "List_of_all_DS_Rom_Hacks", "3DS": "List_of_all_3DS_Rom_Hacks",
                  "Wii": "List_of_Wii_rom_hacks", "Switch": "List_of_Switch_rom_hacks", "GBA": "List_of_all_GBA_Rom_Hacks"}

def gh_search(q, token):
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({"q": f"{q} fork:false pushed:>={since}", "sort": "updated", "order": "desc", "per_page": "50"})
    raw = http_get(url, {"Accept": "application/vnd.github+json", **({"Authorization": "Bearer " + token} if token else {})})
    return (json.loads(raw).get("items") if raw else None) or []

def refresh_discover(projects):
    path = os.path.join(DATA, "discover.json")
    data = load_json(path, {"format": "patch-watch-discover", "version": 1, "items": []})
    known = {norm_link(p.get("l")) for p in projects} | {p.get("k") for p in projects if p.get("k")}
    ignored = set((load_overrides().get("ignoreFound") or []))
    prev = {norm_link(i["url"]): i for i in data.get("items") or []}
    found = []
    # Romhack Plaza: the newest translation entries
    try:
        h = (http_get("https://romhackplaza.org/translations/") or b"").decode("utf-8", "replace")
        rp = A.romhack_plaza_entries("https://romhackplaza.org/translations/", h)
        log(f"  Romhack Plaza: {len(rp)} English console translations on the first page")
        found += rp
    except Exception as e:
        log(f"  Romhack Plaza couldn't be read ({e})")
    # GameBrew: each platform's list of translations and undubs
    for plat, page in GAMEBREW_LISTS.items():
        time.sleep(PAGE_DELAY)
        try:
            base = "https://www.gamebrew.org/wiki/" + page
            h = (http_get(base) or b"").decode("utf-8", "replace")
            gb = A.gamebrew_entries(base, h, plat)
            found += gb
        except Exception as e:
            log(f"  GameBrew {plat} list couldn't be read ({e})")
    # GitHub: topics and keywords
    token = (os.environ.get("PW_GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    for q in GH_QUERIES:
        time.sleep(2.5)                                   # the search API allows 30 requests a minute
        try:
            items = gh_search(q, token)
        except Exception as e:
            log(f"  GitHub search '{q}' failed ({e})"); continue
        for it in items:
            text = " ".join([it.get("full_name", ""), it.get("description") or "", " ".join(it.get("topics") or [])])
            if NON_ENGLISH.search(text) and not re.search(r"\benglish\b", text, re.I):
                continue
            if not GAMEY.search(text) or (TOOLISH.search(it.get("description") or "") and not re.search(r"\b(patch|undub)\b", text, re.I)):
                continue
            name = it.get("name", "")
            title = re.sub(r"\b(english|eng|en|translation|translated|tl|patch|undub|fan|project)\b", "", re.sub(r"[-_.]+", " ", re.sub(r"([a-z])([A-Z])", r"\1 \2", name)), flags=re.I)
            found.append({"url": it.get("html_url"), "k": it.get("full_name", "").lower(), "title": re.sub(r"\s+", " ", title).strip() or name,
                          "platform": A.detect_platform(text), "src": "GitHub", "desc": (it.get("description") or "")[:240], "stars": it.get("stargazers_count"),
                          "date": it.get("pushed_at"), "label": "Undub" if re.search(r"undub", text, re.I) else ("Machine translation" if A.MTL_RE.search(text) else "Human translation")})
    items, seen = [], set()
    for it in found:
        u = norm_link(it.get("url"))
        if not u or u in seen or u in known or (it.get("k") and it["k"] in known) or u in ignored:
            continue
        seen.add(u)
        it["url"] = u
        it["found"] = (prev.get(u) or {}).get("found") or NOW
        items.append({k: v for k, v in it.items() if v not in (None, "")})
    items.sort(key=lambda x: (x["found"], x.get("date") or ""), reverse=True)
    log(f"  {len(items)} patches found that Patch Watch doesn't list yet")
    data["items"] = items[:400]
    data["generated"] = NOW
    return write_json_if_changed(path, data)

# ---------------------------------------------------------------- IGDB screenshots
TWITCH_TOKEN_URL = os.environ.get("PW_TWITCH_TOKEN_URL", "https://id.twitch.tv/oauth2/token")
IGDB_URL = os.environ.get("PW_IGDB_URL", "https://api.igdb.com/v4")
IGDB_PLATFORMS = {"NES": 18, "FDS": 51, "SNES": 19, "Satellaview": 306, "Game Boy": 33, "Game Boy Color": 22, "GBA": 24, "Virtual Boy": 87, "N64": 4, "GameCube": 21,
                  "Wii": 5, "Wii U": 41, "Switch": 130, "DS": 20, "3DS": 37, "PS1": 7, "PS2": 8, "PS3": 9, "PS4": 48, "PSP": 38, "PS Vita": 46,
                  "Mega Drive": 29, "Mega CD": 78, "32X": 30, "Master System": 64, "Game Gear": 35, "Saturn": 32, "Dreamcast": 23, "PC Engine": 86,
                  "PC Engine CD": 150, "PC-FX": 274, "WonderSwan": 57, "WonderSwan Color": 123, "Neo Geo Pocket Color": 120, "Xbox 360": 12, "Arcade": 52}
MAX_IGDB = int(os.environ.get("PW_MAX_IGDB", "400"))

def igdb_token(cid, secret):
    body = urllib.parse.urlencode({"client_id": cid, "client_secret": secret, "grant_type": "client_credentials"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TWITCH_TOKEN_URL, data=body, headers={"User-Agent": UA}), timeout=30) as r:
        return json.loads(r.read())["access_token"]

def igdb_query(cid, token, body):
    req = urllib.request.Request(IGDB_URL + "/games", data=body.encode(), headers={"Client-ID": cid, "Authorization": "Bearer " + token, "Accept": "application/json", "User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(2 * (attempt + 1)); continue
            raise

def igdb_match(titles, results):
    best = None
    for title in [t for t in titles if t]:
        q = norm(title)
        for g in results or []:
            for n in [norm(g.get("name", ""))] + [norm(a.get("name", "")) for a in (g.get("alternative_names") or [])]:
                score = 1.0 if n == q else difflib.SequenceMatcher(None, q, n).ratio()
                if numbers(q) != numbers(n):
                    score -= 0.3
                if best is None or score > best[0]:
                    best = (score, g)
    return best if best and best[0] >= 0.85 else None

def refresh_screens(projects):
    cid, secret = os.environ.get("IGDB_CLIENT_ID", "").strip(), os.environ.get("IGDB_CLIENT_SECRET", "").strip()
    path = os.path.join(DATA, "screens.json")
    data = load_json(path, {"format": "patch-watch-screens", "version": 1, "games": {}, "map": {}})
    games, mapping = data.setdefault("games", {}), data.setdefault("map", {})
    if not cid or not secret:
        log("  IGDB_CLIENT_ID / IGDB_CLIENT_SECRET aren't set; skipping IGDB screenshots")
        return False
    try:
        token = igdb_token(cid, secret)
    except Exception as e:
        log(f"  Twitch sign-in failed ({e}); skipping IGDB screenshots"); return False
    wanted = {}
    for p in projects:
        key = p.get("k") or p["id"]
        title, jp = strip_parens(p.get("g", "")), strip_parens(p.get("jp") or "")
        pid = IGDB_PLATFORMS.get(p.get("p") or "")
        if not title or not pid:
            continue
        q = f"{norm(title)}|{pid}"
        mapping[key] = q
        wanted.setdefault(q, (title, jp, pid))
    keys = {p.get("k") or p["id"] for p in projects}
    for k in [k for k in mapping if k not in keys]:
        del mapping[k]
    now = datetime.datetime.now(datetime.timezone.utc)
    todo = [(q, t, j, pid) for q, (t, j, pid) in wanted.items()
            if not (games.get(q) and (games[q].get("shots") or (now - datetime.datetime.fromisoformat(games[q].get("checked", "2000-01-01T00:00:00Z").replace("Z", "+00:00"))).days < 30))]
    log(f"  {len(todo)} games to look up on IGDB (max {MAX_IGDB} this run)")
    found = 0
    for q, title, jp, pid in todo[:MAX_IGDB]:
        m = None
        for t in [title, jp]:
            if not t:
                continue
            safe = t.replace('"', "").replace("\\", "")
            try:
                res = igdb_query(cid, token, f'search "{safe}"; fields name,alternative_names.name,screenshots.image_id; where platforms = ({pid}); limit 8;')
            except Exception as e:
                log(f"  {t}: IGDB error ({e})"); res = []
            time.sleep(0.3)
            m = igdb_match([title, jp], res)
            if m:
                break
        if m:
            score, g = m
            shots = [s["image_id"] for s in (g.get("screenshots") or []) if s.get("image_id")][:6]
            games[q] = {"name": g.get("name"), "id": g.get("id"), "shots": shots, "match": round(score, 3), "checked": NOW}
            found += bool(shots)
        else:
            games[q] = {"shots": [], "checked": NOW}
    used = set(mapping.values())
    for q in [q for q in games if q not in used]:
        del games[q]
    log(f"  IGDB: screenshots found for {found} of {min(len(todo), MAX_IGDB)} looked up")
    data["generated"] = NOW
    return write_json_if_changed(path, data)

# ---------------------------------------------------------------- main
def main():
    only = set(a for a in sys.argv[1:])                  # e.g. "pages discover" to run just those steps
    seed = seed_projects()
    over = load_overrides()
    projects = all_projects(seed, over)
    log(f"Patch Watch list: {len(seed)} built-in projects; {len(projects)} tracked after shared fixes and added projects")
    steps = [("status", "GitHub and GitLab projects:", lambda: refresh_status(projects)),
             ("pages", "Patch pages:", lambda: refresh_pages(projects)),
             ("discover", "New patches:", lambda: refresh_discover(projects)),
             ("itch", "itch.io devlogs:", lambda: refresh_itch(projects)),
             ("covers", "Covers:", lambda: refresh_covers(projects)),
             ("screens", "IGDB screenshots:", lambda: refresh_screens(projects))]
    for name, title, fn in steps:
        if only and name not in only:
            continue
        log(title)
        try:
            fn()
        except Exception as e:                           # one failing source shouldn't stop the others
            log(f"  {name} failed: {e}")

if __name__ == "__main__":
    main()
