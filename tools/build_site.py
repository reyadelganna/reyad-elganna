"""Prepare the website's data and images from the catalog.

Usage: python tools/build_site.py
Writes site/data.json and site/p/<post id>.webp (resized posters).
"""
import json, sys
from collections import Counter, OrderedDict
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from rules import CATEGORIES  # noqa: E402

SITE = ROOT / "site"
CATS = CATEGORIES + ["متفرقات"]
POSTER_W = 520


def build_standalone():
    """docs/ = a complete static copy of the site (for GitHub Pages or any host)."""
    import shutil
    docs = ROOT / "docs"
    if docs.exists():
        shutil.rmtree(docs)
    shutil.copytree(SITE, docs)
    body = (SITE / "index.html").read_text(encoding="utf8")
    (docs / "index.html").write_text(
        '<!doctype html>\n<html lang="ar" dir="rtl">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<style>html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);'
        'padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}'
        '[hidden]{display:none!important}</style>\n</head>\n<body>\n' + body + "\n</body>\n</html>\n",
        encoding="utf8")
    (docs / ".nojekyll").write_text("", encoding="utf8")


def main():
    items = json.load(open(ROOT / "data/catalog.json", encoding="utf8"))
    posters = json.load(open(ROOT / "data/posters.json", encoding="utf8"))
    (SITE / "p").mkdir(parents=True, exist_ok=True)

    # Resize every poster once (first image of each post).
    for p in posters:
        out = SITE / "p" / f"{p['id']}.webp"
        if not out.exists():
            im = Image.open(ROOT / p["files"][0]).convert("RGB")
            if im.width > POSTER_W:
                im = im.resize((POSTER_W, round(im.height * POSTER_W / im.width)), Image.LANCZOS)
            im.save(out, "WEBP", quality=72, method=6)

    sizes = Counter((i["category"], i["series"]) for i in items)
    series_keys = sorted(sizes, key=lambda k: (CATS.index(k[0]), -sizes[k], k[1]))
    sidx = {k: n for n, k in enumerate(series_keys)}

    by_lecture, covers = {}, {}
    for p in posters:
        if p["kind"] == "lecture":
            for t in p["targets"]:
                by_lecture.setdefault(t, p["id"])
        if p["kind"] in ("lecture", "series") and p["series"]:
            key = next((k for k in series_keys if k[1] == p["series"]), None)
            if key is not None:
                covers.setdefault(sidx[key], {}).setdefault(p["sub"] or "", p["id"])

    series = []
    for n, (cat, name) in enumerate(series_keys):
        subs = list(OrderedDict.fromkeys(i["sub"] for i in sorted(items, key=lambda i: i["id"])
                                         if i["series"] == name and i["category"] == cat and i["sub"]))
        c = covers.get(n, {})
        series.append({"n": name, "c": CATS.index(cat), "k": sizes[(cat, name)], "b": subs,
                       "cv": c.get("") or next(iter(c.values()), None), "bc": {s: c[s] for s in subs if s in c}})

    out_items = []
    for i in sorted(items, key=lambda i: i["id"]):
        r = {"i": i["id"], "s": sidx[(i["category"], i["series"])], "t": i["title"], "d": i["date"]}
        if i["sub"]:
            r["b"] = i["sub"]
        if i["ep"] and i["ep"] < 1000:
            r["e"] = i["ep"]
        if i["topics"]:
            r["p"] = i["topics"]
        if i["type"] != "audio":
            r["y"] = i["type"]
        if i["id"] in by_lecture:
            r["g"] = by_lecture[i["id"]]
        out_items.append(r)

    out_posters = [{"i": p["id"], "k": p["kind"], "t": p.get("title", ""), "d": p["date"],
                    "tg": p["targets"][:20], "s": sidx.get(next((k for k in series_keys if k[1] == p["series"]), None)),
                    "b": p["sub"]} for p in sorted(posters, key=lambda p: -p["id"])]

    author = json.load(open(ROOT / "data/author.json", encoding="utf8"))
    author.pop("_note", None)
    data = {"channel": "reyad_elganna", "built": max(i["date"] for i in items),
            "cats": CATS, "series": series, "items": out_items, "posters": out_posters, "author": author}
    (SITE / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    build_standalone()
    kb = (SITE / "data.json").stat().st_size // 1024
    img = sum(f.stat().st_size for f in (SITE / "p").glob("*.webp")) // 1024
    print(f"series {len(series)} | items {len(out_items)} | posters {len(out_posters)} | data {kb}KB | images {img}KB")


if __name__ == "__main__":
    main()
