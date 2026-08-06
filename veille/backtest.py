#!/usr/bin/env python3
"""Confronte les signaux de l'outil a ce qui s'est reellement passe ensuite.

Le tableau de bord affiche une tendance par actif : « au-dessus de ses
moyennes 50 et 200 jours » = haussiere. Reste la question que personne ne
pose jamais dans une application de finance grand public : est-ce que ce
signal vaut quelque chose ?

Ce module y repond avec des chiffres, pas avec une opinion. Pour chaque
actif, il rejoue la meme regle sur plusieurs annees d'historique, mesure ce
que l'actif a fait dans les VERDICT_HORIZON jours suivants, et compare les
journees classees haussieres aux journees classees baissieres. Si l'ecart
est nul, l'outil le dit — c'est meme le resultat le plus utile qu'il puisse
produire, parce qu'il evite de prendre une decision sur un signal creux.

La regle rejouee est exactement celle de macro.py (annotate_trend), importee
et non recopiee : une mesure qui testerait une autre regle que celle
affichee ne mesurerait rien.

Deuxieme role : situer les chiffres du jour dans leur histoire. « VIX a 16 »
ne dit rien a personne. « VIX a 16, plus calme que 78 % des deux dernieres
annees » se lit d'un coup d'oeil.

Usage:
    python backtest.py
    python backtest.py --show    Affiche sans rien ecrire
"""

import argparse
import json
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from macro import (HTTP_TIMEOUT, SPOT_VENUES, YAHOO_TICKERS, annotate_trend,
                   annualised_volatility, drawdown_from_high, http_json,
                   moving_average, proxy_url, save_json)

DATA_DIR = Path(__file__).parent / "data"
BACKTEST_PATH = DATA_DIR / "backtest.json"

# Horizon de mesure. A un jour, le bruit ecrase tout signal : meme une regle
# qui marche ne se voit pas. A vingt seances (un mois de bourse), l'horizon
# correspond a ce que fait reellement quelqu'un qui consulte un tableau de
# bord une fois par jour et n'entre pas en position toutes les heures.
VERDICT_HORIZON = 20

# En deca, l'echantillon ne permet aucune affirmation.
MIN_SAMPLE = 60

# Nombre de paquets pour les situations comparables. Cinq quintiles laissent
# environ 250 seances par paquet sur cinq ans : assez pour dire quelque chose,
# assez grossier pour ne pas se decouper sur mesure autour du present.
BUCKETS = 5

# Ecart minimal, en points de pourcentage sur l'horizon, pour qu'un signal
# soit dit utile. Sous ce seuil, l'ecart est indiscernable du hasard sur des
# echantillons de cette taille.
EDGE_USEFUL = 2.0
EDGE_WEAK = 0.5

# Actifs mesures : ceux sur lesquels la page affiche un verdict.
CRYPTO_ASSETS = [("btc", "Bitcoin"), ("eth", "Ethereum")]

# Tentatives par ticker, chacune essayant les deux chemins vers Yahoo.
ATTEMPTS = 2

# Version du format ecrit. A incrementer des qu'un champ apparait : un
# fichier d'une version anterieure est alors recalcule sans attendre.
SCHEMA = 3

# Age au-dela duquel le backtest est recalcule. Une journee : la mesure porte
# sur des annees, une seance de plus ou de moins n'y change rien.
MAX_AGE_HOURS = 20


# --- Recuperation des historiques longs -------------------------------------

def iso_day(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%d")

def fetch_crypto_history(failures):
    """Historiques journaliers BTC et ETH, via la meme chaine de repli que macro.

    Kraken plafonne a 720 bougies journalieres, soit environ deux ans. C'est
    court pour un backtest, et cette limite est dite telle quelle sur la page
    plutot que maquillee.
    """
    try:
        import ccxt
    except ImportError:
        failures.append(("ccxt", "paquet absent"))
        return {}

    proxy = proxy_url()
    for name, btc_symbol, eth_symbol in SPOT_VENUES:
        series = {}
        try:
            exchange = getattr(ccxt, name)({"timeout": HTTP_TIMEOUT * 1000,
                                            "enableRateLimit": True})
            if proxy:
                exchange.httpsProxy = proxy
            for key, symbol in (("btc", btc_symbol), ("eth", eth_symbol)):
                candles = exchange.fetch_ohlcv(symbol, "1d", limit=1000)
                points = [(iso_day(c[0] / 1000), c[4])
                          for c in candles if c[4] is not None]
                if len(points) < 300:
                    raise ValueError(f"{symbol}: seulement {len(points)} bougies")
                series[key] = points
            return series
        except Exception as exc:
            failures.append((f"ccxt/{name}", str(exc)[:120]))
    return {}


def _yahoo_direct(ticker, years):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ticker)}?range={years}y&interval=1d")
    result = http_json(url)["chart"]["result"][0]
    closes = result["indicators"]["quote"][0]["close"]
    return [(iso_day(ts), close)
            for ts, close in zip(result["timestamp"], closes)
            if close is not None]


