"""La Tana - notizie Xbox nel forum 🟢-xbox-news, una card per notizia (Components V2).

Gira una volta e termina. Fonte: feed RSS pubblico di MondoXbox, sito italiano solo Xbox
(Xbox Wire blocca i lettori automatici).
"""
import html
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

from stats import API, http

GUILD_ID = "1566752361035341854"
FORUM_ID = os.environ.get("XBOX_FORUM_ID", "1568281182456782908")
FEED = "https://feeds.feedburner.com/mondoxbox/mxnews"
SOURCE = "MondoXbox"
XBOX_GREEN = 0x107C10
FIRST_RUN_MAX = 8   # al primo giro non inondiamo il forum con tutto il feed
RUN_MAX = 10

# nome del tag nel forum (senza emoji) -> regex a parola intera, in ordine di priorità
TAGS = [
    ("Game Pass", r"game pass"),
    ("Offerte", r"scont[io]|scontat[oie]|offert[ae]|saldi|black friday|gratis|gratuit[aoie]|gratuitamente|in regalo"),
    ("Rumor", r"rumor|indiscrezion[ei]|leak|insider|trapelat[oaie]|secondo un report"),
    ("Hardware", r"console|controller|series [xs]|cuffie|headset|handheld|rog xbox ally|hardware|next[- ]gen"),
    ("Aggiornamenti", r"aggiornament[oi]|update|patch|dashboard|firmware"),
    ("Giochi", r"uscit[ao]|in uscita|disponibile|lancio|trailer|recensione|provato|anteprima|gameplay|dlc|stagione|remaster|annunciat[oa]|preload|preordin[ei]"),
]


