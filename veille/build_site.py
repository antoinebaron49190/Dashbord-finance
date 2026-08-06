#!/usr/bin/env python3
"""Genere docs/index.html : une page statique unique, servie par GitHub Pages.

La page est d'abord un JOURNAL. Elle repond, dans cet ordre :

  1. Ou en est le monde, en cinq secondes ? — l'en-tete et ses quatre
     chiffres cles.
  2. Qu'est-ce qui a bouge, et que faut-il savoir ? — l'essentiel redige,
     les basculements, puis l'etat des quatre regions.
  3. Que raconte l'actualite ? — le flux, cherchable et filtrable, ou chaque
     article porte sa rubrique, son importance, son extrait, ses marches et
     un lien vers la source.
  4. Qu'est-ce qui arrive, et que valent ces signaux ? — le calendrier, puis
     la partie analytique, volontairement placee en dernier.

Ce module decide QUOI montrer. `design.py` decide a quoi cela ressemble :
jetons, feuille de style, script et icones y vivent ensemble.

Contraintes tenues ici :
  - un seul fichier HTML, CSS et JS inclus dedans ;
  - aucun framework, aucune compilation, aucune dependance externe ;
  - donnees injectees a la generation : la page ne fait aucune requete, elle
    s'ouvre entiere hors ligne ;
  - du telephone au grand ecran, sans defilement horizontal ;
  - aucun texte sous 14 px, aucune zone tactile sous 38 px.

Usage:
    python build_site.py
"""

import html
import json
import re
import struct
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from design import (CATEGORY_STYLE, ICONS, REGION_ACCENTS, SCRIPT, TOKENS,
                    icon, stylesheet)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT.parent / "docs"

PARIS = ZoneInfo("Europe/Paris")

NEWS_WINDOW_DAYS = 7        # fenetre du decompte favorable/defavorable
FEED_WINDOW_HOURS = 96      # fenetre du flux
FEED_MAX = 32               # articles injectes dans la page
FEED_PER_ZONE = 5           # places reservees a chaque region
EXCERPT_CHARS = 190

TEXT = TOKENS["text"]
DIM = TOKENS["dim"]
FAINT = TOKENS["faint"]
GREEN = TOKENS["positive"]
RED = TOKENS["negative"]
GRAY = TOKENS["dim"]
ACCENT = TOKENS["accent"]

# (cle, libelle, section macro.json, unite, [(indice, nom)], [actifs])
ZONES = [
    ("amerique", "Amérique", "equities", "", [
        ("sp500", "S&P 500"), ("nasdaq", "Nasdaq")], ["sp500"]),
    ("europe", "Europe", "equities", "", [
        ("eurostoxx", "Euro Stoxx 50"), ("cac40", "CAC 40"), ("dax", "DAX")],
        ["europe"]),
    ("asie", "Asie", "equities", "", [
        ("nikkei", "Nikkei"), ("hangseng", "Hang Seng"),
        ("shanghai", "Shanghai")], ["asie"]),
    ("crypto", "Crypto", "crypto", " $", [
        ("btc", "Bitcoin"), ("eth", "Ethereum")], ["btc", "eth"]),
]

GLOBAL_INDEX = ("msci_world", "MSCI World", "equities")

# Rattache un actif du lexique a la region qui le porte sur la page.
ASSET_ZONE = {"sp500": "amerique", "europe": "europe", "asie": "asie",
              "btc": "crypto", "eth": "crypto"}

ASSET_LABEL = {"sp500": "Amérique", "europe": "Europe", "asie": "Asie",
               "btc": "Bitcoin", "eth": "Ethereum", "msci_world": "Monde"}

SOURCE_NAMES = {
    "bce_press": "BCE", "bce_pub": "BCE", "fed_press_all": "Fed",
    "fed_press_monetary": "Fed", "fed_speeches": "Fed",
    "boe_news": "Bank of England", "boj_news": "Banque du Japon",
    "bis_cb_speeches": "BRI", "ec_press": "Commission européenne",
    "fsb_news": "CSF", "esrb_press": "CERS", "sec_press": "SEC",
    "esma_news": "ESMA", "amf_news": "AMF", "coindesk": "CoinDesk",
    "theblock": "The Block", "nikkei_asia": "Nikkei Asia",
    "cnbc_economy": "CNBC", "yahoo_finance": "Yahoo Finance",
    "investing_com": "Investing.com", "marketwatch": "MarketWatch",
}

# Ce texte est une exigence permanente du projet. Il ne doit jamais etre
# retire de la page, ni reformule pour en attenuer la portee.
DISCLAIMER = (
    "Ces indicateurs décrivent l'actualité. Ils ne prédisent rien. "
    "Aucune valeur prédictive n'a été démontrée à ce jour."
)

# Espace fine insecable : typographie francaise devant le signe pourcent, et
# elle empeche « −4,2 » de finir une ligne en laissant le « % » sur la suivante.
NBSP = " "


# --- Icone PNG generee sans dependance --------------------------------------

def png_bytes(width, height, rows):
    """Encode une image RGB en PNG. zlib et struct suffisent."""
    raw = b"".join(b"\x00" + b"".join(struct.pack("BBB", *px) for px in row)
                   for row in rows)

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def hex_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def build_icon(size):
    """Quatre barres, une par region, dans les couleurs d'accent."""
    bg = hex_rgb(TOKENS["bg"])
    rows = [[bg for _ in range(size)] for _ in range(size)]

    unit = size / 180.0
    baseline = int(146 * unit)
    bar_w = max(1, int(26 * unit))
    gap = max(1, int(11 * unit))
    left = int(27 * unit)

    for i, (height, zone) in enumerate(zip([64, 106, 48, 124], ZONES)):
        key = zone[0]
        colour = hex_rgb(REGION_ACCENTS[key])
        x0 = left + i * (bar_w + gap)
        x1 = min(size, x0 + bar_w)
        y0 = max(0, baseline - int(height * unit))
        for y in range(y0, min(size, baseline)):
            for x in range(x0, x1):
                rows[y][x] = colour

    rail = hex_rgb("#232833")
    for y in range(baseline, min(size, baseline + max(1, int(4 * unit)))):
        for x in range(left, min(size, int(154 * unit))):
            rows[y][x] = rail

    return png_bytes(size, size, rows)