def _yahoo_library(ticker, years):
    import yfinance as yf
    history = yf.Ticker(ticker).history(period=f"{years}y", interval="1d",
                                        auto_adjust=False)
    if history.empty:
        raise ValueError("historique vide")
    return [(stamp.strftime("%Y-%m-%d"), float(value))
            for stamp, value in history["Close"].items() if value == value]


def fetch_yahoo_history(ticker, failures, years=5):
    """Cinq ans de clotures journalieres, avec deux chemins et une pause.

    Onze tickers demandes coup sur coup font repondre 429 a Yahoo. Une courte
    pause suffit a repasser, et une source qui reste muette retire seulement
    son actif de la mesure.

    Le nombre de tentatives est volontairement bas. Quand Yahoo ferme
    vraiment la porte — verifie ici, ou les douze tickers ont echoue sur les
    deux chemins — chaque tentative supplementaire coute une minute de plus a
    l'ensemble du tour, pour un resultat identique.
    """
    for attempt in range(ATTEMPTS):
        for name, fetch in (("yahoo-direct", _yahoo_direct),
                            ("yfinance", _yahoo_library)):
            try:
                points = fetch(ticker, years)
                if len(points) < 300:
                    raise ValueError(f"seulement {len(points)} clotures")
                return points
            except Exception as exc:
                if attempt == ATTEMPTS - 1:
                    failures.append((f"{name}/{ticker}", str(exc)[:120]))
        time.sleep(2)
    return []


# --- Rejeu de la regle -------------------------------------------------------

def rolling_means(closes, window):
    """Moyenne mobile a chaque date, en une seule passe.

    La premiere version recalculait la moyenne depuis le debut a chaque
    journee rejouee, et refaisait le meme travail trois fois — une fois par
    mesure. Sur douze marches et cinq ans, cela representait des dizaines de
    millions d'additions pour un resultat identique. La somme glissante donne
    la meme chose en un passage.

    La liste rendue a la longueur de `closes` ; les positions ou la fenetre
    n'est pas encore pleine valent None.
    """
    means = [None] * len(closes)
    total = 0.0
    for i, value in enumerate(closes):
        total += value
        if i >= window:
            total -= closes[i - window]
        if i >= window - 1:
            means[i] = total / window
    return means


def trend_series(closes):
    """Etat de tendance a chaque date, calcule une fois pour toutes.

    La regle reste celle de macro.py : elle est appelee, pas recopiee.
    """
    ma50 = rolling_means(closes, 50)
    ma200 = rolling_means(closes, 200)
    return [annotate_trend({"price": price, "ma50": ma50[i],
                            "ma200": ma200[i]}).get("trend")
            for i, price in enumerate(closes)], ma200


def replay(trends, closes, horizon=VERDICT_HORIZON):
    """Repartit les rendements a venir selon l'etat du jour.

    Les fenetres se chevauchent : deux jours consecutifs partagent 19 des 20
    seances mesurees. Le nombre d'observations est donc un nombre de jours
    observes, pas un nombre d'experiences independantes. C'est dit sur la
    page, parce que confondre les deux est la facon la plus courante de se
    convaincre qu'un signal marche.
    """
    states = {"haussiere": [], "baissiere": [], "indecise": []}
    for i in range(200, len(closes) - horizon):
        trend = trends[i]
        if trend in states:
            states[trend].append(closes[i + horizon] / closes[i] - 1)
    return states


def phase_lengths(trends):
    """Duree, en seances, de chaque phase de tendance passee.

    « Haussier depuis 72 jours » ne dit rien tant qu'on ignore combien de
    temps ces phases durent d'habitude. La phase en cours est exclue : elle
    n'est pas finie, la compter raccourcirait artificiellement la mediane.
    """
    lengths = {"haussiere": [], "baissiere": [], "indecise": []}
    start = 200
    for i in range(201, len(trends)):
        if trends[i] != trends[i - 1]:
            if trends[i - 1] in lengths:
                lengths[trends[i - 1]].append(i - start)
            start = i
    return lengths