def fetch_feed():
    req = urllib.request.Request(FEED, headers={"User-Agent": "LaTanaBot/1.0 (Discord news feed)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        root = ET.fromstring(r.read())
    items = []
    for it in root.findall("./channel/item"):
        desc = it.findtext("description", "")
        items.append({
            "title": html.unescape(it.findtext("title", "")).strip(),
            "link": it.findtext("link", "").strip(),
            "summary": clean(desc),
            "image": big_image(desc),
            "ts": int(parsedate_to_datetime(it.findtext("pubDate")).timestamp()),
        })
    return items


def big_image(desc):
    """Il feed ha solo la miniatura 180px: la versione 1024px sta allo stesso numero sotto /images/shots/."""
    m = re.search(r'<img[^>]+src="([^"]+)"', desc or "")
    if not m:
        return None
    url = m.group(1)
    big = re.sub(r"^https?://static\.mondoxbox\.com/shots/small/", "https://www.mondoxbox.com/images/shots/", url)
    return big


def clean(raw, limit=600):
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    text = re.sub(r"\s+", " ", text).replace("[continua]", "").strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def pick_tags(item):
    text = item["title"].lower()  # solo il titolo: i riassunti citano di tutto e sporcano i tag
    found = [name for name, rx in TAGS if re.search(rf"\b({rx})\b", text)]
    return found[:3] or ["News"]


def card(item, tags):
    """Messaggio Components V2: immagine grande, titolo, meta, riassunto, bottone."""
    inner = []
    if item["image"]:
        inner.append({"type": 12, "items": [{"media": {"url": item["image"]}}]})
    inner += [
        {"type": 10, "content": f"## {item['title']}\n-# 🟢 {SOURCE}  ·  <t:{item['ts']}:R>  ·  {'  ·  '.join(tags)}"},
        {"type": 14, "divider": True, "spacing": 1},
        {"type": 10, "content": item["summary"] or "​"},
        {"type": 1, "components": [{"type": 2, "style": 5, "label": f"Articolo completo su {SOURCE}", "url": item["link"]}]},
    ]
    # 1<<15 Components V2, 1<<12 silenzioso: il forum è una bacheca da sfogliare, non deve far suonare nessuno
    return {"flags": (1 << 15) | (1 << 12), "components": [{"type": 17, "accent_color": XBOX_GREEN, "components": inner}]}


def existing_posts(token):
    """Titoli già pubblicati e ora (unix) del post più recente, letta dall'ID snowflake."""
    active = http("GET", f"{API}/guilds/{GUILD_ID}/threads/active", token)["threads"]
    archived = http("GET", f"{API}/channels/{FORUM_ID}/threads/archived/public?limit=100", token)["threads"]
    posts = [t for t in active + archived if t.get("parent_id") == FORUM_ID]
    newest = max(((int(t["id"]) >> 22) + 1420070400000) // 1000 for t in posts) if posts else 0
    return {t["name"] for t in posts}, newest


def main():
    token = os.environ.get("DISCORD_TOKEN") or Path(__file__).with_name("token.txt").read_text().strip()
    forum = http("GET", f"{API}/channels/{FORUM_ID}", token)
    tag_ids = {re.sub(r"^\W+", "", t["name"]).strip(): t["id"] for t in forum["available_tags"]}
    seen, newest = existing_posts(token)

    # solo notizie uscite dopo l'ultimo post (1h di margine per i feed in ritardo): niente arretrati in cima al forum
    items = [i for i in fetch_feed()
             if i["title"] and i["title"][:100] not in seen and i["ts"] > newest - 3600]
    items = sorted(items, key=lambda i: i["ts"])[-(FIRST_RUN_MAX if not seen else RUN_MAX):]  # dal più vecchio, così il più nuovo sta in cima
    for item in items:
        tags = pick_tags(item)
        http("POST", f"{API}/channels/{FORUM_ID}/threads", token, {
            "name": item["title"][:100],
            "applied_tags": [tag_ids[t] for t in tags if t in tag_ids],
            "message": card(item, tags),
        })
        print("pubblicata:", item["title"], tags)
        time.sleep(1.5)  # gentile con i limiti di Discord
    print(f"{len(items)} notizie nuove")


# cosa rende "grossa" una notizia: annunci ufficiali e franchise importanti salgono, guide e sconti scendono
BIG = r"ufficiale|ufficialmente|annuncia|annunciat[oa]|svelat[oa]|rivelat[oa]|data di uscita|rinviat[oa]|showcase|direct|nuova console|prezzo|esclusiv[oa]|gta|halo|elder scrolls|gears of war|forza|call of duty|fable|fallout|starfield|game pass"
SMALL = r"guida|collezionabili|recensione|provato|scont[io]|offert[ae]"


def importance(item):
    t = item["title"].lower()
    return len(re.findall(rf"\b({BIG})", t)) * 2 - len(re.findall(rf"\b({SMALL})", t))


def daily():
    """Una sola card al giorno in #generale con la notizia più importante delle ultime 24 ore."""
    token = os.environ.get("DISCORD_TOKEN") or Path(__file__).with_name("token.txt").read_text().strip()
    forum = http("GET", f"{API}/channels/{FORUM_ID}", token)
    if any(o["id"] == GUILD_ID and int(o["deny"]) & 1024 for o in forum["permission_overwrites"]):
        print("forum ancora privato: niente big news in #generale")  # parte da sola quando il forum diventa pubblico
        return
    channels = http("GET", f"{API}/guilds/{GUILD_ID}/channels", token)
    general = next(c for c in channels if c["type"] == 0 and "generale" in c["name"])
    recent = [i for i in fetch_feed() if i["ts"] > time.time() - 86400]
    if not recent:
        print("nessuna notizia nelle ultime 24 ore")
        return
    best = max(recent, key=lambda i: (importance(i), i["ts"]))
    active = http("GET", f"{API}/guilds/{GUILD_ID}/threads/active", token)["threads"]
    thread = next((t for t in active if t.get("parent_id") == FORUM_ID and t["name"] == best["title"][:100]), None)
    # il bottone porta al post nel forum: si resta dentro Discord
    target = f"https://discord.com/channels/{GUILD_ID}/{thread['id'] if thread else FORUM_ID}"
    inner = ([{"type": 12, "items": [{"media": {"url": best["image"]}}]}] if best["image"] else []) + [
        {"type": 10, "content": f"-# 🔥 LA BIG NEWS XBOX DI OGGI\n## {best['title']}"},
        {"type": 10, "content": best["summary"] or "​"},
        {"type": 1, "components": [{"type": 2, "style": 5, "label": "Apri nel forum notizie", "emoji": {"name": "🟢"}, "url": target}]},
    ]
    http("POST", f"{API}/channels/{general['id']}/messages", token,
         {"flags": 1 << 15, "components": [{"type": 17, "accent_color": XBOX_GREEN, "components": inner}]})
    print("big news:", best["title"])


def self_test():
    assert clean("<p>Ciao&nbsp;<b>mondo</b></p>") == "Ciao mondo"
    assert clean("parola " * 100, 20).endswith("…") and len(clean("parola " * 100, 20)) <= 21
    assert pick_tags({"title": "Xbox Series X in sconto", "summary": ""}) == ["Offerte", "Hardware"]
    assert pick_tags({"title": "XBOX Game Pass: in arrivo tre giochi", "summary": ""}) == ["Game Pass"]
    assert pick_tags({"title": "Phil Spencer parla del futuro", "summary": ""}) == ["News"]
    assert pick_tags({"title": "Metro Redux: disponibile l'aggiornamento Next Gen", "summary": ""}) == ["Hardware", "Aggiornamenti", "Giochi"]
    assert big_image('<img src="https://static.mondoxbox.com/shots/small/158/158619.jpg">') == "https://www.mondoxbox.com/images/shots/158/158619.jpg"
    assert clean("Testo [continua]") == "Testo"
    c = card({"title": "T", "link": "https://x", "summary": "s", "image": "https://i", "ts": 1}, ["News"])
    assert c["flags"] == 32768 | 4096 and c["components"][0]["type"] == 17
    assert importance({"title": "Bethesda conferma il nome ufficiale di TES VI: The Elder Scrolls VI"}) > \
        importance({"title": "Gears of War: E-Day – Guida a tutti i collezionabili"})
    print("self-test ok")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--test" in sys.argv:
        self_test()
    elif "--giornaliera" in sys.argv:
        daily()
    else:
        main()
