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
import hashlib, datetime, difflib, json, os, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
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

FILLER = {"the", "a", "an", "of", "and", "no", "wo", "ga", "ni", "to", "game", "video"}

def tokens(t):
    return [w for w in norm(t).split() if w]

def same_game(query, name):
    """True when name is the same game as query, not a sibling or a different release of it. Fuzzy matching alone takes
    'Trails in the Sky FC Evolution' for 'Trails in the Sky SC', or a PC release for a console port, so every word that
    tells versions apart has to agree: whatever one title has and the other lacks may only be filler words, or a series
    name before a colon ('The Legend of Heroes: Trails in the Sky' and 'Trails in the Sky')."""
    q, n = norm(query), norm(name)
    if not q or not n:
        return False
    if q == n:
        return True
    def variants(t):
        out = {t}
        if ":" in t:
            out.add(t.split(":", 1)[1])
        return out
    for qa in variants(query):
        for na in variants(name):
            qt, nt = set(tokens(qa)), set(tokens(na))
            if not qt or not nt:
                continue
            if (qt - nt) <= FILLER and (nt - qt) <= FILLER:
                return True
    return False

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
        if not same_game(title, h.get("name", "")):
            continue                      # a sibling game or another version (for example the PC release of a console port)
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

def known_names():
    """English names IGDB and VNDB matched for each game, so covers can be looked up by more than a romanized title."""
    out = {}
    sc = load_json(os.path.join(DATA, "screens.json"), {}) or {}
    for key, q in (sc.get("map") or {}).items():
        n = ((sc.get("games") or {}).get(q) or {}).get("name")
        if n:
            out.setdefault(key, []).append(n)
    for key, g in ((load_json(os.path.join(DATA, "nsfw.json"), {}) or {}).get("games") or {}).items():
        if g.get("name"):
            out.setdefault(key, []).append(g["name"])
    return out

def refresh_covers(projects):
    key = os.environ.get("SGDB_API_KEY", "").strip()
    path = os.path.join(DATA, "covers.json")
    data = load_json(path, {"format": "patch-watch-covers", "version": 1, "covers": {}, "misses": {}})
    covers, misses = data.setdefault("covers", {}), data.setdefault("misses", {})
    if not key:
        log("  SGDB_API_KEY isn't set; skipping covers")
        return False
    todo, seen = [], set()
    names = known_names()
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
            alts = [title, strip_parens(p.get("jp") or "")] + names.get(ck, [])
            if covers[ck].get("title") in alts and any(same_game(a, covers[ck].get("name") or "") for a in alts if a):
                continue                  # still the right game; covers matched under the older, looser rules are looked up again
            covers.pop(ck, None); misses.pop(ck, None)      # the title was corrected: look it up again
        miss = misses.get(ck)
        if miss and (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(miss.replace("Z", "+00:00"))).days < RETRY_MISSES_DAYS:
            continue
        if title:
            todo.append((ck, title, [strip_parens(p.get("jp") or "")] + names.get(ck, [])))
    log(f"  {len(todo)} games need a cover lookup (max {MAX_LOOKUPS} this run)")
    for ck, title, alts in todo[:MAX_LOOKUPS]:
        hit, used = None, title
        try:
            for t in dict.fromkeys([title] + alts):
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
            ident = A.archive_id(links[u])
            if ident:                                        # Internet Archive items are read through its metadata API
                j = json.loads(http_get(ARCHIVE_META + urllib.parse.quote(ident), tries=2, missing_ok=False) or b"{}")
                if not j.get("metadata"):
                    raise HttpStatus(404)                    # the API answers {} for items that don't exist (any more)
                info = A.parse_archive_item(ident, j)
                info.pop("patch", None)
            else:
                raw = http_get(links[u], {"Accept": "text/html,application/xhtml+xml"}, tries=2, missing_ok=False)
                h = (raw or b"").decode("utf-8", "replace")
                info = A.parse_page(links[u], h)
            e = {k: v for k, v in info.items() if v not in (None, "", [], {}, False)}
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
GH_QUERIES = ["topic:undub", "topic:fan-translation", "topic:english-translation", "topic:translation-patch", "topic:english-patch", "topic:romhacking translation",
              "undub in:name,description", '"english patch" in:name,description', '"english translation" in:name,description',
              '"fan translation" in:name,description', '"translation patch" in:name,description', 'localize in:description', 'localization in:name,description patch',
              'undub in:readme', '"english patch" in:readme', '"fan translation" in:readme xdelta']
