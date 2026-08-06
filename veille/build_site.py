#!/usr/bin/env python3
"""Genere docs/index.html : une page statique unique, servie par GitHub Pages.

La page est d'abord un JOURNAL. Elle repond, dans cet ordre :

  1. Qu'est-ce qui a bouge depuis la derniere fois ?
  2. Que raconte l'actualite financiere, region par region ? — Amerique,
     Europe, Asie, Crypto, chacune avec l'etat de ses marches ET les titres
     qui la concernent.
  3. Quelles echeances arrivent ?
  4. Ce que valent ces signaux, et ou en sont les chiffres dans leur
     histoire — la partie analytique, volontairement placee apres.

L'actualite passe devant parce que c'est ce qu'on vient chercher. Les
mesures restent, mais elles servent la lecture au lieu de l'ouvrir.

Contraintes tenues ici :
  - un seul fichier HTML, CSS inclus dedans ;
  - aucun framework, aucune compilation, aucune dependance externe ;
  - donnees injectees a la generation : la page ne fait aucune requete ;
  - pensee pour un iPhone 14 (390 pt), une seule colonne, theme sombre ;
  - aucun texte sous 14 px, aucune zone tactile sous 44 pt.

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

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT.parent / "docs"

PARIS = ZoneInfo("Europe/Paris")

NEWS_WINDOW_DAYS = 7        # fenetre du decompte favorable/defavorable
HEADLINE_WINDOW_HOURS = 72  # fenetre des titres affiches
HEADLINES_PER_ZONE = 3

# --- Palette ---------------------------------------------------------------
# Fond profond, surfaces legerement plus claires, une couleur d'accent par
# region. La couleur ne porte jamais seule l'information : chaque etat reste
# double d'un mot, l'accent ne sert qu'a distinguer les regions entre elles.

BG = "#0a0c10"
SURFACE = "#12151b"
SURFACE_2 = "#171b22"
BORDER = "#232833"
BORDER_SOFT = "#1c212a"
TEXT = "#eaeef4"
TEXT_DIM = "#98a2b2"
TEXT_FAINT = "#6f7a8a"
GREEN = "#5ec48f"
RED = "#e0736b"
GRAY = "#8b94a3"

# (cle, libelle, section macro.json, unite, [(indice, nom)], [actifs], accent)
ZONES = [
    ("amerique", "Amérique", "equities", "", [
        ("sp500", "S&P 500"), ("nasdaq", "Nasdaq")], ["sp500"], "#6aa9ff"),
    ("europe", "Europe", "equities", "", [
        ("eurostoxx", "Euro Stoxx 50"), ("cac40", "CAC 40"), ("dax", "DAX")],
        ["europe"], "#a78bfa"),
    ("asie", "Asie", "equities", "", [
        ("nikkei", "Nikkei"), ("hangseng", "Hang Seng"),
        ("shanghai", "Shanghai")], ["asie"], "#f0b45f"),
    ("crypto", "Crypto", "crypto", " $", [
        ("btc", "Bitcoin"), ("eth", "Ethereum")], ["btc", "eth"], "#4fd0b0"),
]

GLOBAL_INDEX = ("msci_world", "MSCI World", "equities")

# Noms lisibles des sources, pour la signature sous chaque titre.
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
    """Quatre barres, une par region suivie, dans les couleurs d'accent."""
    bg = hex_rgb(BG)
    rows = [[bg for _ in range(size)] for _ in range(size)]

    unit = size / 180.0
    baseline = int(148 * unit)
    bar_w = int(26 * unit)
    gap = int(10 * unit)
    left = int(26 * unit)

    heights = [62, 104, 46, 122]
    for i, (height, zone) in enumerate(zip(heights, ZONES)):
        colour = hex_rgb(zone[6])
        x0 = left + i * (bar_w + gap)
        x1 = min(size, x0 + bar_w)
        y0 = max(0, baseline - int(height * unit))
        for y in range(y0, min(size, baseline)):
            for x in range(x0, x1):
                rows[y][x] = colour

    rail = hex_rgb(BORDER)
    for y in range(baseline, min(size, baseline + max(1, int(4 * unit)))):
        for x in range(left, min(size, int(156 * unit))):
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
    return formatted.replace(",", " ").replace(".", ",")


def price_text(value, unit):
    if value is None:
        return "--"
    return number(value, 0 if value >= 1000 else 2) + unit


