#!/usr/bin/env python3
"""Moteur de scoring lexical + construction de l'indice quotidien.

Deux etages, volontairement separes :

1. Un moteur lexical DETERMINISTE, gratuit et reproductible. C'est la
   propriete essentielle : un meme article produit toujours le meme score,
   aujourd'hui comme dans deux ans. C'est ce qui rend la serie exploitable.

2. Une etape Claude OPTIONNELLE, desactivee par defaut. Elle ne s'active que
   si ANTHROPIC_API_KEY existe. Les scores qui en proviennent sont marques
   comme tels (`scored_by: "claude"`) pour rester distinguables des scores
   lexicaux, qui eux sont rejouables a l'identique.

Usage:
    python analyzer.py              Analyse et met a jour data/index.json
    python analyzer.py --no-claude  Force l'etage lexical seul
    python analyzer.py --explain ID Detaille le calcul pour un article
"""

import argparse
import json
import math
import os
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from pathlib import Path

from lexique import (
    ASSET_KEYWORDS,
    CRYPTO_GENERIC,
    CRYPTO_GENERIC_ASSETS,
    DECISION_MARKERS,
    DECISION_MULTIPLIER,
    DIRECTIONS,
    LEXIQUE,
    TIER1_MULTIPLIER,
)

DATA_DIR = Path(__file__).parent / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
INDEX_PATH = DATA_DIR / "index.json"
SYNTHESE_PATH = DATA_DIR / "synthese.json"

ASSETS = ["sp500", "msci_world", "btc", "eth"]
CRYPTO_ASSETS = {"btc", "eth"}
CRYPTO_CATEGORIES = ("crypto_favorable", "crypto_defavorable")