def median(values):
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def baseline(closes, horizon=VERDICT_HORIZON):
    """Ce qu'a fait une seance quelconque, sans regarder aucun signal.

    C'est le denominateur qui manquait. « +1,2 % apres un signal haussier »
    ne veut rien dire tant qu'on ignore ce qu'a fait une seance ordinaire :
    si la moyenne generale est de +1,5 %, le signal haussier fait moins bien
    que ne rien regarder du tout.
    """
    returns = [closes[i + horizon] / closes[i] - 1
               for i in range(200, len(closes) - horizon)]
    return summarise(returns)


def analogues(closes, ma200, horizon=VERDICT_HORIZON, buckets=BUCKETS):
    """Les seances passees ou le marche etait aussi etire qu'aujourd'hui.

    L'ecart au MM200 est decoupe en quintiles sur tout l'historique. La
    journee d'aujourd'hui tombe dans l'un d'eux ; on regarde ce qu'ont fait
    les autres journees du meme quintile dans les `horizon` seances suivantes.

    C'est volontairement plus grossier qu'une regle ajustee : cinq paquets
    decoupes par les donnees elles-memes, aucun seuil choisi a la main. Une
    regle affinee jusqu'a bien marcher sur le passe ne mesure plus que sa
    propre mise au point.
    """
    stretches, forward = [], []
    for i in range(200, len(closes) - horizon):
        if not ma200[i]:
            continue
        stretches.append(closes[i] / ma200[i] - 1)
        forward.append(closes[i + horizon] / closes[i] - 1)
    if len(stretches) < buckets * MIN_SAMPLE:
        return None

    if not ma200[-1]:
        return None
    current = closes[-1] / ma200[-1] - 1

    ordered = sorted(stretches)
    size = len(ordered) / buckets
    edges = [ordered[min(len(ordered) - 1, int(size * (k + 1)))]
             for k in range(buckets - 1)]

    def bucket_of(value):
        for k, edge in enumerate(edges):
            if value <= edge:
                return k
        return buckets - 1

    here = bucket_of(current)
    same = [f for stretch, f in zip(stretches, forward)
            if bucket_of(stretch) == here]
    if len(same) < MIN_SAMPLE:
        return None

    low = ordered[0] if here == 0 else edges[here - 1]
    high = ordered[-1] if here == buckets - 1 else edges[here]
    return {
        "current_stretch": round(current * 100, 2),
        "bucket": here + 1,
        "buckets": buckets,
        "range_pct": [round(low * 100, 1), round(high * 100, 1)],
        "outcome": summarise(same),
    }


def current_state(dates, trends, lengths):
    """Etat de tendance du jour, depuis quand il dure, et ce qui est habituel.

    « Haussiere » tout court ne dit pas grand-chose. « Haussiere depuis 34
    jours, alors que ces phases en durent 21 d'habitude » situe la position
    dans le temps et dans l'histoire du marche. Les deux sont disponibles des
    le premier jour d'utilisation, contrairement a une memoire que l'outil
    mettrait des mois a se constituer.
    """
    if len(trends) < 201:
        return None
    latest = trends[-1]
    if latest is None:
        return None

    start = len(trends) - 1
    while start > 200 and trends[start - 1] == latest:
        start -= 1

    usual = median(lengths.get(latest) or [])
    return {
        "trend": latest,
        "since": dates[start],
        "days": (datetime.strptime(dates[-1], "%Y-%m-%d")
                 - datetime.strptime(dates[start], "%Y-%m-%d")).days,
        "sessions": len(trends) - start,
        "usual_sessions": None if usual is None else round(usual),
        "past_phases": len(lengths.get(latest) or []),
    }


def summarise(returns):
    if not returns:
        return None
    ordered = sorted(returns)
    middle = len(ordered) // 2
    median = (ordered[middle] if len(ordered) % 2
              else (ordered[middle - 1] + ordered[middle]) / 2)
    return {
        "days": len(returns),
        "mean_pct": round(sum(returns) / len(returns) * 100, 2),
        "median_pct": round(median * 100, 2),
        "positive_pct": round(sum(1 for r in returns if r > 0)
                              / len(returns) * 100, 1),
    }


def percent(value):
    """Pourcentage signe, virgule decimale : ces phrases se lisent en francais."""
    return f"{value:+.1f} %".replace(".", ",")


