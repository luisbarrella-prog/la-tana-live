"""Pubblica in #📢-annunci i file annunci/*.md passati come argomenti.

Formato del file: la prima riga "# Titolo", il resto è il testo (markdown Discord).
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from stats import API, http

CHANNEL_ID = os.environ.get("ANNUNCI_CHANNEL_ID", "1566752851609395230")  # #📢-annunci


def build_embed(text):
    first, _, body = text.strip().partition("\n")
    return {
        "title": "📣 " + first.lstrip("# ").strip(),
        "description": body.strip()[:4096],
        "color": 0xF1C40F,
        "footer": {"text": "La Tana · annuncio"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main(paths):
    token = os.environ.get("DISCORD_TOKEN") or Path(__file__).with_name("token.txt").read_text().strip()
    for p in paths:
        http("POST", f"{API}/channels/{CHANNEL_ID}/messages", token,
             {"embeds": [build_embed(Path(p).read_text(encoding="utf-8"))]})
        print("pubblicato:", p)


def self_test():
    e = build_embed("# Novità\n\nRiga uno\nRiga due\n")
    assert e["title"] == "📣 Novità" and e["description"] == "Riga uno\nRiga due"
    print("self-test ok")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    self_test() if "--test" in sys.argv else main(sys.argv[1:])
