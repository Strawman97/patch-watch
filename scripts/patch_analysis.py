"""Patch Watch's detection rules, ported from index.html so the shared refresh gives the same answers as the page.

Keep this file in step with the JavaScript in index.html (EXTRAS, MTL_RE, NOT_MTL_RE, UNDUB_RE, COV_RES, analyzePatch,
SHOT_SKIP, readmeShots, LURE_RE, PLAT_RULES). Flags: re.I | re.A gives JavaScript's ASCII-only \\b and \\w.

It also holds the page readers the refresh uses for patch pages that aren't code repositories (GameBrew, Romhack Plaza,
Romhacking.net, GBAtemp and ordinary websites). They only use the Python standard library and are deliberately forgiving:
anything they can't find is simply left out.
"""
import datetime, html as htmllib, re, urllib.parse

F = re.I | re.A

EXTRAS = [
    ("retrans", r"\bre-?translat|re-?locali[sz]"),
    ("port", r"\bport(ed|s)? (of )?(the )?(official|existing|english|fan|steam|pc|ps4|switch)( english)? (script|translation|localization|text)|translation port|(script|translation) (ported|port) (from|of)"),
    ("subs", r"\bsubtit|\bsubbed\b"),
    ("restore", r"\brestor(e|es|ed|ation)\b|cut content|unused content|removed content"),
    ("uncensor", r"\buncensor"),
    ("fixes", r"\bbug ?fix|fix(es|ed)? (bugs|glitches|crash)"),
    ("gameplay", r"\brebalanc|difficulty (option|mode|tweak)|gameplay (change|tweak|improvement)|quality of life|\bqol\b"),
    ("gfx", r"\btextures?\b|\bwidescreen\b|\bhd (graphics|textures|fonts?)\b|redrawn|new font"),
    ("dual", r"\bdual[- ]audio\b|switch between (the )?(japanese|english) and (japanese|english)"),
]
EXTRAS = [(i, re.compile(p, F)) for i, p in EXTRAS]
MTL_RE = re.compile(r"\bmachine[- ]?translat|\bmtl\b|google translat|\bdeepl\b|\bai[- ](translat|assisted|generated)|\bai translation|chat ?gpt|\bllm\b|translated (with|using|by) (an? )?(ai|machine|gpt)", F)
NOT_MTL_RE = re.compile(r"\b(not|no|without|isn'?t|zero)\b[^.\n]{0,25}(machine[- ]?translat|\bmtl\b|\bai\b)", F)
UNDUB_RE = re.compile(r"\bun-?dub(bed|s)?\b|japanese (voices?|audio|voice acting) (restored|patch)|restores? (the )?japanese (voices?|audio)", F)
COV_RES = [
    ("Menus only", re.compile(r"\b(menus?|ui|interface)[- ](only|translation|patch)\b|\bonly (the )?(menus?|ui|interface)\b", F)),
    ("Story only", re.compile(r"\b(main )?(story|script|dialogue) (is )?(fully )?translated\b[^.\n]{0,80}\b(side|optional|sub-?quests?|extras?|minigames?|bonus)\b[^.\n]{0,40}\b(not|untranslated|japanese)\b", F)),
    ("Partial", re.compile(r"\bpartial(ly)?( translat|\b)|\bwork[- ]in[- ]progress\b|\bwip\b|\bdemo patch\b|\bprologue (patch|translation)\b|\bincomplete\b|\b(?:[1-9]|[1-9]\d)\s?% (translated|complete|done)\b", F)),
    ("Complete", re.compile(r"\b100\s?% (translated|complete|done)\b|\bfully translated\b|\bcomplete (english )?translation\b|\btranslation is (now )?complete\b|\ball (of the )?(text|dialogue|script) (is |has been )?translated\b", F)),
]
ADULT_RE = re.compile(r"\b(hentai|eroge|ecchi|nsfw|r-?18|18\+ (only|content|game|patch|version)|adults? only|adult (content|game|visual novel|scenes?)|explicit (sexual|content|scenes?)|sexual content|h-?scenes?)\b", F)
OTHER_PATCH_RE = re.compile(r"\b(other|previous|older|earlier|prior|old|existing|original|first|another|floating around|someone else'?s?|was|were|used to be)\b[^.\n]{0,60}\b(patch|patches|translation|translations|release|version)\b|\b(patch|patches|translation|translations)\b[^.\n]{0,40}\bby (?!this|us|me|our)\w+", F)
STRONG_COMPLETE_RE = re.compile(r"\b(completely|fully|entirely) translat|\btranslates the (entire|whole|full|complete) game\b|\b100\s?% (translated|complete|done)\b|\bcomplete (english )?translation\b|\bevery(thing| line| text)\b[^.\n]{0,30}\btranslated\b", F)


def coverage_of(t):
    """Coverage judged sentence by sentence (see coverageOf in index.html): sentences about other or older patches are
    ignored, and a clear 'completely translates the game' outranks a passing 'partial'."""
    ss = [s.strip() for s in re.split(r"\n+|(?<=[.!?;])\s+|,\s+(?:but|while|whereas|although)\s+", str(t or "")) if s.strip() and not OTHER_PATCH_RE.search(s)]
    has = lambda rx: any(rx.search(s) for s in ss)
    by = dict(COV_RES)
    for name, rx in (("Menus only", by["Menus only"]), ("Story only", by["Story only"]), ("Complete", STRONG_COMPLETE_RE), ("Partial", by["Partial"]), ("Complete", by["Complete"])):
        if has(rx):
            return name
    return None


