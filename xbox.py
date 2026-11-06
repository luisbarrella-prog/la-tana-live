"""La Tana - notizie Xbox nel forum 🟢-xbox-news, una card per notizia (Components V2).

Gira una volta e termina. Fonte: feed RSS pubblico di Pure Xbox (Xbox Wire blocca i lettori automatici).
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
FEED = "https://www.purexbox.com/feeds/latest"
MRSS = "{http://search.yahoo.com/mrss/}"
XBOX_GREEN = 0x107C10
FIRST_RUN_MAX = 8   # al primo giro non inondiamo il forum con tutto il feed
RUN_MAX = 10

# nome del tag nel forum (senza emoji) -> regex a parola intera, in ordine di priorità
TAGS = [
    ("Game Pass", r"game pass"),
    ("Offerte", r"deals|on sale|sale|discounts?|discounted|\d+% off|price drop|cheapest|black friday"),
    ("Rumor", r"rumou?rs?|leak(ed|s)?|reportedly|insider|allegedly"),
    ("Hardware", r"consoles?|controllers?|series [xs]|headsets?|handheld|rog xbox ally|hardware|next-gen"),
    ("Aggiornamenti", r"updates?|patch(es)?|dashboard|firmware|upgrade"),
    ("Giochi", r"releas(e|es|ing)|launch(es|ing)?|trailer|review|gameplay|dlc|season|remaster(ed)?|out now|screenshots?"),
]


def fetch_feed():
    req = urllib.request.Request(FEED, headers={"User-Agent": "LaTanaBot/1.0 (Discord news feed)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        root = ET.fromstring(r.read())
    items = []
    for it in root.findall("./channel/item"):
        img = it.find(f"{MRSS}content")  # immagine grande; un Element senza figli è falsy, niente "or"
        if img is None:
            img = it.find(f"{MRSS}thumbnail")
        items.append({
            "title": html.unescape(it.findtext("title", "")).strip(),
            "link": it.findtext("link", "").strip(),
            "summary": clean(it.findtext("description", "")),
            "image": img.get("url") if img is not None else None,
            "ts": int(parsedate_to_datetime(it.findtext("pubDate")).timestamp()),
        })
    return items


def clean(raw, limit=320):
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    text = re.sub(r"\s+", " ", text).strip()
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
        {"type": 10, "content": f"## {item['title']}\n-# 🟢 Pure Xbox  ·  <t:{item['ts']}:R>  ·  {'  ·  '.join(tags)}"},
        {"type": 14, "divider": True, "spacing": 1},
        {"type": 10, "content": item["summary"] or "​"},
        {"type": 1, "components": [{"type": 2, "style": 5, "label": "Leggi l'articolo", "emoji": {"name": "📖"}, "url": item["link"]}]},
    ]
    return {"flags": 1 << 15, "components": [{"type": 17, "accent_color": XBOX_GREEN, "components": inner}]}


def existing_titles(token):
    active = http("GET", f"{API}/guilds/{GUILD_ID}/threads/active", token)["threads"]
    archived = http("GET", f"{API}/channels/{FORUM_ID}/threads/archived/public?limit=100", token)["threads"]
    return {t["name"] for t in active + archived if t.get("parent_id") == FORUM_ID}


def main():
    token = os.environ.get("DISCORD_TOKEN") or Path(__file__).with_name("token.txt").read_text().strip()
    forum = http("GET", f"{API}/channels/{FORUM_ID}", token)
    tag_ids = {re.sub(r"^\W+", "", t["name"]).strip(): t["id"] for t in forum["available_tags"]}
    seen = existing_titles(token)

    items = [i for i in fetch_feed() if i["title"] and i["title"][:100] not in seen]
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


def self_test():
    assert clean("<p>Ciao&nbsp;<b>mondo</b></p>") == "Ciao mondo"
    assert clean("parola " * 100, 20).endswith("…") and len(clean("parola " * 100, 20)) <= 21
    assert pick_tags({"title": "Huge Xbox Series X Deals", "summary": ""}) == ["Offerte", "Hardware"]
    assert pick_tags({"title": "Three Day One Game Pass titles", "summary": ""}) == ["Game Pass"]
    assert pick_tags({"title": "Phil Spencer talks", "summary": ""}) == ["News"]
    assert pick_tags({"title": "It Really Finally Signs A Deal", "summary": ""}) == ["News"]  # niente "ally"/"deal"
    c = card({"title": "T", "link": "https://x", "summary": "s", "image": "https://i", "ts": 1}, ["News"])
    assert c["flags"] == 32768 and c["components"][0]["type"] == 17
    print("self-test ok")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    self_test() if "--test" in sys.argv else main()