def verdict(states):
    """Traduit l'ecart haussier/baissier en une phrase honnete.

    Trois issues seulement, et la plus frequente est « aucun ecart » : c'est
    le resultat normal quand on teste une regle simple sur un marche liquide.
    """
    up = states.get("haussiere")
    down = states.get("baissiere")
    if not up or not down:
        return None, "Pas encore assez d'historique dans les deux états."
    if up["days"] < MIN_SAMPLE or down["days"] < MIN_SAMPLE:
        return None, (f"Échantillon trop court : {up['days']} jours haussiers "
                      f"et {down['days']} baissiers, il en faut {MIN_SAMPLE} "
                      "de chaque.")

    edge = up["mean_pct"] - down["mean_pct"]
    detail = (f"Après un signal haussier, {percent(up['mean_pct'])} en moyenne "
              f"sur {VERDICT_HORIZON} séances ; après un signal baissier, "
              f"{percent(down['mean_pct'])}.")

    if edge >= EDGE_USEFUL:
        return edge, "Le signal a séparé les deux cas. " + detail
    if edge <= -EDGE_USEFUL:
        return edge, ("Le signal a séparé les deux cas, mais à l'envers de "
                      "l'intuition. " + detail)
    if abs(edge) <= EDGE_WEAK:
        return edge, ("Aucun écart mesurable : suivre ce signal revenait à "
                      "ne pas le suivre. " + detail)
    return edge, "Écart trop faible pour en tirer quoi que ce soit. " + detail


def verdict_word(edge):
    if edge is None:
        return "non mesurable"
    if abs(edge) >= EDGE_USEFUL:
        return "signal utile" if edge > 0 else "signal inversé"
    if abs(edge) <= EDGE_WEAK:
        return "sans valeur"
    return "signal faible"


# --- Percentiles : situer le chiffre du jour dans son histoire ---------------

def percentile_of(value, series):
    """Part de l'historique strictement inferieure a `value`, en pourcent."""
    if value is None or not series:
        return None
    below = sum(1 for v in series if v < value)
    return round(below / len(series) * 100)


def rolling(series, window, func):
    """Applique `func` sur chaque fenetre glissante : la distribution du passe."""
    out = []
    for i in range(window, len(series) + 1):
        value = func(series[:i])
        if value is not None:
            out.append(value)
    return out


def fetch_fear_greed_history(failures):
    try:
        payload = http_json("https://api.alternative.me/fng/?limit=0")
        return [int(entry["value"]) for entry in payload.get("data", [])
                if str(entry.get("value", "")).isdigit()]
    except Exception as exc:
        failures.append(("alternative.me/histoire", str(exc)[:120]))
        return []


def build_context(crypto_series, vix_closes, fng_history, failures):
    """Quatre chiffres du jour, chacun replace dans sa propre histoire."""
    items = []

    if vix_closes:
        current = vix_closes[-1]
        rank = percentile_of(current, vix_closes)
        if rank is not None:
            items.append({
                "label": "VIX (nervosité des actions américaines)",
                "value": f"{current:.1f}".replace(".", ","),
                "percentile": rank,
                "sentence": (f"plus calme que {100 - rank} % des 5 dernières années"
                             if rank <= 50 else
                             f"plus nerveux que {rank} % des 5 dernières années"),
            })

    if fng_history:
        current = fng_history[0]  # l'API renvoie du plus recent au plus ancien
        rank = percentile_of(current, fng_history)
        if rank is not None:
            items.append({
                "label": "Fear & Greed crypto",
                "value": f"{current}/100",
                "percentile": rank,
                "sentence": (f"plus optimiste que {rank} % de toute l'histoire "
                             "de l'indice" if rank >= 50 else
                             f"plus craintif que {100 - rank} % de toute "
                             "l'histoire de l'indice"),
            })

    btc = crypto_series.get("btc") or []
    if len(btc) > 60:
        volatility = annualised_volatility(btc, 30)
        distribution = rolling(btc, 31, lambda s: annualised_volatility(s, 30))
        rank = percentile_of(volatility, distribution)
        if volatility is not None and rank is not None:
            items.append({
                "label": "Volatilité du Bitcoin sur 30 jours",
                "value": f"{volatility * 100:.0f} %",
                "percentile": rank,
                "sentence": f"plus calme que {100 - rank} % des 2 dernières "
                            "années" if rank <= 50 else
                            f"plus agité que {rank} % des 2 dernières années",
            })

        drawdown = drawdown_from_high(btc)
        distribution = rolling(btc, 30, drawdown_from_high)
        rank = percentile_of(drawdown, distribution)
        if drawdown is not None and rank is not None:
            items.append({
                "label": "Décote du Bitcoin sous son plus haut",
                "value": f"−{drawdown * 100:.0f} %",
                "percentile": rank,
                "sentence": f"plus proche du sommet que {100 - rank} % des "
                            "2 dernières années" if rank <= 50 else
                            f"plus loin du sommet que {rank} % des 2 dernières "
                            "années",
            })

    return items


