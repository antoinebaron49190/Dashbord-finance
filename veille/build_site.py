#!/usr/bin/env python3
"""Genere docs/index.html : une page statique unique, servie par GitHub Pages.

Contraintes tenues par ce script :
  - un seul fichier HTML, CSS et JS inclus dedans ;
  - aucun framework, aucune etape de compilation, aucune dependance externe ;
  - les donnees sont injectees au moment de la generation, la page ne fait
    aucune requete reseau ;
  - pensee pour un iPhone 14 (390pt), une seule colonne, thème sombre.

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

from sources import SOURCES

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT.parent / "docs"

PARIS = ZoneInfo("Europe/Paris")
CHART_DAYS = 90
TOP_PER_ASSET = 10

SOURCE_NAMES = {s["id"]: s["name"] for s in SOURCES}

# --- Palette ---------------------------------------------------------------
# Sobre, sans degrade. Les couleurs ne portent jamais seules l'information :
# chaque valeur coloree est doublee d'un mot et chaque variation d'un signe.

BG = "#0e1116"
BG_CARD = "#161b22"
BORDER = "#262c36"
TEXT = "#e6e9ee"
TEXT_DIM = "#98a1ad"
GREEN = "#5fa97c"
RED = "#cf6b62"
GRAY = "#8b94a1"

METRICS = [
    ("tone_cb", "Banques centrales", "tone", "#7fb2f0", "none"),
    ("tone_global", "Tonalité globale", "tone", "#e0e4ea", "7 4"),
    ("regul_crypto", "Réglementaire crypto", "tone", "#b98ee0", "2 4"),
    ("stress", "Part de stress", "stress", "#d97a6c", "9 3 2 3"),
]

ASSET_TABS = [
    ("sp500", "S&P 500"),
    ("msci_world", "MSCI World"),
    ("btc", "Bitcoin"),
    ("eth", "Ethereum"),
]

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
    """Quatre barres sur fond sombre : un rappel des quatre indicateurs.

    Volontairement minimal, pour rester lisible a 40px sur l'ecran d'accueil.
    """
    bg = hex_rgb(BG)
    bar = hex_rgb("#d5dae1")
    accent = hex_rgb("#7fb2f0")
    rows = [[bg for _ in range(size)] for _ in range(size)]

    unit = size / 180.0
    baseline = int(150 * unit)
    bar_w = int(24 * unit)
    gap = int(12 * unit)
    left = int(28 * unit)
    heights = [58, 96, 44, 118]

    for i, h in enumerate(heights):
        x0 = left + i * (bar_w + gap)
        x1 = min(size, x0 + bar_w)
        y0 = max(0, baseline - int(h * unit))
        colour = accent if i == 3 else bar
        for y in range(y0, min(size, baseline)):
            for x in range(x0, x1):
                rows[y][x] = colour

    # Ligne de base
    for y in range(baseline, min(size, baseline + max(1, int(4 * unit)))):
        for x in range(left, min(size, int(160 * unit))):
            rows[y][x] = bar

    return png_bytes(size, size, rows)


# --- Chargement et mesures --------------------------------------------------

def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_day(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def day_span(index, count):
    """Les `count` derniers jours calendaires, jusqu'au dernier jour indexe."""
    if not index:
        return []
    last = max(parse_day(d) for d in index)
    return [last - timedelta(days=offset) for offset in range(count - 1, -1, -1)]


def series_values(index, key, days):
    """Valeurs alignees sur `days`. None = pas de donnee, jamais interpole."""
    return [index.get(d.isoformat(), {}).get(key) for d in days]


def latest_value(index, key):
    """Derniere valeur non nulle, avec le jour dont elle provient.

    Un jour calme peut n'avoir aucun signal. Plutot que d'afficher un tiret
    sur les quatre cartes un dimanche, on remonte a la derniere valeur
    disponible — mais en affichant explicitement sa date, pour ne pas la
    faire passer pour celle du jour.
    """
    for day in sorted(index, reverse=True):
        value = index[day].get(key)
        if value is not None:
            return value, parse_day(day)
    return None, None


def value_at_or_before(index, key, target):
    for day in sorted(index, reverse=True):
        if parse_day(day) <= target:
            value = index[day].get(key)
            if value is not None:
                return value
    return None