PATCHY = re.compile(r"translat|locali[sz]|undub|english|\beng?\b|\bpatch|voice|dub", re.I)
NON_ENGLISH = re.compile(r"\b(spanish|espa[nñ]ol|portugu[eê]s|portuguese|brazilian|pt-?br|french|fran[cç]ais|german|deutsch|italian|italiano|russian|chinese|korean|vietnamese|indonesian|polish|turkish|arabic|ukrainian|thai|traduc|traduz|übersetzung|перевод)\b", re.I)
GAMEY = re.compile(r"\b(game|rpg|visual novel|vn|rom|iso|patch|undub|xdelta|ips|bps|ppf|japanese|japan|famicom|nintendo|sega|playstation|ps[1-5p]|psx|vita|nds|3ds|gba|snes|sfc|n64|gamecube|wii|switch|saturn|dreamcast|pc ?engine|mega ?drive|genesis)\b", re.I)
TOOLISH = re.compile(r"\b(tool|toolkit|library|framework|sdk|editor|extractor|unpacker|compressor|plugin|api|bot|website|font)\b", re.I)
ARCHIVE_META = os.environ.get("PW_ARCHIVE_META", "https://archive.org/metadata/")
ARCHIVE_SCRAPE = os.environ.get("PW_ARCHIVE_SCRAPE", "https://archive.org/services/search/v1/scrape")
ARCHIVE_QUERY = '(title:undub OR title:"english patch" OR title:"translation patch" OR title:"english translation" OR title:"fan translation") AND mediatype:(software OR data OR texts)'
MAX_ARCHIVE_CHECKS = int(os.environ.get("PW_MAX_ARCHIVE_CHECKS", "80"))   # new archive.org items checked for game files per run
# Uploaders and GitHub accounts known for translations and undubs. Add more in overrides.json under "watch".
WATCH_DEFAULTS = {"archiveCreators": ["swosho"], "githubOwners": ["lifebottle", "SymphoniaLauren", "AGTTeam", "Kaisaan", "Arks-Layer", "blashy101", "Supper", "pleonex"]}
GAMEBREW_LISTS = {"PSP": "List_of_PSP_Rom_Hacks", "PS Vita": "List_of_Vita_Rom_Hacks", "DS": "List_of_all_DS_Rom_Hacks", "3DS": "List_of_all_3DS_Rom_Hacks",
                  "Wii": "List_of_Wii_rom_hacks", "Switch": "List_of_Switch_rom_hacks", "GBA": "List_of_all_GBA_Rom_Hacks"}

def gh_search(q, token):
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({"q": f"{q} fork:false pushed:>={since}", "sort": "updated", "order": "desc", "per_page": "50"})
    raw = http_get(url, {"Accept": "application/vnd.github+json", **({"Authorization": "Bearer " + token} if token else {})})
    return (json.loads(raw).get("items") if raw else None) or []

def gh_repos(owner, token):
    """Every public repository of a user or organisation, most recently pushed first (None if the account doesn't exist)."""
    hdr = {"Accept": "application/vnd.github+json", **({"Authorization": "Bearer " + token} if token else {})}
    out = []
    for page in (1, 2, 3):
        raw = http_get(f"https://api.github.com/users/{urllib.parse.quote(owner)}/repos?type=owner&sort=pushed&per_page=100&page={page}", hdr)
        if raw is None:
            return None if page == 1 else out
        got = json.loads(raw) or []
        out += [r for r in got if not r.get("fork")]
        if len(got) < 100:
            break
    return out

def gh_item(it, text, src):
    name = it.get("name", "")
    title = re.sub(r"\b(english|eng|en|translation|translated|tl|patch|undub|fan|project|full voice edition)\b", lambda m: m.group(0) if m.group(0).lower() == "full voice edition" else "",
                   re.sub(r"[-_.]+", " ", re.sub(r"([a-z])([A-Z])", r"\1 \2", name)), flags=re.I)
    return {"url": it.get("html_url"), "k": it.get("full_name", "").lower(), "title": re.sub(r"\s+", " ", title).strip() or name,
            "platform": A.detect_platform(text), "src": src, "desc": (it.get("description") or "")[:240], "stars": it.get("stargazers_count"),
            "date": it.get("pushed_at"), "label": "Undub" if re.search(r"undub", text, re.I) else ("Machine translation" if A.MTL_RE.search(text) else "Human translation")}


