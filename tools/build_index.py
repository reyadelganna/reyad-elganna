"""Build the channel index from data/catalog.json.

Usage: python tools/build_index.py
Outputs:
  فهرس قناة رياض الجنة.xlsx          - full searchable index (one sheet per category)
  index/telegram/NN_*.txt              - ready-to-paste Telegram index posts (<= 4096 chars each)
  index/telegram/00_الفهرس_الرئيسي.txt - master index (hashtags of every series post)
"""
import json, re, sys
from collections import Counter, OrderedDict
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from rules import CATEGORIES  # noqa: E402

CATS = CATEGORIES + ["متفرقات"]
TYPE_AR = {"audio": "صوتي", "video": "فيديو", "pdf": "PDF"}
TG_LIMIT = 4000
FONT = "Arial"
GREEN = "1F5C46"


def grouped(items):
    """category -> series -> [items], series ordered by size, items by post id."""
    out = OrderedDict((c, OrderedDict()) for c in CATS)
    sizes = Counter((i["category"], i["series"]) for i in items)
    for i in sorted(items, key=lambda i: (-sizes[(i["category"], i["series"])], i["series"], i["id"])):
        out[i["category"]].setdefault(i["series"], []).append(i)
    return out


def tag(s):
    s = re.sub(r"^شرح\s+|\s*\(.*?\)|\s*ﷺ|\s+(للألباني|لابن قدامة|لابن القيم|للسعدي|عليه السلام)$", "", s)
    return "#فهرس_" + re.sub(r"[^\w]+", "_", s).strip("_")


# ───────────────────────── Excel ─────────────────────────
HEAD = ["م", "التصنيف", "السلسلة", "الكتاب / الباب", "رقم الدرس", "عنوان الدرس", "الموضوعات", "النوع", "التاريخ", "الرابط"]
WIDTH = [7, 18, 34, 28, 10, 50, 60, 9, 12, 16]


def style_header(ws, row=1):
    for c in ws[row]:
        c.font = Font(name=FONT, bold=True, color="FFFFFF", size=11)
        c.fill = PatternFill("solid", fgColor=GREEN)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def fill_sheet(ws, rows):
    ws.sheet_view.rightToLeft = True
    ws.append(HEAD)
    style_header(ws)
    thin = Side(style="thin", color="D9D9D9")
    for n, i in enumerate(rows, 1):
        ws.append([n, i["category"], i["series"], i["sub"] or "", i["ep"] if i["ep"] and i["ep"] < 1000 else "",
                   i["title"], " • ".join(i["topics"]), TYPE_AR[i["type"]], i["date"], "فتح في تليجرام"])
        r = ws.max_row
        link = ws.cell(r, 10)
        link.hyperlink = i["url"]
        link.font = Font(name=FONT, color="0563C1", underline="single")
        for c in ws[r][:9]:
            c.font = Font(name=FONT)
        for c in ws[r]:
            c.alignment = Alignment(vertical="top", wrap_text=c.column in (6, 7))
            c.border = Border(bottom=thin)
    for k, w in enumerate(WIDTH, 1):
        ws.column_dimensions[get_column_letter(k)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEAD))}{ws.max_row}"


