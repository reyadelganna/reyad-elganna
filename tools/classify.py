"""Turn the raw channel posts (data/posts.json) into a classified catalog.

Usage: python tools/classify.py
Writes data/catalog.json and prints a short report (details in work/).
"""
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from rules import RULES, CATEGORIES, BOOK_ALIASES, OVERRIDES, remap  # noqa: E402

CH = "reyad_elganna"
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
INVISIBLE = re.compile(r"[​-‏‪-‮⁦-⁩﻿]")
EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")
# Telegram's automatic captions for forwarded media carry no information.
GENERIC = re.compile(r"(مقطع صوتي|فيديو|مستند|صورة)( من .*)?|Noor-Book\.com|تحميل المتن")
MISC = "متفرقات"


def clean(text):
    return INVISIBLE.sub("", text).translate(AR_DIGITS).replace("*", "")


def lines_of(text):
    out = []
    for raw in clean(text).split("\n"):
        l = EMOJI.sub("", raw).strip(" \t-–_:•|/")
        if not l or re.fullmatch(r"[\W_]+", l) or re.fullmatch(r"https?://\S+", l):
            continue
        out.append(l)
    return out


def real_lines(text):
    return [l for l in lines_of(text)
            if not re.fullmatch(r"(#[\w]+\s*)+", l) and not GENERIC.fullmatch(l)]


BULLETIN = "نشرة أخبار قناة رياض الجنة"


def media_type(p):
    if BULLETIN in p["text"]:
        return "text"
    if p["videos"] or any(d["title"].lower().endswith(".mp4") for d in p["docs"]):
        return "video"
    if any(".pdf" in d["title"].lower() or d["title"].startswith("Noor_Book") for d in p["docs"]):
        return "pdf"
    if p["voice"] or p["docs"]:
        return "audio"
    return None


def norm_book(name, series):
    name = re.sub(r"\s+", " ", name).strip(" -–:.,،")
    name = re.sub(r"^(شرح\s+)?كتاب\s+", "", name)
    name = re.sub(r"\s*(من السلسلة الصحيحة.*|للشيخ الألباني.*|من صحيح.*|من الفقه الميسر.*)$", "", name)
    name = re.sub(r"ه(\s|$)", r"ة\1", name).strip(" .")
    for pat, canon in BOOK_ALIASES.get(series, []) + BOOK_ALIASES["*"]:
        if re.search(pat, name):
            return canon
    return name or None


def extract_book(text, series):
    text = text.replace("_", " ")
    m = re.search(r"كتاب\s+([^\-–\d\n/]+?)(?:\s*[\-–:/.]|\s*\d|\n|$)", text)
    return norm_book(m.group(1), series) if m else None


def extract_ep(text):
    head = "\n".join(clean(text).replace("_", " ").split("\n")[:5])
    m = re.search(r"[\-–\s(]\s*(\d{1,4})\s*[)*.]?\s*(?:\n|$|:)", head) or re.search(r"(\d{1,4})", head)
    return int(m.group(1)) if m else None


GENERIC_WORDS = set("""شرح كتاب من في السلسلة السلسله الصحيحة الصحيحه للشيخ الشيخ الألباني الالباني رحمه الله
صحيح الإمام الامام مسلم البخاري أحاديث احاديث الأحكام الاحكام الدرس درس لقاء لقاءات الجمعة اليوم خطبة سلسلة تابع
للدكتور مع و عليه السلام""".split())


def words(s):
    return re.findall(r"[ء-ي]+", s)


def lesson_title(lines, series, sub, ep, date):
    """Most specific line of the post; lines made only of series words are skipped."""
    known = GENERIC_WORDS | set(words(series)) | set(words(sub or ""))
    for l in lines:
        l2 = l.lstrip("#").replace("_", " ").strip(" .-–")
        ws = words(l2)
        if len(ws) >= 1 and not all(w in known or w.lstrip("و") in known or w.lstrip("ال") in known for w in ws):
            return re.sub(r"\s+", " ", l2), l
    base = sub or series
    return (f"{base} - الدرس {ep}" if ep else f"{base} ({date})"), None


def classify(p):
    if p["id"] in OVERRIDES:
        return dict(OVERRIDES[p["id"]])
    text = clean(p["text"])
    flat = text.replace("_", " ")
    for r in RULES:
        if re.search(r["match"], flat) and not (r.get("unless") and re.search(r["unless"], flat)):
            res = {"category": r["category"], "series": r["series"]}
            sub = r.get("sub")
            if sub == "book":
                res["sub"] = extract_book(text, r["series"])
            elif callable(sub):
                res["sub"] = sub(flat)
            return res
    return {"category": MISC, "series": "مواد متنوعة"}


def topics_of(text):
    """Lines that follow ⛔️/♦️ markers are the lesson's topics."""
    out = []
    for block in re.split(r"[⛔♦🔸]️?", INVISIBLE.sub("", text))[1:]:
        for l in lines_of(block)[:1]:
            if not l.startswith("#") and not GENERIC.fullmatch(l):
                out.append(l.replace("_", " "))
    return out