def archive_search(q, fields="identifier,title,publicdate,creator"):
    url = ARCHIVE_SCRAPE + "?" + urllib.parse.urlencode({"q": q, "fields": fields, "count": "1000", "sorts": "publicdate desc"})
    return (json.loads(http_get(url) or b"{}").get("items")) or []


def archive_candidates(watch, prev, known, bad):
    """New patch items on the Internet Archive: everything from the watched uploaders, plus keyword matches. Items that hold
    game files (ROMs or disc images) are left out; only patches are listed."""
    hits = []
    for creator in watch.get("archiveCreators") or []:
        try:
            hits += [(i, f"Internet Archive ({creator})") for i in archive_search(f"creator:({creator})")]
        except Exception as e:
            log(f"  Internet Archive uploader {creator} couldn't be searched ({e})")
    try:
        hits += [(i, "Internet Archive") for i in archive_search(ARCHIVE_QUERY)[:300]]
    except Exception as e:
        log(f"  Internet Archive search failed ({e})")
    out, checks, skipped = [], 0, 0
    seen = set()
    for it, src in hits:
        ident = it.get("identifier") or ""
        url = "https://archive.org/details/" + ident
        title = it.get("title") if isinstance(it.get("title"), str) else " ".join(it.get("title") or [])
        if not ident or url in seen or url in known or url in bad or not re.search(r"undub|patch|translat|subtit|english", title or "", re.I):
            continue
        seen.add(url)
        if NON_ENGLISH.search(title) and not re.search(r"\benglish\b", title, re.I):
            continue
        p = prev.get(url)
        if p is None or "rom" not in p:
            if checks >= MAX_ARCHIVE_CHECKS:
                continue                                  # checked on a later run
            checks += 1
            try:
                info = A.parse_archive_item(ident, json.loads(http_get(ARCHIVE_META + urllib.parse.quote(ident)) or b"{}"))
            except Exception:
                continue
            time.sleep(0.5)
            p = {"rom": info.get("rom"), "platform": info.get("plat") or A.detect_platform(title), "date": info.get("upd")}
        if p.get("rom"):
            bad.add(url)
            skipped += 1
            continue                                      # holds game files, not just a patch: never listed
        clean = re.sub(r"\s*(UNDUB|undub|English|Translation|Translated)?\s*(patch(es)?|addendum)\b.*$", "", title).strip(" -–:/") or title
        clean = re.sub(r"\s*\((PS2|PS3|PSV|PSP|GBA|DS|3DS|Wii|PC|PS1|PSX)\)\s*$", "", clean).strip()
        out.append({"url": url, "title": clean, "platform": p.get("platform") or A.detect_platform(title), "src": src, "date": p.get("date") or it.get("publicdate"),
                    "label": "Undub" if re.search(r"undub", title, re.I) else "Human translation", "desc": title, "rom": False})
    log(f"  Internet Archive: {len(out)} patch items, {skipped} left out because they contain game files, {checks} newly checked")
    return out


# CDRomance: a discovery signal only. Its newest translation and undub posts are read to find each one's credited
# original source; only that source (patch page, repository, thread) is listed. CDRomance pages are never linked or stored:
# posts already read are remembered by a hash of their path, not their address.
CDR_BASE = os.environ.get("PW_CDR_BASE", "https://cdromance.org")
CDR_LISTS = ["/translations/", "/translations/?language=undub"]
CDR_PAGES = int(os.environ.get("PW_CDR_PAGES", "3"))              # listing pages read per section (about 20 posts each)
MAX_CDR_POSTS = int(os.environ.get("PW_MAX_CDR_POSTS", "120"))     # new posts opened per run
CDR_DELAY = float(os.environ.get("PW_CDR_DELAY", "1.5"))
CDR_V = 3                                                        # bumped when post reading changes: skipped posts are read again

def cdr_hash(cat, slug):
    return hashlib.sha1(f"{cat}/{slug}".encode()).hexdigest()[:16]