# --- Ce qui bouge avec quoi --------------------------------------------------

# Fenetre de correlation, en seances communes aux deux series.
CORRELATION_WINDOW = 90

# Paires suivies : (cle A, cle B, phrase quand la correlation est forte,
# phrase quand elle est faible).
CORRELATION_PAIRS = [
    ("btc", "nasdaq", "Bitcoin et Nasdaq"),
    ("btc", "sp500", "Bitcoin et S&P 500"),
    ("eth", "btc", "Ethereum et Bitcoin"),
]


def daily_returns(points):
    """Rendements journaliers indexes par date."""
    out = {}
    for (_, previous), (date, current) in zip(points, points[1:]):
        if previous and current:
            out[date] = current / previous - 1
    return out


def correlation(points_a, points_b, window=CORRELATION_WINDOW):
    """Correlation des rendements sur les dernieres seances communes.

    Les deux series n'ont pas le meme calendrier : les cryptos cotent le
    week-end, pas les indices. On ne garde donc que les dates presentes des
    deux cotes, sans quoi on comparerait un mouvement du samedi a un zero.
    """
    a, b = daily_returns(points_a), daily_returns(points_b)
    dates = sorted(set(a) & set(b))[-window:]
    if len(dates) < 30:
        return None, 0

    xs = [a[d] for d in dates]
    ys = [b[d] for d in dates]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    covariance = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None, len(dates)
    return covariance / (vx * vy) ** 0.5, len(dates)


def link_word(value):
    """Traduit un coefficient en mots, sans faire dire plus qu'il ne dit."""
    strength = abs(value)
    if strength >= 0.6:
        return "bougent ensemble"
    if strength >= 0.3:
        return "bougent un peu ensemble"
    return "bougent chacun de leur côté"


def build_correlations(series):
    items = []
    for key_a, key_b, label in CORRELATION_PAIRS:
        points_a, points_b = series.get(key_a), series.get(key_b)
        if not points_a or not points_b:
            continue
        value, sessions = correlation(points_a, points_b)
        if value is None:
            continue
        items.append({
            "label": label,
            "value": round(value, 2),
            "sessions": sessions,
            "word": link_word(value),
        })
    return items


# --- Assemblage --------------------------------------------------------------

def collect():
    failures = []
    crypto_series = fetch_crypto_history(failures)

    equity_series = {}
    for key, ticker, label in YAHOO_TICKERS:
        points = fetch_yahoo_history(ticker, failures)
        if points:
            equity_series[key] = {"label": label, "points": points}

    assets = {}
    for key, label in CRYPTO_ASSETS:
        points = crypto_series.get(key)
        if points:
            assets[key] = build_asset(label, points, "2 ans (limite de la bourse)")

    # Seuls les indices sur lesquels la page affiche un verdict sont mesures :
    # mesurer le VIX ou le dollar avec une regle de tendance n'aurait pas de
    # sens, ils ne sont pas suivis comme des actifs a detenir.
    for key in ("sp500", "nasdaq", "eurostoxx", "cac40", "dax", "nikkei",
                "hangseng", "shanghai", "msci_world"):
        block = equity_series.get(key)
        if block:
            assets[key] = build_asset(block["label"], block["points"], "5 ans")

    context = build_context(
        {key: [c for _, c in points]
         for key, points in crypto_series.items()},
        [c for _, c in (equity_series.get("vix") or {}).get("points") or []],
        fetch_fear_greed_history(failures),
        failures)

    dated = dict(crypto_series)
    for key, block in equity_series.items():
        dated[key] = block["points"]

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon_days": VERDICT_HORIZON,
        "assets": assets,
        "correlations": build_correlations(dated),
        "context": context,
        "failures": [{"source": s, "reason": r} for s, r in failures],
    }