def link_labels(posts):
    """Titles that index/poster posts give to the lessons they link to."""
    labels = {}
    for p in posts:
        prev, waiting = None, None
        for raw in clean(p["text"]).split("\n"):
            m = re.search(rf"t\.me/{CH}/(\d+)", raw)
            if m and int(m.group(1)) != p["id"]:
                if prev:
                    labels.setdefault(int(m.group(1)), prev)
                    prev = None
                else:
                    waiting = int(m.group(1))   # title comes on the next line
                continue
            l = EMOJI.sub("", raw).strip(" \t-–_:•|/")
            if l and not l.startswith("http") and not re.fullmatch(r"[\W_]+", l):
                l = l.lstrip("#").replace("_", " ")
                if waiting:
                    labels.setdefault(waiting, l)
                    waiting = None
                else:
                    prev = l
    return labels


def fallback_title(p, tags, mt):
    if tags:
        return max(tags, key=len).lstrip("#").replace("_", " ")
    for d in p["docs"]:
        name = re.sub(r"\.(pdf|mp4|m4a|ogg)$", "", d["title"], flags=re.I).replace("_", " ").strip()
        if name and not re.match(r"(Audio|DOC|VID|AUD|IMG)[\s\-]|^\d|^Audio$|^[\w\-]{1,8}$", name):
            return name
    return {"video": "مقطع فيديو", "pdf": "ملف PDF"}.get(mt, "مقطع صوتي")


def main():
    posts = json.load(open(ROOT / "data/posts.json", encoding="utf8"))
    labels = link_labels(posts)
    media = [p for p in posts if media_type(p)]
    by_id = {}

    def neighbour(idx):
        """Closest captioned media post of the same day (before first, then after)."""
        p = media[idx]
        for q in media[max(0, idx - 5):idx][::-1] + media[idx + 1:idx + 3]:
            if q["date"][:10] != p["date"][:10] or not real_lines(q["text"]):
                continue
            c = by_id.get(q["id"]) or classify(q)
            if c["category"] != MISC:
                return c
        return None

    items = []
    for idx, p in enumerate(media):
        ls = real_lines(p["text"])
        label = None if ls else labels.get(p["id"])
        if label and GENERIC.fullmatch(label):
            label = None
        c = classify({**p, "text": p["text"] + "\n" + (label or "")})
        if media_type(p) == "text":
            m = re.search(r"\(([^)]*\d{4})\)", clean(p["text"]))
            c = {"category": "الاقتصاد الإسلامي", "series": "النشرة الدورية للاقتصاد الإسلامي حول العالم",
                 "title": "النشرة الدورية: " + (m.group(1).strip() if m else p["date"][:10])}
        inherited = False
        if not ls and c["category"] == MISC and p["id"] not in OVERRIDES:
            nb = neighbour(idx)
            if nb:
                c = {k: nb.get(k) for k in ("category", "series", "sub")}
                inherited = True
        cat, series, sub = remap(c["series"], c.get("sub"), p["id"], p["text"] + "\n" + (label or ""))
        c = {**c, "category": cat, "series": series, "sub": sub}
        no_urls = re.sub(r"https?://\S+", "", p["text"] + "\n" + (label or ""))
        ep = extract_ep(no_urls) if (ls or label) else None
        used = None
        if c.get("title"):
            title = c["title"]
        elif series == "شرح الأسماء الحسنى" and c.get("sub"):
            title = f"اسم الله «{c['sub']}»"
        elif ls or label:
            title, used = lesson_title(ls or [label], series, c.get("sub"), ep, p["date"][:10])
        elif inherited:
            title = (c.get("sub") or series) + " (تابع)"
        else:
            title = fallback_title(p, re.findall(r"#[\w]+", clean(p["text"])), media_type(p))
        title = re.sub(r"\s+", " ", title).strip()
        topics = [t for t in topics_of(p["text"]) if t != used and t.strip(" .-–") != title]
        if not topics and used and used in ls:
            rest = ls[ls.index(used) + 1:ls.index(used) + 4]
            topics = [l.lstrip("#").replace("_", " ") for l in rest]
        item = {
            "id": p["id"],
            "url": p["url"],
            "date": (p["date"] or "")[:10],
            "type": media_type(p),
            "category": c["category"],
            "series": series,
            "sub": c.get("sub"),
            "ep": ep,
            "title": title,
            "topics": topics[:6],
            "tags": sorted(set(re.findall(r"#[\w]+", clean(p["text"])))),
            "inherited": inherited,
            "views": p["views"],
        }
        by_id[p["id"]] = item
        items.append(item)

    json.dump(items, open(ROOT / "data/catalog.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)

    cat_count = Counter(i["category"] for i in items)
    print("items", len(items))
    for c in CATEGORIES + [MISC]:
        print(f"  {cat_count.get(c, 0):5} {c}")
    ser = defaultdict(Counter)
    for i in items:
        ser[(i["category"], i["series"])][i["sub"] or ""] += 1
    (ROOT / "work").mkdir(exist_ok=True)
    with open(ROOT / "work/series_report.txt", "w", encoding="utf8") as f:
        for (c, s), subs in sorted(ser.items()):
            f.write(f"{c} | {s} | {sum(subs.values())}\n")
            for sb, n in subs.most_common():
                if sb:
                    f.write(f"      {n:4} {sb}\n")
    with open(ROOT / "work/misc.txt", "w", encoding="utf8") as f:
        for i in items:
            if i["category"] == MISC or i["title"] in ("مقطع صوتي", "مقطع فيديو", "ملف PDF"):
                f.write(f"{i['id']} {i['date']} {i['type']} | {i['category']} | {i['title'][:90]} | {' '.join(i['tags'])}\n")


if __name__ == "__main__":
    main()