def cdromance_candidates(prev_seen):
    """Returns (items, seen). seen maps a post hash to the source it credits ("" when it credits none worth listing)."""
    posts, blocked = [], False
    for lst in CDR_LISTS:
        for n in range(1, CDR_PAGES + 1):
            path = lst if n == 1 else lst.replace("/translations/", f"/translations/page/{n}/")
            try:
                h = (http_get(CDR_BASE + path) or b"").decode("utf-8", "replace")
            except Exception as e:
                log(f"  CDRomance listing couldn't be read ({e}); skipped this run"); blocked = True; break
            if re.search(r"cf-chl|challenge-platform|Just a moment", h[:5000]):
                log("  CDRomance asked for a browser check; skipped this run"); blocked = True; break
            got = A.cdromance_posts(h)
            if not got:
                break
            posts += [(c, s, u, "undub" in lst) for c, s, u in got]
            time.sleep(CDR_DELAY)
        if blocked:
            break
    seen, items, opened, skipped = dict(prev_seen), [], 0, {}
    done = set()
    for cat, slug, url, from_undub in posts:
        hk = cdr_hash(cat, slug)
        if hk in done:
            continue
        done.add(hk)
        rec = seen.get(hk)
        if rec is None:
            if opened >= MAX_CDR_POSTS:
                continue                                       # read on a later run
            opened += 1
            time.sleep(CDR_DELAY)
            try:
                h = (http_get(url) or b"").decode("utf-8", "replace")
            except Exception:
                continue
            info = A.parse_cdromance_post(url, h, cat)
            if info.get("skip") or info.get("notConsole"):
                r = info.get("skip") or "not a console"
                skipped[r] = skipped.get(r, 0) + 1
                seen[hk] = {"src": "", "why": r}
                continue
            rec = {k: info[k] for k in ("src", "title", "platform", "label", "authors", "undub") if info.get(k)}
            if from_undub:
                rec["undub"] = True
            seen[hk] = rec
        if not rec.get("src"):
            continue
        label = rec.get("label") or "Human translation"
        if rec.get("undub") and label == "Human translation" and from_undub and not re.search(r"translat|english", rec.get("src", ""), re.I):
            label = "Undub"
        desc = "Credited source of a new release" + (f" by {', '.join(rec['authors'])}" if rec.get("authors") else "") + (" (also undubbed)" if rec.get("undub") and label != "Undub" else "")
        items.append({"url": rec["src"], "title": rec.get("title"), "platform": rec.get("platform"), "label": label,
                      "src": "Credited on CDRomance", "desc": desc,
                      "k": (lambda m: m.group(1).lower() if m else None)(re.match(r"https?://github\.com/([^/]+/[^/#?]+)", rec["src"]))})
    log(f"  CDRomance: {len(done)} recent posts, {opened} newly read, {len(items)} credited sources" +
        (f", skipped: {', '.join(f'{v} {k}' for k, v in skipped.items())}" if skipped else ""))
    return items, seen


