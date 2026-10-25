"""Link the channel's poster images to lectures and series.

Usage: python tools/posters.py
Reads data/posts.json + data/catalog.json, writes data/posters.json.

kinds:
  lecture - an announcement for specific lecture(s)
  series  - a cover for a whole series (or a book inside it)
  card    - a da'wah reminder card (e.g. Friday sunnahs)
  event   - seminar / news / certificate posts
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CH = "reyad_elganna"

SILSILA = "شرح السلسلة الصحيحة (كاملة)"
MUSLIM = "شرح صحيح الإمام مسلم (متجدد)"
SERIES = {
    (27, 71): (SILSILA, None),
    (286,): (SILSILA, "الصيام والقيام"),
    (1343,): (SILSILA, "الطب والعيادة والتداوي"),
    (288,): ("شرح طاقة ورد في فقه الورد", None),
    (324, 328, 332, 336, 1141, 2256, 2263, 2698): ("سلسلة شرح الأسماء الحسنى", None),
    (120, 159): ("لقاءات السيرة النبوية", "غزوة بني المصطلق (المريسيع)"),
    (2827, 2876, 2882): ("لقاءات السيرة النبوية", "غزوة تبوك"),
    (1120, 1754): ("رمضان والصيام", None),
    (1848,): ("الحج وعشر ذي الحجة", None),
    (2738,): ("سلسلة تأملات إيمانية في قصص الأنبياء", "مؤمن آل فرعون"),
    (2743,): ("شرح أحاديث الصيام (الجامع لأحكام الصيام)", None),
    (2766,): ("فقه العهود والمواثيق", "فقه العهود والموازنات من خلال السيرة النبوية"),
    (2770,): ("شرح مقدمة في الاقتصاد الإسلامي", None),
    (2777, 2849): ("دورة ما لا يسع المسلمة جهله", None),
    (2791, 2878, 2884): (MUSLIM, "الزكاة"),
    (2800,): (MUSLIM, "المساجد ومواضع الصلاة"),
    (2919, 2946): (MUSLIM, "الإيمان"),
    (3110, 3122): (MUSLIM, "الجنائز"),
    (2870,): ("سلسلة تأملات إيمانية في أدعية النبي ﷺ", None),
    (2845, 2847, 3011): ("شرح الفقه الميسر", "النكاح"),
    (2922,): ("شرح كتاب الحيوانات ما يجوز أكله وما لا يجوز", None),
    (3119, 3151, 3209, 3213): ("النشرة الدورية للاقتصاد الإسلامي حول العالم", None),
    (3033, 3041): ("شرح كتاب أربعون قاعدة في فقه معاملات الأسواق", None),
}
SERIES_OF = {pid: s for ids, s in SERIES.items() for pid in ids}

CARDS = {48, 51, 64, 66, 435, 695, 733, 765, 812, 864, 874, 919, 939, 954, 957, 971, 986, 997, 998,
         1012, 1018, 1041, 1042, 1047, 1196, 1254, 1269, 1290, 1299, 1300, 1311, 1312, 1322, 1331,
         1340, 1358, 1374, 1375, 1381, 1382, 1383, 1397, 1398, 1411, 1412, 1759, 1760, 2684, 2780,
         2782, 2783, 3069, 3139, 2772}
EVENTS = {1522, 2126, 2128, 2159, 2338, 2469, 2473, 2475, 2537, 2538, 2643, 2662, 2663, 2666, 2668,
          2670, 2674, 2675, 2683, 2685, 2773, 2871, 2873, 2875, 3113, 3121, 3130, 3131, 3163, 3165}
# Lecture announcements whose lecture is not the nearest following post.
LECTURE = {2720: [2723], 2727: [2726], 3033: [3040], 3041: [3040], 2710: [2470],
           2785: [2784], 3186: [3185], 3220: [3219], 2902: [2901]}

CARD_TITLES = {"الجمعة": "من سنن يوم الجمعة"}


def main():
    posts = json.load(open(ROOT / "data/posts.json", encoding="utf8"))
    cat = {i["id"]: i for i in json.load(open(ROOT / "data/catalog.json", encoding="utf8"))}
    ids = sorted(cat)
    out = []
    for p in posts:
        if not p["photos"]:
            continue
        files = [f"data/posters/{p['id']}_{k}.jpg" for k in range(len(p["photos"]))]
        linked = [int(x) for x in re.findall(rf"t\.me/{CH}/(\d+)", p["text"]) if int(x) in cat]
        rec = {"id": p["id"], "url": p["url"], "date": p["date"][:10], "files": files,
               "caption": p["text"].strip()[:400], "targets": [], "series": None, "sub": None}
        if p["id"] in LECTURE:
            rec.update(kind="lecture", targets=LECTURE[p["id"]])
        elif linked:
            rec.update(kind="lecture", targets=list(dict.fromkeys(linked)))
        elif p["id"] in SERIES_OF:
            s, sub = SERIES_OF[p["id"]]
            rec.update(kind="series", series=s, sub=sub)
        elif p["id"] in CARDS:
            rec.update(kind="card")
        elif p["id"] in EVENTS:
            rec.update(kind="event")
        else:
            nxt = [i for i in ids if p["id"] < i <= p["id"] + 3]
            prv = [i for i in ids if p["id"] - 3 <= i < p["id"]]
            tgt = nxt[:1] or prv[-1:]
            rec.update(kind="lecture" if tgt else "event", targets=tgt)
        if rec["kind"] == "lecture" and rec["targets"]:
            first = cat[rec["targets"][0]]
            rec["series"], rec["sub"] = first["series"], first["sub"]
            rec["title"] = first["title"] if len(rec["targets"]) == 1 else (first["sub"] or first["series"])
        elif rec["kind"] == "series":
            rec["title"] = rec["sub"] or rec["series"]
        else:
            lines = [l.strip(" *#‏‌") for l in p["text"].split("\n")]
            lines = [l for l in lines if len(l) > 3 and not l.startswith("http") and "صورة من" not in l]
            rec["title"] = lines[0][:80] if lines else ""
        out.append(rec)

    json.dump(out, open(ROOT / "data/posters.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(Counter(r["kind"] for r in out))
    with open(ROOT / "work/posters_check.txt", "w", encoding="utf8") as f:
        for r in out:
            if r["kind"] == "lecture" and r["id"] not in LECTURE and not re.search(rf"t\.me/{CH}/", r["caption"]):
                f.write(f"{r['id']} -> {r['targets']} | {r['title'][:70]}\n")


if __name__ == "__main__":
    main()
