"""La Tana - giocatori online nel mondo, aggiornati in un messaggio Discord.

Gira una volta e termina: va lanciato ogni N minuti (GitHub Actions, cron, ...).
Solo libreria standard, nessuna dipendenza.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CHANNEL_ID = os.environ.get("CHANNEL_ID", "1566756447365103687")  # #📡-live-giochi
API = "https://discord.com/api/v10"

# (nome, emoji, appid Steam o None se l'editore non pubblica i numeri)
GAMES = [
    ("Battlefield 6",           "🪖", 2807960),
    ("Hell Let Loose",          "🎖️", 686810),
    ("Hell Let Loose: Vietnam", "🚁", 3079210),
    ("Call of Duty",            "💀", 1938090),
    ("Fortnite",                "🦙", None),
]
MEDALS = ["🥇", "🥈", "🥉"]


def http(method, url, token=None, body=None):
    headers = {"User-Agent": "DiscordBot (https://discord.com, 1.0)"}
    if token:
        headers["Authorization"] = f"Bot {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read() or b"null")


def steam_players(appid):
    try:
        url = f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}"
        return http("GET", url)["response"].get("player_count")
    except Exception as ex:  # Steam giù per un gioco: lo mostriamo come non disponibile
        print(f"Steam {appid}: {ex}")
        return None


def fmt(n):
    return f"{n:,}".replace(",", ".")


def previous_counts(message):
    """Legge i numeri dal messaggio precedente, per mostrare se salgono o scendono."""
    out = {}
    for f in (message or {}).get("embeds", [{}])[0].get("fields", []):
        m = re.search(r"\*\*([\d.]+)\*\*", f["value"])
        for name, _, _ in GAMES:
            if f["name"].endswith(name) and m:  # endswith: "Hell Let Loose" non deve prendere il Vietnam
                out[name] = int(m.group(1).replace(".", ""))
    return out


def trend(now, before):
    if before is None or now == before:
        return ""
    d = now - before
    return f" ▲ +{fmt(d)}" if d > 0 else f" ▼ {fmt(d)}"


def build_embed(counts, before):
    known = sorted(((n, e, c) for n, e, c in counts if c is not None), key=lambda x: -x[2])
    fields = []
    for i, (name, emoji, c) in enumerate(known):
        rank = MEDALS[i] if i < len(MEDALS) else "▫️"
        fields.append({"name": f"{rank} {emoji} {name}",
                       "value": f"**{fmt(c)}** online ora{trend(c, before.get(name))}",
                       "inline": False})
    for name, emoji, c in counts:
        if c is None:
            fields.append({"name": f"▫️ {emoji} {name}",
                           "value": "-# numero non pubblico" if name == "Fortnite" else "-# Steam non risponde",
                           "inline": False})
    total = sum(c for _, _, c in known)
    return {
        "title": "🖥️ GIOCATORI ONLINE SU STEAM (PC)",
        "description": f"**{fmt(total)}** giocatori su Steam in questo momento",
        "color": 0x2ECC71,
        "fields": fields,
        "footer": {"text": "Solo PC Steam: Xbox, PlayStation, EA ed Epic non pubblicano dati, "
                              "i \"totali\" che si trovano online sono stime · aggiornato ogni ~5 min"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main():
    token = os.environ.get("DISCORD_TOKEN") or Path(__file__).with_name("token.txt").read_text().strip()
    me = http("GET", f"{API}/users/@me", token)["id"]
    history = http("GET", f"{API}/channels/{CHANNEL_ID}/messages?limit=20", token)
    old = next((m for m in history if m["author"]["id"] == me), None)

    counts = [(n, e, steam_players(a) if a else None) for n, e, a in GAMES]
    body = {"content": None, "embeds": [build_embed(counts, previous_counts(old))]}
    if old:
        http("PATCH", f"{API}/channels/{CHANNEL_ID}/messages/{old['id']}", token, body)
    else:
        http("POST", f"{API}/channels/{CHANNEL_ID}/messages", token, body)
    print("aggiornato:", ", ".join(f"{n}={c}" for n, _, c in counts))


def self_test():
    e = build_embed([("A", "x", 10), ("B", "y", 2000), ("Fortnite", "z", None)], {"B": 1500})
    assert e["fields"][0]["name"].startswith("🥇") and "B" in e["fields"][0]["name"]
    assert "**2.000**" in e["fields"][0]["value"] and "▲ +500" in e["fields"][0]["value"]
    assert "non pubblico" in e["fields"][2]["value"]
    prev = previous_counts({"embeds": [{"fields": [{"name": "🥇 🪖 Battlefield 6", "value": "**15.930** online ora"}]}]})
    assert prev == {"Battlefield 6": 15930}
    prev = previous_counts({"embeds": [{"fields": [
        {"name": "🥉 🎖️ Hell Let Loose", "value": "**3.177** online ora"},
        {"name": "▫️ 🚁 Hell Let Loose: Vietnam", "value": "**899** online ora"}]}]})
    assert prev == {"Hell Let Loose": 3177, "Hell Let Loose: Vietnam": 899}
    print("self-test ok")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # la console Windows non regge le emoji
    self_test() if "--test" in sys.argv else main()
