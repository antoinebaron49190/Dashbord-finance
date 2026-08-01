#!/usr/bin/env python3
"""Genere docs/index.html : une page statique unique, servie par GitHub Pages.

La page repond a deux questions, dans cet ordre :
  1. Ou en est chaque actif ? (S&P 500, MSCI World, Bitcoin, Ethereum)
  2. Que raconte l'actualite economique ?

Tout le reste a ete retire : un tableau de bord qu'on ne lit pas en dix
secondes sur un telephone ne sert a rien. Le graphique 90 jours, la liste
des 11 criteres et les 40 titres d'articles restent dans l'historique git
(commit da89e9f) si le besoin revient.

Contraintes tenues ici :
  - un seul fichier HTML, CSS et JS inclus dedans ;
  - aucun framework, aucune compilation, aucune dependance externe ;
  - donnees injectees a la generation : la page ne fait aucune requete ;
  - pensee pour un iPhone 14 (390 pt), une seule colonne, theme sombre.

Usage:
    python build_site.py
"""

import html
import json
import struct
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT.parent / "docs"

PARIS = ZoneInfo("Europe/Paris")
NEWS_WINDOW_DAYS = 7
HEADLINE_WINDOW_HOURS = 48

# --- Palette ---------------------------------------------------------------
# Sobre, sans degrade. La couleur ne porte jamais seule l'information :
# chaque etat est double d'un mot.

BG = "#0e1116"
BG_CARD = "#161b22"
BORDER = "#262c36"
TEXT = "#e6e9ee"
TEXT_DIM = "#98a1ad"
GREEN = "#5fa97c"
RED = "#cf6b62"
GRAY = "#8b94a1"

# Une carte par zone, pas par indice : dix marches en quatre cartes.
# Le dernier champ relie la zone aux actifs du lexique (analyzer.ASSETS), ce
# qui permet de mettre l'actualite en face du marche qu'elle concerne.
# (cle, libelle, section macro.json, unite, [(cle_indice, libelle)], [actifs])
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

# Reference mondiale, affichee en une ligne sous les zones.
GLOBAL_INDEX = ("msci_world", "MSCI World", "equities")

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
    """Quatre barres sur fond sombre : un rappel des quatre actifs suivis."""
    bg = hex_rgb(BG)
    bar = hex_rgb("#d5dae1")
    accent = hex_rgb("#7fb2f0")
    rows = [[bg for _ in range(size)] for _ in range(size)]

    unit = size / 180.0
    baseline = int(150 * unit)
    bar_w = int(24 * unit)
    gap = int(12 * unit)
    left = int(28 * unit)

    for i, height in enumerate([58, 96, 44, 118]):
        x0 = left + i * (bar_w + gap)
        x1 = min(size, x0 + bar_w)
        y0 = max(0, baseline - int(height * unit))
        colour = accent if i == 3 else bar
        for y in range(y0, min(size, baseline)):
            for x in range(x0, x1):
                rows[y][x] = colour

    for y in range(baseline, min(size, baseline + max(1, int(4 * unit)))):
        for x in range(left, min(size, int(160 * unit))):
            rows[y][x] = bar

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


def safe_url(url):
    """N'accepte que http(s) : le contenu des flux n'est pas de confiance."""
    return url if url.startswith(("http://", "https://")) else "#"