# --- Outils -----------------------------------------------------------------

def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def number(value, decimals=2):
    """Format francais : espace pour les milliers, virgule pour les decimales."""
    if value is None:
        return "--"
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", " ").replace(".", ",")


def price_text(value, unit):
    if value is None:
        return "--"
    return number(value, 0 if value >= 1000 else 2) + unit


def percent(value):
    """Pourcentage signe a la francaise : virgule, vrai signe moins."""
    return f"{value:+.1f}{NBSP}%".replace(".", ",").replace("-", "−")


def safe_url(url):
    """N'accepte que http(s) : le contenu des flux n'est pas de confiance."""
    return url if url.startswith(("http://", "https://")) else "#"


def parse_date(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def ago(published, now):
    """Anciennete en clair : « il y a 40 min », « il y a 3 h », « hier »."""
    if not published:
        return ""
    minutes = int((now - published).total_seconds() // 60)
    if minutes < 60:
        return f"il y a {max(minutes, 1)} min"
    hours = minutes // 60
    if hours < 24:
        return f"il y a {hours} h"
    days = hours // 24
    return "hier" if days == 1 else f"il y a {days} j"


def esc(value):
    return html.escape(value or "")


def attr(value):
    return html.escape(value or "", quote=True)


# --- Marches ----------------------------------------------------------------

TREND_BADGE = {
    "haussiere": ("Haussière", "badge-up", "trend_up"),
    "baissiere": ("Baissière", "badge-down", "trend_down"),
    "indecise": ("Sans direction", "badge-flat", "trend_flat"),
}


def zone_verdict(blocks):
    """Verdict d'une zone a partir de la tendance de chacun de ses indices.

    Les etats sont calcules et stockes par macro.py : la page ne fait que
    les mettre en forme. La regle ne vit qu'a un seul endroit.
    """
    trends = [b.get("trend") for b in blocks if b.get("trend")]
    if not trends:
        return "Données indisponibles", "badge-flat", "trend_flat", ""

    up = trends.count("haussiere")
    down = trends.count("baissiere")
    total = len(trends)

    def tous(position):
        # Le pluriel suit le nombre d'indices reellement disponibles : une
        # zone dont un seul indice a repondu ne dit pas « les 1 indices ».
        if total == 1:
            return f"Seul indice disponible : {position} ses moyennes 50 et 200 jours."
        if total == 2:
            return f"Les deux indices {position} leurs moyennes 50 et 200 jours."
        return f"Les {total} indices {position} leurs moyennes 50 et 200 jours."

    if up == total:
        return "Haussière", "badge-up", "trend_up", tous("au-dessus de")
    if down == total:
        return "Baissière", "badge-down", "trend_down", tous("sous")
    if up == 0 and down == 0:
        return ("Sans direction", "badge-flat", "trend_flat",
                f"Aucun des {total} indices n'est clairement orienté."
                if total > 1 else "Indice sans orientation claire.")

    parts = []
    if up:
        parts.append(f"{up} en hausse")
    if down:
        parts.append(f"{down} en baisse")
    undecided = total - up - down
    if undecided:
        parts.append(f"{undecided} sans direction")
    return ("Partagée", "badge-flat", "trend_flat",
            f"Sur {total} indices : {', '.join(parts)}.")


def history_closes(macro, key, limit=30):
    """Serie des clotures relevees par l'outil, tous formats d'historique.

    Les journees enregistrees avant l'ajout du sous-objet `assets` rangeaient
    la cloture a plat. Les lire aussi evite de perdre une semaine de courbe
    pour une raison de format.
    """
    history = (macro or {}).get("history") or {}
    points = []
    for day in sorted(history):
        entry = history[day] or {}
        assets = entry.get("assets") or {}
        value = None
        if isinstance(assets.get(key), dict):
            value = assets[key].get("close")
        elif isinstance(entry.get(key), (int, float)):
            value = entry[key]
        if isinstance(value, (int, float)):
            points.append(float(value))
    return points[-limit:]


def sparkline(points, width=76, height=26, colour=ACCENT):
    """Courbe minimale, en SVG, sans axe ni etiquette.

    Elle ne sert qu'a donner la forme des derniers jours. Sous quatre points,
    elle ne dirait rien de plus qu'une ligne droite : on ne l'affiche pas.
    """
    if len(points) < 4:
        return ""
    low, high = min(points), max(points)
    span = (high - low) or 1.0
    step = width / (len(points) - 1)
    coords = [(i * step, height - 3 - (value - low) / span * (height - 6))
              for i, value in enumerate(points)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    rising = points[-1] >= points[0]
    stroke = GREEN if rising else RED
    area = (f"0,{height} " + line + f" {width},{height}")
    return (f'<svg class="market-spark" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" aria-hidden="true">'
            f'<polygon points="{area}" fill="{stroke}" opacity=".08"/>'
            f'<polyline points="{line}" fill="none" stroke="{stroke}" '
            'stroke-width="1.75" stroke-linecap="round" '
            'stroke-linejoin="round"/></svg>')


def breadth(macro):
    trends = []
    for _key, _label, section, _unit, indices, _news in ZONES:
        source = macro.get(section) or {}
        for key, _name in indices:
            trend = (source.get(key) or {}).get("trend")
            if trend:
                trends.append(trend)
    return trends.count("haussiere"), len(trends)


# --- Actualite --------------------------------------------------------------

def editorial_score(article):
    """Ce qui merite d'etre lu, plutot que ce qui vient de la source la plus lourde.

    L'importance seule fait remonter les bulletins administratifs : « Green
    notice 2026/02 » sort de la Bank of England avec le meme poids qu'une
    decision de taux. En la multipliant par l'intensite lexicale — la somme
    de ce que l'article declenche dans le lexique — les textes qui parlent
    reellement de taux, de crise ou de croissance passent devant les avis de
    publication. Le terme constant evite d'annuler un article dont le titre
    est sobre mais la source decisive.
    """
    intensity = sum((article.get("categories") or {}).values())
    return article.get("importance", 0) * (0.35 + intensity)


def clean_excerpt(text, title=""):
    """Extrait lisible, ou rien du tout.

    Plusieurs flux — la Fed en particulier — recopient le titre dans le
    resume. L'afficher donnerait une carte qui dit deux fois la meme phrase,
    ce qui fait moins serieux qu'une carte sans extrait. On compare donc les
    debuts normalises et on n'affiche que ce qui apporte quelque chose.
    """
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()

    def skeleton(value):
        return re.sub(r"\W+", "", (value or "").lower())[:60]

    if skeleton(text) == skeleton(title):
        return ""
    if len(text) <= EXCERPT_CHARS:
        return text
    cut = text[:EXCERPT_CHARS].rsplit(" ", 1)[0]
    return cut + "…"


def impact_words(article):
    """Importance et sens, en mots. Deux mesures distinctes, jamais melangees.

    L'importance vient de la source et du type d'article ; le sens vient du
    lexique. Un communique de banque centrale peut etre tres important et
    parfaitement neutre — les confondre en une seule note ferait dire au
    tableau ce qu'il ne mesure pas.
    """
    importance = article.get("importance", 0)
    if importance >= 1.5:
        level, css = "Impact élevé", "tag-high"
    elif importance >= 0.8:
        level, css = "Impact modéré", "tag"
    else:
        level, css = "Impact limité", "tag"

    tone = article.get("tone", 0)
    if tone >= 0.15:
        sense, colour = "favorable", GREEN
    elif tone <= -0.15:
        sense, colour = "défavorable", RED
    else:
        sense, colour = "neutre", FAINT
    return level, css, sense, colour


def feed_articles(articles, now):
    """Les articles du flux : recents, porteurs de signal, dedoublonnes.

    Deux garde-fous, tous deux constates sur les vraies donnees :

    Les depeches reprennent souvent le meme communique mot pour mot. Sans
    dedoublonnage sur le debut du titre, le flux affiche trois fois la meme
    nouvelle et donne l'impression qu'il ne s'est rien passe d'autre.

    Un classement purement global etouffe les regions peu bavardes : mesure
    ici, l'Asie ne placait qu'UN article sur trente, ce qui vide de son sens
    le filtre par region et la promesse d'une veille mondiale. Chaque region
    recoit donc un quota reserve, et les places restantes vont aux meilleurs
    articles quelle que soit leur origine.
    """
    cutoff = now - timedelta(hours=FEED_WINDOW_HOURS)
    pool = []
    for article in articles:
        if not article.get("categories") and article.get("scored_by") != "claude":
            continue
        published = parse_date(article.get("published_at"))
        if not published or published < cutoff:
            continue
        pool.append((editorial_score(article), published, article))

    pool.sort(key=lambda row: (-row[0], -row[1].timestamp()))

    seen = set()
    chosen = {}

    def take(score, published, article):
        fingerprint = re.sub(r"\W+", " ", article.get("title", "").lower())[:45]
        if fingerprint in seen or article["id"] in chosen:
            return False
        seen.add(fingerprint)
        chosen[article["id"]] = (score, published, article)
        return True

    for key, *_rest in ZONES:
        quota = 0
        for score, published, article in pool:
            zones = {ASSET_ZONE.get(a) for a in
                     (article.get("assets_effective") or [])}
            if key not in zones:
                continue
            if take(score, published, article):
                quota += 1
            if quota >= FEED_PER_ZONE:
                break

    for score, published, article in pool:
        if len(chosen) >= FEED_MAX:
            break
        take(score, published, article)

    ordered = sorted(chosen.values(), key=lambda row: (-row[0],
                                                       -row[1].timestamp()))
    return [(article, published) for _score, published, article in ordered]


def render_story(article, published, now):
    category = article.get("category", "marche")
    cat_label, cat_colour = CATEGORY_STYLE.get(category,
                                               ("Marché", TOKENS["dim"]))
    level, level_css, sense, sense_colour = impact_words(article)

    zones = sorted({ASSET_ZONE[a] for a in (article.get("assets_effective") or [])
                    if a in ASSET_ZONE})
    marches = [ASSET_LABEL[a] for a in (article.get("assets_effective") or [])
               if a in ASSET_LABEL]

    source = SOURCE_NAMES.get(article.get("source", ""), article.get("source", ""))
    excerpt = clean_excerpt(article.get("summary"), article.get("title"))
    url = attr(safe_url(article.get("url", "")))
    identifier = attr(article.get("id", ""))

    haystack = " ".join([article.get("title", ""), source, cat_label,
                         " ".join(marches), excerpt]).lower()

    tags = [f'<span class="tag tag-cat">{esc(cat_label)}</span>',
            f'<span class="{level_css}">{esc(level)}</span>',
            f'<span class="tag" style="color:{sense_colour}">Ton {esc(sense)}</span>']
    for name in marches[:3]:
        tags.append(f'<span class="tag">{esc(name)}</span>')

    return (
        f'<article class="card story reveal" data-story data-id="{identifier}" '
        f'data-zones="{attr(" ".join(zones))}" data-search="{attr(haystack)}" '
        f'style="--cat:{cat_colour}">'
        f'<div class="story-head">{"".join(tags)}</div>'
        f'<h3 class="story-title">{esc(article.get("title", ""))}</h3>'
        + (f'<p class="story-excerpt">{esc(excerpt)}</p>' if excerpt else "")
        + '<div class="story-foot">'
        f'<span class="story-src">{esc(source)}</span>'
        f'<span class="dotsep">·</span><span>{esc(ago(published, now))}</span>'
        '<span class="story-actions">'
        f'<button class="act" type="button" data-act="fav" aria-pressed="false" '
        f'title="Mettre en favori" aria-label="Mettre en favori">'
        f'{icon("star", 18)}</button>'
        f'<button class="act" type="button" data-act="later" aria-pressed="false" '
        f'title="Lire plus tard" aria-label="Lire plus tard">'
        f'{icon("clock", 18)}</button>'
        f'<a class="act" href="{url}" target="_blank" rel="noopener noreferrer" '
        f'title="Ouvrir la source" aria-label="Ouvrir la source">'
        f'{icon("external", 18)}</a>'
        '</span></div></article>')


def render_feed(articles, now):
    items = feed_articles(articles, now)
    if not items:
        return ""

    counts = {key: 0 for key, *_ in ZONES}
    for article, _ in items:
        for asset in article.get("assets_effective") or []:
            zone = ASSET_ZONE.get(asset)
            if zone:
                counts[zone] += 1

    chips = [f'<button class="chip" type="button" data-filter="tout" '
             f'aria-pressed="true">Tout<span class="chip-count">'
             f'{len(items)}</span></button>']
    for key, label, *_ in ZONES:
        chips.append(f'<button class="chip" type="button" data-filter="{key}" '
                     f'aria-pressed="false">{esc(label)}'
                     f'<span class="chip-count">{counts[key]}</span></button>')
    chips.append('<button class="chip" type="button" data-filter="fav" '
                 f'aria-pressed="false">{icon("star", 15)}Favoris</button>')
    chips.append('<button class="chip" type="button" data-filter="later" '
                 f'aria-pressed="false">{icon("clock", 15)}À lire</button>')

    stories = "".join(render_story(article, published, now)
                      for article, published in items)

    return (
        '<section class="section">'
        '<div class="section-head">'
        f'<p class="eyebrow">{icon("globe", 16)}L\'actualité financière</p>'
        f'<span class="section-sub"><span id="feed-count">{len(items)}</span> '
        f'articles · {FEED_WINDOW_HOURS // 24} derniers jours · classés par '
        'importance</span></div>'
        '<div class="toolbar">'
        f'<label class="search">{icon("search", 18)}'
        '<input id="q" type="search" placeholder="Rechercher un titre, une '
        'source, un marché…" aria-label="Rechercher dans l\'actualité">'
        '</label>'
        f'<div class="chips" role="group" aria-label="Filtres">{"".join(chips)}'
        '</div></div>'
        f'<div class="feed" id="feed">{stories}</div>'
        '<div class="card empty feed-wide" id="feed-empty" hidden>'
        '<strong>Aucun article ne correspond</strong>'
        'Essayez un autre mot-clé, ou revenez au filtre « Tout ».</div>'
        '</section>')


def zone_news_count(articles, asset_keys, now, days=NEWS_WINDOW_DAYS):
    cutoff = now - timedelta(days=days)
    keys = set(asset_keys)
    favorable = defavorable = 0
    for article in articles:
        if not keys & set(article.get("assets_effective") or []):
            continue
        if not article.get("categories") and article.get("scored_by") != "claude":
            continue
        published = parse_date(article.get("published_at"))
        if not published or published < cutoff:
            continue
        tone = article.get("tone", 0)
        if tone >= 0.15:
            favorable += 1
        elif tone <= -0.15:
            defavorable += 1
    return favorable, defavorable


def balance_word(favorable, defavorable):
    """Qualifie le rapport de force entre articles, sans l'aplatir.

    On compte au lieu de moyenner : 14 articles favorables et 9 defavorables
    donnent une moyenne de 0,00, et afficher « neutre » laisserait croire
    qu'il ne se passe rien alors que l'actualite est nourrie mais partagee.
    """
    if favorable == 0 and defavorable == 0:
        return "rien de marquant", GRAY
    if favorable >= defavorable * 2:
        return "plutôt favorable", GREEN
    if defavorable >= favorable * 2:
        return "plutôt défavorable", RED
    return "partagée", GRAY


# --- En-tete ----------------------------------------------------------------

def render_topbar(stamp):
    return (
        '<div class="topbar"><div class="topbar-in">'
        f'<span class="brand"><span class="brand-mark">{icon("spark", 17)}</span>'
        '<span class="brand-name">Veille économique</span></span>'
        f'<span class="live"><span class="live-dot"></span>{esc(stamp)}</span>'
        '</div></div>')


def render_hero(macro, articles, backtest, now):
    up, total = breadth(macro)
    favorable = defavorable = 0
    for _key, _label, _section, _unit, _indices, news_keys in ZONES:
        plus, moins = zone_news_count(articles, news_keys, now)
        favorable += plus
        defavorable += moins
    word, word_colour = balance_word(favorable, defavorable)

    if total:
        colour = GREEN if up * 2 > total else (RED if up * 2 < total else DIM)
        lede = (f'<b style="color:{colour}">{up} des {total} marchés suivis</b> '
                'sont au-dessus de leurs moyennes 50 et 200 jours, et '
                f'l\'actualité de la semaine est <b style="color:{word_colour}">'
                f'{word}</b>.')
        tile_markets = f'{up}<span style="color:{FAINT}">/{total}</span>'
    else:
        lede = ('Les séries de marché sont momentanément indisponibles. '
                'L\'actualité, elle, continue d\'être collectée.')
        tile_markets = "--"

    vix = next((c for c in (backtest or {}).get("context") or []
                if c["label"].startswith("VIX")), None)
    fng = next((c for c in (backtest or {}).get("context") or []
                if "Fear" in c["label"]), None)
    events = ((load_json(DATA_DIR / "agenda.json", {})).get("upcoming") or [])
    next_event = events[0] if events else None

    # Libelles courts a dessein : sur un telephone, « Marches orientes a la
    # hausse » se casse en trois lignes au-dessus du chiffre et ruine la
    # lecture en un coup d'oeil que ces tuiles sont censees permettre.
    tiles = [
        ('trend_up', 'Marchés haussiers', tile_markets,
         'sur les dix indices suivis'),
        ('pulse', 'Ton de l\'actualité', esc(word.capitalize()),
         f'{favorable} pour · {defavorable} contre, sur 7 jours'),
    ]
    if vix:
        tiles.append(('gauge', 'Nervosité (VIX)', esc(vix["value"]),
                      esc(vix.get("sentence", ""))))
    if fng:
        tiles.append(('shield', 'Sentiment crypto', esc(fng["value"]),
                      esc(fng.get("sentence", ""))))
    if next_event and len(tiles) < 4:
        tiles.append(('calendar', 'Prochaine échéance',
                      esc(next_event["when"]), esc(next_event["label"])))

    cells = "".join(
        f'<div class="tile reveal"><span class="tile-label">'
        f'{icon(name, 15)}{esc(label)}</span>'
        f'<div class="tile-value">{value}</div>'
        f'<div class="tile-note">{note}</div></div>'
        for name, label, value, note in tiles[:4])

    return ('<header class="hero">'
            '<h1>L\'économie mondiale,<br>en un coup d\'œil.</h1>'
            f'<p class="hero-lede">{lede}</p>'
            f'<div class="tiles">{cells}</div></header>')


# --- L'essentiel, redige -----------------------------------------------------

def render_essentiel(synthese):
    """Les points a connaitre, rediges par Claude quand la cle existe.

    C'est le seul endroit du projet ou un modele de langage apporte ce qu'un
    lexique ne peut pas donner : transformer cent depeches en cinq phrases
    hierarchisees. Sans cle, la section dit comment l'obtenir plutot que de
    disparaitre en silence — sinon la fonction reste invisible et personne ne
    l'active jamais.
    """
    points = (synthese or {}).get("points") or []
    if not points:
        return ('<section class="section"><div class="card panel reveal">'
                f'<div class="panel-head">{icon("spark", 18)}'
                '<h2>L\'essentiel</h2></div>'
                '<p class="note">Une synthèse rédigée des points à connaître '
                's\'affichera ici dès qu\'une clé <code>ANTHROPIC_API_KEY</code> '
                'sera renseignée dans les secrets GitHub du dépôt. D\'ici là, '
                'l\'actualité est classée par importance dans le flux '
                'ci-dessous.</p></div></section>')

    items = "".join(f'<li class="point">{esc(point)}</li>' for point in points)
    return ('<section class="section"><div class="card panel reveal">'
            f'<div class="panel-head">{icon("spark", 18)}'
            '<h2>L\'essentiel</h2></div>'
            f'<ol class="points">{items}</ol>'
            f'<p class="note">Synthèse rédigée à partir des '
            f'{(synthese or {}).get("based_on", 0)} éléments les plus '
            'importants des 72 dernières heures.</p></div></section>')


# --- Ce qui a change ---------------------------------------------------------

RECENT_DAYS = 45
CHANGES_SHOWN = 4

# La locution porte son auxiliaire : « est passe » et « a perdu » ne se
# conjuguent pas pareil, un prefixe commun donnerait « a passe haussier ».
TREND_SHORT = {
    "haussiere": ("est passé haussier", GREEN, "trend_up"),
    "baissiere": ("est passé baissier", RED, "trend_down"),
    "indecise": ("a perdu sa direction", DIM, "trend_flat"),
}


def recent_changes(backtest):
    """Les actifs qui ont bascule recemment, du plus recent au plus ancien.

    Cette information vient des historiques longs, pas de la memoire de
    l'outil : elle est donc complete des le premier jour, au lieu de rester
    vide pendant des semaines le temps que l'outil accumule des releves.
    """
    changes = []
    for asset in ((backtest or {}).get("assets") or {}).values():
        current = asset.get("current") or {}
        days = current.get("days")
        trend = current.get("trend")
        if days is None or trend not in TREND_SHORT or days > RECENT_DAYS:
            continue
        changes.append((days, asset["label"], trend))
    return sorted(changes)


def render_changes(backtest):
    # Sans mesure du tout, la section disparait. Afficher « rien n'a bouge »
    # alors qu'on ne sait pas serait un mensonge par omission.
    if not ((backtest or {}).get("assets") or {}):
        return ""

    changes = recent_changes(backtest)
    if not changes:
        return ('<div class="card panel reveal">'
                f'<div class="panel-head">{icon("pulse", 18)}'
                '<h2>Ce qui a changé</h2></div>'
                f'<p class="note">Aucun basculement de tendance depuis '
                f'{RECENT_DAYS} jours. Une absence de mouvement est une '
                'information : rien ne s\'est retourné.</p></div>')

    rows = []
    for days, label, trend in changes[:CHANGES_SHOWN]:
        word, colour, glyph = TREND_SHORT[trend]
        quand = ("aujourd'hui" if days == 0 else
                 "hier" if days == 1 else f"il y a {days} j")
        rows.append(
            f'<li class="row row-flat"><span class="row-name">{esc(label)}</span>'
            f'<span class="row-word" style="color:{colour}">{word}</span>'
            f'<span class="row-value" style="font-size:14px;color:{FAINT}">'
            f'{quand}</span></li>')

    reste = len(changes) - len(rows)
    note = (f'{reste} autre{"s" if reste > 1 else ""} basculement'
            f'{"s" if reste > 1 else ""} plus ancien{"s" if reste > 1 else ""}, '
            f'dans les {RECENT_DAYS} derniers jours.' if reste > 0 else
            f'Changements d\'état sur les {RECENT_DAYS} derniers jours.')

    return ('<div class="card panel reveal">'
            f'<div class="panel-head">{icon("pulse", 18)}'
            '<h2>Ce qui a changé</h2></div>'
            f'<ul class="rows">{"".join(rows)}</ul>'
            f'<p class="note">{note}</p></div>')


# --- Regions ----------------------------------------------------------------

def render_markets(macro, articles, now):
    cards = []
    for key, label, section, unit, indices, news_keys in ZONES:
        source = macro.get(section) or {}
        rows = [(name, source.get(k) or {}) for k, name in indices]
        state, badge_css, glyph, detail = zone_verdict([b for _, b in rows])
        accent = REGION_ACCENTS[key]

        quotes = "".join(
            f'<span class="quote">{esc(name)}<b>'
            f'{price_text(block.get("price"), unit)}</b></span>'
            for name, block in rows if block.get("price") is not None)

        curve = sparkline(history_closes(macro, indices[0][0]))
        favorable, defavorable = zone_news_count(articles, news_keys, now)
        word, word_colour = balance_word(favorable, defavorable)
        quotes = quotes or '<span class="quote">--</span>'

        cards.append(
            f'<section class="card market reveal" style="--accent:{accent}">'
            '<div class="market-top">'
            f'<span class="market-name">{esc(label)}</span>{curve}</div>'
            f'<div class="market-state"><span class="badge {badge_css}">'
            f'{icon(glyph, 15)}{esc(state)}</span></div>'
            f'<p class="market-detail">{esc(detail)}</p>'
            f'<div class="quotes">{quotes}</div>'
            f'<div class="market-foot">Actualité 7 jours : '
            f'<span style="color:{word_colour}">{word}</span> · {favorable} pour, '
            f'{defavorable} contre</div></section>')

    return f'<div class="markets">{"".join(cards)}</div>'


# --- Agenda -----------------------------------------------------------------

def render_agenda(agenda):
    events = (agenda or {}).get("upcoming") or []
    if not events:
        return ""
    rows = []
    for event in events:
        soon = " soon" if event.get("imminent") else ""
        rows.append(
            f'<li class="tl{soon}"><span class="tl-mark"></span>'
            '<span class="tl-body">'
            f'<span class="tl-when">{esc(event["when"])}</span>'
            f'<span class="tl-label">{esc(event["label"])}</span>'
            f'<span class="tl-date">{esc(event["date_fr"])}</span>'
            '</span></li>')
    return ('<div class="card panel reveal" style="padding:18px 0 4px">'
            f'<div class="panel-head" style="padding:0 18px">'
            f'{icon("calendar", 18)}<h2>À surveiller</h2></div>'
            '<p class="panel-sub" style="padding:0 18px">Décisions de taux '
            'des quatre banques centrales qui portent les zones suivies.</p>'
            f'<ul class="timeline">{"".join(rows)}</ul></div>')


# --- Analyses ----------------------------------------------------------------

ANALOGUE_SHOWN = 4
ANALOGUE_MIN_GAP = 1.0


def analogue_rows(backtest):
    rows = []
    for asset in ((backtest or {}).get("assets") or {}).values():
        similar = asset.get("analogues")
        base = asset.get("baseline")
        if not similar or not base:
            continue
        gap = similar["outcome"]["mean_pct"] - base["mean_pct"]
        rows.append((abs(gap), gap, asset, similar, base))
    return sorted(rows, key=lambda row: -row[0])


def render_analogues(backtest):
    """Ce qu'ont fait les seances passees ressemblant a celle d'aujourd'hui.

    C'est la question qu'on se pose reellement devant un cours : « c'est deja
    arrive, et ensuite ? ». Elle se repond sans rien predire, en comptant.
    """
    rows = analogue_rows(backtest)
    if not rows:
        return ""
    horizon = (backtest or {}).get("horizon_days", 20)
    notable = [row for row in rows if row[0] >= ANALOGUE_MIN_GAP]
    shown = (notable or rows)[:ANALOGUE_SHOWN]

    items = []
    for _, gap, asset, similar, base in shown:
        colour = GREEN if gap > 0 else (RED if gap < 0 else DIM)
        items.append(
            '<li class="row"><span class="row-top">'
            f'<span class="row-name">{esc(asset["label"])}</span>'
            f'<span class="row-value" style="color:{colour}">'
            f'{percent(similar["outcome"]["mean_pct"])}</span></span>'
            f'<span class="row-line">{percent(similar["current_stretch"])} par '
            f'rapport à sa moyenne 200 jours — les {similar["outcome"]["days"]} '
            'séances comparables ont été suivies de '
            f'{percent(similar["outcome"]["mean_pct"])} en {horizon} séances, '
            f'contre {percent(base["mean_pct"])} pour une séance quelconque.'
            '</span></li>')

    reste = len(rows) - len(shown)
    note = ('Chaque marché est découpé en cinq paquets selon son écart à la '
            'moyenne 200 jours ; on regarde ce qu\'ont fait les séances du '
            'même paquet. Découpage fait par les données, aucun seuil choisi '
            'à la main. Ce qui a suivi n\'est pas ce qui suivra.')
    if reste > 0:
        note = (f'Les {reste} autres marchés sont proches de leur moyenne '
                'générale. ') + note

    return ('<div class="card panel reveal">'
            f'<div class="panel-head">{icon("layers", 18)}'
            '<h2>Situations comparables</h2></div>'
            '<p class="panel-sub">C\'est déjà arrivé — et ensuite ?</p>'
            f'<ul class="rows">{"".join(items)}</ul>'
            f'<p class="note">{note}</p></div>')


PHASE_PERCENTILE = 90
PHASE_FLOOR = 15
PHASE_SHOWN = 3


def long_phases(backtest):
    found = []
    for asset in ((backtest or {}).get("assets") or {}).values():
        current = asset.get("current") or {}
        sessions = current.get("sessions") or 0
        rank = current.get("longer_than_pct")
        if rank is None or sessions < PHASE_FLOOR or rank < PHASE_PERCENTILE:
            continue
        found.append((rank, sessions, asset["label"], current))
    return sorted(found, reverse=True)


def render_long_phases(backtest):
    phases = long_phases(backtest)
    if not phases:
        return ""
    rows = []
    for rank, sessions, label, current in phases[:PHASE_SHOWN]:
        word, _css, _glyph = TREND_BADGE.get(current["trend"],
                                             ("état inconnu", "", ""))
        colour = (GREEN if current["trend"] == "haussiere"
                  else RED if current["trend"] == "baissiere" else DIM)
        rows.append(
            '<li class="row"><span class="row-top">'
            f'<span class="row-name">{esc(label)}</span>'
            f'<span class="row-value" style="color:{colour}">{sessions} '
            'séances</span></span>'
            f'<span class="row-line">tendance {esc(word.lower())} sans '
            f'interruption — plus long que {rank} % des '
            f'{current.get("past_phases", 0)} phases de même nature qu\'a '
            'connues ce marché.</span></li>')
    return ('<div class="card panel reveal">'
            f'<div class="panel-head">{icon("clock", 18)}'
            '<h2>Phases qui durent</h2></div>'
            '<p class="panel-sub">Inhabituellement longues pour ce marché.</p>'
            f'<ul class="rows">{"".join(rows)}</ul>'
            '<p class="note">Une phase longue ne se retourne pas parce '
            'qu\'elle est longue : c\'est un repère, pas un signal.</p></div>')


VERDICT_STYLE = {
    "signal utile": ("a séparé les deux cas", GREEN),
    "signal faible": ("a peu séparé", DIM),
    "sans valeur": ("n'a rien séparé", RED),
    "signal inversé": ("a séparé à l'envers", RED),
    "non mesurable": ("pas assez d'historique", DIM),
}


def render_verdicts(backtest):
    """Ce que le signal affiche plus haut a reellement valu par le passe.

    C'est la section qui manque a toutes les applications de finance grand
    public : celle qui dit quand l'indicateur affiche du vide.
    """
    assets = (backtest or {}).get("assets") or {}
    if not assets:
        return ""
    horizon = backtest.get("horizon_days", 20)
    ordered = sorted(assets.values(),
                     key=lambda a: (a.get("edge_pct") is None,
                                    -(a.get("edge_pct") or 0)))
    rows = []
    for asset in ordered:
        word, colour = VERDICT_STYLE.get(asset.get("verdict"),
                                         ("non mesuré", DIM))
        edge = asset.get("edge_pct")
        chiffre = ("--" if edge is None
                   else f"{edge:+.1f}{NBSP}pt".replace(".", ",").replace("-", "−"))
        rows.append(
            f'<li class="row row-flat"><span class="row-name">'
            f'{esc(asset["label"])}</span>'
            f'<span class="row-word" style="color:{colour}">{word}</span>'
            f'<span class="row-value" style="font-size:15px;color:{FAINT}">'
            f'{chiffre}</span></li>')

    useless = sum(1 for a in assets.values()
                  if a.get("verdict") in ("sans valeur", "signal faible"))
    resume = (f'Sur {len(assets)} marchés suivis, le signal de tendance n\'a '
              f'rien apporté sur {useless} d\'entre eux.'
              if useless else
              'Le signal a séparé les deux cas sur tous les marchés suivis.')

    return ('<div class="card panel reveal">'
            f'<div class="panel-head">{icon("gauge", 18)}'
            '<h2>Ce que valent ces signaux</h2></div>'
            '<p class="panel-sub">Mesuré, pas supposé.</p>'
            f'<ul class="rows">{"".join(rows)}</ul>'
            f'<p class="note">{resume} L\'écart est la différence de '
            f'performance moyenne sur {horizon} séances entre les journées '
            'classées haussières et baissières. Mesure faite après coup, sur '
            'les mêmes données : elle dit ce qui s\'est passé, pas ce qui se '
            'passera.</p></div>')


def render_correlations(backtest):
    items = (backtest or {}).get("correlations") or []
    if not items:
        return ""
    rows = []
    for item in items:
        value = f'{item["value"]:+.2f}'.replace(".", ",").replace("-", "−")
        colour = DIM if abs(item["value"]) < 0.3 else TEXT
        rows.append(
            '<li class="row"><span class="row-top">'
            f'<span class="row-name">{esc(item["label"])}</span>'
            f'<span class="row-value" style="color:{colour}">{value}</span>'
            f'</span><span class="row-line">{esc(item["word"])} — mesuré sur '
            f'{item["sessions"]} séances communes aux deux marchés.'
            '</span></li>')
    return ('<div class="card panel reveal">'
            f'<div class="panel-head">{icon("layers", 18)}'
            '<h2>Ce qui bouge avec quoi</h2></div>'
            '<p class="panel-sub">Deux paris, ou le même ?</p>'
            f'<ul class="rows">{"".join(rows)}</ul>'
            '<p class="note">Corrélation des variations quotidiennes, entre '
            '−1 et +1. Proche de 1, les deux marchés ne se diversifient pas '
            'l\'un l\'autre. Seules les journées cotées des deux côtés sont '
            'comparées : les cryptos cotent le week-end, pas les '
            'indices.</p></div>')


def render_context(backtest):
    items = (backtest or {}).get("context") or []
    if not items:
        return ""
    rows = []
    for item in items:
        rows.append(
            '<li class="row"><span class="row-top">'
            f'<span class="row-name">{esc(item["label"])}</span>'
            f'<span class="row-value">{esc(item["value"])}</span></span>'
            f'<span class="row-line">{esc(item.get("sentence", ""))}'
            '</span></li>')
    return ('<div class="card panel reveal">'
            f'<div class="panel-head">{icon("gauge", 18)}'
            '<h2>En perspective</h2></div>'
            '<p class="panel-sub">Chaque chiffre face à sa propre histoire.</p>'
            f'<ul class="rows">{"".join(rows)}</ul>'
            '<p class="note">Un niveau rare décrit le présent ; il ne dit '
            'rien de la suite.</p></div>')


# --- Mesure en direct, tenue en reserve -------------------------------------

def reliability(macro):
    """Confronte chaque signal passe au rendement du lendemain.

    Cette mesure-ci n'est pas affichee : le backtest la devance sur tous les
    points, il porte sur des annees plutot que sur les quelques jours
    accumules. Elle continue d'etre calculee et rapportee en console, parce
    qu'elle a une qualite que le backtest n'aura jamais : elle est
    enregistree en direct, sans connaitre la suite. Le jour ou elle aura
    assez d'observations, elle pourra contredire le backtest — et ce sera
    elle qui aura raison.
    """
    history = (macro or {}).get("history") or {}
    days = sorted(history)
    buckets = {"haussiere": [], "baissiere": [], "indecise": []}
    observations = 0
    for earlier, later in zip(days, days[1:]):
        before = (history[earlier] or {}).get("assets") or {}
        after = (history[later] or {}).get("assets") or {}
        for key, entry in before.items():
            if not isinstance(entry, dict):
                continue
            trend = entry.get("trend")
            close = entry.get("close")
            next_close = (after.get(key) or {}).get("close")
            if trend in buckets and close and next_close:
                buckets[trend].append(next_close / close - 1)
                observations += 1
    return observations, buckets


# --- Page -------------------------------------------------------------------

def render_page(articles, macro, agenda, synthese, backtest, generated_at):
    now = datetime.now(timezone.utc)
    stamp = generated_at.strftime("%d/%m à %H:%M")

    panels = "".join(filter(None, [
        render_changes(backtest),
        render_agenda(agenda),
        render_analogues(backtest),
        render_long_phases(backtest),
        render_verdicts(backtest),
        render_correlations(backtest),
        render_context(backtest),
    ]))

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Veille économique</title>
<meta name="description" content="Veille macro et actualité financière mondiale — Amérique, Europe, Asie, crypto.">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="{TOKENS['bg']}">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Veille">
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="192x192" href="icon-192.png">
<style>{stylesheet()}</style>
</head>
<body>
{render_topbar(stamp)}
<main class="shell">
{render_hero(macro, articles, backtest, now)}
{render_essentiel(synthese)}

<section class="section">
<p class="eyebrow">{icon("globe", 16)}Les marchés, région par région</p>
{render_markets(macro, articles, now)}
</section>

{render_feed(articles, now)}

<section class="section">
<p class="eyebrow">{icon("layers", 16)}Contexte et mesures</p>
<div class="grid">{panels}</div>
</section>
</main>

<!-- Bandeau permanent : ne jamais retirer. -->
<div class="disclaimer" role="note">{esc(DISCLAIMER)}</div>
<script>{SCRIPT}</script>
</body>
</html>
"""


MANIFEST = {
    "name": "Veille économique",
    "short_name": "Veille",
    "start_url": "./index.html",
    "scope": "./",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": TOKENS["bg"],
    "theme_color": TOKENS["bg"],
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png",
         "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png",
         "purpose": "any"},
    ],
}


def main():
    articles = load_json(DATA_DIR / "articles.json", [])
    macro = load_json(DATA_DIR / "macro.json", {})
    agenda = load_json(DATA_DIR / "agenda.json", {})
    synthese = load_json(DATA_DIR / "synthese.json", {})
    backtest = load_json(DATA_DIR / "backtest.json", {})

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).astimezone(PARIS)
    now = datetime.now(timezone.utc)

    page = render_page(articles, macro, agenda, synthese, backtest,
                       generated_at)
    (DOCS_DIR / "index.html").write_text(page, encoding="utf-8")

    with open(DOCS_DIR / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(MANIFEST, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    for name, size in (("apple-touch-icon.png", 180), ("icon-192.png", 192),
                       ("icon-512.png", 512)):
        (DOCS_DIR / name).write_bytes(build_icon(size))

    size_kb = (DOCS_DIR / "index.html").stat().st_size / 1024
    print(f"docs/index.html genere ({size_kb:.1f} Ko)")
    for _key, label, section, _unit, indices, news_keys in ZONES:
        source = macro.get(section) or {}
        blocks = [source.get(k) or {} for k, _ in indices]
        state, _, _, _ = zone_verdict(blocks)
        plus, moins = zone_news_count(articles, news_keys, now)
        courbe = "courbe" if sparkline(history_closes(macro, indices[0][0])) else "--"
        print(f"  {label:<10} {state:<16} actu {plus}+/{moins}-  {courbe}")
    print(f"  flux      : {len(feed_articles(articles, now))} article(s)")
    print(f"  backtest  : {len(backtest.get('assets') or {})} marche(s), "
          f"{len(recent_changes(backtest))} basculement(s) recent(s)")
    print(f"  agenda    : {len(agenda.get('upcoming') or [])} echeance(s)")
    observations, _ = reliability(macro)
    print(f"  mesure en direct (hors page) : {observations} observation(s)")


if __name__ == "__main__":
    main()
