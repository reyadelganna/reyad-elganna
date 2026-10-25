"""Index posts for the Telegram channel, published and kept up to date by a bot.

Usage:
  python tools/telegram_index.py            -> preview only: index/telegram_bot/*.txt
  python tools/telegram_index.py --publish  -> post/edit in the channel

Publishing needs the TELEGRAM_BOT_TOKEN environment variable (a GitHub secret)
and "enabled": true in data/telegram_index.json. Without both it only previews.

One post per series (split when long) with every lesson as a link, then a
master index post that links to each series post; the master is pinned.
Posts are sent silently. Later runs edit only the posts whose text changed,
and add a post when a series outgrows its posts.
"""
import hashlib, html, json, os, re, sys, time, urllib.parse, urllib.request
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from rules import CATEGORIES, SERIES_ORDER  # noqa: E402

CH = "reyad_elganna"
SITE = "https://reyadelganna.github.io/reyad-elganna/"
STATE = ROOT / "data/telegram_index.json"
PREVIEW = ROOT / "index/telegram_bot"
CATS = CATEGORIES + ["متفرقات"]
MAX_CHARS = 3800      # Telegram allows 4096 visible characters per message
MAX_LINKS = 90        # keep well under Telegram's per-message entity limit
TITLE_MAX = 75


def e(s):
    return html.escape(str(s), quote=False)


def grouped(items):
    out = OrderedDict((c, OrderedDict()) for c in CATS)
    sizes = Counter((i["category"], i["series"]) for i in items)
    # each book/section starts where its first lesson was posted, and keeps its lessons together
    first = {}
    for i in sorted(items, key=lambda i: i["id"]):
        first.setdefault((i["series"], i["sub"]), i["id"])
    order = lambda s: SERIES_ORDER.index(s) if s in SERIES_ORDER else 999
    for i in sorted(items, key=lambda i: (order(i["series"]), -sizes[(i["category"], i["series"])], i["series"],
                                         first[(i["series"], i["sub"])], i["id"])):
        out[i["category"]].setdefault(i["series"], []).append(i)
    return out


def key_of(series):
    return hashlib.md5(series.encode("utf8")).hexdigest()[:10]


def lesson_line(i):
    t = i["title"] if len(i["title"]) <= TITLE_MAX else i["title"][:TITLE_MAX - 1] + "…"
    ep = f"{i['ep']}. " if i["ep"] and i["ep"] < 1000 and str(i["ep"]) not in t else ""
    icon = {"video": "🎬 ", "pdf": "📄 ", "text": "📰 "}.get(i["type"], "")
    return f'▫️ {icon}<a href="https://t.me/{CH}/{i["id"]}">{e(ep + t)}</a>', len(icon) + len(ep + t) + 3


def series_posts(cat, series, items):
    """List of HTML texts for one series."""
    head = f"🗂 <b>{e(series)}</b>\n📚 {e(cat)} · {len(items)} مادة\n"
    head_len = len(series) + len(cat) + 20
    foot = f'\n🌐 <a href="{SITE}">البحث في كل الدروس على الموقع</a>'
    blocks, cur_sub = [], object()
    for i in items:
        if i["sub"] != cur_sub and i["sub"]:
            blocks.append((f"\n📖 <b>{e(i['sub'])}</b>", len(i["sub"]) + 4, 0))
        cur_sub = i["sub"]
        line, n = lesson_line(i)
        blocks.append((line, n, 1))
    posts, cur, cur_len, links = [], head, head_len, 0
    for text, n, is_link in blocks:
        if cur_len + n + 40 > MAX_CHARS or links + is_link > MAX_LINKS:
            posts.append(cur)
            cur, cur_len, links = f"🗂 <b>{e(series)}</b> (تابع)\n", len(series) + 10, 0
        cur += "\n" + text
        cur_len += n + 1
        links += is_link
    posts.append(cur)
    return [p + foot for p in posts]


def master_post(g, first_ids, total):
    lines = ["📌 <b>الفهرس الرئيسي لقناة رياض الجنة</b>",
             f"{total} مادة علمية مرتبة حسب الموضوع. اضغط على اسم السلسلة لفتح فهرس دروسها.", ""]
    for cat, series in g.items():
        if not series:
            continue
        lines.append(f"\n🔹 <b>{e(cat)}</b>")
        for s, items in series.items():
            mid = first_ids.get(key_of(s))
            name = f'<a href="https://t.me/{CH}/{mid}">{e(s)}</a>' if mid else e(s)
            lines.append(f"▪️ {name} ({len(items)})")
    lines.append(f'\n🌐 <a href="{SITE}">موقع رياض الجنة: بحث واستعراض لكل الدروس والإعلانات</a>')
    return "\n".join(lines)


def build():
    items = json.load(open(ROOT / "data/catalog.json", encoding="utf8"))
    g = grouped(items)
    plan = OrderedDict()
    for cat, series in g.items():
        for s, its in series.items():
            plan[key_of(s)] = {"series": s, "posts": series_posts(cat, s, its)}
    return g, plan, len(items)


# ───────────────────────── Telegram API ─────────────────────────
class TG:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method, **params):
        data = urllib.parse.urlencode({k: (json.dumps(v) if isinstance(v, (dict, list, bool)) else v)
                                       for k, v in params.items()}).encode()
        for attempt in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(self.base + method, data=data), timeout=40) as r:
                    res = json.load(r)
            except urllib.error.HTTPError as err:
                res = json.load(err)
            if res.get("ok"):
                time.sleep(3.2)   # stay under the per-chat rate limit
                return res["result"]
            wait = res.get("parameters", {}).get("retry_after")
            if wait:
                time.sleep(wait + 1)
                continue
            if "message is not modified" in res.get("description", ""):
                return None
            raise RuntimeError(f"{method}: {res.get('description')}")
        raise RuntimeError(f"{method}: too many retries")

    def send(self, text):
        return self.call("sendMessage", chat_id=f"@{CH}", text=text, parse_mode="HTML",
                         disable_notification=True, link_preview_options={"is_disabled": True})["message_id"]

    def edit(self, mid, text):
        self.call("editMessageText", chat_id=f"@{CH}", message_id=mid, text=text, parse_mode="HTML",
                  link_preview_options={"is_disabled": True})