PCT_RE = re.compile(r"\b(\d{1,3})\s?% (translated|complete|done)\b", F)


def analyze_patch(text):
    t = str(text or "")
    out = {"ex": {}}
    if MTL_RE.search(t) and not NOT_MTL_RE.search(t):
        out["mtl"] = True
    if UNDUB_RE.search(t):
        out["undub"] = True
    cov = coverage_of(t)
    if cov:
        out["cov"] = cov
    m = PCT_RE.search(t)
    if m and int(m.group(1)) <= 100:
        out["pct"] = int(m.group(1))
    for i, rx in EXTRAS:
        if rx.search(t):
            out["ex"][i] = True
    if ADULT_RE.search(t):
        out["adult"] = True
    return out


# ---------------------------------------------------------------- README screenshots and malware-lure signals
SHOT_SKIP = re.compile(r"shields\.io|badge|powered-?by|gplv?\d|gnu\.org/graphics|licen[cs]e|made-?with|built-?with|logo|icon|banner|favicon|box-?art|cover|background|\.svg(\?|$)|discord|invidget|widget|ko-?fi|patreon|paypal|buymeacoffee|sponsor|readme-typing|skillicons|github-readme-stats|star-history|contrib\.rocks|visitor|komarev|wakatime|capsule-render|emoji|avatar|qr-?code|\.mp4|\.webm|\.mov", F)
IMG_MD = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)|<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"'][^>]*>", re.I)


def resolve_img(u, full):
    if not u or u.lower().startswith("data:"):
        return ""
    x = u.replace("&amp;", "&").strip()
    b = re.match(r"^https?://github\.com/([^/]+/[^/]+)/(?:blob|raw)/(.+)$", x, re.I)
    if b:
        return "https://raw.githubusercontent.com/" + b.group(1) + "/" + re.sub(r"\?raw=true$", "", b.group(2), flags=re.I)
    if re.match(r"^https?://", x, re.I):
        return x
    if x.startswith("//"):
        return "https:" + x
    if not full:
        return ""
    x = re.sub(r"^\./", "", x).lstrip("/").split("#")[0]
    if not x or x.startswith("../"):
        return ""
    return "https://raw.githubusercontent.com/" + full + "/HEAD/" + x


def readme_shots(text, full):
    out = []
    for m in IMG_MD.finditer(str(text or "")):
        if len(out) >= 6:
            break
        raw = (m.group(2) or m.group(3) or "").strip()
        alt = m.group(1) or (re.search(r"\balt=[\"']([^\"']*)[\"']", m.group(0), re.I) or [None, ""])[1] or ""
        if not raw or SHOT_SKIP.search(raw) or SHOT_SKIP.search(alt):
            continue
        u = resolve_img(raw, full)
        if not u:
            continue
        if not re.search(r"\.(png|jpe?g|gif|webp)(\?|$)", u, re.I) and not re.search(r"user-attachments/assets/", u, re.I):
            continue
        if u not in out:
            out.append(u)
    return out


LURE_RE = {
    "badges": re.compile(r"img\.shields\.io/badge/((downloads?|installs?|users|players|active[-_%20 ]*users)[-_]\d|rating[-_]\d)", re.I),
    "filehost": re.compile(r"(mediafire\.com|mega\.nz|gofile\.io|pixeldrain\.com|anonfiles|dropbox\.com/s|bit\.ly/|tinyurl\.com|cutt\.ly|t\.me/|discord(app)?\.com/attachments|qiwi\.gg|krakenfiles|sendspace)", re.I),
    "offsite": re.compile(r"\]\(https?://[a-z0-9-]+\.github\.io/[^)\s]*(download|setup|install)[^)\s]*\)|download (for )?(windows|mac(os)?)[^\n]{0,200}?\]\(https?://(?!github\.com/|img\.shields\.io/)[^)\s]+\)", re.I),
    "password": re.compile(r"(archive|zip|rar|7z|extract)[^\n]{0,60}password|password[^\n]{0,25}[:=]\s*\S{2,}", re.I),
}


def lure_signals(text):
    return [k for k, rx in LURE_RE.items() if rx.search(text or "")]


def readme_analysis(text):
    return {"patch": analyze_patch(text), "v": 1}


