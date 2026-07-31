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

# Actif -> (libelle, bloc dans macro.json, unite)
ASSETS = [
    ("sp500", "S&P 500", "equities", ""),
    ("msci_world", "MSCI World", "equities", ""),
    ("btc", "Bitcoin", "crypto", " $"),
    ("eth", "Ethereum", "crypto", " $"),
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


# --- Tendance par actif -----------------------------------------------------

def trend_of(block, is_crypto):
    """Position du cours face a ses moyennes 50 et 200 jours.

    Regle mecanique et verifiable, pas une prevision : elle decrit ou se
    situe le cours aujourd'hui, elle ne dit rien de demain. C'est aussi
    pour cela que le libelle parle de « tendance » et jamais d'« acheter ».
    """
    price = block.get("price")
    ma50 = block.get("ma50")
    ma200 = block.get("ma200")
    if price is None or ma50 is None or ma200 is None:
        return None, "Données indisponibles pour le moment.", GRAY

    above50 = price > ma50
    above200 = price > ma200

    if above50 and above200:
        state, colour = "Tendance haussière", GREEN
        reason = "Au-dessus de ses moyennes 50 et 200 jours"
    elif not above50 and not above200:
        state, colour = "Tendance baissière", RED
        reason = "Sous ses moyennes 50 et 200 jours"
    else:
        state, colour = "Sans direction nette", GRAY
        reason = ("Au-dessus de sa moyenne 200 jours, sous celle à 50 jours"
                  if above200 else
                  "Sous sa moyenne 200 jours, au-dessus de celle à 50 jours")

    if is_crypto:
        drawdown = block.get("drawdown_1y")
        if drawdown is not None and drawdown >= 0.05:
            reason += f", à −{drawdown * 100:.0f} % du plus haut sur un an"

    return state, reason + ".", colour


# --- Tonalite de l'actualite ------------------------------------------------

def news_for_asset(articles, asset, days=NEWS_WINDOW_DAYS):
    """Compte les articles favorables et defavorables pour cet actif.

    On compte au lieu de moyenner, volontairement. Sur ces donnees, une
    semaine a 14 articles favorables et 9 defavorables donne une moyenne de
    0,00 : afficher « neutre » laisserait croire qu'il ne se passe rien,
    alors que l'actualite est nourrie mais partagee. Le decompte dit la
    verite la ou la moyenne l'efface.

    Seuls les articles portant reellement un terme du lexique votent : les
    depeches sans contenu macro ne doivent pas diluer la mesure.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    favorable = defavorable = total = 0
    for article in articles:
        if asset not in article.get("assets_effective", []):
            continue
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


def news_overall(articles, days=NEWS_WINDOW_DAYS):
    """Meme decompte que news_for_asset, mais tous actifs confondus."""
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
    """Qualifie le rapport de force entre articles, sans l'aplatir."""
    if favorable == 0 and defavorable == 0:
        return "rien de marquant", GRAY
    if favorable >= defavorable * 2:
        return "plutôt favorable", GREEN
    if defavorable >= favorable * 2:
        return "plutôt défavorable", RED
    return "partagée", GRAY


def tone_word(tone):
    if tone is None:
        return "pas de signal", GRAY
    if tone >= 0.15:
        return "favorable", GREEN
    if tone <= -0.15:
        return "défavorable", RED
    return "neutre", GRAY


# --- Cartes d'actifs --------------------------------------------------------

def render_assets(macro, articles):
    cards = []
    for key, label, section, unit in ASSETS:
        block = (macro.get(section) or {}).get(key) or {}
        is_crypto = section == "crypto"
        state, reason, colour = trend_of(block, is_crypto)
        favorable, defavorable, total = news_for_asset(articles, key)
        word, tone_colour = balance_word(favorable, defavorable)

        if favorable or defavorable:
            detail = (f"{favorable} pour, {defavorable} contre"
                      if favorable and defavorable else
                      (f"{favorable} article{'s' if favorable > 1 else ''}"
                       if favorable else
                       f"{defavorable} article{'s' if defavorable > 1 else ''}"))
            news_line = (f'Actualité 7 jours : <span style="color:{tone_colour}">'
                         f'{word}</span> — {detail}')
        elif total:
            news_line = f"Actualité 7 jours : {total} articles, aucun marquant"
        else:
            news_line = "Actualité 7 jours : rien de significatif"

        cards.append(
            '<article class="asset">'
            f'<div class="asset-head"><span class="asset-name">{html.escape(label)}</span>'
            f'<span class="asset-price">{price_text(block.get("price"), unit)}</span></div>'
            f'<div class="asset-state" style="color:{colour}">'
            f'{html.escape(state or "Indisponible")}</div>'
            f'<div class="asset-reason">{html.escape(reason)}</div>'
            f'<div class="asset-news">{news_line}</div>'
            '</article>'
        )
    return "".join(cards)


# --- Resume de l'actualite --------------------------------------------------

def average_over(index, key, days=NEWS_WINDOW_DAYS):
    """Moyenne d'une serie de l'indice sur les `days` derniers jours indexes."""
    values = []
    for day in sorted(index, reverse=True)[:days]:
        value = index[day].get(key)
        if value is not None:
            values.append(value)
    if not values:
        return None
    return sum(values) / len(values)


def top_headline(articles, hours=HEADLINE_WINDOW_HOURS):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent = []
    for article in articles:
        published = parse_date(article.get("published_at"))
        if published and published >= cutoff:
            recent.append(article)
    if not recent:
        return None
    return max(recent, key=lambda a: (a.get("importance", 0),
                                      a.get("published_at", "")))


def render_news(index, articles, macro):
    lines = []

    tone_cb = average_over(index, "tone_cb")
    word, colour = tone_word(tone_cb)
    lines.append('Banques centrales : ton '
                 f'<span style="color:{colour}">{word}</span> sur 7 jours.')

    # Meme methode que les cartes d'actifs : on compte, on ne moyenne pas.
    # Melanger les deux sur une meme page produisait une contradiction
    # visible — « defavorable » ici, « partagee » partout au-dessus.
    favorable, defavorable, _ = news_overall(articles)
    word, colour = balance_word(favorable, defavorable)
    lines.append("Actualité générale : "
                 f'<span style="color:{colour}">{word}</span> — '
                 f'{favorable} favorables, {defavorable} défavorables sur 7 jours.')

    stress = average_over(index, "stress")
    if stress is None:
        lines.append("Part des sujets de crise : pas de mesure disponible.")
    else:
        if stress >= 0.20:
            mot, colour = "élevée", RED
        elif stress >= 0.08:
            mot, colour = "modérée", GRAY
        else:
            mot, colour = "faible", GREEN
        lines.append('Part des sujets de crise : '
                     f'<span style="color:{colour}">{mot}</span> '
                     f'({stress * 100:.0f} % du flux).')

    regime = macro.get("regime") or {}
    if regime.get("available"):
        lines.append(f'Régime de marché : {html.escape(regime["state"])} '
                     f'({regime["favorable"]} critères favorables sur '
                     f'{regime["available"]}).')

    body = "".join(f"<li>{line}</li>" for line in lines)

    headline = top_headline(articles)
    marquant = ""
    if headline:
        url = html.escape(safe_url(headline.get("url", "")), quote=True)
        marquant = (
            f'<a class="headline" target="_blank" rel="noopener noreferrer" href="{url}">'
            '<span class="headline-label">Le fait marquant</span>'
            f'<span class="headline-title">{html.escape(headline.get("title", ""))}</span>'
            '</a>')

    return f'<ul class="news">{body}</ul>{marquant}'


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
.asset{background:__CARD__;border:1px solid __BORDER__;border-radius:12px;
 padding:14px 15px;margin-bottom:10px}
.asset-head{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.asset-name{font-size:17px;font-weight:600;letter-spacing:-.01em}
.asset-price{font-size:17px;color:__DIM__;font-variant-numeric:tabular-nums;
 white-space:nowrap}
.asset-state{font-size:21px;font-weight:600;letter-spacing:-.01em;margin:6px 0 3px}
.asset-reason{font-size:15px;line-height:1.4}
.asset-news{font-size:15px;color:__DIM__;margin-top:7px;padding-top:7px;
 border-top:1px solid __BORDER__}
.news{list-style:none;margin:0;padding:0;background:__CARD__;
 border:1px solid __BORDER__;border-radius:12px}
.news li{font-size:16px;line-height:1.4;padding:12px 15px;
 border-bottom:1px solid __BORDER__}
.news li:last-child{border-bottom:0}
.headline{display:block;min-height:44px;margin-top:10px;padding:12px 15px;
 background:__CARD__;border:1px solid __BORDER__;border-radius:12px;
 text-decoration:none;color:__TEXT__;-webkit-tap-highlight-color:transparent}
.headline-label{display:block;font-size:14px;color:__DIM__;
 text-transform:uppercase;letter-spacing:.07em;margin-bottom:3px}
.headline-title{display:block;font-size:16px;line-height:1.35;overflow-wrap:anywhere}
.disclaimer{position:fixed;left:0;right:0;bottom:0;background:__CARD__;
 border-top:1px solid __BORDER__;color:__DIM__;font-size:14px;line-height:1.35;
 padding:10px 16px calc(10px + env(safe-area-inset-bottom));text-align:center;z-index:10}
"""


def render_page(index, articles, macro, generated_at):
    css = CSS
    for token, colour in (("__BG__", BG), ("__CARD__", BG_CARD),
                          ("__BORDER__", BORDER), ("__TEXT__", TEXT),
                          ("__DIM__", TEXT_DIM)):
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

{render_assets(macro, articles)}

<h2>Ce que dit l'actualité</h2>
{render_news(index, articles, macro)}

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
    print(f"docs/index.html genere ({size_kb:.1f} Ko)")
    for key, label, section, unit in ASSETS:
        block = (macro.get(section) or {}).get(key) or {}
        state, _, _ = trend_of(block, section == "crypto")
        fav, unfav, total = news_for_asset(articles, key)
        print(f"  {label:<12} {price_text(block.get('price'), unit):>12}  "
              f"{state or 'indisponible':<22} actu: {balance_word(fav, unfav)[0]} "
              f"({fav} pour / {unfav} contre sur {total})")


if __name__ == "__main__":
    main()