# Espace fine insecable : la typographie francaise en met une devant le
# signe pourcent, et elle empeche « −4,2 » de finir une ligne en laissant le
# « % » seul sur la suivante.
NBSP = " "


def percent(value):
    """Pourcentage signe a la francaise : virgule decimale, vrai signe moins.

    Le trait d'union et le signe moins sont deux caracteres differents ; la
    page affiche « −50 % » ailleurs, et melanger les deux se voit.
    """
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
    if days == 1:
        return "hier"
    return f"il y a {days} j"


# --- Verdict par zone -------------------------------------------------------

TREND_TEXT = {
    "haussiere": ("Tendance haussière", GREEN),
    "baissiere": ("Tendance baissière", RED),
    "indecise": ("Sans direction nette", GRAY),
}


def zone_verdict(blocks):
    """Verdict d'une zone a partir de la tendance de chacun de ses indices.

    Les etats sont calcules et stockes par macro.py : la page ne fait que
    les mettre en forme. La regle ne vit qu'a un seul endroit.
    """
    trends = [b.get("trend") for b in blocks if b.get("trend")]
    if not trends:
        return "Données indisponibles", GRAY, ""

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
        return "Tendance haussière", GREEN, tous("au-dessus de")
    if down == total:
        return "Tendance baissière", RED, tous("sous")

    if up == 0 and down == 0:
        return ("Sans direction nette", GRAY,
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
    return "Marchés partagés", GRAY, f"Sur {total} indices : {', '.join(parts)}."


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


def zone_headlines(articles, asset_keys, now, count=HEADLINES_PER_ZONE):
    """Les titres marquants d'une region, dedoublonnes.

    Les depeches reprennent souvent le meme communique mot pour mot ; sans
    dedoublonnage sur le debut du titre, une region affiche trois fois la
    meme nouvelle et donne l'impression qu'il ne s'est rien passe d'autre.
    """
    cutoff = now - timedelta(hours=HEADLINE_WINDOW_HOURS)
    keys = set(asset_keys)
    pool = []
    for article in articles:
        if not keys & set(article.get("assets_effective") or []):
            continue
        if not article.get("categories") and article.get("scored_by") != "claude":
            continue
        published = parse_date(article.get("published_at"))
        if not published or published < cutoff:
            continue
        pool.append((editorial_score(article), published, article))

    pool.sort(key=lambda row: (-row[0], -row[1].timestamp()))

    seen = set()
    kept = []
    for _, published, article in pool:
        fingerprint = re.sub(r"\W+", " ", article.get("title", "").lower())[:45]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        kept.append((article, published))
        if len(kept) >= count:
            break
    return kept


def render_headlines(articles, asset_keys, now):
    items = zone_headlines(articles, asset_keys, now)
    if not items:
        return ('<p class="no-news">Aucun titre marquant sur cette région '
                'ces trois derniers jours.</p>')
    rows = []
    for article, published in items:
        tone = article.get("tone", 0)
        if tone >= 0.15:
            dot = GREEN
        elif tone <= -0.15:
            dot = RED
        else:
            dot = TEXT_FAINT
        source = SOURCE_NAMES.get(article.get("source", ""),
                                  article.get("source", ""))
        url = html.escape(safe_url(article.get("url", "")), quote=True)
        rows.append(
            f'<a class="story" href="{url}" target="_blank" rel="noopener noreferrer">'
            f'<span class="story-dot" style="background:{dot}"></span>'
            f'<span class="story-body">'
            f'<span class="story-title">{html.escape(article.get("title", ""))}</span>'
            f'<span class="story-meta">{html.escape(source)}'
            f'<span class="story-sep">·</span>{ago(published, now)}</span>'
            '</span></a>')
    return "".join(rows)


def zone_news_count(articles, asset_keys, now, days=NEWS_WINDOW_DAYS):
    """Decompte d'articles favorables et defavorables sur la periode."""
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


# --- Les quatre regions -----------------------------------------------------

def render_regions(macro, articles, now):
    blocks = []
    for _key, label, section, unit, indices, news_keys, accent in ZONES:
        source = macro.get(section) or {}
        rows = [(name, source.get(k) or {}) for k, name in indices]
        state, colour, detail = zone_verdict([b for _, b in rows])

        quotes = "".join(
            f'<span class="quote"><span class="quote-name">'
            f'{html.escape(name)}</span>'
            f'<span class="quote-value">{price_text(block.get("price"), unit)}'
            '</span></span>'
            for name, block in rows if block.get("price") is not None)

        favorable, defavorable = zone_news_count(articles, news_keys, now)
        word, word_colour = balance_word(favorable, defavorable)
        tally = (f'<span class="tally">Actualité 7 jours : '
                 f'<span style="color:{word_colour}">{word}</span>'
                 f' · {favorable} pour, {defavorable} contre</span>')

        quotes = quotes or '<span class="quote">--</span>'
        blocks.append(
            f'<section class="region" style="--accent:{accent}">'
            '<header class="region-head">'
            f'<span class="region-name">{html.escape(label)}</span>'
            f'<span class="region-state" style="color:{colour}">'
            f'{html.escape(state)}</span>'
            '</header>'
            f'<p class="region-detail">{html.escape(detail)}</p>'
            f'<div class="quotes">{quotes}</div>'
            f'<div class="stories">{render_headlines(articles, news_keys, now)}</div>'
            f'<footer class="region-foot">{tally}</footer>'
            '</section>')

    key, label, section = GLOBAL_INDEX
    block = (macro.get(section) or {}).get(key) or {}
    if block.get("trend"):
        text, colour = TREND_TEXT[block["trend"]]
        blocks.append(
            f'<p class="global-line">{html.escape(label)} '
            f'{price_text(block.get("price"), "")} — '
            f'<span style="color:{colour}">{html.escape(text.lower())}</span></p>')

    return "".join(blocks)


# --- En-tete ----------------------------------------------------------------

def breadth(macro):
    """Combien de marches suivis sont orientes a la hausse, sur le total."""
    trends = []
    for _key, _label, section, _unit, indices, _news, _accent in ZONES:
        source = macro.get(section) or {}
        for key, _name in indices:
            trend = (source.get(key) or {}).get("trend")
            if trend:
                trends.append(trend)
    if not trends:
        return None, 0, 0
    return trends.count("haussiere"), len(trends), trends.count("baissiere")


def render_hero(macro, articles, now, stamp):
    up, total, down = breadth(macro)
    if total:
        colour = GREEN if up * 2 > total else (RED if up * 2 < total else GRAY)
        marches = (f'<span style="color:{colour}">{up} marché'
                   f'{"s" if up > 1 else ""} sur {total}</span> '
                   'au-dessus de leurs moyennes 50 et 200 jours')
    else:
        marches = "Données de marché indisponibles"

    favorable = defavorable = 0
    for _key, _label, _section, _unit, _indices, news_keys, _accent in ZONES:
        plus, moins = zone_news_count(articles, news_keys, now)
        favorable += plus
        defavorable += moins
    word, word_colour = balance_word(favorable, defavorable)

    return (
        '<header class="hero">'
        '<h1>Veille économique</h1>'
        f'<p class="hero-stamp">{stamp} · heure de Paris</p>'
        f'<p class="hero-line">{marches}.</p>'
        f'<p class="hero-line">Actualité <span style="color:{word_colour}">'
        f'{word}</span> sur les 7 derniers jours : {favorable} article'
        f'{"s" if favorable > 1 else ""} favorable'
        f'{"s" if favorable > 1 else ""}, {defavorable} défavorable'
        f'{"s" if defavorable > 1 else ""}.</p>'
        '</header>')


# --- L'essentiel, redige -----------------------------------------------------

def render_essentiel(synthese):
    """Les cinq points a connaitre, rediges par Claude quand la cle existe.

    C'est le seul endroit du projet ou un modele de langage apporte ce qu'un
    lexique ne peut pas donner : transformer cent depeches en cinq phrases
    hierarchisees. Sans cle, la section se reduit a une ligne qui dit
    comment l'obtenir, plutot que de disparaitre en silence — sinon la
    fonction reste invisible et personne ne l'active jamais.
    """
    points = (synthese or {}).get("points") or []
    if not points:
        return ('<section class="band"><h2>L\'essentiel</h2>'
                '<p class="band-empty">Une synthèse rédigée des points à '
                'connaître apparaîtra ici dès qu\'une clé '
                '<code>ANTHROPIC_API_KEY</code> sera renseignée dans les '
                'secrets GitHub du dépôt. D\'ici là, l\'actualité est '
                'présentée région par région, ci-dessous.</p></section>')

    items = "".join(f'<li class="point">{html.escape(point)}</li>'
                    for point in points)
    return ('<section class="band"><h2>L\'essentiel</h2>'
            f'<ol class="points">{items}</ol>'
            '<p class="note">Synthèse rédigée à partir des '
            f'{(synthese or {}).get("based_on", 0)} éléments les plus '
            'importants des 72 dernières heures.</p></section>')


# --- Ce qui a change ---------------------------------------------------------

RECENT_DAYS = 45

# Trois suffisent. Cette section repond a « pourquoi ouvrir aujourd'hui » ;
# au-dela elle repousse l'actualite — ce qu'on vient vraiment lire — sous le
# premier ecran.
CHANGES_SHOWN = 3

# La locution porte son auxiliaire : « est passe » et « a perdu » ne se
# conjuguent pas pareil, un prefixe commun donnerait « a passe haussier ».
TREND_SHORT = {
    "haussiere": ("est passé haussier", GREEN),
    "baissiere": ("est passé baissier", RED),
    "indecise": ("a perdu sa direction", GRAY),
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
        return ('<section class="band">'
                '<h2>Ce qui a changé</h2>'
                f'<p class="band-empty">Aucun basculement de tendance depuis '
                f'{RECENT_DAYS} jours sur les marchés suivis. Une absence de '
                'mouvement est une information : rien ne s\'est retourné.</p>'
                '</section>')

    chips = []
    for days, label, trend in changes[:CHANGES_SHOWN]:
        word, colour = TREND_SHORT[trend]
        quand = ("aujourd'hui" if days == 0 else
                 "hier" if days == 1 else f"il y a {days} j")
        chips.append(
            f'<li class="chip"><span class="chip-name">{html.escape(label)}</span>'
            f'<span class="chip-word" style="color:{colour}">{word}</span>'
            f'<span class="chip-when">{quand}</span></li>')

    reste = len(changes) - len(chips)
    note = (f'{reste} autre{"s" if reste > 1 else ""} basculement'
            f'{"s" if reste > 1 else ""} plus ancien{"s" if reste > 1 else ""}, '
            f'dans les {RECENT_DAYS} derniers jours.' if reste > 0 else
            f'Changements d\'état sur les {RECENT_DAYS} derniers jours.')

    return ('<section class="band">'
            '<h2>Ce qui a changé</h2>'
            f'<ul class="chips">{"".join(chips)}</ul>'
            f'<p class="note">{note}</p>'
            '</section>')


# --- Agenda -----------------------------------------------------------------

def render_agenda(agenda):
    events = (agenda or {}).get("upcoming") or []
    if not events:
        return ""
    rows = []
    for event in events:
        marker = ' soon' if event.get("imminent") else ""
        rows.append(
            f'<li class="event{marker}">'
            f'<span class="event-when">{html.escape(event["when"])}</span>'
            '<span class="event-body">'
            f'<span class="event-label">{html.escape(event["label"])}</span>'
            f'<span class="event-date">{html.escape(event["date_fr"])}</span>'
            '</span></li>')
    return ('<section class="band">'
            '<h2>À surveiller</h2>'
            f'<ul class="events">{"".join(rows)}</ul></section>')


# --- Situations comparables --------------------------------------------------

ANALOGUE_SHOWN = 4
ANALOGUE_MIN_GAP = 1.0


def analogue_rows(backtest):
    """Marches classes par ecart entre situation comparable et moyenne."""
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
        colour = GREEN if gap > 0 else (RED if gap < 0 else GRAY)
        items.append(
            '<li class="stat">'
            '<span class="stat-top">'
            f'<span class="stat-name">{html.escape(asset["label"])}</span>'
            f'<span class="stat-value" style="color:{colour}">'
            f'{percent(similar["outcome"]["mean_pct"])}</span></span>'
            f'<span class="stat-line">{percent(similar["current_stretch"])} par '
            'rapport à sa moyenne 200 jours — les '
            f'{similar["outcome"]["days"]} séances comparables ont été suivies '
            f'de {percent(similar["outcome"]["mean_pct"])} en {horizon} '
            f'séances, contre {percent(base["mean_pct"])} pour une séance '
            'quelconque.</span></li>')

    reste = len(rows) - len(shown)
    note = ('Chaque marché est découpé en cinq paquets selon son écart à la '
            'moyenne 200 jours ; on regarde ce qu\'ont fait les séances du '
            'même paquet. Découpage fait par les données, aucun seuil choisi '
            'à la main. Ce qui a suivi n\'est pas ce qui suivra.')
    if reste > 0:
        note = (f'Les {reste} autres marchés suivis sont proches de leur '
                'moyenne générale. ') + note

    return ('<section class="band">'
            '<h2>Des situations comparables</h2>'
            f'<ul class="stats">{"".join(items)}</ul>'
            f'<p class="note">{note}</p></section>')


# --- Phases qui durent -------------------------------------------------------

PHASE_PERCENTILE = 90
PHASE_FLOOR = 15
PHASE_SHOWN = 3


def long_phases(backtest):
    """Marches dont l'etat actuel dure plus longtemps que d'ordinaire."""
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
        word, colour = TREND_TEXT.get(current["trend"], ("état inconnu", GRAY))
        rows.append(
            '<li class="stat"><span class="stat-top">'
            f'<span class="stat-name">{html.escape(label)}</span>'
            f'<span class="stat-value" style="color:{colour}">{sessions} '
            'séances</span></span>'
            f'<span class="stat-line">{html.escape(word.lower())} sans '
            f'interruption — plus long que {rank} % des '
            f'{current.get("past_phases", 0)} phases de même nature qu\'a '
            'connues ce marché.</span></li>')
    return ('<section class="band">'
            '<h2>Des phases qui durent</h2>'
            f'<ul class="stats">{"".join(rows)}</ul>'
            '<p class="note">Comparaison avec les phases passées du même '
            'marché. Une phase longue ne se retourne pas parce qu\'elle est '
            'longue : c\'est un repère, pas un signal.</p></section>')


# --- Ce que valent les signaux ----------------------------------------------

# Formulations courtes a dessein : sur onze marches, une phrase entiere par
# ligne double la hauteur de la section sans rien ajouter au sens.
VERDICT_STYLE = {
    "signal utile": ("a séparé les deux cas", GREEN),
    "signal faible": ("a peu séparé", GRAY),
    "sans valeur": ("n'a rien séparé", RED),
    "signal inversé": ("a séparé à l'envers", RED),
    "non mesurable": ("pas assez d'historique", GRAY),
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
                                         ("non mesuré", GRAY))
        edge = asset.get("edge_pct")
        chiffre = ("--" if edge is None
                   else f"{edge:+.1f}{NBSP}pt".replace(".", ",")
                   .replace("-", "−"))
        rows.append(
            f'<li class="verdict"><span class="verdict-name">'
            f'{html.escape(asset["label"])}</span>'
            f'<span class="verdict-word" style="color:{colour}">{word}</span>'
            f'<span class="verdict-edge">{chiffre}</span></li>')

    useless = sum(1 for a in assets.values()
                  if a.get("verdict") in ("sans valeur", "signal faible"))
    resume = (f'Sur {len(assets)} marchés suivis, le signal de tendance n\'a '
              f'rien apporté sur {useless} d\'entre eux.'
              if useless else
              'Le signal de tendance a séparé les deux cas sur tous les '
              'marchés suivis.')

    return ('<section class="band">'
            '<h2>Ce que valent ces signaux</h2>'
            f'<ul class="verdicts">{"".join(rows)}</ul>'
            f'<p class="note">{resume} L\'écart est la différence de '
            f'performance moyenne sur {horizon} séances entre les journées '
            'classées haussières et les journées classées baissières. Mesure '
            'faite après coup, sur les mêmes données : elle dit ce qui s\'est '
            'passé, pas ce qui se passera.</p></section>')


# --- Correlations ------------------------------------------------------------

def render_correlations(backtest):
    """Ce qui bouge avec quoi, sur les 90 dernieres seances communes."""
    items = (backtest or {}).get("correlations") or []
    if not items:
        return ""
    rows = []
    for item in items:
        value = f'{item["value"]:+.2f}'.replace(".", ",").replace("-", "−")
        colour = GRAY if abs(item["value"]) < 0.3 else TEXT
        rows.append(
            '<li class="stat"><span class="stat-top">'
            f'<span class="stat-name">{html.escape(item["label"])}</span>'
            f'<span class="stat-value" style="color:{colour}">{value}</span>'
            f'</span><span class="stat-line">{html.escape(item["word"])} — '
            f'mesuré sur {item["sessions"]} séances communes aux deux '
            'marchés.</span></li>')
    return ('<section class="band">'
            '<h2>Ce qui bouge avec quoi</h2>'
            f'<ul class="stats">{"".join(rows)}</ul>'
            '<p class="note">Corrélation des variations quotidiennes, entre '
            '−1 et +1. Proche de 1, les deux marchés montent et descendent '
            'ensemble et ne se diversifient donc pas l\'un l\'autre. Seules '
            'les journées cotées des deux côtés sont comparées : les cryptos '
            'cotent le week-end, pas les indices.</p></section>')


# --- Reperes historiques -----------------------------------------------------

def render_context(backtest):
    items = (backtest or {}).get("context") or []
    if not items:
        return ""
    rows = []
    for item in items:
        rows.append(
            '<li class="stat"><span class="stat-top">'
            f'<span class="stat-name">{html.escape(item["label"])}</span>'
            f'<span class="stat-value">{html.escape(item["value"])}</span>'
            f'</span><span class="stat-line">'
            f'{html.escape(item.get("sentence", ""))}</span></li>')
    return ('<section class="band">'
            '<h2>Où on en est, en perspective</h2>'
            f'<ul class="stats">{"".join(rows)}</ul>'
            '<p class="note">Chaque chiffre est comparé à sa propre histoire. '
            'Un niveau rare décrit le présent ; il ne dit rien de la '
            'suite.</p></section>')


# --- Mesure en direct, tenue en reserve -------------------------------------

def reliability(macro):
    """Confronte chaque signal passe au rendement du lendemain.

    Cette mesure-ci n'est pas affichee sur la page : le backtest la devance
    sur tous les points, il porte sur des annees plutot que sur les quelques
    jours accumules. Elle continue pourtant d'etre calculee et rapportee en
    console, parce qu'elle a une qualite que le backtest n'aura jamais : elle
    est enregistree en direct, sans connaitre la suite. Le jour ou elle aura
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
            trend = entry.get("trend")
            close = entry.get("close")
            next_close = (after.get(key) or {}).get("close")
            if trend in buckets and close and next_close:
                buckets[trend].append(next_close / close - 1)
                observations += 1

    return observations, buckets


# --- Page -------------------------------------------------------------------

CSS = """
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0 auto;max-width:440px;background:__BG__;color:__TEXT__;
 font-size:17px;line-height:1.5;letter-spacing:-.005em;
 font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,
 Helvetica,Arial,sans-serif;
 padding:0 18px calc(84px + env(safe-area-inset-bottom));
 overflow-x:hidden;-webkit-font-smoothing:antialiased}

.hero{padding:34px 2px 22px;border-bottom:1px solid __BORDER__;margin-bottom:26px}
h1{margin:0;font-size:30px;line-height:1.1;font-weight:700;letter-spacing:-.03em}
.hero-stamp{margin:9px 0 18px;font-size:14px;color:__FAINT__;
 text-transform:uppercase;letter-spacing:.09em;font-weight:600}
.hero-line{margin:0 0 7px;font-size:17px;line-height:1.45;color:__DIM__}
.hero-line:last-child{margin-bottom:0}

h2{font-size:14px;margin:0 0 13px;font-weight:700;color:__FAINT__;
 text-transform:uppercase;letter-spacing:.11em}

.region{background:__SURFACE__;border:1px solid __BORDER__;border-radius:18px;
 padding:0;margin-bottom:16px;overflow:hidden;
 box-shadow:0 1px 0 rgba(255,255,255,.02) inset}
.region-head{display:flex;align-items:baseline;justify-content:space-between;
 gap:12px;padding:16px 18px 0;border-top:3px solid var(--accent)}
.region-name{font-size:21px;font-weight:700;letter-spacing:-.02em}
.region-state{font-size:15px;font-weight:600;text-align:right;flex:0 0 auto}
.region-detail{margin:5px 18px 0;font-size:15px;line-height:1.4;color:__DIM__}
.quotes{display:flex;flex-wrap:wrap;gap:7px;padding:13px 18px 15px}
.quote{display:inline-flex;gap:6px;align-items:baseline;background:__SURFACE2__;
 border:1px solid __BORDERSOFT__;border-radius:999px;padding:5px 11px;
 font-size:14px;font-variant-numeric:tabular-nums}
.quote-name{color:__DIM__}
.quote-value{color:__TEXT__;font-weight:600}

.stories{border-top:1px solid __BORDERSOFT__}
.story{display:flex;gap:11px;padding:14px 18px;min-height:44px;
 border-bottom:1px solid __BORDERSOFT__;text-decoration:none;color:inherit;
 -webkit-tap-highlight-color:transparent}
.story:last-child{border-bottom:0}
.story-dot{flex:0 0 auto;width:7px;height:7px;border-radius:50%;margin-top:8px}
.story-body{min-width:0}
.story-title{display:block;font-size:16px;line-height:1.38;
 overflow-wrap:anywhere}
.story-meta{display:block;margin-top:5px;font-size:14px;color:__FAINT__}
.story-sep{margin:0 6px}
.no-news{margin:0;padding:15px 18px;font-size:15px;color:__FAINT__}
.region-foot{padding:12px 18px 14px;background:__SURFACE2__;
 border-top:1px solid __BORDERSOFT__}
.tally{font-size:14px;color:__DIM__}
.global-line{margin:2px 2px 0;font-size:15px;color:__DIM__;
 font-variant-numeric:tabular-nums}

.band{margin-top:32px}
.band-empty{margin:0;background:__SURFACE__;border:1px solid __BORDER__;
 border-radius:16px;padding:15px 17px;font-size:16px;line-height:1.45;
 color:__DIM__}
.note{margin:10px 3px 0;font-size:14px;line-height:1.45;color:__FAINT__}

.points{list-style:none;counter-reset:pt;margin:0;padding:0;
 background:__SURFACE__;border:1px solid __BORDER__;border-radius:16px;
 overflow:hidden}
.point{counter-increment:pt;position:relative;padding:14px 17px 14px 46px;
 font-size:16px;line-height:1.45;border-bottom:1px solid __BORDERSOFT__}
.point:last-child{border-bottom:0}
.point::before{content:counter(pt);position:absolute;left:17px;top:14px;
 width:20px;height:20px;border-radius:50%;background:__SURFACE2__;
 border:1px solid __BORDER__;color:__FAINT__;font-size:14px;font-weight:700;
 line-height:19px;text-align:center}
.band-empty code{font-size:14px;background:__SURFACE2__;border-radius:5px;
 padding:1px 5px;overflow-wrap:anywhere}

.chips{list-style:none;margin:0;padding:0;background:__SURFACE__;
 border:1px solid __BORDER__;border-radius:16px;overflow:hidden}
.chip{display:flex;align-items:baseline;gap:9px;padding:11px 16px;
 font-size:16px;border-bottom:1px solid __BORDERSOFT__}
.chip:last-child{border-bottom:0}
.chip-name{font-weight:600;flex:0 0 auto}
.chip-word{flex:1;font-size:15px}
.chip-when{flex:0 0 auto;font-size:14px;color:__FAINT__;white-space:nowrap}

.events{list-style:none;margin:0;padding:0;background:__SURFACE__;
 border:1px solid __BORDER__;border-radius:16px;overflow:hidden}
.event{display:flex;gap:13px;align-items:baseline;padding:14px 17px;
 border-bottom:1px solid __BORDERSOFT__}
.event:last-child{border-bottom:0}
.event.soon .event-when{color:__RED__}
.event-when{flex:0 0 104px;font-size:14px;color:__DIM__;font-weight:600}
.event-body{flex:1;min-width:0}
.event-label{display:block;font-size:16px;line-height:1.35;
 overflow-wrap:anywhere}
.event-date{display:block;font-size:14px;color:__FAINT__;margin-top:3px}

.stats,.verdicts{list-style:none;margin:0;padding:0;background:__SURFACE__;
 border:1px solid __BORDER__;border-radius:16px;overflow:hidden}
.stat{padding:13px 17px;border-bottom:1px solid __BORDERSOFT__}
.stat:last-child,.verdict:last-child{border-bottom:0}
.stat-top{display:flex;gap:12px;align-items:baseline;justify-content:space-between}
.stat-name{font-size:16px;line-height:1.3;overflow-wrap:anywhere}
.stat-value{flex:0 0 auto;font-size:17px;font-weight:700;
 font-variant-numeric:tabular-nums}
.stat-line{display:block;margin-top:4px;font-size:14px;line-height:1.45;
 color:__FAINT__}
.verdict{display:flex;gap:11px;align-items:baseline;padding:12px 17px;
 border-bottom:1px solid __BORDERSOFT__}
.verdict-name{flex:0 0 96px;font-size:16px;overflow-wrap:anywhere}
.verdict-word{flex:1;font-size:15px;line-height:1.3}
.verdict-edge{flex:0 0 auto;font-size:15px;color:__DIM__;
 font-variant-numeric:tabular-nums}

.disclaimer{position:fixed;left:0;right:0;bottom:0;
 background:rgba(10,12,16,.94);backdrop-filter:blur(12px);
 -webkit-backdrop-filter:blur(12px);border-top:1px solid __BORDER__;
 color:__FAINT__;font-size:14px;line-height:1.4;text-align:center;
 padding:11px 18px calc(11px + env(safe-area-inset-bottom));z-index:10}
"""


def render_page(index, articles, macro, agenda, synthese, backtest,
                generated_at):
    css = CSS
    for token, colour in (("__BG__", BG), ("__SURFACE__", SURFACE),
                          ("__SURFACE2__", SURFACE_2), ("__BORDER__", BORDER),
                          ("__BORDERSOFT__", BORDER_SOFT), ("__TEXT__", TEXT),
                          ("__DIM__", TEXT_DIM), ("__FAINT__", TEXT_FAINT),
                          ("__RED__", RED)):
        css = css.replace(token, colour)

    now = datetime.now(timezone.utc)
    stamp = generated_at.strftime("%d/%m/%Y à %H:%M")

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Veille économique</title>
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="{BG}">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<meta name="apple-mobile-web-app-title" content="Veille">
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="192x192" href="icon-192.png">
<style>{css}</style>
</head>
<body>
{render_hero(macro, articles, now, stamp)}
{render_essentiel(synthese)}
{render_changes(backtest)}

<section class="band">
<h2>L'actualité, région par région</h2>
{render_regions(macro, articles, now)}
</section>

{render_agenda(agenda)}
{render_analogues(backtest)}
{render_long_phases(backtest)}
{render_verdicts(backtest)}
{render_correlations(backtest)}
{render_context(backtest)}

<!-- Bandeau permanent : ne jamais retirer. -->
<div class="disclaimer" role="note">{html.escape(DISCLAIMER)}</div>
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
    "background_color": BG,
    "theme_color": BG,
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png",
         "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png",
         "purpose": "any"},
    ],
}


def main():
    index = load_json(DATA_DIR / "index.json", {})
    articles = load_json(DATA_DIR / "articles.json", [])
    macro = load_json(DATA_DIR / "macro.json", {})
    agenda = load_json(DATA_DIR / "agenda.json", {})
    synthese = load_json(DATA_DIR / "synthese.json", {})
    backtest = load_json(DATA_DIR / "backtest.json", {})

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).astimezone(PARIS)

    page = render_page(index, articles, macro, agenda, synthese, backtest,
                       generated_at)
    (DOCS_DIR / "index.html").write_text(page, encoding="utf-8")

    with open(DOCS_DIR / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(MANIFEST, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    for name, size in (("apple-touch-icon.png", 180), ("icon-192.png", 192),
                       ("icon-512.png", 512)):
        (DOCS_DIR / name).write_bytes(build_icon(size))

    now = datetime.now(timezone.utc)
    size_kb = (DOCS_DIR / "index.html").stat().st_size / 1024
    print(f"docs/index.html genere ({size_kb:.1f} Ko)")
    for _key, label, section, _unit, indices, news_keys, _accent in ZONES:
        source = macro.get(section) or {}
        blocks = [source.get(k) or {} for k, _ in indices]
        state, _, _ = zone_verdict(blocks)
        titres = len(zone_headlines(articles, news_keys, now))
        plus, moins = zone_news_count(articles, news_keys, now)
        print(f"  {label:<10} {state:<22} {titres} titre(s), "
              f"actu {plus}+/{moins}-")
    print(f"  backtest  : {len(backtest.get('assets') or {})} marche(s), "
          f"{len(recent_changes(backtest))} basculement(s) recent(s)")
    print(f"  agenda    : {len(agenda.get('upcoming') or [])} echeance(s)")
    observations, _ = reliability(macro)
    print(f"  mesure en direct (hors page) : {observations} observation(s)")


if __name__ == "__main__":
    main()