# ---------------------------------------------------------------- platforms named in text
PLAT_RULES = [(p, re.compile(r, F)) for p, r in [
    ("PS Vita", r"ps ?vita\b|\bpsvita\b|\bvita\b"), ("PSP", r"\bpsp\b|playstation portable"), ("PS4", r"\bps4\b|playstation 4"), ("PS3", r"\bps3\b|playstation 3"),
    ("PS2", r"\bps2\b|playstation 2"), ("PS1", r"\bps1\b|\bpsx\b|playstation 1|\bplaystation\b(?! ?([2-5]|portable|vita|plus|network))"),
    ("Switch", r"nintendo switch|\bswitch\b|\bnsw\b|\bnsp\b"), ("Wii U", r"wii ?u\b"), ("Wii", r"\bwii\b"), ("GameCube", r"gamecube|\bgcn\b|\bngc\b"),
    ("3DS", r"\b3ds\b"), ("DS", r"\bnds\b|nintendo ds\b|\bds\b"), ("N64", r"\bn64\b|nintendo 64"), ("Satellaview", r"satellaview|\bbs-x\b"),
    ("SNES", r"\bsnes\b|super nintendo|super famicom|\bsfc\b"), ("FDS", r"disk system|\bfds\b"), ("NES", r"\bnes\b|famicom"),
    ("GBA", r"\bgba\b|game ?boy advance"), ("Game Boy Color", r"\bgbc\b|game ?boy colou?r"), ("Game Boy", r"game ?boy\b"), ("Dreamcast", r"dreamcast"),
    ("Saturn", r"sega saturn|\bsaturn\b"), ("Mega CD", r"mega[- ]?cd|sega cd"), ("Mega Drive", r"mega ?drive|sega genesis|\bgenesis\b"),
    ("PC Engine CD", r"pc ?engine cd|turbografx[- ]cd|pce[- ]cd"), ("PC Engine", r"pc ?engine|turbografx|\bpce\b"), ("WonderSwan Color", r"wonderswan colou?r"),
    ("WonderSwan", r"wonderswan"), ("Neo Geo Pocket Color", r"neo ?geo pocket"), ("Game Gear", r"game gear"), ("Master System", r"master system|sega mark iii")]]


def detect_platform(text):
    for p, rx in PLAT_RULES:
        if rx.search(text or ""):
            return p
    return ""