def refresh_discover(projects):
    path = os.path.join(DATA, "discover.json")
    data = load_json(path, {"format": "patch-watch-discover", "version": 1, "items": []})
    known = {norm_link(p.get("l")) for p in projects} | {p.get("k") for p in projects if p.get("k")}
    loose = lambda u: re.sub(r"^https?://(www\.)?", "", norm_link(u).lower())
    known_loose = {loose(p.get("l")) for p in projects if p.get("l")}
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
            found.append(gh_item(it, text, "GitHub"))
    watch = {**WATCH_DEFAULTS, **((load_overrides().get("watch")) or {})}
    # GitHub accounts known for translations: every repository of theirs that looks like a patch
    for owner in watch.get("githubOwners") or []:
        time.sleep(2.5)
        try:
            items = gh_repos(owner, token)
        except Exception as e:
            log(f"  GitHub account {owner} couldn't be read ({e})"); continue
        if items is None:
            log(f"  GitHub account {owner} doesn't exist (check the name under watch.githubOwners in overrides.json)"); continue
        for it in items:
            text = " ".join([it.get("full_name", ""), it.get("description") or "", " ".join(it.get("topics") or [])])
            if not PATCHY.search(text) or (TOOLISH.search(it.get("description") or "") and not re.search(r"\b(patch|undub|locali[sz]e)\b", text, re.I)):
                continue
            found.append(gh_item(it, text, f"GitHub ({owner})"))
    bad = set(data.get("archiveGameFiles") or [])          # items found to hold game files: never checked or listed again
    found += archive_candidates(watch, prev, known, bad)
    data["archiveGameFiles"] = sorted(bad)
    # CDRomance: credited original sources of new releases (sources that are archive.org items get the same game-file check)
    try:
        prev_seen = data.get("cdromanceSeen") or {}
        if data.get("cdromanceV") != CDR_V:
            prev_seen = {k: v for k, v in prev_seen.items() if v.get("src")}
        cdr, data["cdromanceSeen"] = cdromance_candidates(prev_seen)
        data["cdromanceV"] = CDR_V
        for it in cdr:
            ident = A.archive_id(it["url"]) if "archive.org/" in it["url"] else ""
            if ident:
                u = "https://archive.org/details/" + ident
                if u in bad:
                    continue
                try:
                    info = A.parse_archive_item(ident, json.loads(http_get(ARCHIVE_META + urllib.parse.quote(ident)) or b"{}"))
                except Exception:
                    continue
                if info.get("rom"):
                    bad.add(u); continue
                it["url"] = u
            found.append(it)
        data["archiveGameFiles"] = sorted(bad)
    except Exception as e:
        log(f"  CDRomance step failed ({e})")
    items, seen = [], set()
    for it in found:
        u = norm_link(it.get("url"))
        if not u or u in seen or u in known or loose(u) in known_loose or (it.get("k") and it["k"] in known) or u in ignored:
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
IGDB_TV = 3                                              # bumped when the lookup changes, so every game is looked up again once
IGDB_EROTIC = 42                                         # IGDB's theme id for "Erotic"

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
            for raw in [g.get("name", "")] + [a.get("name", "") for a in (g.get("alternative_names") or [])]:
                if not same_game(title, raw):
                    continue
                n = norm(raw)
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
            if not (games.get(q) and games[q].get("tv") == IGDB_TV and (games[q].get("shots") or games[q].get("cover") or (now - datetime.datetime.fromisoformat(games[q].get("checked", "2000-01-01T00:00:00Z").replace("Z", "+00:00"))).days < 30))]
    log(f"  {len(todo)} games to look up on IGDB (max {MAX_IGDB} this run)")
    found = 0
    fields = "fields name,alternative_names.name,screenshots.image_id,cover.image_id,themes;"
    for q, title, jp, pid in todo[:MAX_IGDB]:
        m = None
        # 1. IGDB's search on this platform, by the title and then the Japanese title. 2. The romanized or Japanese name
        # among IGDB's alternative names (Japanese-only games are often filed under their English name). 3. Any platform,
        # for an exact title match only (IGDB sometimes files a port under the original platform).
        tries = []
        for t in [title, jp]:
            if t:
                safe = t.replace('"', "").replace("\\", "")
                tries.append((f'search "{safe}"; {fields} where platforms = ({pid}); limit 8;', 0.85))
        for t in [jp, title]:
            if t and len(t) >= 4:
                safe = t.replace('"', "").replace("\\", "")
                tries.append((f'{fields} where alternative_names.name ~ *"{safe}"* & platforms = ({pid}); limit 8;', 0.85))
        for t in [title, jp]:
            if t:
                safe = t.replace('"', "").replace("\\", "")
                tries.append((f'search "{safe}"; {fields} limit 8;', 0.97))
        any_plat = False
        for body, need in tries:
            any_plat = "platforms" not in body
            try:
                res = igdb_query(cid, token, body)
            except Exception as e:
                log(f"  {title}: IGDB error ({e})"); res = []
            time.sleep(0.3)
            m = igdb_match([title, jp], res)
            if m and m[0] >= need:
                break
            m = None
        if m:
            score, g = m
            shots = [s["image_id"] for s in (g.get("screenshots") or []) if s.get("image_id")][:6]
            games[q] = {"name": g.get("name"), "id": g.get("id"), "shots": shots, "match": round(score, 3), "checked": NOW, "tv": IGDB_TV}
            if (g.get("cover") or {}).get("image_id"):
                games[q]["cover"] = g["cover"]["image_id"]
            if any_plat:
                games[q]["anyPlat"] = True                # matched on another platform: its cover may show a different release
            if IGDB_EROTIC in (g.get("themes") or []):
                games[q]["nsfw"] = True                   # IGDB lists the game under its "Erotic" theme
            found += bool(shots)
        else:
            games[q] = {"shots": [], "checked": NOW, "tv": IGDB_TV}
    used = set(mapping.values())
    for q in [q for q in games if q not in used]:
        del games[q]
    log(f"  IGDB: matched {sum(1 for q, *_ in todo[:MAX_IGDB] if games.get(q, {}).get('id'))} of {min(len(todo), MAX_IGDB)} looked up ({found} with screenshots)")
    data["generated"] = NOW
    return write_json_if_changed(path, data)