def parse_date(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


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
        # Le pluriel doit suivre le nombre d'indices reellement disponibles :
        # une zone dont un seul indice a repondu ne dit pas « les 1 indices ».
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


def breadth(macro):
    """Combien de marches suivis sont orientes a la hausse, sur le total.

    Une seule ligne, mais c'est la question que resument mal quatre cartes
    lues separement : le mouvement est-il general ou isole ?
    """
    trends = []
    for _key, _label, section, _unit, indices, _news in ZONES:
        source = macro.get(section) or {}
        for key, _name in indices:
            trend = (source.get(key) or {}).get("trend")
            if trend:
                trends.append(trend)
    if not trends:
        return ""
    up = trends.count("haussiere")
    total = len(trends)
    colour = GREEN if up * 2 > total else (RED if up * 2 < total else GRAY)
    return (f'<div class="breadth"><span style="color:{colour}">{up} '
            f'marché{"s" if up > 1 else ""} sur {total}</span> '
            'au-dessus de leurs moyennes 50 et 200 jours.</div>')


def zone_news(articles, asset_key, days=NEWS_WINDOW_DAYS):
    """Decompte d'articles favorables et defavorables pour une zone."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    favorable = defavorable = 0
    for article in articles:
        if asset_key not in (article.get("assets_effective") or []):
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


def render_zone_news(articles, asset_keys):
    """L'actualite de la zone, en une ligne, ou rien si le flux est muet."""
    favorable = defavorable = 0
    for key in asset_keys:
        plus, moins = zone_news(articles, key)
        favorable += plus
        defavorable += moins
    if not favorable and not defavorable:
        return ""
    word, colour = balance_word(favorable, defavorable)
    return (f'<div class="zone-news">Actualité 7 jours : '
            f'<span style="color:{colour}">{word}</span> — {favorable} '
            f'favorable{"s" if favorable > 1 else ""}, {defavorable} '
            f'défavorable{"s" if defavorable > 1 else ""}.</div>')


def render_zones(macro, articles):
    cards = [breadth(macro)]
    for _key, label, section, unit, indices, news_keys in ZONES:
        source = macro.get(section) or {}
        blocks = [(name, source.get(k) or {}) for k, name in indices]
        present = [b for _, b in blocks if b.get("price") is not None]
        state, colour, detail = zone_verdict([b for _, b in blocks])

        # Ligne de cours : « S&P 500 7 500 · Nasdaq 24 100 »
        quotes = " · ".join(
            f'<span class="q-name">{html.escape(name)}</span> '
            f'{price_text(block.get("price"), unit)}'
            for name, block in blocks if block.get("price") is not None)

        # Pour la crypto, la decote sur un an dit quelque chose que les
        # moyennes mobiles ne disent pas.
        extra = ""
        if section == "crypto" and present:
            drawdowns = [f'{name} −{block["drawdown_1y"] * 100:.0f} %'
                         for name, block in blocks
                         if block.get("drawdown_1y") is not None]
            if drawdowns:
                extra = (f'<div class="zone-extra">Sous le plus haut sur un an : '
                         f'{html.escape(" · ".join(drawdowns))}.</div>')

        cards.append(
            '<article class="zone">'
            f'<div class="zone-name">{html.escape(label)}</div>'
            f'<div class="zone-state" style="color:{colour}">{html.escape(state)}</div>'
            f'<div class="zone-detail">{html.escape(detail)}</div>'
            f'<div class="zone-quotes">{quotes or "--"}</div>'
            f'{extra}{render_zone_news(articles, news_keys)}</article>'
        )

    key, label, section = GLOBAL_INDEX
    block = (macro.get(section) or {}).get(key) or {}
    if block.get("trend"):
        text, colour = TREND_TEXT[block["trend"]]
        cards.append(
            f'<div class="global-line">{html.escape(label)} '
            f'{price_text(block.get("price"), "")} — '
            f'<span style="color:{colour}">{html.escape(text.lower())}</span></div>')

    return "".join(cards)


# --- Agenda -----------------------------------------------------------------

def render_agenda(agenda):
    events = (agenda or {}).get("upcoming") or []
    if not events:
        return ""
    rows = []
    for event in events:
        marker = ' class="soon"' if event.get("imminent") else ""
        rows.append(
            f'<li{marker}><span class="ag-when">{html.escape(event["when"])}</span>'
            f'<span class="ag-body"><span class="ag-label">'
            f'{html.escape(event["label"])}</span>'
            f'<span class="ag-date">{html.escape(event["date_fr"])}</span></span></li>')
    return f'<h2>À surveiller</h2><ul class="agenda">{"".join(rows)}</ul>'


# --- Actualite --------------------------------------------------------------

def news_overall(articles, days=NEWS_WINDOW_DAYS):
    """Decompte des articles favorables et defavorables sur la periode."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    favorable = defavorable = total = 0
    for article in articles:
        if not article.get("categories") and article.get("scored_by") != "claude":
            continue
        published = parse_date(article.get("published_at"))
        if not published or published < cutoff:
            continue
        total += 1
        tone = article.get("tone", 0)
        if tone >= 0.15:
            favorable += 1
        elif tone <= -0.15:
            defavorable += 1
    return favorable, defavorable, total


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


def average_over(index, key, days=NEWS_WINDOW_DAYS):
    values = []
    for day in sorted(index, reverse=True)[:days]:
        value = index[day].get(key)
        if value is not None:
            values.append(value)
    return sum(values) / len(values) if values else None


def top_headline(articles, hours=HEADLINE_WINDOW_HOURS):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent = [a for a in articles
              if (parse_date(a.get("published_at")) or cutoff) >= cutoff]
    if not recent:
        return None
    return max(recent, key=lambda a: (a.get("importance", 0),
                                      a.get("published_at", "")))


def render_news(index, articles, synthese):
    """La synthese redigee si elle existe, sinon le resume mecanique."""
    if synthese and synthese.get("points"):
        items = "".join(f"<li>{html.escape(point)}</li>"
                        for point in synthese["points"])
        note = ('<div class="news-note">Synthèse rédigée à partir des '
                f'{synthese.get("based_on", 0)} éléments les plus importants '
                'des 72 dernières heures.</div>')
        return f'<ul class="news">{items}</ul>{note}'

    lines = []
    word, colour = tone_word(average_over(index, "tone_cb"))
    lines.append('Banques centrales : ton '
                 f'<span style="color:{colour}">{word}</span> sur 7 jours.')

    favorable, defavorable, _ = news_overall(articles)
    word, colour = balance_word(favorable, defavorable)
    lines.append('Actualité générale : '
                 f'<span style="color:{colour}">{word}</span> — '
                 f'{favorable} favorables, {defavorable} défavorables sur 7 jours.')

    stress = average_over(index, "stress")
    if stress is not None:
        if stress >= 0.20:
            mot, colour = "élevée", RED
        elif stress >= 0.08:
            mot, colour = "modérée", GRAY
        else:
            mot, colour = "faible", GREEN
        lines.append('Part des sujets de crise : '
                     f'<span style="color:{colour}">{mot}</span> '
                     f'({stress * 100:.0f} % du flux).')

    body = "".join(f"<li>{line}</li>" for line in lines)
    note = ('<div class="news-note">Résumé mécanique. Une synthèse rédigée '
            'apparaîtra ici dès qu\'une clé ANTHROPIC_API_KEY sera '
            'renseignée dans les secrets GitHub.</div>')
    return f'<ul class="news">{body}</ul>{note}'


def tone_word(tone):
    if tone is None:
        return "pas de signal", GRAY
    if tone >= 0.15:
        return "favorable", GREEN
    if tone <= -0.15:
        return "défavorable", RED
    return "neutre", GRAY


def render_headline(articles):
    headline = top_headline(articles)
    if not headline:
        return ""
    url = html.escape(safe_url(headline.get("url", "")), quote=True)
    return (f'<a class="headline" target="_blank" rel="noopener noreferrer" href="{url}">'
            '<span class="headline-label">Le fait marquant</span>'
            f'<span class="headline-title">{html.escape(headline.get("title", ""))}</span>'
            '</a>')


# --- Ce qui a change ---------------------------------------------------------

# Au-dela, le basculement n'est plus une nouvelle.
RECENT_DAYS = 45

# Nombre de basculements affiches. Neuf lignes repoussaient les cartes de
# marche sous le premier ecran ; les plus recents suffisent a savoir s'il
# s'est passe quelque chose, le compte des autres est rappele en note.
CHANGES_SHOWN = 5

# La locution porte son auxiliaire : « est passé » et « a perdu » ne se
# conjuguent pas pareil, un prefixe commun donnerait « a passé haussier ».
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
    # alors qu'on ne sait pas serait un mensonge par omission : c'est
    # exactement ce que fait une jauge qui affiche zero quand elle est
    # debranchee.
    if not ((backtest or {}).get("assets") or {}):
        return ""

    changes = recent_changes(backtest)
    if not changes:
        return ('<h2>Ce qui a changé</h2><div class="reliab">'
                '<div class="reliab-progress">Aucun basculement de tendance '
                f'depuis {RECENT_DAYS} jours sur les marchés suivis.</div>'
                '<div class="reliab-note">Une absence de mouvement est une '
                'information : rien ne s\'est retourné, inutile de chercher '
                'quoi faire.</div></div>')

    rows = []
    for days, label, trend in changes[:CHANGES_SHOWN]:
        word, colour = TREND_SHORT[trend]
        quand = ("aujourd'hui" if days == 0 else
                 "hier" if days == 1 else f"il y a {days} jours")
        rows.append(f'<li><span class="chg-what">{html.escape(label)} '
                    f'<span style="color:{colour}">{word}</span></span>'
                    f'<span class="chg-when">{quand}</span></li>')

    reste = len(changes) - len(rows)
    note = (f'Les {len(rows)} basculements les plus récents. '
            if reste > 0 else '')
    note += (f'{reste} autre{"s" if reste > 1 else ""} plus ancien'
             f'{"s" if reste > 1 else ""}, dans les {RECENT_DAYS} derniers '
             'jours. ' if reste > 0 else
             f'Changements d\'état de tendance sur les {RECENT_DAYS} derniers '
             'jours. ')
    note += 'Le reste des marchés suivis est dans le même état qu\'avant.'

    return (f'<h2>Ce qui a changé</h2><ul class="agenda chg">{"".join(rows)}</ul>'
            f'<div class="news-note">{note}</div>')


# --- Ce que valent les signaux ----------------------------------------------

VERDICT_STYLE = {
    "signal utile": ("a séparé les deux cas", GREEN),
    "signal faible": ("a peu séparé les deux cas", GRAY),
    "sans valeur": ("n'a rien séparé du tout", RED),
    "signal inversé": ("a séparé les deux cas à l'envers", RED),
    "non mesurable": ("pas assez d'historique", GRAY),
}


def render_verdicts(backtest):
    """Ce que le signal affiche plus haut a réellement valu par le passé.

    C'est la section qui manque a toutes les applications de finance grand
    public : celle qui dit quand l'indicateur affiche du vide. Elle passe
    avant l'actualite parce qu'elle conditionne la lecture de tout le reste.
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
        chiffre = "--" if edge is None else f"{edge:+.1f} pt".replace(".", ",")
        rows.append(f'<li><span class="vd-name">{html.escape(asset["label"])}</span>'
                    f'<span class="vd-word" style="color:{colour}">{word}</span>'
                    f'<span class="vd-edge">{chiffre}</span></li>')

    useless = sum(1 for a in assets.values()
                  if a.get("verdict") in ("sans valeur", "signal faible"))
    resume = (f'Sur {len(assets)} marchés suivis, le signal de tendance n\'a '
              f'rien apporté sur {useless} d\'entre eux.'
              if useless else
              'Le signal de tendance a séparé les deux cas sur tous les '
              'marchés suivis.')

    return ('<h2>Ce que valent ces signaux</h2>'
            f'<ul class="verdicts">{"".join(rows)}</ul>'
            f'<div class="news-note">{resume} L\'écart affiché est la '
            f'différence de performance moyenne sur {horizon} séances entre '
            'les journées classées haussières et les journées classées '
            'baissières, mesurée sur l\'historique disponible. Mesure faite '
            'après coup, sur les mêmes données : elle dit ce qui s\'est passé, '
            'pas ce qui se passera.</div>')


# --- Situations comparables --------------------------------------------------

# Nombre de marches detailles. Au-dela, la section devient un tableau qu'on
# ne lit plus ; les marches ecartes sont comptes dans la note.
ANALOGUE_SHOWN = 5

# En deca, l'ecart avec la moyenne generale ne merite pas d'etre souligne.
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
        position = (percent(similar["current_stretch"])
                    + " par rapport à sa moyenne 200 jours")
        items.append(
            f'<li><span class="ctx-top">'
            f'<span class="ctx-label">{html.escape(asset["label"])}</span>'
            f'<span class="ctx-value" style="color:{colour}">'
            f'{percent(similar["outcome"]["mean_pct"])}</span></span>'
            f'<span class="ctx-sentence">{html.escape(position)} — '
            f'les {similar["outcome"]["days"]} séances comparables ont été '
            f'suivies de {percent(similar["outcome"]["mean_pct"])} en '
            f'{horizon} séances, contre {percent(base["mean_pct"])} pour une '
            f'séance quelconque.</span></li>')

    reste = len(rows) - len(shown)
    note = ('Chaque marché est découpé en cinq paquets selon son écart à la '
            'moyenne 200 jours, et on regarde ce qu\'ont fait les séances du '
            'même paquet. Découpage fait par les données, aucun seuil choisi '
            'à la main. Ce qui a suivi n\'est pas ce qui suivra.')
    if reste > 0:
        note = (f'Les {reste} autres marchés suivis sont proches de leur '
                'moyenne générale. ') + note

    return ('<h2>Des situations comparables</h2>'
            f'<ul class="context">{"".join(items)}</ul>'
            f'<div class="news-note">{note}</div>')


def percent(value):
    """Pourcentage signe a la francaise : virgule decimale, vrai signe moins.

    Le trait d'union et le signe moins sont deux caracteres differents ; la
    page affiche deja « −50 % » ailleurs, et melanger les deux se voit.
    """
    return f"{value:+.1f} %".replace(".", ",").replace("-", "−")


# --- Contexte : situer les chiffres du jour ---------------------------------

def render_context(backtest):
    items = (backtest or {}).get("context") or []
    if not items:
        return ""
    rows = []
    for item in items:
        rows.append(f'<li><span class="ctx-top">'
                    f'<span class="ctx-label">{html.escape(item["label"])}</span>'
                    f'<span class="ctx-value">{html.escape(item["value"])}</span>'
                    f'</span><span class="ctx-sentence">'
                    f'{html.escape(item.get("sentence", ""))}</span></li>')
    return ('<h2>Où on en est, en perspective</h2>'
            f'<ul class="context">{"".join(rows)}</ul>'
            '<div class="news-note">Chaque chiffre est comparé à sa propre '
            'histoire. Un niveau rare décrit le présent ; il ne dit rien de '
            'la suite.</div>')


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
body{margin:0 auto;background:__BG__;color:__TEXT__;font-size:16px;line-height:1.45;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 padding:0 16px calc(90px + env(safe-area-inset-bottom)) 16px;
 max-width:430px;overflow-x:hidden}
h1{font-size:20px;margin:22px 0 2px;font-weight:600;letter-spacing:-.01em}
h2{font-size:15px;margin:26px 0 10px;font-weight:600;color:__DIM__;
 text-transform:uppercase;letter-spacing:.07em}
.updated{color:__DIM__;font-size:15px;margin:0 0 16px}
.zone{background:__CARD__;border:1px solid __BORDER__;border-radius:12px;
 padding:13px 15px;margin-bottom:9px}
.zone-name{font-size:14px;color:__DIM__;text-transform:uppercase;
 letter-spacing:.07em;font-weight:600}
.zone-state{font-size:21px;font-weight:600;letter-spacing:-.01em;margin:3px 0 3px}
.zone-detail{font-size:15px;line-height:1.4}
.zone-quotes{font-size:15px;color:__DIM__;margin-top:7px;padding-top:7px;
 border-top:1px solid __BORDER__;font-variant-numeric:tabular-nums;
 overflow-wrap:anywhere}
.q-name{color:__TEXT__}
.zone-extra{font-size:15px;color:__DIM__;margin-top:5px;overflow-wrap:anywhere}
.zone-news{font-size:15px;color:__DIM__;margin-top:5px;overflow-wrap:anywhere}
.breadth{font-size:16px;line-height:1.4;padding:0 2px 10px;margin-top:22px}
.global-line{font-size:15px;color:__DIM__;padding:4px 2px 0;
 font-variant-numeric:tabular-nums}
.agenda{list-style:none;margin:0;padding:0;background:__CARD__;
 border:1px solid __BORDER__;border-radius:12px}
.agenda li{display:flex;gap:12px;align-items:baseline;padding:12px 15px;
 border-bottom:1px solid __BORDER__}
.agenda li:last-child{border-bottom:0}
.agenda li.soon .ag-when{color:__RED__}
.ag-when{flex:0 0 112px;font-size:15px;color:__DIM__;font-weight:600}
.ag-body{flex:1;min-width:0}
.ag-label{display:block;font-size:16px;line-height:1.35;overflow-wrap:anywhere}
.ag-date{display:block;font-size:14px;color:__DIM__;margin-top:2px}
.news{list-style:none;margin:0;padding:0;background:__CARD__;
 border:1px solid __BORDER__;border-radius:12px}
.news li{font-size:16px;line-height:1.45;padding:12px 15px;
 border-bottom:1px solid __BORDER__}
.news li:last-child{border-bottom:0}
.news-note{font-size:14px;color:__DIM__;line-height:1.35;margin-top:7px;padding:0 3px}
.headline{display:block;min-height:44px;margin-top:10px;padding:12px 15px;
 background:__CARD__;border:1px solid __BORDER__;border-radius:12px;
 text-decoration:none;color:__TEXT__;-webkit-tap-highlight-color:transparent}
.headline-label{display:block;font-size:14px;color:__DIM__;
 text-transform:uppercase;letter-spacing:.07em;margin-bottom:3px}
.headline-title{display:block;font-size:16px;line-height:1.35;overflow-wrap:anywhere}
.chg li{justify-content:space-between}
.chg-what{font-size:16px;line-height:1.35;overflow-wrap:anywhere}
.chg-when{flex:0 0 auto;font-size:14px;color:__DIM__;white-space:nowrap}
.verdicts,.context{list-style:none;margin:0;padding:0;background:__CARD__;
 border:1px solid __BORDER__;border-radius:12px}
.verdicts li{display:flex;gap:10px;align-items:baseline;padding:11px 15px;
 border-bottom:1px solid __BORDER__}
.verdicts li:last-child,.context li:last-child{border-bottom:0}
.vd-name{flex:0 0 92px;font-size:16px;overflow-wrap:anywhere}
.vd-word{flex:1;font-size:15px;line-height:1.3}
.vd-edge{flex:0 0 auto;font-size:15px;color:__DIM__;
 font-variant-numeric:tabular-nums}
.context li{padding:11px 15px;border-bottom:1px solid __BORDER__}
.ctx-top{display:flex;gap:10px;align-items:baseline;justify-content:space-between}
.ctx-label{font-size:16px;line-height:1.3;overflow-wrap:anywhere}
.ctx-value{flex:0 0 auto;font-size:16px;font-weight:600;
 font-variant-numeric:tabular-nums}
.ctx-sentence{display:block;font-size:14px;color:__DIM__;margin-top:3px;
 line-height:1.35}
.reliab{background:__CARD__;border:1px solid __BORDER__;
 border-radius:12px;padding:12px 15px;margin:0}
.reliab-progress{font-size:16px;line-height:1.4}
.reliab-note{font-size:14px;color:__DIM__;line-height:1.35;margin-top:7px}
.disclaimer{position:fixed;left:0;right:0;bottom:0;background:__CARD__;
 border-top:1px solid __BORDER__;color:__DIM__;font-size:14px;line-height:1.35;
 padding:10px 16px calc(10px + env(safe-area-inset-bottom));text-align:center;z-index:10}
"""


def render_page(index, articles, macro, agenda, synthese, backtest,
                generated_at):
    css = CSS
    for token, colour in (("__BG__", BG), ("__CARD__", BG_CARD),
                          ("__BORDER__", BORDER), ("__TEXT__", TEXT),
                          ("__DIM__", TEXT_DIM), ("__RED__", RED)):
        css = css.replace(token, colour)

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
<h1>Veille économique</h1>
<p class="updated">Mise à jour le {stamp} (heure de Paris)</p>

{render_changes(backtest)}

{render_zones(macro, articles)}
{render_agenda(agenda)}

<h2>Ce qu'il faut savoir</h2>
{render_news(index, articles, synthese)}
{render_headline(articles)}

{render_analogues(backtest)}
{render_verdicts(backtest)}
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

    size_kb = (DOCS_DIR / "index.html").stat().st_size / 1024
    print(f"docs/index.html genere ({size_kb:.1f} Ko)")
    for _key, label, section, unit, indices, news_keys in ZONES:
        source = macro.get(section) or {}
        blocks = [source.get(k) or {} for k, _ in indices]
        state, _, detail = zone_verdict(blocks)
        counts = [zone_news(articles, key) for key in news_keys]
        plus = sum(c[0] for c in counts)
        moins = sum(c[1] for c in counts)
        print(f"  {label:<10} {state:<22} (actu {plus}+/{moins}-) {detail}")
    observations, _ = reliability(macro)
    print(f"  backtest  : {len(backtest.get('assets') or {})} marche(s) mesure(s), "
          f"{len(recent_changes(backtest))} basculement(s) recent(s)")
    print(f"  comparable: {len(analogue_rows(backtest))} marche(s) situe(s)")
    print(f"  contexte  : {len(backtest.get('context') or [])} repere(s)")
    print(f"  agenda    : {len(agenda.get('upcoming') or [])} echeance(s)")
    print(f"  synthese  : {'oui' if synthese.get('points') else 'non (pas de cle)'}")
    print(f"  mesure en direct (hors page) : {observations} observation(s)")


if __name__ == "__main__":
    main()