# ---------------------------------------------------------------- patch pages
SCRIPT_RE = re.compile(r"<(script|style|noscript|svg|template)\b[\s\S]*?</\1>", re.I)
BLOCK_RE = re.compile(r"<\s*/?\s*(p|div|br|li|tr|td|th|dt|dd|h[1-6]|section|article|table|ul|ol|header|footer|blockquote)\b[^>]*>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
PAGE_SHOT_HINT = re.compile(r"screen|snap|shot|gallery|storage/entries|dlhb\.gamebrew\.org|/images/[0-9a-f]/|attachments?/|imgur\.com|/uploads/|/data/attachments", re.I)
PAGE_SHOT_SKIP = re.compile(r"logo|icon|avatar|banner|flag|badge|emoji|smil|sprite|button|gravatar|/ads?/|advert|header|favicon|placeholder|loading|spinner|rating|star|thumb_|/skins?/|/styles?/|patreon|paypal|ko-?fi|discord|\.svg(\?|$)|1x1|pixel|youtube|ytimg", re.I)


def html_text(h):
    t = SCRIPT_RE.sub(" ", h or "")
    t = BLOCK_RE.sub("\n", t)
    t = TAG_RE.sub(" ", t)
    t = htmllib.unescape(t)
    t = re.sub(r"[ \t ]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def parse_date(s):
    """Dates as patch pages write them: 2021-08-15, 2014/06/18, Aug 15, 2021, 15 August 2021, ISO timestamps."""
    s = (s or "").strip()
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T ](\d{1,2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h, mi, se = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
    else:
        m = re.search(r"\b([A-Za-z]{3,9})\.? (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})\b", s) or re.search(r"\b(\d{1,2})(?:st|nd|rd|th)? ([A-Za-z]{3,9}),? (\d{4})\b", s)
        if not m:
            return ""
        a, b, y = m.group(1), m.group(2), int(m.group(3))
        mon, day = (a, b) if a[0].isalpha() else (b, a)
        mo = MONTHS.get(mon[:3].lower())
        if not mo:
            return ""
        d, h, mi, se = int(day), 0, 0, 0
    try:
        dt = datetime.datetime(y, mo, d, h, mi, se, tzinfo=datetime.timezone.utc)
    except ValueError:
        return ""
    if dt.year < 1990 or dt > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2):
        return ""
    return dt.isoformat().replace("+00:00", "Z")


def meta(h, *names):
    for n in names:
        m = re.search(r"<meta[^>]+(?:property|name|itemprop)=[\"']" + re.escape(n) + r"[\"'][^>]*content=[\"']([^\"']*)[\"']", h, re.I) or \
            re.search(r"<meta[^>]+content=[\"']([^\"']*)[\"'][^>]*(?:property|name|itemprop)=[\"']" + re.escape(n) + r"[\"']", h, re.I)
        if m and m.group(1).strip():
            return htmllib.unescape(m.group(1).strip())
    return ""


def field(text, labels, value=r"([^\n]{1,80})"):
    """'Version: 1.2', 'Version\\n1.2' or 'Version 1.2' style fields in a page's text."""
    for lab in labels:
        m = re.search(r"(?im)^\s*" + lab + r"(?![a-z])\s*:?\s*(?:\n\s*)?" + value, text)
        if m:
            return m.group(1).strip()
    return ""


def absolute(base, u):
    u = htmllib.unescape((u or "").strip())
    if not u or u.startswith(("data:", "javascript:", "#", "mailto:")):
        return ""
    return urllib.parse.urljoin(base, u)


def page_images(base, h, limit=8):
    out = []
    for m in re.finditer(r"<img\b[^>]*>", h, re.I):
        tag = m.group(0)
        src = (re.search(r"\b(?:data-src|data-url|src)=[\"']([^\"']+)[\"']", tag, re.I) or [None, ""])[1]
        big = (re.search(r"\bsrcset=[\"']([^\"']+)[\"']", tag, re.I) or [None, ""])[1]
        if big:
            src = big.split(",")[-1].strip().split(" ")[0] or src
        u = absolute(base, src)
        if not u or not re.match(r"^https?://", u):
            continue
        if PAGE_SHOT_SKIP.search(u) or not PAGE_SHOT_HINT.search(u):
            continue
        w = re.search(r"\bwidth=[\"']?(\d+)", tag, re.I)
        if w and int(w.group(1)) < 120:
            continue
        if u not in out:
            out.append(u)
        if len(out) >= limit:
            break
    return out


def page_cover(url, h, host):
    """The box art a patch page shows: GameBrew's infobox image or Romhack Plaza's main image."""
    if "gamebrew.org" in host:
        box = re.search(r"<table[^>]+class=[\"'][^\"']*infobox[\s\S]*?</table>", h, re.I)
        m = re.search(r"<img\b[^>]*\bsrc=[\"']([^\"']*/images/[^\"']+)[\"']", box.group(0) if box else h, re.I)
        if m and not re.search(r"logo|icon|button|banner", m.group(1), re.I):
            return absolute(url, re.sub(r"/thumb(/[0-9a-f]/[0-9a-f]{2}/[^/]+)/\d+px-[^/]+$", r"\1", m.group(1)))
    if "romhackplaza.org" in host:
        m = re.search(r"[\"'](https?://[^\"']*/storage/entries/main-images/[^\"']+)[\"']", h, re.I)
        if m:
            return m.group(1)
    return ""


def anchors(base, h):
    for m in re.finditer(r"<a\b[^>]*\bhref=[\"']([^\"']+)[\"'][^>]*>([\s\S]*?)</a>", h, re.I):
        yield absolute(base, m.group(1)), html_text(m.group(2)).strip()


def host_of(u):
    try:
        return urllib.parse.urlsplit(u).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def parse_page(url, h):
    """Reads a patch page. Returns title, ver, upd (ISO date), st (status text), dl / site links, shots and a (analysis)."""
    host = host_of(url)
    out = {}
    title = meta(h, "og:title", "twitter:title") or html_text((re.search(r"<title[^>]*>([\s\S]*?)</title>", h, re.I) or [None, ""])[1])
    if title:
        out["title"] = re.sub(r"\s+", " ", title)[:160]
    body = h
    if "gbatemp.net" in host:            # only the opening post of a forum thread is about the patch
        parts = re.split(r"<article[^>]+class=[\"'][^\"']*message\b", h, flags=re.I)
        body = parts[1] if len(parts) > 1 else h
    elif "gamebrew.org" in host:
        m = re.search(r"<div[^>]+id=[\"']mw-content-text[\"'][\s\S]*", h, re.I)
        body = m.group(0) if m else h
    text = html_text(body)
    # version
    ver = field(text, [r"Patch Version", r"Version", r"Latest Version", r"Current Version"], r"([vV]?\d[\w.\-]{0,20}(?: (?:beta|alpha|rc|final)\w*)?)")
    if not ver:
        m = re.search(r"\b(?:version|ver\.?|v)\s?(\d+(?:\.\d+){1,3}[a-z]?)\b", (out.get("title") or "") + " " + text[:4000], F)
        ver = m.group(1) if m else ""
    if ver:
        out["ver"] = ver
    # updated
    upd = parse_date(meta(h, "article:modified_time", "og:updated_time", "dateModified"))
    if not upd:
        upd = parse_date(field(text, [r"Last Updated", r"Last Modified", r"Updated", r"Last update"], r"([^\n]{4,40})"))
    if not upd and "gbatemp.net" in host:
        times = re.findall(r"<time[^>]+datetime=[\"']([^\"']+)[\"']", body, re.I)
        edited = re.search(r"Last edited[\s\S]{0,200}?<time[^>]+datetime=[\"']([^\"']+)[\"']", body, re.I)
        upd = parse_date(edited.group(1) if edited else (times[0] if times else ""))
    if not upd:
        upd = parse_date(field(text, [r"Release Date", r"Released", r"Date"], r"([^\n]{4,40})")) or parse_date(meta(h, "article:published_time", "datePublished"))
    if upd:
        out["upd"] = upd
    st = field(text, [r"Status"], r"([A-Za-z][A-Za-z ]{2,30})")
    if st:
        out["st"] = st
    # links called Download / Website / Source on the page
    for href, label in anchors(url, body):
        if not href or host_of(href) == host and "romhacking.net" not in host_of(href):
            continue
        l = label.lower()
        if "dl" not in out and re.fullmatch(r"(download( page| patch| here)?|patch|get it here)", l):
            out["dl"] = href
        elif "site" not in out and re.fullmatch(r"(website|official (web)?site|homepage|project (page|site)|source|github)", l):
            out["site"] = href
    shots = page_images(url, body)
    if shots:
        out["shots"] = shots
    cover = page_cover(url, h, host)
    if cover:
        out["cover"] = cover
    out["a"] = analyze_patch(text[:30000])
    return out


# ---------------------------------------------------------------- lists of new patches
ROMHACK_PLAZA_PLATFORMS = {
    "nintendo-entertainment-system": "NES", "family-computer-disk-system": "FDS", "super-nintendo": "SNES", "satellaview": "Satellaview", "game-boy": "Game Boy",
    "game-boy-color": "Game Boy Color", "game-boy-advance": "GBA", "nintendo-64": "N64", "nintendo-ds": "DS", "nintendo-3ds": "3DS", "gamecube": "GameCube",
    "nintendo-gamecube": "GameCube", "wii": "Wii", "nintendo-wii": "Wii", "wii-u": "Wii U", "nintendo-wii-u": "Wii U", "nintendo-switch": "Switch", "virtual-boy": "Virtual Boy",
    "playstation": "PS1", "playstation-2": "PS2", "playstation-3": "PS3", "playstation-4": "PS4", "playstation-portable": "PSP", "psp": "PSP", "playstation-vita": "PS Vita",
    "sega-saturn": "Saturn", "sega-dreamcast": "Dreamcast", "dreamcast": "Dreamcast", "sega-genesis": "Mega Drive", "mega-drive": "Mega Drive", "sega-mega-drive": "Mega Drive",
    "sega-cd": "Mega CD", "sega-master-system": "Master System", "sega-game-gear": "Game Gear", "game-gear": "Game Gear", "sega-32x": "32X",
    "turbografx-16": "PC Engine", "pc-engine": "PC Engine", "turbografx-cd": "PC Engine CD", "pc-engine-cd": "PC Engine CD", "pc-fx": "PC-FX",
    "wonderswan": "WonderSwan", "wonderswan-color": "WonderSwan Color", "neo-geo-pocket-color": "Neo Geo Pocket Color", "neo-geo-pocket": "Neo Geo Pocket Color",
}


def romhack_plaza_entries(base, h):
    """New entries on Romhack Plaza's translation list that are English and for a console Patch Watch covers."""
    out, seen = [], set()
    for href, label in anchors(base, h):
        m = re.match(r"^https?://(?:www\.)?romhackplaza\.org/translations/([a-z0-9-]+)/?$", href or "", re.I)
        if not m or href in seen:
            continue
        slug = m.group(1)
        if "-english" not in slug:
            continue
        lang_plat = re.search(r"-((?:[a-z]+-)*?english(?:-[a-z]+)*?)-translation-([a-z0-9-]+)$", slug)
        if not lang_plat:
            continue
        plat = ROMHACK_PLAZA_PLATFORMS.get(lang_plat.group(2))
        if not plat:
            continue                  # PC-98, MSX, Java ME and other systems are outside Patch Watch's scope
        seen.add(href)
        title = label.strip() if label and len(label.strip()) > 1 else ""
        if not title:
            title = slug[:lang_plat.start()].replace("-", " ").title()
        title = re.sub(r"\s*\((?:[A-Za-z, ]+ )?Translation\)\s*$", "", title).strip()
        out.append({"url": href.rstrip("/"), "title": title, "platform": plat, "src": "Romhack Plaza",
                    "label": "Undub" if re.search(r"\bundub", title, re.I) else "Human translation"})
    return out


def gamebrew_entries(base, h, platform):
    """Rows of a GameBrew 'List of ... rom hacks' page that are English translations or undubs."""
    out, seen = [], set()
    for sec in re.split(r"<h2\b", h, flags=re.I)[1:]:
        head = html_text(sec[:400]).lower()
        is_tl = "translation" in head
        for row in re.findall(r"<tr\b[\s\S]*?</tr>", sec, re.I):
            a = re.search(r"<a\b[^>]*href=[\"'](/wiki/[^\"'#?]+)[\"'][^>]*>([\s\S]*?)</a>", row, re.I)
            if not a:
                continue
            name = html_text(a.group(2)).strip()
            if not name or re.match(r"^(file|category|template|special):", a.group(1)[6:], re.I):
                continue
            undub = bool(re.search(r"\bundub", name, re.I))
            if not (is_tl or undub):
                continue
            rowtext = html_text(row)
            if re.search(r"\b(spanish|portuguese|brazilian|french|german|italian|russian|chinese|korean|vietnamese|indonesian|polish|turkish|arabic|ukrainian|thai)\b", rowtext + " " + name, re.I) and not re.search(r"\benglish\b", rowtext + " " + name, re.I):
                continue
            url = urllib.parse.urljoin(base, a.group(1))
            if url in seen:
                continue
            seen.add(url)
            out.append({"url": url, "title": re.sub(r"\s*[-–]?\s*(English )?(Translation|Localization)( Patch| Project)?\s*$", "", name, flags=re.I).strip() or name,
                        "platform": platform, "src": "GameBrew", "label": "Undub" if undub else "Human translation", "desc": rowtext[:200]})
    return out


# ---------------------------------------------------------------- Internet Archive items
ROM_FILE = re.compile(r"\.(iso|bin|cue|chd|cso|zso|rvz|wbfs|wia|gcz|ciso|nsp|xci|nsz|3ds|cia|nds|gba|gbc|gb|sfc|smc|nes|fds|z64|n64|v64|pbp|vpk|gdi|cdi|mdf|mds|img|ecm|pkg)$", re.I)
PATCH_FILE = re.compile(r"\.(xdelta3?|vcdiff|ppf|ips|bps|ups|aps|patch|diff)$|patch|undub|translat", re.I)
IA_SKIP = re.compile(r"(_meta\.xml|_files\.xml|_meta\.sqlite|_reviews\.xml|__ia_thumb\.jpg|_archive\.torrent|_thumb\.jpg|_itemimage\.\w+)$", re.I)


def archive_id(url):
    m = re.match(r"^https?://(?:www\.)?archive\.org/details/([^/?#]+)", url or "", re.I)
    return m.group(1) if m else ""


def parse_archive_item(ident, j):
    """Reads an item from archive.org/metadata/<id>: title, last change, version, platform guess, screenshots, and whether it
    holds game files (ROMs or disc images) rather than just a patch."""
    md = j.get("metadata") or {}
    files = [f for f in (j.get("files") or []) if f.get("name") and not IA_SKIP.search(f["name"]) and f.get("source") != "metadata"]
    as_text = lambda v: " ".join(v) if isinstance(v, list) else str(v or "")
    title, desc = as_text(md.get("title")), html_text(as_text(md.get("description")))
    out = {"title": title[:160]}
    times = [int(f["mtime"]) for f in files if str(f.get("mtime", "")).isdigit()]
    if times:
        out["upd"] = datetime.datetime.fromtimestamp(max(times), datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    else:
        out["upd"] = parse_date(as_text(md.get("publicdate")))
    m = re.search(r"\bv(?:er(?:sion)?)?\.? ?(\d+(?:\.\d+){0,3}[a-z]?)\b", title + " " + " ".join(f["name"] for f in files), F)
    if m:
        out["ver"] = m.group(1)
    plat = detect_platform(" ".join([title, as_text(md.get("subject")), desc[:2000]]))
    if plat:
        out["plat"] = plat
    shots = ["https://archive.org/download/%s/%s" % (ident, urllib.parse.quote(f["name"])) for f in files
             if re.search(r"\.(png|jpe?g|gif|webp)$", f["name"], re.I) and not re.search(r"cover|box|logo|icon", f["name"], re.I)]
    if shots:
        out["shots"] = shots[:8]
    out["rom"] = any(ROM_FILE.search(f["name"]) for f in files)
    out["patch"] = any(PATCH_FILE.search(f["name"]) for f in files) or bool(re.search(r"\bpatch|undub|translat", title, re.I))
    out["a"] = analyze_patch(title + "\n" + desc[:20000])
    return out


# ---------------------------------------------------------------- CDRomance (discovery only)
# CDRomance's translation and undub sections are read only to learn about new patches. Patch Watch never links to,
# stores or shows a CDRomance page: each post's credited "Source:" link is followed and only that original page is listed.
ROM_SITE = re.compile(r"romsfun|cdromance|ziperto|romspedia|vimm|coolrom|emuparadise|nsw2u|nswgame|wowroms|romsgames|consoleroms|romhustler|edgeemu|freeroms|romsmania|retrostic|romulation|retrogametalk|nxbrew|hexrom|downloadroms|romspure", re.I)
NOT_SOURCE = re.compile(r"facebook\.com|twitter\.com|x\.com/intent|reddit\.com/submit|pinterest|tumblr\.com/share|whatsapp|t\.me/share|mailto:|/community/\d|/members?/|/profile/|/users?/\d|discord\.(gg|com/invite)|patreon|ko-?fi|paypal|youtube\.com|youtu\.be|wikipedia\.org|mobygames|gamefaqs|redump|no-intro|datomatic|imgur|amazon\.|ebay\.|keeplinks|ouo\.io|adf\.ly|shrink|linkvertise|mediafire|mega\.nz|drive\.google|dropbox|1fichier|pixeldrain|gofile|zippyshare|rapidgator|uptobox|krakenfiles|/download/|\.(zip|7z|rar|iso|chd|xdelta|ppf|ips|bps)(\?|$)", re.I)
CDR_CATEGORIES = {
    "psx-iso": "PS1", "psx2psp-eboots": "PS1", "ps2-iso": "PS2", "psp": "PSP", "ps-vita": "PS Vita", "psvita": "PS Vita", "ps3-iso": "PS3",
    "nes-roms": "NES", "famicom-disk-system": "FDS", "snes-rom": "SNES", "n64-roms": "N64", "gamecube": "GameCube", "wii-iso": "Wii", "wii": "Wii",
    "gameboy-roms": "Game Boy", "gameboy-color-roms": "Game Boy Color", "gba-roms": "GBA", "nds-roms": "DS", "nds": "DS", "3ds-roms": "3DS", "3ds": "3DS",
    "switch": "Switch", "virtual-boy": "Virtual Boy", "sega_saturn_isos": "Saturn", "dreamcast": "Dreamcast", "sega-cd": "Mega CD", "segacd": "Mega CD",
    "sega-genesis-roms": "Mega Drive", "genesis": "Mega Drive", "master-system": "Master System", "game-gear": "Game Gear",
    "turbografx-cd": "PC Engine CD", "pce-cd": "PC Engine CD", "turbografx-16": "PC Engine", "pc-engine": "PC Engine", "pc-fx": "PC-FX",
    "wonderswan": "WonderSwan", "wonderswan-color": "WonderSwan Color", "neo-geo-pocket": "Neo Geo Pocket Color"}
CDR_NOT_CONSOLE = re.compile(r"^(pc|pc-?games?|pc-?isos?|pc-?98|msx\d?|msx-?roms?|x68000|sharp-x68000|fm-towns|dos|windows|mac|arcade|mame)$", re.I)   # whole category names: "pc-engine" is a console
CDR_POST = re.compile(r"https?://(?:www\.)?cdromance\.(?:org|com)/([a-z0-9_-]+)/([a-z0-9_.%-]+)/?(?=[\"'#?])", re.I)
CDR_NOT_POST = {"translations", "page", "tag", "category", "author", "genre", "wp-content", "wp-json", "feed", "search", "forum", "forums", "members", "request", "requests", "about", "contact", "dmca"}


def cdromance_posts(h):
    """Game posts linked from a CDRomance listing page, in page order: (category, slug, post URL)."""
    out, seen = [], set()
    for m in CDR_POST.finditer(h or ""):
        cat, slug = m.group(1).lower(), m.group(2).lower()
        if cat in CDR_NOT_POST or slug in ("page", "feed") or (cat, slug) in seen:
            continue
        seen.add((cat, slug))
        out.append((cat, slug, m.group(0).rstrip("/") + "/"))
    return out


def _section(h, label):
    """The HTML between a heading or bold label such as "Source:" and the next heading."""
    m = re.search(r"<(h[1-6]|strong|b|dt|th)(?=[\s>])[^>]*>\s*(?:<[^>]+>\s*)*" + label + r"\s*:?\s*(?:</[^>]+>\s*)*", h, re.I)
    if not m:
        return ""
    rest = h[m.end():]
    end = re.search(r"<h[1-6]\b|<(strong|b|dt|th)\b[^>]*>\s*[A-Z][\w ]{2,30}:\s*<", rest, re.I)
    return rest[:end.start() if end else 4000]


IMG_LINK = re.compile(r"\.(png|jpe?g|gif|webp|bmp)(\?|$)|/wp-content/uploads/", re.I)
PATCH_PAGE = re.compile(r"romhacking\.net/(translations|hacks|homebrew|utilities)/\d+|romhackplaza\.org/|github\.com/[^/]+/[^/#?]+|gitlab\.com/[^/]+/|"
                        r"gbatemp\.net/threads/|archive\.org/details/|\.itch\.io/|gamebrew\.org/wiki/|segaxtreme\.net/resources/|"
                        r"viewtopic\.php|/threads?/|/forums?/[^/]+/\d|translat|undub|patch|/projects?/|neocities|wordpress\.com|blogspot\.|tumblr\.com/post", re.I)


CDR_TITLE_JUNK = re.compile(r"\s*\((?:[^()]*\b(?:english|patched|translat|undub|japan|usa|europe|hack|mtl|j\+e)\b[^()]*)\)|\s*\[[^\]]*\]|\s+(?:PSX2PSP|English Patched|English Patch|Undub(?:bed)?|ISO|ROM|Eboot|Download)\b.*$", re.I)


def clean_cdr_title(t):
    t = CDR_TITLE_JUNK.sub("", t or "")
    t = re.sub(r"\s+-\s+[\w ]+ Version\b.*$", "", t, flags=re.I)
    t = re.sub(r"(\s+(PS1|PSX|PS2|PSP|Sega|Saturn|Genesis|Mega Drive|Mega CD|Sega CD|SNES|SFC|NES|Famicom Disk System|Famicom|FDS|GBA|GBC|NDS|3DS|N64|GameCube|GCN|"
               r"WiiWare WAD|WiiWare|WAD|Wii|PCE|PC Engine CD|PC Engine|PC-FX|TurboGrafx-16|TurboGrafx-CD|TurboGrafx|TG-?16|Dreamcast|DC|Game Gear|GG|Master System|SMS|"
               r"WonderSwan Color|WonderSwan|WSC|Neo Geo Pocket Color|Neo Geo Pocket|NGPC|NGP|Virtual Boy|Satellaview))+\s*$", "", t, flags=re.I)
    return re.sub(r"\s{2,}", " ", t).strip(" -–:") or (t or "").strip()


def norm_source(u):
    """GitHub release or tree links become the repository itself, so it matches what Patch Watch already tracks."""
    m = re.match(r"^(https?://(?:www\.)?github\.com/[^/]+/[^/#?]+)", u or "", re.I)
    return re.sub(r"\.git$", "", m.group(1)) if m else u


def title_overlap(u, title):
    words = {w for w in re.findall(r"[a-z0-9]{3,}", (title or "").lower()) if w not in ("the", "and", "english", "patched", "patch", "translation", "japan")}
    path = urllib.parse.unquote((u or "").lower())
    return sum(1 for w in words if w in path)


def _rank(links, title):
    """Links that share words with the game's title come first (a post can link several projects)."""
    words = {w for w in re.findall(r"[a-z0-9]{3,}", (title or "").lower()) if w not in ("the", "and", "english", "patched", "patch", "translation", "japan")}
    def score(u):
        path = urllib.parse.unquote(u.lower())
        return -sum(1 for w in words if w in path)
    return sorted(links, key=score)


def _post_body(h):
    """The post itself: from the title to the download section, without menus, sidebars and related posts."""
    low = h.lower()
    a = low.find("<h1")
    a = a if a >= 0 else 0
    # the download section starts with a heading such as "Download: Giftpia (English Patched) ISO"; the info table's
    # "Downloads" row must not end the post early
    dl = re.compile(r"<h[1-6]\b[^>]*>(?:\s*<[^>]+>)*\s*download", re.I).search(h, a)
    ends = [i for i in (low.find("related games", a), dl.start() if dl else -1, low.find('id="comments"', a),
                        low.find("<aside", a), low.find("<footer", a)) if i > a]
    return h[a:min(ends)] if ends else h[a:]


def _source_html(body):
    """HTML after a "Source:" / "Sources:" / "Original source:" label (heading, bold or plain line) up to the next heading or label."""
    m = re.search(r">\s*(?:Original\s+)?Sources?\s*:?\s*<|(?:^|>|\n)\s*(?:Original\s+)?Sources?\s*:", body, re.I)
    if not m:
        return ""
    rest = body[m.end():]
    end = re.search(r"<h[1-6]\b|<(strong|b)\b[^>]*>\s*[A-Z][\w ]{2,30}:?\s*</(strong|b)>|\n\s*[A-Z][\w ]{2,30}:\s", rest)
    return rest[:end.start() if end else 3000]


def parse_cdromance_post(url, h, category=""):
    """Reads one CDRomance game post. Returns the credited original source(s), authors, title, platform and label, or
    {"skip": reason}. The post's own URL is never returned."""
    h = h or ""
    title = meta(h, "og:title") or ""
    if not title:
        m = re.search(r"<h1\b[^>]*>([\s\S]*?)</h1>", h, re.I)
        title = html_text(m.group(1)) if m else ""
    title = re.sub(r"\s*[-–|]\s*CDRomance\s*$", "", htmllib.unescape(title), flags=re.I)
    title = re.sub(r"\s+(ISO|ROM|Eboot|CHD|NSP|Game)\s*$", "", title, flags=re.I)
    title = re.sub(r"\s+(PSX|PS1|PS2|PSP|GBA|GBC|GB|NES|SNES|N64|NDS|3DS|Wii|GCN|GameCube|Saturn|Dreamcast|PCE|TG-?16|TurboGrafx-CD|Sega CD|Genesis|PSV|Vita|Switch)\s*$", "", title, flags=re.I)
    text = html_text(h)
    lang = field(text, ["Languages", "Language"], r"([^\n]{1,160})") or ""
    # the game information table links each language to a filter such as ?ep_filter_language=english-patched
    tags = " ".join(m.group(1).replace("-", " ") for m in re.finditer(r"ep_filter_language=([a-z0-9-]+)", h[:h.lower().find("related games")] if "related games" in h.lower() else h, re.I))
    probe = (lang + " " + tags).strip() or title
    undub = bool(re.search(r"\bundub", probe, re.I))
    english = bool(re.search(r"english", probe, re.I))
    if not undub and not english:
        return {"skip": "not English"}
    # The credit is written several ways: a "Source(s):" heading or line, an info box whose "Version" links to the patch
    # page, or a link in the description. Links under a "Source" label win, then links that look like patch pages.
    body = _post_body(h)
    links = []
    def keep(u):
        return u.startswith("http") and not ROM_SITE.search(u) and not NOT_SOURCE.search(u) and not IMG_LINK.search(u) and u not in links
    for u, _t in anchors(url, _source_html(body)):
        if keep(u):
            links.append(u)
    for u in re.findall(r"https?://[^\s<>\"']+", html_text(_source_html(body))):
        u = u.rstrip(").,;")
        if keep(u):
            links.append(u)
    if not links:
        others = [u for u, _t in anchors(url, body)] + [u.rstrip(").,;") for u in re.findall(r"https?://[^\s<>\"']+", html_text(body))]
        links = [u for u in dict.fromkeys(others) if keep(u) and PATCH_PAGE.search(u)]
    links = list(dict.fromkeys(norm_source(u) for u in _rank(links, title)))
    if not links:
        return {"skip": "no credited source"}
    src = links[0]
    if re.search(r"romhacking\.net/hacks/", src, re.I) and not undub:
        return {"skip": "gameplay hack"}
    a = field(html_text(body), ["Patch authors?", "Authors?", "Translated by", "Patch by"], r"([^\n]{2,80})")
    auth = [t.strip() for t in re.split(r",|&| and ", a) if t.strip()]
    mtl = bool(re.search(r"machine translation|\bmtl\b", probe + " " + title, re.I))
    label = "Machine translation" if mtl else ("Human translation" if english and re.search(r"english patched|english translat|english \(", probe, re.I) else ("Undub" if undub else "Human translation"))
    console = field(text, ["Console", "Platform", "System"], r"([^\n]{2,40})")
    plat = CDR_CATEGORIES.get(category) or detect_platform(console) or detect_platform(category.replace("-", " ").replace("_", " ") + " " + title)
    # the game information table names the game ("Game Name") and its Japanese title ("Original Title")
    name = field(text, ["Game Name", "Name"], r"([^\n]{2,120})")
    jp = field(text, ["Original Title", "Japanese Title"], r"([^\n]{1,120})")
    jp = jp if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", jp or "") else ""
    return {"src": src, "more": links[1:4], "title": clean_cdr_title(title), "name": clean_cdr_title(name) if name else "", "jp": jp,
            "authors": auth[:6], "platform": plat, "label": label, "undub": undub,
            "notConsole": bool(CDR_NOT_CONSOLE.search(category))}
