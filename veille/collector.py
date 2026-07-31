#!/usr/bin/env python3
"""Collecteur RSS pour l'outil de veille economique.

Usage:
    python collector.py --check   Teste chaque flux (OK/KO + date du dernier
                                   element), sans rien ecrire sur le disque.
    python collector.py           Fait une passe de collecte : recupere tous
                                   les flux, dedoublonne, nettoie le HTML et
                                   met a jour data/articles.json.

data/index.json est ecrit par analyzer.py, pas ici : la collecte rassemble
la matiere, le scoring est un etage separe.
"""

import argparse
import hashlib
import html
import json
import re
import socket
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser

from sources import SOURCES

DATA_DIR = Path(__file__).parent / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"

RETENTION_DAYS = 90
SUMMARY_MAX_LEN = 600
FETCH_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (compatible; VeilleEconomiqueBot/1.0; "
    "+https://github.com/) FeedFetcher"
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def fetch_feed(url):
    """Recupere et parse un flux RSS. Ne leve jamais d'exception :
    renvoie toujours un objet feedparser (bozo=1 en cas d'echec)."""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
            raw = response.read()
        return feedparser.parse(raw)
    except (urllib.error.URLError, socket.timeout, TimeoutError, ValueError) as exc:
        parsed = feedparser.FeedParserDict()
        parsed.bozo = True
        parsed.bozo_exception = exc
        parsed.entries = []
        return parsed


def clean_html(raw_text):
    """Retire les balises HTML et decode les entites, normalise les espaces."""
    if not raw_text:
        return ""
    text = html.unescape(raw_text)
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def truncate(text, max_len=SUMMARY_MAX_LEN):
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def entry_published(entry):
    """Renvoie la date de publication d'une entree en UTC, ou None."""
    for field in ("published_parsed", "updated_parsed"):
        struct = getattr(entry, field, None)
        if struct:
            return datetime(*struct[:6], tzinfo=timezone.utc)
    return None


def make_article_id(url, title):
    digest_input = f"{url}|{title}".encode("utf-8", errors="ignore")
    return hashlib.sha256(digest_input).hexdigest()[:24]


def check_feeds():
    """Teste chaque flux et affiche un tableau OK/KO. N'ecrit rien."""
    rows = []
    for source in SOURCES:
        parsed = fetch_feed(source["url"])
        entries = getattr(parsed, "entries", [])
        has_content = bool(entries)
        status = "OK" if has_content else "KO"

        last_date = "-"
        if has_content:
            published = entry_published(entries[0])
            if published:
                last_date = published.strftime("%Y-%m-%d")

        reason = ""
        if not has_content:
            exc = getattr(parsed, "bozo_exception", None)
            reason = str(exc) if exc else "aucune entree"

        rows.append((source["id"], source["name"], status, last_date, reason))

    name_width = max(len(r[1]) for r in rows) + 1
    id_width = max(len(r[0]) for r in rows) + 1
    print(f"{'id':<{id_width}} {'source':<{name_width}} {'statut':<7} {'dernier':<11} detail")
    print("-" * (id_width + name_width + 7 + 11 + 20))
    ok_count = 0
    for source_id, name, status, last_date, reason in rows:
        if status == "OK":
            ok_count += 1
        print(f"{source_id:<{id_width}} {name:<{name_width}} {status:<7} {last_date:<11} {reason}")
    print("-" * (id_width + name_width + 7 + 11 + 20))
    print(f"{ok_count}/{len(rows)} flux OK")
    return rows


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def collect_articles():
    """Recupere tous les flux et renvoie la liste des nouveaux articles."""
    now = datetime.now(timezone.utc)
    collected = []

    for source in SOURCES:
        parsed = fetch_feed(source["url"])
        entries = getattr(parsed, "entries", [])

        for entry in entries:
            title = clean_html(getattr(entry, "title", "") or "")
            url = getattr(entry, "link", "") or ""
            if not title or not url:
                continue

            summary_raw = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
            summary = truncate(clean_html(summary_raw))

            published = entry_published(entry) or now

            collected.append({
                "id": make_article_id(url, title),
                "source": source["id"],
                "tier": source["tier"],
                "weight": source["weight"],
                "category": source["category"],
                "assets": source["assets"],
                "title": title,
                "url": url,
                "summary": summary,
                "published_at": published.isoformat(),
                "collected_at": now.isoformat(),
            })

    return collected


def merge_articles(existing, new_articles):
    """Fusionne en dedoublonnant par id, en gardant la premiere collected_at."""
    by_id = {a["id"]: a for a in existing}
    for article in new_articles:
        if article["id"] not in by_id:
            by_id[article["id"]] = article
    return list(by_id.values())


def purge_old(articles, retention_days=RETENTION_DAYS):
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    kept = []
    for article in articles:
        try:
            published = datetime.fromisoformat(article["published_at"])
        except (KeyError, ValueError):
            kept.append(article)
            continue
        if published >= cutoff:
            kept.append(article)
    return kept


def run_collection():
    existing_articles = load_json(ARTICLES_PATH, [])

    new_articles = collect_articles()
    merged = merge_articles(existing_articles, new_articles)
    purged = purge_old(merged)
    purged.sort(key=lambda a: a["published_at"], reverse=True)

    save_json(ARTICLES_PATH, purged)

    new_count = len(merged) - len(existing_articles)
    print(f"Collecte terminee : {len(new_articles)} entrees vues, "
          f"{new_count} nouveaux articles, "
          f"{len(purged)} articles conserves (fenetre {RETENTION_DAYS}j).")
    print("Lance `python analyzer.py` pour mettre a jour l'indice.")


def main():
    parser = argparse.ArgumentParser(description="Collecteur RSS de veille economique")
    parser.add_argument("--check", action="store_true", help="Teste les flux sans ecrire de donnees")
    args = parser.parse_args()

    if args.check:
        check_feeds()
    else:
        run_collection()


if __name__ == "__main__":
    main()
