"""Scrape the posts of a public Telegram channel via the t.me/s/ web preview.

Usage: python tools/scrape.py <channel> <out.json> [--full]
By default only posts newer than those already in <out.json> are fetched;
--full re-reads the whole channel (picks up edits and deletions).
New poster images are saved to data/posters/<post id>_<n>.jpg.
"""
import json, os, re, sys, time, urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

CH = sys.argv[1]
OUT = sys.argv[2]
FULL = "--full" in sys.argv
UA = {"User-Agent": "Mozilla/5.0"}
POSTERS = Path(__file__).resolve().parent.parent / "data/posters"


def fetch(before=None):
    url = f"https://t.me/s/{CH}" + (f"?before={before}" if before else "")
    for i in range(5):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=30).read().decode("utf8")
        except Exception as e:
            print("retry", url, e, file=sys.stderr)
            time.sleep(3 * (i + 1))
    raise RuntimeError(url)


def txt(el, sel):
    x = el.select_one(sel)
    return x.get_text(" ", strip=True) if x else ""


def parse(html):
    s = BeautifulSoup(html, "html.parser")
    posts = []
    for m in s.select(".tgme_widget_message[data-post]"):
        pid = int(m["data-post"].split("/")[1])
        t = m.select_one(".tgme_widget_message_text")
        text = t.get_text("\n").strip() if t else ""
        links = [a["href"] for a in (t.select("a[href]") if t else [])]
        docs = []
        for d in m.select(".tgme_widget_message_document"):
            icon = d.select_one(".tgme_widget_message_document_icon")
            docs.append({
                "title": txt(d, ".tgme_widget_message_document_title"),
                "extra": txt(d, ".tgme_widget_message_document_extra"),
                "audio": bool(icon and "audio" in icon.get("class", [])),
            })
        tm = m.select_one(".tgme_widget_message_date time")
        reply = m.select_one("a.tgme_widget_message_reply")
        reply_id = None
        if reply and reply.get("href"):
            mm = re.search(r"/(\d+)$", reply["href"])
            reply_id = int(mm.group(1)) if mm else None
        posts.append({
            "id": pid,
            "url": f"https://t.me/{CH}/{pid}",
            "date": tm["datetime"] if tm else None,
            "text": text,
            "links": links,
            "docs": docs,
            "voice": len(m.select(".tgme_widget_message_voice_player")),
            "photos": [
                mm.group(1)
                for pw in m.select(".tgme_widget_message_photo_wrap")
                if (mm := re.search(r"url\('([^']+)'\)", pw.get("style", "")))
            ],
            "videos": len(m.select(".tgme_widget_message_video_player, .tgme_widget_message_roundvideo_player")),
            "views": txt(m, ".tgme_widget_message_views"),
            "reply_to": reply_id,
            "forwarded_from": txt(m, ".tgme_widget_message_forwarded_from_name"),
        })
    return posts


old = {}
if os.path.exists(OUT) and not FULL:
    old = {p["id"]: p for p in json.load(open(OUT, encoding="utf8"))}
known_max = max(old, default=0)

fetched = {}
before = None
while True:
    ps = parse(fetch(before))
    new = [p for p in ps if p["id"] not in fetched]
    for p in ps:
        fetched[p["id"]] = p
    if not ps or not new:
        break
    before = min(p["id"] for p in ps)
    print(f"got {len(ps)} (min {before}) total {len(fetched)}", file=sys.stderr)
    if before <= 1 or before <= known_max:
        break
    time.sleep(0.7)

all_posts = {**old, **fetched}
data = sorted(all_posts.values(), key=lambda p: p["id"])
json.dump(data, open(OUT, "w", encoding="utf8"), ensure_ascii=False, indent=1)
added = len([i for i in fetched if i not in old]) if old else len(fetched)
print("saved", len(data), "posts,", added, "new", file=sys.stderr)

# Poster images: the CDN links are only fresh right after scraping, so fetch now.
POSTERS.mkdir(parents=True, exist_ok=True)
for p in fetched.values():
    for k, url in enumerate(p["photos"]):
        f = POSTERS / f"{p['id']}_{k}.jpg"
        if f.exists():
            continue
        try:
            req = urllib.request.Request(url, headers=UA)
            f.write_bytes(urllib.request.urlopen(req, timeout=30).read())
            print("poster", f.name, file=sys.stderr)
        except Exception as e:
            print("poster failed", p["id"], e, file=sys.stderr)