# ---------------------------------------------------------------- NSFW cover art (VNDB)
VNDB_API = os.environ.get("PW_VNDB_API", "https://api.vndb.org/kana/vn")
MAX_VNDB = int(os.environ.get("PW_MAX_VNDB", "150"))   # VNDB allows 200 requests every 5 minutes
VNDB_PLATFORMS = {"NES": "nes", "FDS": "nes", "SNES": "sfc", "Game Boy": "gba", "GBA": "gba", "N64": "n64", "GameCube": "gcn", "Wii": "wii", "Wii U": "wiu",
                  "Switch": "swi", "DS": "nds", "3DS": "n3d", "PS1": "ps1", "PS2": "ps2", "PS3": "ps3", "PS4": "ps4", "PSP": "psp", "PS Vita": "psv",
                  "Saturn": "sat", "Dreamcast": "drc", "Mega Drive": "smd", "Mega CD": "scd", "PC Engine": "pce", "PC Engine CD": "pce", "PC-FX": "pcf",
                  "WonderSwan": "wsw", "WonderSwan Color": "wsw", "Xbox 360": "xb3", "PC": "win"}
NSFW_SEXUAL = 1.0                                        # VNDB rates cover images 0 (safe), 1 (suggestive) and 2 (explicit); blur from suggestive up