def level_of(key, kind, value):
    """Renvoie (couleur, mot). Le mot double la couleur, toujours."""
    if value is None:
        return GRAY, "sans signal"
    if kind == "stress":
        # Une part de stress elevee est defavorable : l'echelle est inversee.
        if value >= 0.20:
            return RED, "élevée"
        if value >= 0.08:
            return GRAY, "modérée"
        return GREEN, "faible"
    if value >= 0.15:
        return GREEN, "favorable"
    if value <= -0.15:
        return RED, "défavorable"
    return GRAY, "neutre"


def format_value(kind, value):
    if value is None:
        return "--"
    if kind == "stress":
        return f"{value * 100:.0f} %"
    return f"{value:+.2f}"


def build_cards(index):
    cards = []
    for key, label, kind, _colour, _dash in METRICS:
        value, day = latest_value(index, key)
        colour, word = level_of(key, kind, value)

        delta_text = "pas de comparaison sur 7 jours"
        arrow = "—"  # tiret cadratin : ni hausse ni baisse
        if value is not None and day is not None:
            previous = value_at_or_before(index, key, day - timedelta(days=7))
            if previous is not None:
                delta = value - previous
                if kind == "stress":
                    shown = f"{delta * 100:+.0f} pts"
                else:
                    shown = f"{delta:+.2f}"
                if abs(delta) < 0.005:
                    arrow, trend = "—", "stable"
                elif delta > 0:
                    arrow, trend = "▲", "en hausse"
                else:
                    arrow, trend = "▼", "en baisse"
                delta_text = f"{shown} sur 7 jours, {trend}"

        cards.append({
            "label": label,
            "value": format_value(kind, value),
            "colour": colour,
            "word": word,
            "arrow": arrow,
            "delta": delta_text,
            "day": day,
        })
    return cards


# --- Graphique SVG ----------------------------------------------------------