# Etape Claude (optionnelle)
CLAUDE_MODEL = os.environ.get("VEILLE_CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_MAX_ITEMS = 25
CLAUDE_WINDOW_HOURS = 48

_WS_RE = re.compile(r"\s+")


# --- Normalisation ----------------------------------------------------------

def strip_accents(text):
    """Retire les accents : "reglementaire" et "réglementaire" se valent."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def normalize(text):
    """Minuscules, sans accents, espaces normalises."""
    return _WS_RE.sub(" ", strip_accents(text or "").lower()).strip()


@lru_cache(maxsize=2048)
def term_regex(term):
    """Compile un terme avec frontieres de mots.

    IMPERATIF : la recherche par sous-chaine ferait matcher "ban" dans
    "banks" et "eth" dans "ethics". Ce sont de vrais bugs, pas des
    hypotheses. `\\b` autour du terme les elimine.
    """
    return re.compile(r"\b" + re.escape(term) + r"\b")


def count_term(text, term):
    return len(term_regex(term).findall(text))


# --- Scoring lexical --------------------------------------------------------

def saturate(count):
    """n occurrences valent racine(n), pas n.

    Trois mentions ne pesent pas trois fois une mention : au-dela du premier
    signal, la repetition d'un meme mot apporte de moins en moins.
    """
    return math.sqrt(count) if count > 0 else 0.0


def score_categories(text):
    """Renvoie {categorie: intensite saturee} pour les categories presentes.

    La saturation s'applique par terme, puis on somme sur la categorie :
    trois mentions d'"inflation" pesent moins que "inflation" + "hausse des
    taux". La diversite du vocabulaire compte plus que la repetition.
    """
    scores = {}
    for category, terms in LEXIQUE.items():
        total = 0.0
        matched = []
        for term in terms:
            count = count_term(text, term)
            if count:
                total += saturate(count)
                matched.append((term, count))
        if total:
            scores[category] = {"intensity": round(total, 4), "terms": matched}
    return scores


def detect_assets(text):
    """Actifs concernes, deduits du texte.

    Les termes generiques (crypto, stablecoin, blockchain, MiCA...)
    rattachent l'article a la fois a BTC et a ETH.
    """
    found = set()
    for asset, keywords in ASSET_KEYWORDS.items():
        if any(count_term(text, kw) for kw in keywords):
            found.add(asset)
    if any(count_term(text, kw) for kw in CRYPTO_GENERIC):
        found.update(CRYPTO_GENERIC_ASSETS)
    return [a for a in ASSETS if a in found]


def has_decision_marker(text):
    return any(count_term(text, marker) for marker in DECISION_MARKERS)


def compute_importance(weight, tier, decision):
    """Poids de la source, x1.5 si marqueur de decision, x1.3 si tier 1."""
    importance = float(weight)
    if decision:
        importance *= DECISION_MULTIPLIER
    if tier == 1:
        importance *= TIER1_MULTIPLIER
    return round(importance, 4)


def bounded(raw):
    """Ramene un score non borne dans ]-1, 1[, de facon monotone.

    Pas de seuil arbitraire, pas de saturation brutale : x / (1 + |x|)
    conserve l'ordre des scores tout en rendant la serie comparable d'un
    jour a l'autre.
    """
    return round(raw / (1.0 + abs(raw)), 4)


def raw_tone(categories, assets):
    """Somme ponderee des categories.

    Les categories crypto ne comptent dans la tonalite generale que si
    l'article concerne effectivement BTC ou ETH : sans ce garde-fou,
    "approval" ou "adoption" dans un texte reglementaire europeen
    tirerait le score global vers le haut sans raison.
    """
    is_crypto = bool(set(assets) & CRYPTO_ASSETS)
    total = 0.0
    for category, data in categories.items():
        if category in CRYPTO_CATEGORIES and not is_crypto:
            continue
        total += DIRECTIONS[category] * data["intensity"]
    return round(total, 4)


def raw_crypto_tone(categories):
    """Tonalite du climat reglementaire crypto, categories crypto seules."""
    total = 0.0
    for category in CRYPTO_CATEGORIES:
        if category in categories:
            total += DIRECTIONS[category] * categories[category]["intensity"]
    return round(total, 4)


def analyze_article(article):
    """Enrichit un article avec son analyse lexicale. Idempotent."""
    text = normalize(f"{article.get('title', '')} {article.get('summary', '')}")

    categories = score_categories(text)
    detected = detect_assets(text)

    # Le texte prime quand il parle. Quand il ne dit rien, on ne retombe sur
    # les actifs declares par la source que pour les tiers 1 et 2 : une
    # decision de la BCE concerne bien les quatre actifs meme sans les
    # nommer, alors qu'une depeche de presse sur une valeur isolee ne
    # concerne aucun de nos quatre actifs. Sans ce garde-fou, chaque bruit
    # de marche se retrouvait attribue a BTC et ETH.
    tier = article.get("tier", 3)
    if detected:
        assets = detected
    elif tier in (1, 2):
        assets = article.get("assets", [])
    else:
        assets = []

    decision = has_decision_marker(text)
    tone_lexical = bounded(raw_tone(categories, assets))

    # Seules les intensites sont persistees : les termes exacts se
    # reconstruisent a la demande avec --explain, et n'ont pas a alourdir
    # articles.json ni ses diffs git.
    article["categories"] = {c: d["intensity"] for c, d in categories.items()}
    article["assets_detected"] = detected
    article["assets_effective"] = assets
    article["has_decision_marker"] = decision
    article["importance"] = compute_importance(
        article.get("weight", 0.3), article.get("tier", 3), decision
    )
    article["tone_lexical"] = tone_lexical
    article["crypto_tone"] = bounded(raw_crypto_tone(categories))
    article["is_stress"] = "stress_financier" in categories

    # Un score Claude d'une passe precedente reste prioritaire, et reste
    # marque comme tel. Le score lexical est conserve a cote pour pouvoir
    # comparer les deux plus tard.
    if article.get("tone_claude") is not None:
        article["tone"] = article["tone_claude"]
        article["scored_by"] = "claude"
    else:
        article["tone"] = tone_lexical
        article["scored_by"] = "lexique"

    return article


# --- Indice quotidien -------------------------------------------------------

def weighted_mean(pairs):
    """Moyenne ponderee par l'importance. None si aucun element."""
    total_weight = sum(w for _, w in pairs)
    if total_weight <= 0:
        return None
    return round(sum(v * w for v, w in pairs) / total_weight, 4)


def day_of(article):
    try:
        return datetime.fromisoformat(article["published_at"]).strftime("%Y-%m-%d")
    except (KeyError, ValueError):
        return None


def has_signal(article):
    """Vrai si le lexique a trouve quelque chose, ou si Claude a tranche.

    Un article sans aucun terme reconnu ne vote pas dans les tonalites : la
    plupart des depeches de presse portent sur une valeur isolee et n'ont
    aucun contenu macro. Les compter comme des zeros diluerait les series
    jusqu'a les rendre illisibles.
    """
    return bool(article.get("categories")) or article.get("scored_by") == "claude"


def build_day(articles):
    """Construit les quatre series ponderees pour un jour donne."""
    signal = [a for a in articles if has_signal(a)]

    cb = [(a["tone"], a["importance"]) for a in signal if a.get("tier") == 1]
    glob = [(a["tone"], a["importance"]) for a in signal]
    # Le climat crypto ne se mesure que sur les articles qui portent
    # effectivement un signal crypto. Un article sur BTC qui ne dit rien de
    # reglementaire ne doit pas voter zero et tirer la serie vers le neutre.
    crypto = [
        (a["crypto_tone"], a["importance"])
        for a in signal
        if set(a.get("assets_effective", [])) & CRYPTO_ASSETS
        and any(c in a.get("categories", {}) for c in CRYPTO_CATEGORIES)
    ]

    # Le stress est une part du flux, pas une tonalite : il se calcule sur
    # l'ensemble des articles du jour, pas seulement ceux qui ont un signal.
    total_importance = sum(a["importance"] for a in articles)
    stress_importance = sum(a["importance"] for a in articles if a.get("is_stress"))
    stress = round(stress_importance / total_importance, 4) if total_importance else 0.0

    top = sorted(
        articles,
        key=lambda a: (a["importance"], abs(a["tone"])),
        reverse=True,
    )[:5]

    return {
        "articles_count": len(articles),
        "signal_count": len(signal),
        "tone_cb": weighted_mean(cb),
        "tone_global": weighted_mean(glob),
        "regul_crypto": weighted_mean(crypto),
        "stress": stress,
        "top": [
            {
                "id": a["id"],
                "title": a["title"],
                "source": a["source"],
                "score": a["importance"],
                "tone": a["tone"],
                "url": a["url"],
            }
            for a in top
        ],
    }


def build_index(index, articles):
    """Recalcule les jours presents dans `articles`, preserve les autres.

    L'indice n'est jamais purge : les jours anterieurs a la fenetre de
    retention des articles restent dans le fichier. C'est la memoire longue
    de l'outil, et c'est ce qui la rend exploitable dans deux ans.
    """
    by_day = {}
    for article in articles:
        day = day_of(article)
        if day:
            by_day.setdefault(day, []).append(article)

    for day, day_articles in by_day.items():
        index[day] = build_day(day_articles)

    return dict(sorted(index.items(), reverse=True))


# --- Etape Claude (optionnelle, desactivee par defaut) ----------------------

CLAUDE_SYSTEM = """Tu requalifies des titres d'actualite economique pour un \
outil de veille personnel. Pour chaque element, evalue la tonalite pour les \
actifs risques (actions et cryptos).

Reponds UNIQUEMENT avec une ligne par element, au format strict :
ID|tonalite|actifs|theme

- ID : l'identifiant fourni, recopie a l'identique
- tonalite : un nombre entre -1 et 1 (-1 tres defavorable, 0 neutre, \
1 tres favorable)
- actifs : liste separee par des virgules parmi sp500, msci_world, btc, eth \
(ou "aucun")
- theme : deux ou trois mots en minuscules, sans virgule

Aucun texte avant, aucun texte apres, aucune ligne d'explication."""


def select_for_claude(articles):
    """Les elements les plus importants des dernieres 48 h."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CLAUDE_WINDOW_HOURS)
    recent = []
    for article in articles:
        try:
            published = datetime.fromisoformat(article["published_at"])
        except (KeyError, ValueError):
            continue
        if published >= cutoff:
            recent.append(article)
    recent.sort(key=lambda a: a["importance"], reverse=True)
    return recent[:CLAUDE_MAX_ITEMS]


def parse_claude_line(line):
    """Parse une ligne ID|tonalite|actifs|theme. None si malformee."""
    parts = [p.strip() for p in line.split("|")]
    if len(parts) != 4:
        return None
    article_id, tone_raw, assets_raw, theme = parts
    if not article_id:
        return None
    try:
        tone = float(tone_raw.replace(",", "."))
    except ValueError:
        return None
    tone = max(-1.0, min(1.0, tone))
    assets = [a.strip() for a in assets_raw.split(",") if a.strip() in ASSETS]
    return article_id, round(tone, 4), assets, theme[:60]


def claude_requalify(articles):
    """Requalifie les elements les plus importants via l'API Anthropic.

    Sans ANTHROPIC_API_KEY, l'etape est ignoree silencieusement et tout
    continue de fonctionner : c'est un bonus, jamais une dependance.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return 0

    try:
        import anthropic
    except ImportError:
        print("  (paquet anthropic absent, etape Claude ignoree)")
        return 0

    selected = select_for_claude(articles)
    if not selected:
        return 0

    listing = "\n".join(
        f"{a['id']} :: {a['title']} :: {a['summary'][:200]}" for a in selected
    )

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            system=CLAUDE_SYSTEM,
            messages=[{"role": "user", "content": listing}],
        )
    except Exception as exc:  # l'etape est un bonus : jamais bloquante
        print(f"  (etape Claude en echec, on continue : {exc})")
        return 0

    text = "".join(b.text for b in response.content if b.type == "text")

    by_id = {a["id"]: a for a in selected}
    updated = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parsed = parse_claude_line(line)
        if not parsed:
            continue
        article_id, tone, assets, theme = parsed
        article = by_id.get(article_id)
        if article is None:
            continue
        article["tone_claude"] = tone
        article["tone"] = tone
        article["scored_by"] = "claude"
        article["claude_theme"] = theme
        if assets:
            article["claude_assets"] = assets
            article["assets_effective"] = assets
        updated += 1

    return updated