def vndb_query(title):
    body = json.dumps({"filters": ["search", "=", title], "fields": "title, alttitle, titles.title, platforms, image.url, image.sexual, image.violence", "results": 8}).encode()
    req = urllib.request.Request(VNDB_API, data=body, headers={"Content-Type": "application/json", "User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read()).get("results") or []
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(30); continue
            raise

def refresh_nsfw(projects):
    """Looks each game up on VNDB (visual novels) and records how sexual its cover art is rated, so the page can blur it."""
    path = os.path.join(DATA, "nsfw.json")
    data = load_json(path, {"format": "patch-watch-nsfw", "version": 1, "games": {}})
    games = data.setdefault("games", {})
    now = datetime.datetime.now(datetime.timezone.utc)
    keys = {p.get("k") or p["id"] for p in projects}
    for k in [k for k in games if k not in keys]:
        del games[k]
    todo = []
    for p in projects:
        key = p.get("k") or p["id"]
        g = games.get(key)
        if g and g.get("iv") == 1 and g.get("title") == p.get("g") and (now - datetime.datetime.fromisoformat(g.get("checked", "2000-01-01T00:00:00Z").replace("Z", "+00:00"))).days < 60:
            continue
        todo.append(p)
    log(f"  {len(todo)} games to look up on VNDB (max {MAX_VNDB} this run)")
    hits = 0
    for p in todo[:MAX_VNDB]:
        key = p.get("k") or p["id"]
        titles = [t for t in [strip_parens(p.get("g", "")), strip_parens(p.get("jp") or "")] if t]
        best, plat = None, VNDB_PLATFORMS.get(p.get("p") or "")
        try:
            for t in titles:
                for vn in vndb_query(t):
                    names = [vn.get("title"), vn.get("alttitle")] + [x.get("title") for x in (vn.get("titles") or [])]
                    if not any(same_game(tt, n) for n in names if n for tt in titles):
                        continue
                    score = max((1.0 if norm(n) == norm(tt) else difflib.SequenceMatcher(None, norm(n), norm(tt)).ratio())
                                for n in names if n for tt in titles)
                    if numbers(norm(names[0] or "")) != numbers(norm(titles[0])):
                        score -= 0.3
                    if plat and plat not in (vn.get("platforms") or []):
                        score -= 0.15                     # same title, but VNDB doesn't list it on this platform
                    if score >= 0.9 and (best is None or score > best[0]):
                        best = (score, vn)
                time.sleep(1.6)
                if best:
                    break
        except Exception as e:
            log(f"  {titles[0] if titles else key}: VNDB error ({e})")
            continue
        e = {"title": p.get("g"), "checked": NOW, "iv": 1}
        if best:
            img = best[1].get("image") or {}
            e.update({"vn": best[1].get("id"), "name": best[1].get("title"), "sexual": img.get("sexual"), "match": round(best[0], 3)})
            if img.get("url"):
                e["img"] = img["url"]                     # the visual novel's cover, used when nothing better is found
            if (img.get("sexual") or 0) >= NSFW_SEXUAL:
                e["nsfw"] = True
                hits += 1
        games[key] = e
    log(f"  VNDB: {hits} covers rated suggestive or explicit")
    data["generated"] = NOW
    return write_json_if_changed(path, data)

# ---------------------------------------------------------------- LaunchBox Games Database covers
# LaunchBox publishes its whole games database every day as one zip, with each game's alternate names (including
# romanized and Japanese titles) and its box art per region. Box art is served from images.launchbox-app.com.
LB_URL = os.environ.get("PW_LAUNCHBOX_URL", "https://gamesdb.launchbox-app.com/Metadata.zip")
LB_IMG = "https://images.launchbox-app.com/"
LB_CACHE = os.path.join(ROOT, ".cache", "launchbox")
LB_PLATFORMS = {"Nintendo Entertainment System": "NES", "Nintendo Famicom Disk System": "FDS", "Super Nintendo Entertainment System": "SNES",
                "Nintendo Satellaview": "Satellaview", "Nintendo Game Boy": "Game Boy", "Nintendo Game Boy Color": "Game Boy Color",
                "Nintendo Game Boy Advance": "GBA", "Nintendo Virtual Boy": "Virtual Boy", "Nintendo 64": "N64", "Nintendo GameCube": "GameCube",
                "Nintendo Wii": "Wii", "Nintendo Wii U": "Wii U", "Nintendo Switch": "Switch", "Nintendo DS": "DS", "Nintendo 3DS": "3DS",
                "Sony Playstation": "PS1", "Sony Playstation 2": "PS2", "Sony Playstation 3": "PS3", "Sony Playstation 4": "PS4", "Sony PSP": "PSP",
                "Sony Playstation Vita": "PS Vita", "Sega Genesis": "Mega Drive", "Sega CD": "Mega CD", "Sega 32X": "32X", "Sega Master System": "Master System",
                "Sega Game Gear": "Game Gear", "Sega Saturn": "Saturn", "Sega Dreamcast": "Dreamcast", "NEC TurboGrafx-16": "PC Engine",
                "NEC TurboGrafx-CD": "PC Engine CD", "NEC PC-FX": "PC-FX", "WonderSwan": "WonderSwan", "WonderSwan Color": "WonderSwan Color",
                "SNK Neo Geo Pocket Color": "Neo Geo Pocket Color", "Microsoft Xbox 360": "Xbox 360", "Windows": "PC"}
LB_TYPES = ["Box - Front", "Box - Front - Reconstructed", "Fanart - Box - Front"]
LB_JP_FIRST = ["Japan", "Asia", "World", "", "North America", "United States", "Europe"]
LB_WEST_FIRST = ["North America", "United States", "World", "", "Europe", "United Kingdom", "Australia", "Japan", "Asia"]

def launchbox_zip():
    """The cached Metadata.zip, downloaded again when it's over a week old (the workflow keeps .cache between runs)."""
    os.makedirs(LB_CACHE, exist_ok=True)
    path, stamp = os.path.join(LB_CACHE, "Metadata.zip"), os.path.join(LB_CACHE, "downloaded")
    try:
        when = float(open(stamp).read().strip())       # file times change when the cache is restored, so the date is kept in a file
    except (OSError, ValueError):
        when = 0
    if not os.path.exists(path) or time.time() - when > 7 * 86400:
        log("  downloading the LaunchBox Games Database")
        req = urllib.request.Request(LB_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=600) as r, open(path + ".part", "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(path + ".part", path)
        open(stamp, "w").write(str(time.time()))
    return path

def refresh_launchbox(projects):
    import zipfile
    path = os.path.join(DATA, "launchbox.json")
    data = load_json(path, {"format": "patch-watch-launchbox", "version": 1, "games": {}})
    games = data.setdefault("games", {})
    keys = {p.get("k") or p["id"]: p for p in projects}
    last = data.get("generated") or "2000-01-01T00:00:00Z"
    age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(last.replace("Z", "+00:00"))).days
    missing = [k for k in keys if k not in games]
    if age < 7 and not missing:
        log("  nothing new to look up (the database is matched again weekly)")
        return False
    try:
        zpath = launchbox_zip()
    except Exception as e:
        log(f"  the LaunchBox Games Database couldn't be downloaded ({e})")
        return False
    names_by_plat, plat_of, images = {}, {}, {}
    wanted_plats = {LB_PLATFORMS.get(x) for x in LB_PLATFORMS} & {p.get("p") for p in projects}
    def text(el, tag):
        x = el.find(tag)
        return (x.text or "").strip() if x is not None and x.text else ""
    with zipfile.ZipFile(zpath) as z:
        member = next((n for n in z.namelist() if n.lower().endswith("metadata.xml")), None)
        if not member:
            log("  Metadata.xml isn't in the zip; skipping")
            return False
        alt_rows = []
        with z.open(member) as f:
            for _, el in ET.iterparse(f, events=("end",)):
                tag = el.tag
                if tag == "Game":
                    plat = LB_PLATFORMS.get(text(el, "Platform"))
                    gid = text(el, "DatabaseID")
                    if plat in wanted_plats and gid:
                        plat_of[gid] = plat
                        names_by_plat.setdefault(plat, []).append((text(el, "Name"), gid))
                    el.clear()
                elif tag == "GameAlternateName":
                    alt_rows.append((text(el, "DatabaseID"), text(el, "AlternateName")))
                    el.clear()
                elif tag == "GameImage":
                    gid, typ = text(el, "DatabaseID"), text(el, "Type")
                    if typ in LB_TYPES:
                        images.setdefault(gid, []).append((typ, text(el, "Region"), text(el, "FileName")))
                    el.clear()
                elif tag in ("EmulatorPlatform", "GameHash", "PlatformAlternateName"):   # never "Platform": it is also a field inside <Game>
                    el.clear()
        for gid, alt in alt_rows:
            plat = plat_of.get(gid)
            if plat and alt:
                names_by_plat[plat].append((alt, gid))
    index = {}
    for plat, rows in names_by_plat.items():
        by_norm = {}
        for name, gid in rows:
            by_norm.setdefault(norm(name), []).append((name, gid))
        index[plat] = (rows, by_norm)
    extra = known_names()
    found = 0
    for key, p in keys.items():
        plat = p.get("p")
        if plat not in index:
            continue
        rows, by_norm = index[plat]
        titles = [t for t in dict.fromkeys([strip_parens(p.get("g", "")), strip_parens(p.get("jp") or "")] + extra.get(key, [])) if t]
        gid, matched = None, ""
        for t in titles:
            exact = [r for r in by_norm.get(norm(t), []) if images.get(r[1])]
            if exact:
                matched, gid = exact[0]
                break
        if not gid:
            for t in titles:
                cands = [r for r in rows if images.get(r[1]) and same_game(t, r[0])]
                if cands:
                    matched, gid = cands[0]
                    break
        if not gid:
            games.pop(key, None)
            continue
        order = LB_WEST_FIRST if "Undub" in (p.get("lb") or []) else LB_JP_FIRST
        imgs = sorted(images[gid], key=lambda x: (LB_TYPES.index(x[0]), order.index(x[1]) if x[1] in order else len(order)))
        typ, region, fn = imgs[0]
        games[key] = {"url": LB_IMG + urllib.parse.quote(fn), "name": matched, "region": region or "", "id": gid}
        found += 1
    for k in [k for k in games if k not in keys]:
        del games[k]
    log(f"  LaunchBox: box art for {found} of {len(keys)} games")
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
             ("screens", "IGDB covers and screenshots:", lambda: refresh_screens(projects)),
             ("nsfw", "VNDB covers and NSFW ratings:", lambda: refresh_nsfw(projects)),
             ("covers", "SteamGridDB covers:", lambda: refresh_covers(projects)),
             ("launchbox", "LaunchBox covers:", lambda: refresh_launchbox(projects))]
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