def build_chart(index, days):
    """SVG pur, genere ici. Aucune bibliotheque, cote page comme cote script.

    Les quatre series se distinguent par la couleur ET par le style de trait :
    un lecteur qui ne percoit pas les couleurs garde l'information.
    """
    width, height = 360, 214
    pad_l, pad_r, pad_t, pad_b = 34, 8, 12, 30
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def x_of(i):
        if len(days) <= 1:
            return pad_l
        return pad_l + i * plot_w / (len(days) - 1)

    def y_of(v):
        # Les tonalites vivent dans [-1, 1], la part de stress dans [0, 1] :
        # les deux tiennent dans le meme repere.
        return pad_t + (1 - v) / 2 * plot_h

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Évolution des quatre indicateurs sur {len(days)} jours" '
        f'xmlns="http://www.w3.org/2000/svg">'
    ]

    for level in (1.0, 0.5, 0.0, -0.5, -1.0):
        y = y_of(level)
        strong = level == 0.0
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" '
            f'stroke="{"#39414d" if strong else "#1e242d"}" stroke-width="1"/>'
        )
        if level in (1.0, 0.0, -1.0):
            parts.append(
                f'<text x="{pad_l - 6}" y="{y + 4.2:.1f}" text-anchor="end" '
                f'font-size="12" fill="{TEXT_DIM}">{level:+.0f}</text>'
            )

    for key, label, _kind, colour, dash in METRICS:
        values = series_values(index, key, days)
        dash_attr = "" if dash == "none" else f' stroke-dasharray="{dash}"'

        # Un jour isole entre deux trous se dessine en point : sans cela il
        # serait invisible. Il est volontairement plus gros que les tirets du
        # pointille, pour ne pas se confondre avec eux.
        run = []
        for i, value in enumerate(values):
            if value is None:
                if len(run) > 1:
                    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in run)
                    parts.append(
                        f'<polyline points="{points}" fill="none" stroke="{colour}" '
                        f'stroke-width="1.6" stroke-linejoin="round"{dash_attr}/>'
                    )
                elif len(run) == 1:
                    parts.append(f'<circle cx="{run[0][0]:.1f}" cy="{run[0][1]:.1f}" '
                                 f'r="2.4" fill="{colour}"/>')
                run = []
            else:
                run.append((x_of(i), y_of(value)))
        if len(run) > 1:
            points = " ".join(f"{x:.1f},{y:.1f}" for x, y in run)
            parts.append(
                f'<polyline points="{points}" fill="none" stroke="{colour}" '
                f'stroke-width="1.6" stroke-linejoin="round"{dash_attr}/>'
            )
        elif len(run) == 1:
            parts.append(f'<circle cx="{run[0][0]:.1f}" cy="{run[0][1]:.1f}" '
                         f'r="2.4" fill="{colour}"/>')

    if days:
        for i, anchor in ((0, "start"), (len(days) // 2, "middle"), (len(days) - 1, "end")):
            parts.append(
                f'<text x="{x_of(i):.1f}" y="{height - 9}" text-anchor="{anchor}" '
                f'font-size="12" fill="{TEXT_DIM}">{days[i].strftime("%d/%m")}</text>'
            )

    parts.append("</svg>")
    return "".join(parts)


# --- Onglets d'actifs -------------------------------------------------------

def safe_url(url):
    """N'accepte que http(s) : le contenu des flux n'est pas de confiance."""
    return url if url.startswith(("http://", "https://")) else "#"


def top_by_asset(articles, asset):
    selected = [a for a in articles if asset in a.get("assets_effective", [])]
    selected.sort(
        key=lambda a: (a.get("importance", 0), a.get("published_at", "")),
        reverse=True,
    )
    return selected[:TOP_PER_ASSET]


def render_items(articles, asset):
    items = top_by_asset(articles, asset)
    if not items:
        return '<p class="empty">Aucun élément pour cet actif.</p>'

    rows = []
    for article in items:
        try:
            day = datetime.fromisoformat(article["published_at"]).strftime("%d/%m")
        except (KeyError, ValueError):
            day = ""
        source = SOURCE_NAMES.get(article.get("source"), article.get("source", ""))
        rows.append(
            '<li><a href="{url}" rel="noopener noreferrer" target="_blank">'
            '<span class="item-title">{title}</span>'
            '<span class="item-meta">{source} &middot; {day} &middot; '
            'score {score:.2f}</span></a></li>'.format(
                url=html.escape(safe_url(article.get("url", "")), quote=True),
                title=html.escape(article.get("title", "")),
                source=html.escape(source),
                day=html.escape(day),
                score=article.get("importance", 0),
            )
        )
    return f'<ul class="items">{"".join(rows)}</ul>'


# --- Section marche (donnees chiffrees) -------------------------------------

REGIME_COLOURS = {
    "favorable au risque": GREEN,
    "neutre": GRAY,
    "défavorable au risque": RED,
    "indisponible": GRAY,
}


def render_macro(macro):
    """Section chiffree, tenue a l'ecart de la section actualite.

    Les deux ne doivent jamais se lire comme un seul bloc : l'une mesure ce
    que raconte la presse, l'autre ce que font les prix. Elles sont donc
    separees par un titre, un liseré et un fond distinct.
    """
    if not macro or not macro.get("criteria"):
        return ""

    regime = macro.get("regime", {})
    state = regime.get("state", "indisponible")
    colour = REGIME_COLOURS.get(state, GRAY)

    if regime.get("available"):
        compte = (f"{regime['favorable']} critères favorables "
                  f"sur {regime['available']} disponibles")
    else:
        compte = "aucun critère calculable"

    manquants = regime.get("total", 0) - regime.get("available", 0)
    note = ""
    if manquants:
        pluriel = "s" if manquants > 1 else ""
        note = (f'<div class="macro-note">{manquants} critère{pluriel} non '
                f'calculable{pluriel} : source indisponible. '
                f'{"Ils sont exclus" if manquants > 1 else "Il est exclu"} du '
                f'décompte, pas {"comptés" if manquants > 1 else "compté"} comme '
                f'défavorable{pluriel}.</div>')

    lignes = []
    groupe_courant = None
    for item in macro["criteria"]:
        if item["group"] != groupe_courant:
            groupe_courant = item["group"]
            lignes.append(f'<li class="crit-group">{html.escape(groupe_courant)}</li>')
        if item["ok"] is None:
            marque, mot, teinte = "?", "indisponible", GRAY
        elif item["ok"]:
            marque, mot, teinte = "oui", "favorable", GREEN
        else:
            marque, mot, teinte = "non", "défavorable", RED
        lignes.append(
            '<li class="crit">'
            f'<span class="crit-mark" style="color:{teinte}" '
            f'aria-label="{mot}">{marque}</span>'
            f'<span class="crit-body"><span class="crit-label">'
            f'{html.escape(item["label"])}</span>'
            f'<span class="crit-meta">{html.escape(item["value"])} '
            f'&middot; seuil : {html.escape(item["reference"])}</span></span></li>'
        )

    return (
        '<h2>Marché</h2>'
        '<div class="macro">'
        f'<div class="regime" style="border-color:{colour}">'
        f'<div class="regime-label">Régime</div>'
        f'<div class="regime-state" style="color:{colour}">{html.escape(state)}</div>'
        f'<div class="regime-count">{html.escape(compte)}</div>'
        f'</div>'
        f'{note}'
        f'<ul class="crits">{"".join(lignes)}</ul>'
        '</div>'
    )


# --- Page -------------------------------------------------------------------

CSS = """
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:__BG__;color:__TEXT__;font-size:16px;line-height:1.45;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 padding:0 16px calc(96px + env(safe-area-inset-bottom)) 16px;
 max-width:430px;margin:0 auto;overflow-x:hidden}
h1{font-size:19px;margin:20px 0 2px;font-weight:600;letter-spacing:-.01em}
h2{font-size:15px;margin:26px 0 10px;font-weight:600;color:__DIM__;
 text-transform:uppercase;letter-spacing:.06em}
.updated{color:__DIM__;font-size:15px;margin:0 0 4px}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
.card{background:__CARD__;border:1px solid __BORDER__;border-radius:10px;padding:12px}
.card-label{font-size:14px;color:__DIM__;line-height:1.3;min-height:38px}
.card-value{font-size:26px;font-weight:600;letter-spacing:-.02em;margin:2px 0}
.card-word{font-size:14px;font-weight:600}
.card-delta{font-size:14px;color:__DIM__;margin-top:4px}
.card-day{font-size:14px;color:__DIM__;margin-top:2px}
.chart{background:__CARD__;border:1px solid __BORDER__;border-radius:10px;
 padding:10px 8px 4px}
.chart svg{display:block;width:100%;height:auto}
.legend{display:grid;grid-template-columns:1fr 1fr;gap:6px 10px;margin-top:8px;
 padding:0 4px 8px}
.legend div{display:flex;align-items:center;gap:7px;font-size:14px;color:__DIM__}
.legend svg{flex:0 0 22px}
.tabs{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.tabs button{min-height:44px;font-size:16px;font-family:inherit;font-weight:600;
 color:__DIM__;background:__CARD__;border:1px solid __BORDER__;border-radius:10px;
 padding:0 8px;cursor:pointer;-webkit-tap-highlight-color:transparent}
.tabs button[aria-selected="true"]{color:__TEXT__;border-color:#4a5563;
 background:#1d232c}
.items{list-style:none;margin:0;padding:0}
.items li{border-bottom:1px solid __BORDER__}
.items li:last-child{border-bottom:0}
.items a{display:block;min-height:44px;padding:11px 2px;text-decoration:none;
 color:__TEXT__;-webkit-tap-highlight-color:transparent}
.item-title{display:block;font-size:16px;line-height:1.35;overflow-wrap:anywhere}
.item-meta{display:block;font-size:14px;color:__DIM__;margin-top:3px}
.empty{color:__DIM__;font-size:16px}
.section-sep{border:0;border-top:1px solid __BORDER__;margin:30px 0 0}
.macro{background:#12171f;border:1px solid __BORDER__;border-radius:10px;padding:12px}
.regime{border-left:4px solid __DIM__;padding:2px 0 2px 12px;margin-bottom:12px}
.regime-label{font-size:14px;color:__DIM__;text-transform:uppercase;letter-spacing:.06em}
.regime-state{font-size:22px;font-weight:600;letter-spacing:-.01em;margin:1px 0}
.regime-count{font-size:14px;color:__DIM__}
.macro-note{font-size:14px;color:__DIM__;margin-bottom:10px;line-height:1.35}
.crits{list-style:none;margin:0;padding:0}
.crit-group{font-size:14px;color:__DIM__;text-transform:uppercase;letter-spacing:.06em;
 margin:12px 0 4px;padding-top:8px;border-top:1px solid __BORDER__}
.crit-group:first-child{margin-top:0;padding-top:0;border-top:0}
.crit{display:flex;gap:10px;align-items:baseline;padding:7px 0}
.crit-mark{flex:0 0 34px;font-size:14px;font-weight:600}
.crit-body{flex:1;min-width:0}
.crit-label{display:block;font-size:16px;line-height:1.3;overflow-wrap:anywhere}
.crit-meta{display:block;font-size:14px;color:__DIM__;margin-top:2px;overflow-wrap:anywhere}
.disclaimer{position:fixed;left:0;right:0;bottom:0;background:__CARD__;
 border-top:1px solid __BORDER__;color:__DIM__;font-size:14px;line-height:1.35;
 padding:10px 16px calc(10px + env(safe-area-inset-bottom));text-align:center;z-index:10}
"""


def render_page(index, articles, macro, generated_at):
    days = day_span(index, CHART_DAYS)
    cards = build_cards(index)

    card_html = []
    for card in cards:
        day_line = ""
        if card["day"] and card["day"] != (days[-1] if days else None):
            day_line = (f'<div class="card-day">valeur du '
                        f'{card["day"].strftime("%d/%m")}</div>')
        card_html.append(
            f'<div class="card">'
            f'<div class="card-label">{html.escape(card["label"])}</div>'
            f'<div class="card-value" style="color:{card["colour"]}">'
            f'{html.escape(card["value"])}</div>'
            f'<div class="card-word" style="color:{card["colour"]}">'
            f'{html.escape(card["word"])}</div>'
            f'<div class="card-delta">{card["arrow"]} '
            f'{html.escape(card["delta"])}</div>'
            f'{day_line}</div>'
        )

    legend_html = []
    for _key, label, _kind, colour, dash in METRICS:
        dash_attr = "" if dash == "none" else f' stroke-dasharray="{dash}"'
        legend_html.append(
            f'<div><svg width="22" height="8" aria-hidden="true">'
            f'<line x1="0" y1="4" x2="22" y2="4" stroke="{colour}" '
            f'stroke-width="2"{dash_attr}/></svg>{html.escape(label)}</div>'
        )

    tab_buttons = []
    panels = []
    for position, (asset, label) in enumerate(ASSET_TABS):
        selected = "true" if position == 0 else "false"
        hidden = "" if position == 0 else " hidden"
        tab_buttons.append(
            f'<button role="tab" id="tab-{asset}" aria-controls="panel-{asset}" '
            f'aria-selected="{selected}" data-asset="{asset}">{html.escape(label)}</button>'
        )
        panels.append(
            f'<div role="tabpanel" id="panel-{asset}" aria-labelledby="tab-{asset}"'
            f'{hidden}>{render_items(articles, asset)}</div>'
        )

    macro_html = render_macro(macro)
    stamp = generated_at.strftime("%d/%m/%Y à %H:%M")
    css = CSS
    for token, colour in (("__BG__", BG), ("__CARD__", BG_CARD),
                          ("__BORDER__", BORDER), ("__TEXT__", TEXT),
                          ("__DIM__", TEXT_DIM)):
        css = css.replace(token, colour)

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

<h2>Actualité</h2>
<div class="cards">{"".join(card_html)}</div>

<h2>90 derniers jours</h2>
<div class="chart">{build_chart(index, days)}
<div class="legend">{"".join(legend_html)}</div>
</div>

<h2>Par actif</h2>
<div class="tabs" role="tablist">{"".join(tab_buttons)}</div>
{"".join(panels)}

<hr class="section-sep">
{macro_html}

<!-- Bandeau permanent : ne jamais retirer. -->
<div class="disclaimer" role="note">{html.escape(DISCLAIMER)}</div>

<script>
(function () {{
  var tabs = document.querySelectorAll('.tabs button');
  Array.prototype.forEach.call(tabs, function (tab) {{
    tab.addEventListener('click', function () {{
      Array.prototype.forEach.call(tabs, function (other) {{
        var panel = document.getElementById('panel-' + other.dataset.asset);
        var active = other === tab;
        other.setAttribute('aria-selected', active ? 'true' : 'false');
        if (panel) {{ panel.hidden = !active; }}
      }});
    }});
  }});
}})();
</script>
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

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).astimezone(PARIS)

    page = render_page(index, articles, macro, generated_at)
    (DOCS_DIR / "index.html").write_text(page, encoding="utf-8")

    with open(DOCS_DIR / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(MANIFEST, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    for name, size in (("apple-touch-icon.png", 180), ("icon-192.png", 192),
                       ("icon-512.png", 512)):
        (DOCS_DIR / name).write_bytes(build_icon(size))

    size_kb = (DOCS_DIR / "index.html").stat().st_size / 1024
    regime = (macro.get("regime") or {}).get("state", "absent")
    print(f"docs/index.html genere ({size_kb:.1f} Ko), "
          f"{len(index)} jours, {len(articles)} articles, regime : {regime}.")
    print(f"Derniere mise a jour affichee : "
          f"{generated_at.strftime('%d/%m/%Y a %H:%M')} (heure de Paris)")


if __name__ == "__main__":
    main()