def build_excel(items, g):
    wb = Workbook()
    summary = wb.active
    summary.title = "ملخص"
    allws = wb.create_sheet("الفهرس العام")
    fill_sheet(allws, [i for c in g.values() for s in c.values() for i in s])
    last = allws.max_row

    summary.sheet_view.rightToLeft = True
    summary["A1"] = "فهرس قناة رياض الجنة (م. محمود علي)"
    summary["A1"].font = Font(name=FONT, bold=True, size=16, color=GREEN)
    summary["A2"] = "الأعداد محسوبة بالمعادلات من ورقة «الفهرس العام». لكل تصنيف ورقة مستقلة، ويمكن التصفية والبحث من رأس كل عمود."
    summary["A2"].font = Font(name=FONT, italic=True, color="595959")
    summary.append([])
    summary.append(["التصنيف", "السلسلة", "عدد المواد"])
    style_header(summary, summary.max_row)
    rng_cat = f"'الفهرس العام'!$B$2:$B${last}"
    rng_ser = f"'الفهرس العام'!$C$2:$C${last}"
    first_row = summary.max_row + 1
    for cat, series in g.items():
        if not series:
            continue
        summary.append([cat, "", f'=COUNTIF({rng_cat},A{summary.max_row + 1})'])
        r = summary.max_row
        for c in summary[r]:
            c.font = Font(name=FONT, bold=True)
            c.fill = PatternFill("solid", fgColor="E2EFDA")
        for s in series:
            summary.append(["", s, f'=COUNTIFS({rng_cat},"{cat}",{rng_ser},B{summary.max_row + 1})'])
            for c in summary[summary.max_row]:
                c.font = Font(name=FONT)
    summary.append(["الإجمالي", "", f"=SUMPRODUCT((A{first_row}:A{summary.max_row}<>\"\")*(B{first_row}:B{summary.max_row}=\"\"),C{first_row}:C{summary.max_row})"])
    for c in summary[summary.max_row]:
        c.font = Font(name=FONT, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=GREEN)
    summary.column_dimensions["A"].width = 22
    summary.column_dimensions["B"].width = 48
    summary.column_dimensions["C"].width = 12

    for cat, series in g.items():
        rows = [i for s in series.values() for i in s]
        if rows:
            fill_sheet(wb.create_sheet(cat[:31]), rows)
    out = ROOT / "فهرس قناة رياض الجنة.xlsx"
    wb.save(out)
    return out


# ───────────────────────── Telegram ─────────────────────────
def lesson_line(i):
    ep = f"{i['ep']}. " if i["ep"] and i["ep"] < 1000 and str(i["ep"]) not in i["title"] else ""
    icon = {"video": "🎬 ", "pdf": "📄 "}.get(i["type"], "")
    return f"▫️ {icon}{ep}{i['title']}\nt.me/reyad_elganna/{i['id']}"


def chunk_posts(header, lines):
    posts, cur = [], header
    for l in lines:
        if len(cur) + len(l) + 2 > TG_LIMIT:
            posts.append(cur)
            cur = header.split("\n")[0] + " (تابع)\n\n"
        cur += l + "\n"
    posts.append(cur)
    return posts


def build_telegram(g):
    outdir = ROOT / "index/telegram"
    outdir.mkdir(parents=True, exist_ok=True)
    for f in outdir.glob("*.txt"):
        f.unlink()
    master = ["📚 الفهرس الرئيسي لقناة رياض الجنة", "اضغط على الهاشتاج للوصول إلى فهرس السلسلة", ""]
    n = 0
    all_posts = []
    for cat, series in g.items():
        if not series:
            continue
        master.append(f"\n🔹 {cat}")
        for s, items in series.items():
            t = tag(s)
            master.append(f"▪️ {s} ({len(items)}) {t}")
            lines, cur_sub = [], object()
            for i in items:
                if i["sub"] != cur_sub and i["sub"]:
                    lines.append(f"\n📖 {i['sub']}")
                cur_sub = i["sub"]
                lines.append(lesson_line(i))
            header = f"🗂 {s}\n{t} #{re.sub(r'[^\w]+', '_', cat)}\n\n"
            for k, post in enumerate(chunk_posts(header, lines), 1):
                n += 1
                all_posts.append(post)
                (outdir / f"{n:03d}_{re.sub(r'[^\w]+', '_', s)[:40]}_{k}.txt").write_text(post, encoding="utf8")
    master_txt = "\n".join(master)
    master_posts = chunk_posts("", master_txt.split("\n"))
    for k, mp in enumerate(master_posts, 1):
        (outdir / f"000_الفهرس_الرئيسي_{k}.txt").write_text(mp, encoding="utf8")
    sep = "\n\n" + "═" * 30 + "\n\n"
    (ROOT / "index/منشورات فهرس تليجرام (كلها).txt").write_text(
        sep.join(master_posts + all_posts), encoding="utf8")
    return len(master_posts), n


def main():
    items = json.load(open(ROOT / "data/catalog.json", encoding="utf8"))
    g = grouped(items)
    x = build_excel(items, g)
    m, n = build_telegram(g)
    print("excel:", x.name, "| telegram posts:", m, "master +", n, "series posts")


if __name__ == "__main__":
    main()