def build_asset(label, points, depth):
    dates = [d for d, _ in points]
    closes = [c for _, c in points]
    # Les moyennes mobiles et les etats de tendance sont calcules une seule
    # fois, puis partages par les quatre mesures qui les utilisent.
    trends, ma200 = trend_series(closes)
    states = {name: summarise(values)
              for name, values in replay(trends, closes).items()}
    edge, sentence = verdict(states)
    return {
        "label": label,
        "depth": depth,
        "observed_days": len(closes),
        "current": current_state(dates, trends, phase_lengths(trends)),
        "states": states,
        "baseline": baseline(closes),
        "analogues": analogues(closes, ma200),
        "edge_pct": None if edge is None else round(edge, 2),
        "verdict": verdict_word(edge),
        "sentence": sentence,
    }


def print_report(result):
    print(f"Horizon : {result['horizon_days']} seances\n")
    for key, asset in result["assets"].items():
        edge = asset["edge_pct"]
        edge_text = "--" if edge is None else f"{edge:+.2f} pt"
        current = asset.get("current") or {}
        etat = (f"{current.get('trend', '?')} depuis {current.get('days', '?')} j"
                if current else "etat inconnu")
        print(f"  {asset['label']:<16} {asset['verdict']:<16} "
              f"ecart {edge_text:>10}   {etat}")
        for name in ("haussiere", "baissiere"):
            state = asset["states"].get(name)
            if state:
                print(f"      {name:<10} {state['mean_pct']:+7.2f} % moyen  "
                      f"{state['positive_pct']:5.1f} % de hausses  "
                      f"{state['days']} jours")
        base = asset.get("baseline")
        if base:
            print(f"      {'reference':<10} {base['mean_pct']:+7.2f} % moyen  "
                  f"{base['positive_pct']:5.1f} % de hausses  "
                  f"{base['days']} jours (toutes seances)")
        similar = asset.get("analogues")
        if similar:
            out = similar["outcome"]
            print(f"      comparable {out['mean_pct']:+7.2f} % moyen  "
                  f"{out['positive_pct']:5.1f} % de hausses  "
                  f"{out['days']} jours (ecart MM200 "
                  f"{similar['current_stretch']:+.1f} %, paquet "
                  f"{similar['bucket']}/{similar['buckets']})")
    if result.get("correlations"):
        print("\n  Ce qui bouge avec quoi :")
        for item in result["correlations"]:
            print(f"    {item['label']:<24} {item['value']:+.2f}  "
                  f"{item['word']} ({item['sessions']} seances)")
    if result["context"]:
        print("\n  Contexte :")
        for item in result["context"]:
            print(f"    {item['label']:<44} {item['value']:>8}  "
                  f"({item['sentence']})")
    if result["failures"]:
        print(f"\n  {len(result['failures'])} source(s) muette(s) :")
        for failure in result["failures"]:
            print(f"    - {failure['source']} : {failure['reason']}")


def hours_since(path):
    """Age du fichier existant, ou None s'il est absent, illisible ou perime.

    « Perime » vaut aussi pour un fichier ecrit par une version anterieure du
    module : sans ce controle, ajouter un champ laisserait la page amputee
    pendant toute la duree de fraicheur, alors que le code sait deja le
    calculer.
    """
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        if saved.get("schema") != SCHEMA:
            return None
        age = datetime.now(timezone.utc) - datetime.fromisoformat(
            saved["generated_at"])
        return age.total_seconds() / 3600
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Mesure la valeur des signaux")
    parser.add_argument("--show", action="store_true",
                        help="Affiche sans rien ecrire")
    parser.add_argument("--max-age-hours", type=float, default=MAX_AGE_HOURS,
                        help="Ne recalcule pas si le fichier est plus recent")
    parser.add_argument("--force", action="store_true",
                        help="Recalcule quel que soit l'age du fichier")
    args = parser.parse_args()

    # Douze marches sur cinq ans, c'est une douzaine de requetes longues.
    # Les rejouer toutes les heures sature les serveurs de Yahoo pour rien :
    # un backtest sur cinq ans ne change pas d'une heure a l'autre.
    age = hours_since(BACKTEST_PATH)
    if not args.force and age is not None and age < args.max_age_hours:
        print(f"data/backtest.json a {age:.1f} h, recalcul inutile "
              f"(seuil {args.max_age_hours:.0f} h).")
        return

    result = collect()
    print_report(result)

    if not args.show:
        save_json(BACKTEST_PATH, result)
        print(f"\ndata/backtest.json ecrit ({len(result['assets'])} actifs mesures).")


if __name__ == "__main__":
    main()