# --- Synthese redigee (optionnelle, necessite une cle) ----------------------

SYNTHESE_SYSTEM = """Tu rediges la synthese quotidienne d'un outil de veille \
economique personnel, pour un particulier qui suit le S&P 500, le MSCI World, \
les marches europeens et asiatiques, le Bitcoin et l'Ethereum.

A partir des titres fournis, degage les points qu'il doit absolument \
connaitre aujourd'hui.

Regles :
- exactement 5 points, un par ligne, chacun commencant par "- "
- une phrase par point, 25 mots maximum, en francais
- du plus important au moins important
- factuel : ce qui s'est passe et pourquoi cela compte pour ces marches
- ne predis rien, ne conseille ni achat ni vente, n'invente aucun chiffre
- si plusieurs titres traitent du meme sujet, fusionne-les en un seul point

Aucun texte avant, aucun texte apres, aucun titre, aucune numerotation."""

SYNTHESE_MAX_ITEMS = 30
SYNTHESE_WINDOW_HOURS = 72


def build_synthese(articles):
    """Demande a Claude les cinq points a retenir. Silencieuse sans cle.

    C'est le seul endroit du projet ou un modele de langage apporte quelque
    chose qu'un lexique ne peut pas donner : transformer cent depeches en
    cinq phrases hierarchisees. Sans ANTHROPIC_API_KEY, la page retombe sur
    le resume mecanique et rien ne casse.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    try:
        import anthropic
    except ImportError:
        print("  (paquet anthropic absent, synthese ignoree)")
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(hours=SYNTHESE_WINDOW_HOURS)
    recent = []
    for article in articles:
        try:
            published = datetime.fromisoformat(article["published_at"])
        except (KeyError, ValueError):
            continue
        if published >= cutoff:
            recent.append(article)
    if not recent:
        return None

    recent.sort(key=lambda a: a["importance"], reverse=True)
    selection = recent[:SYNTHESE_MAX_ITEMS]
    listing = "\n".join(f"- [{a['source']}] {a['title']} :: {a['summary'][:180]}"
                         for a in selection)

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1200,
            system=SYNTHESE_SYSTEM,
            messages=[{"role": "user", "content": listing}],
        )
    except Exception as exc:  # bonus, jamais bloquant
        print(f"  (synthese en echec, on continue : {exc})")
        return None

    text = "".join(b.text for b in response.content if b.type == "text")
    points = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(("- ", "\u2022 ", "* ")):
            point = line[2:].strip()
            if point:
                points.append(point[:300])
    if not points:
        return None

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": CLAUDE_MODEL,
        "based_on": len(selection),
        "points": points[:5],
    }


# --- Entree -----------------------------------------------------------------

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


def explain(articles, article_id):
    """Detaille le calcul pour un article — utile pour verifier le lexique."""
    for article in articles:
        if article["id"].startswith(article_id):
            analyze_article(article)
            text = normalize(f"{article.get('title', '')} {article.get('summary', '')}")
            matched = score_categories(text)
            print(f"\n{article['title']}\n")
            print(f"  source      : {article['source']} (tier {article['tier']}, "
                  f"poids {article['weight']})")
            print(f"  decision    : {article['has_decision_marker']}")
            print(f"  importance  : {article['importance']}")
            print(f"  actifs      : {article['assets_effective']} "
                  f"(detectes: {article['assets_detected']})")
            print("  categories  :")
            for category, data in matched.items():
                detail = ", ".join(f"{t} x{n}" for t, n in data["terms"])
                print(f"      {DIRECTIONS[category]:+.1f} "
                      f"{category:<22} {data['intensity']:.3f}  [{detail}]")
            print(f"  tonalite    : {article['tone']} (via {article['scored_by']})")
            print(f"  crypto      : {article['crypto_tone']}")
            print(f"  stress      : {article['is_stress']}\n")
            return
    print(f"Aucun article ne correspond a l'id {article_id}")


def main():
    parser = argparse.ArgumentParser(description="Scoring lexical et indice quotidien")
    parser.add_argument("--no-claude", action="store_true",
                        help="Force l'etage lexical seul")
    parser.add_argument("--explain", metavar="ID",
                        help="Detaille le calcul pour un article (prefixe d'id)")
    args = parser.parse_args()

    articles = load_json(ARTICLES_PATH, [])
    if not articles:
        print("Aucun article a analyser. Lance d'abord `python collector.py`.")
        return

    if args.explain:
        explain(articles, args.explain)
        return

    for article in articles:
        analyze_article(article)

    requalified = 0
    if not args.no_claude:
        requalified = claude_requalify(articles)

    index = build_index(load_json(INDEX_PATH, {}), articles)

    synthese = None if args.no_claude else build_synthese(articles)

    save_json(ARTICLES_PATH, articles)
    save_json(INDEX_PATH, index)
    if synthese:
        save_json(SYNTHESE_PATH, synthese)
        print(f"  synthese : {len(synthese['points'])} points "
              f"(modele {synthese['model']})")

    latest = next(iter(index), None)
    print(f"Analyse terminee : {len(articles)} articles scores "
          f"({requalified} requalifies par Claude), {len(index)} jours dans l'indice.")
    if latest:
        day = index[latest]
        print(f"  {latest} : {day['articles_count']} articles | "
              f"tone_cb={day['tone_cb']} tone_global={day['tone_global']} "
              f"regul_crypto={day['regul_crypto']} stress={day['stress']}")


if __name__ == "__main__":
    main()
