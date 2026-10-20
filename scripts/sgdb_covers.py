#!/usr/bin/env python3
"""Fetch SteamGridDB cover art for Patch Watch.

Usage:
  python3 sgdb_covers.py patch-watch-needs-covers.json --key YOUR_SGDB_KEY
  (or set SGDB_API_KEY instead of passing --key)

Reads the file Patch Watch exports ("Export games needing covers" in Settings),
looks each game up on SteamGridDB and writes patch-watch-covers.json, which you
import back with "Import covers". Uses only the Python standard library.
"""
import argparse, difflib, json, os, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("SGDB_BASE", "https://www.steamgriddb.com/api/v2")
DIMENSIONS = "600x900,342x482,660x930"


def norm(t):
    t = "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c)).lower()
    t = t.replace("&", " and ")
    t = re.sub(r"[’'`]", "", t)
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return re.sub(r"^the ", "", t)


def numbers(t):
    roman = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
    return sorted(roman.get(w, w) for w in t.split() if w.isdigit() or w in roman)


def get(path, key, tries=4):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + key, "User-Agent": "patch-watch-covers/1.0"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                sys.exit("SteamGridDB rejected the API key (401). Check the key in your SteamGridDB preferences.")
            if e.code == 404:
                return None
            if e.code == 429 and attempt < tries - 1:
                time.sleep(int(e.headers.get("Retry-After", "5")))
                continue
            raise
        except urllib.error.URLError:
            if attempt < tries - 1:
                time.sleep(2)
                continue
            raise
    return None


def best_match(title, results):
    q = norm(title)
    best = None
    for g in results or []:
        n = norm(g.get("name", ""))
        score = 1.0 if n == q else difflib.SequenceMatcher(None, q, n).ratio()
        if numbers(q) != numbers(n):
            score -= 0.3
        if best is None or score > best[0]:
            best = (score, g)
    return best


def main():
    ap = argparse.ArgumentParser(description="Fetch SteamGridDB covers for Patch Watch")
    ap.add_argument("input", help="patch-watch-needs-covers.json exported from Patch Watch")
    ap.add_argument("--key", default=os.environ.get("SGDB_API_KEY"), help="SteamGridDB API key (or set SGDB_API_KEY)")
    ap.add_argument("--out", default="patch-watch-covers.json")
    ap.add_argument("--min-match", type=float, default=0.85, help="minimum title similarity to accept (0-1)")
    ap.add_argument("--delay", type=float, default=0.25, help="seconds between requests")
    a = ap.parse_args()
    if not a.key:
        sys.exit("Give your SteamGridDB API key with --key or the SGDB_API_KEY variable.")
    data = json.load(open(a.input, encoding="utf-8"))
    if data.get("format") != "patch-watch-cover-request":
        sys.exit("That file isn't a Patch Watch export. Use 'Export games needing covers' in Patch Watch's Settings.")
    games = data.get("games", [])
    covers, unsure, missed = {}, [], []
    for i, g in enumerate(games, 1):
        title = g["title"]
        print(f"[{i}/{len(games)}] {title} ({g.get('platform', '')})", end=" ... ", flush=True)
        m = None
        for t in [title, g.get("jp") or ""]:      # Japanese-only games are often listed under their Japanese title
            if not t:
                continue
            res = get("/search/autocomplete/" + urllib.parse.quote(t, safe=""), a.key)
            time.sleep(a.delay)
            m = best_match(t, (res or {}).get("data"))
            if m and m[0] >= a.min_match:
                break
        if not m or m[0] < a.min_match:
            print("no confident match")
            missed.append(title)
            continue
        score, hit = m
        grids = get(f"/grids/game/{hit['id']}?dimensions={DIMENSIONS}&types=static&nsfw=false&humor=false&epilepsy=false", a.key)
        time.sleep(a.delay)
        imgs = (grids or {}).get("data") or []
        if not imgs:
            print(f"matched '{hit['name']}' but it has no portrait covers")
            missed.append(title)
            continue
        covers[g["key"]] = {"url": imgs[0]["url"], "name": hit["name"], "match": round(score, 3)}
        if score < 1.0:
            unsure.append(f"{title}  ->  {hit['name']} ({score:.2f})")
        print(f"ok ({hit['name']})")
    json.dump({"format": "patch-watch-covers", "version": 1, "covers": covers}, open(a.out, "w", encoding="utf-8"), indent=1)
    print(f"\nWrote {len(covers)} covers to {a.out}. Import it in Patch Watch: Settings > Import covers.")
    if unsure:
        print("\nAccepted with an inexact title match, worth a glance:\n  " + "\n  ".join(unsure))
    if missed:
        print("\nNo cover found for:\n  " + "\n  ".join(missed))


if __name__ == "__main__":
    main()