def digest(t):
    return hashlib.md5(t.encode("utf8")).hexdigest()


def publish(g, plan, total):
    state = json.load(open(STATE, encoding="utf8")) if STATE.exists() else {"enabled": False}
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not state.get("enabled") or not token:
        print("telegram index: preview only (publishing", "disabled)" if not state.get("enabled") else "has no token)")
        return
    tg = TG(token)
    me = tg.call("getMe")
    member = tg.call("getChatMember", chat_id=f"@{CH}", user_id=me["id"])
    if member.get("status") != "administrator" or not member.get("can_post_messages"):
        raise SystemExit(f"البوت @{me['username']} ليس مشرفًا بصلاحية النشر في القناة")
    print("bot:", "@" + me["username"], "| can edit:", member.get("can_edit_messages"))

    # One-off maintenance, set by hand in the state file: remove the bot's own
    # posts listed in "delete" (allowed within 48 hours of posting), re-pin the master.
    if state.get("delete"):
        ids = state["delete"]
        for n in range(0, len(ids), 100):
            tg.call("deleteMessages", chat_id=f"@{CH}", message_ids=ids[n:n + 100])
        state["deleted"] = state.get("deleted", []) + ids
        state["delete"] = []
        json.dump(state, open(STATE, "w", encoding="utf8"), ensure_ascii=False, indent=1)
        print("telegram index: deleted", len(ids), "posts")
    if state.get("repin") and state.get("master"):
        tg.call("pinChatMessage", chat_id=f"@{CH}", message_id=state["master"], disable_notification=True)
        state["repin"] = False
        json.dump(state, open(STATE, "w", encoding="utf8"), ensure_ascii=False, indent=1)
        print("telegram index: re-pinned", state["master"])

    # "relayout": the series order changed, so reuse the existing posts in their
    # channel order for the new layout (edit in place), post any extra at the end,
    # and delete leftovers. Progress is saved after every post so a failed run resumes.
    if state.get("relayout"):
        if "relayout_pool" not in state:
            state["relayout_pool"] = sorted(i for v in state.get("series", {}).values() for i in v["ids"])
            state["series"] = {}
            json.dump(state, open(STATE, "w", encoding="utf8"), ensure_ascii=False, indent=1)
        for k, p in plan.items():
            if k in state["series"]:
                continue
            entry = {"ids": [], "hashes": []}
            for text in p["posts"]:
                if state["relayout_pool"]:
                    mid = state["relayout_pool"].pop(0)
                    tg.edit(mid, text)
                else:
                    mid = tg.send(text)
                entry["ids"].append(mid)
                entry["hashes"].append(digest(text))
                state["series"][k] = entry
                json.dump(state, open(STATE, "w", encoding="utf8"), ensure_ascii=False, indent=1)
        left = state["relayout_pool"]
        if left:
            tg.call("deleteMessages", chat_id=f"@{CH}", message_ids=left)
            state["deleted"] = state.get("deleted", []) + left
        print("telegram index: relayout done,", len(left), "leftover posts deleted")
        state["relayout"] = False
        del state["relayout_pool"]
        state["master_hash"] = None
        json.dump(state, open(STATE, "w", encoding="utf8"), ensure_ascii=False, indent=1)

    msgs = state.setdefault("series", {})
    changed = 0
    for k, p in plan.items():
        cur = msgs.setdefault(k, {"ids": [], "hashes": []})
        for n, text in enumerate(p["posts"]):
            h = digest(text)
            if n < len(cur["ids"]):
                if cur["hashes"][n] != h:
                    tg.edit(cur["ids"][n], text)
                    cur["hashes"][n] = h
                    changed += 1
            else:
                cur["ids"].append(tg.send(text))
                cur["hashes"].append(h)
                changed += 1
            json.dump(state, open(STATE, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    first_ids = {k: v["ids"][0] for k, v in msgs.items() if v["ids"]}
    text = master_post(g, first_ids, total)
    h = digest(text)
    if not state.get("master"):
        state["master"] = tg.send(text)
        tg.call("pinChatMessage", chat_id=f"@{CH}", message_id=state["master"], disable_notification=True)
        changed += 1
    elif state.get("master_hash") != h:
        tg.edit(state["master"], text)
        changed += 1
    state["master_hash"] = h
    json.dump(state, open(STATE, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print("telegram index:", changed, "posts sent or edited")


def preview(g, plan, total):
    PREVIEW.mkdir(parents=True, exist_ok=True)
    for f in PREVIEW.glob("*.txt"):
        f.unlink()
    n = 0
    for k, p in plan.items():
        for m, text in enumerate(p["posts"], 1):
            n += 1
            (PREVIEW / f"{n:03d}_{re.sub(r'[^\w]+', '_', p['series'])[:40]}_{m}.txt").write_text(text, encoding="utf8")
    fake = {k: 1000 + i for i, k in enumerate(plan)}
    (PREVIEW / "000_الفهرس_الرئيسي.txt").write_text(master_post(g, fake, total), encoding="utf8")
    print("telegram index preview:", n, "series posts + 1 master")
    return n


if __name__ == "__main__":
    g, plan, total = build()
    preview(g, plan, total)
    if "--publish" in sys.argv:
        publish(g, plan, total)
