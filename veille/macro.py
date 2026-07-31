#!/usr/bin/env python3
"""Series numeriques gratuites et calcul du regime de marche.

Quatre sources, toutes gratuites et sans compte obligatoire :
  - ccxt          : BTC et ETH (prix, MM50, MM200, decote 1 an, volatilite 30j,
                    taux de financement des perpetuels)
  - yfinance      : ^GSPC, URTH, ^VIX, DX-Y.NYB
  - alternative.me: indice Fear & Greed crypto
  - FRED          : DGS10 et DFF, uniquement si FRED_API_KEY existe

Le regime tient en trois etats — favorable au risque, neutre, defavorable —
obtenus en comptant les criteres favorables parmi ceux qui ont pu etre
calcules. Chaque critere est conserve avec sa valeur et son seuil : le
calcul doit rester verifiable d'un coup d'oeil, sans relire ce fichier.

Aucune source n'est indispensable. Une source muette retire ses criteres du
decompte au lieu de les compter comme defavorables — sans quoi une panne
reseau se lirait comme un marche baissier.

Usage:
    python macro.py
    python macro.py --show    Affiche le detail sans rien ecrire
"""

import argparse
import json
import math
import os
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
MACRO_PATH = DATA_DIR / "macro.json"

HTTP_TIMEOUT = 12  # borne le pire cas : 11 sources x 2 tentatives reste sous le timeout du workflow
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36")

# Chaines de repli : la premiere bourse qui repond gagne. Binance est
# volontairement absente des premiers choix, elle renvoie 451 depuis une
# bonne partie des hebergeurs (dont les runners GitHub).
SPOT_VENUES = [
    ("kraken", "BTC/USD", "ETH/USD"),
    ("coinbase", "BTC/USD", "ETH/USD"),
    ("okx", "BTC/USDT", "ETH/USDT"),
    ("kucoin", "BTC/USDT", "ETH/USDT"),
    ("bitstamp", "BTC/USD", "ETH/USD"),
]

FUNDING_VENUES = [
    ("okx", "BTC/USDT:USDT"),
    ("kucoin", "BTC/USDT:USDT"),
    ("krakenfutures", "BTC/USD:USD"),
    ("bybit", "BTC/USDT:USDT"),
]

YAHOO_TICKERS = [
    ("sp500", "^GSPC", "S&P 500"),
    ("msci_world", "URTH", "MSCI World"),
    ("vix", "^VIX", "VIX"),
    ("dxy", "DX-Y.NYB", "Dollar (DXY)"),
]


# --- Outils -----------------------------------------------------------------

def http_json(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def proxy_url():
    """Le bac a sable local passe par un proxy ; les runners GitHub non.

    On lit l'environnement au lieu de coder une adresse en dur : le meme
    fichier marche donc des deux cotes.
    """
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")


def moving_average(values, window):
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def annualised_volatility(closes, window=30):
    """Ecart-type des rendements logarithmiques, annualise (365 jours)."""
    if len(closes) < window + 1:
        return None
    returns = []
    for previous, current in zip(closes[-(window + 1):-1], closes[-window:]):
        if previous > 0 and current > 0:
            returns.append(math.log(current / previous))
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(365)


def drawdown_from_high(closes, window=365):
    """Decote par rapport au plus haut de la fenetre, entre 0 et 1."""
    recent = closes[-window:] if len(closes) > window else closes
    if not recent:
        return None
    peak = max(recent)
    if peak <= 0:
        return None
    return (peak - recent[-1]) / peak


# --- ccxt : crypto ----------------------------------------------------------

def fetch_crypto(failures):
    """Prix, moyennes mobiles, decote, volatilite et taux de financement."""
    try:
        import ccxt
    except ImportError:
        failures.append(("ccxt", "paquet absent"))
        return {}

    data = {}
    proxy = proxy_url()

    for name, btc_symbol, eth_symbol in SPOT_VENUES:
        try:
            exchange = getattr(ccxt, name)({"timeout": HTTP_TIMEOUT * 1000,
                                            "enableRateLimit": True})
            if proxy:
                exchange.httpsProxy = proxy

            for key, symbol in (("btc", btc_symbol), ("eth", eth_symbol)):
                candles = exchange.fetch_ohlcv(symbol, "1d", limit=400)
                closes = [c[4] for c in candles if c[4] is not None]
                if len(closes) < 200:
                    raise ValueError(f"{symbol}: seulement {len(closes)} bougies")
                data[key] = {
                    "price": closes[-1],
                    "ma50": moving_average(closes, 50),
                    "ma200": moving_average(closes, 200),
                    "drawdown_1y": drawdown_from_high(closes),
                    "volatility_30d": annualised_volatility(closes, 30),
                }
            data["spot_venue"] = name
            break
        except Exception as exc:
            failures.append((f"ccxt/{name}", str(exc)[:120]))

    for name, symbol in FUNDING_VENUES:
        try:
            exchange = getattr(ccxt, name)({"timeout": HTTP_TIMEOUT * 1000,
                                            "enableRateLimit": True,
                                            "options": {"defaultType": "swap"}})
            if proxy:
                exchange.httpsProxy = proxy
            funding = exchange.fetch_funding_rate(symbol)
            rate = funding.get("fundingRate")
            if rate is None:
                raise ValueError("taux absent de la reponse")
            data["funding_btc"] = rate
            data["funding_venue"] = name
            break
        except Exception as exc:
            failures.append((f"funding/{name}", str(exc)[:120]))

    return data


# --- yfinance (avec repli urllib) -------------------------------------------

def _yahoo_via_urllib(ticker):
    """Repli direct sur l'API publique de Yahoo, sans dependance.

    yfinance s'appuie sur curl_cffi, qui echoue derriere certains proxies
    d'entreprise. Ce repli utilise urllib, qui honore les variables
    d'environnement de proxy — la section ne disparait donc pas du tableau
    de bord juste parce que la bibliotheque a trebuche.
    """
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ticker)}?range=1y&interval=1d")
    payload = http_json(url)
    result = payload["chart"]["result"][0]
    closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
    if not closes:
        raise ValueError("aucune cloture")
    return closes


def _yahoo_via_yfinance(ticker):
    import yfinance as yf
    history = yf.Ticker(ticker).history(period="1y", interval="1d",
                                        auto_adjust=False)
    if history.empty:
        raise ValueError("historique vide")
    return [float(v) for v in history["Close"].tolist() if v == v]


def fetch_equities(failures):
    """^GSPC, URTH, ^VIX, DX-Y.NYB : dernier cours et moyennes mobiles."""
    data = {}
    for key, ticker, label in YAHOO_TICKERS:
        closes = None
        for method, fetch in (("yfinance", _yahoo_via_yfinance),
                              ("yahoo-direct", _yahoo_via_urllib)):
            try:
                closes = fetch(ticker)
                data.setdefault("equities_source", method)
                break
            except Exception as exc:
                failures.append((f"{method}/{ticker}", str(exc)[:120]))
        if not closes:
            continue
        data[key] = {
            "label": label,
            "price": closes[-1],
            "ma50": moving_average(closes, 50),
            "ma200": moving_average(closes, 200),
        }
    return data


# --- alternative.me ---------------------------------------------------------

def fetch_fear_greed(failures):
    try:
        payload = http_json("https://api.alternative.me/fng/?limit=1")
        entry = payload["data"][0]
        return {
            "value": int(entry["value"]),
            "label": entry.get("value_classification", ""),
        }
    except Exception as exc:
        failures.append(("alternative.me", str(exc)[:120]))
        return {}


# --- FRED (seulement si la cle existe) --------------------------------------

def fetch_fred(failures):
    """DGS10 et DFF. Sans FRED_API_KEY, l'etape est ignoree en silence."""
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        return {}

    start = (datetime.now(timezone.utc) - timedelta(days=200)).strftime("%Y-%m-%d")
    data = {}
    for series_id in ("DGS10", "DFF"):
        try:
            url = ("https://api.stlouisfed.org/fred/series/observations"
                   f"?series_id={series_id}&api_key={urllib.parse.quote(api_key)}"
                   f"&file_type=json&observation_start={start}")
            payload = http_json(url)
            points = [(o["date"], float(o["value"]))
                      for o in payload.get("observations", [])
                      if o.get("value") not in (None, ".", "")]
            if not points:
                raise ValueError("aucune observation exploitable")
            latest_date, latest = points[-1]
            # Niveau d'il y a environ trois mois, pour juger du sens.
            target = datetime.strptime(latest_date, "%Y-%m-%d") - timedelta(days=90)
            earlier = min(points, key=lambda p: abs(
                datetime.strptime(p[0], "%Y-%m-%d") - target))[1]
            data[series_id.lower()] = {"value": latest, "date": latest_date,
                                       "three_months_ago": earlier}
        except Exception as exc:
            failures.append((f"fred/{series_id}", str(exc)[:120]))
    return data


# --- Criteres et regime -----------------------------------------------------

def money(value):
    if value is None:
        return "--"
    if value >= 1000:
        return f"{value:,.0f} $".replace(",", " ")
    return f"{value:,.2f} $".replace(",", " ")


def criterion(group, label, ok, value, reference):
    return {"group": group, "label": label, "ok": ok,
            "value": value, "reference": reference}


def build_criteria(crypto, equities, fear_greed, fred):
    """Chaque critere porte sa valeur ET son seuil, pour etre verifiable.

    `ok = None` signifie « non calculable » : le critere sort du decompte au
    lieu de compter comme defavorable.
    """
    items = []

    # --- Crypto
    for key, name in (("btc", "BTC"), ("eth", "ETH")):
        block = crypto.get(key) or {}
        price, ma200, ma50 = block.get("price"), block.get("ma200"), block.get("ma50")
        items.append(criterion(
            "Crypto", f"{name} au-dessus de sa MM200",
            None if price is None or ma200 is None else price > ma200,
            money(price), f"MM200 {money(ma200)}"))
        if key == "btc":
            items.append(criterion(
                "Crypto", "BTC au-dessus de sa MM50",
                None if price is None or ma50 is None else price > ma50,
                money(price), f"MM50 {money(ma50)}"))

    btc = crypto.get("btc") or {}
    drawdown = btc.get("drawdown_1y")
    items.append(criterion(
        "Crypto", "Décote BTC sur le plus haut 1 an",
        None if drawdown is None else drawdown < 0.25,
        "--" if drawdown is None else f"-{drawdown * 100:.0f} %", "moins de 25 %"))

    volatility = btc.get("volatility_30d")
    items.append(criterion(
        "Crypto", "Volatilité BTC 30 jours",
        None if volatility is None else volatility < 0.60,
        "--" if volatility is None else f"{volatility * 100:.0f} %", "moins de 60 %"))

    funding = crypto.get("funding_btc")
    items.append(criterion(
        "Crypto", "Financement des perpétuels BTC",
        None if funding is None else funding > 0,
        "--" if funding is None else f"{funding * 100:+.4f} %", "positif"))

    # --- Actions et devises
    for key, label, reference_key, sense in (
            ("sp500", "S&P 500 au-dessus de sa MM200", "ma200", "above"),
            ("msci_world", "MSCI World au-dessus de sa MM200", "ma200", "above"),
            ("dxy", "Dollar sous sa MM50", "ma50", "below")):
        block = equities.get(key) or {}
        price, reference = block.get("price"), block.get(reference_key)
        if price is None or reference is None:
            ok = None
        else:
            ok = price > reference if sense == "above" else price < reference
        label_ref = "MM200" if reference_key == "ma200" else "MM50"
        items.append(criterion(
            "Actions et devises", label, ok,
            "--" if price is None else f"{price:,.2f}".replace(",", " "),
            f"{label_ref} {'--' if reference is None else f'{reference:,.2f}'.replace(',', chr(8201))}"))

    vix = (equities.get("vix") or {}).get("price")
    items.append(criterion(
        "Actions et devises", "VIX calme",
        None if vix is None else vix < 20,
        "--" if vix is None else f"{vix:.1f}", "moins de 20"))

    # --- Sentiment
    value = fear_greed.get("value")
    items.append(criterion(
        "Sentiment", "Fear & Greed crypto",
        None if value is None else value >= 50,
        "--" if value is None else f"{value}/100", "50 ou plus"))

    # --- Taux (seulement si FRED a repondu)
    for series_id, label in (("dgs10", "Taux 10 ans en détente"),
                             ("dff", "Taux directeur en détente")):
        block = fred.get(series_id)
        if block is None:
            continue
        latest, earlier = block["value"], block["three_months_ago"]
        items.append(criterion(
            "Taux", label, latest <= earlier,
            f"{latest:.2f} %", f"il y a 3 mois {earlier:.2f} %"))

    return items


def compute_regime(criteria):
    """Trois etats, a partir de la part de criteres favorables.

    Le denominateur ne compte que les criteres reellement calcules : une
    source muette ne doit pas faire basculer le regime vers le defavorable.
    """
    available = [c for c in criteria if c["ok"] is not None]
    favorable = [c for c in available if c["ok"]]

    if not available:
        return {"state": "indisponible", "favorable": 0, "available": 0,
                "total": len(criteria), "ratio": None}

    ratio = len(favorable) / len(available)
    if ratio >= 0.60:
        state = "favorable au risque"
    elif ratio <= 0.35:
        state = "défavorable au risque"
    else:
        state = "neutre"

    return {"state": state, "favorable": len(favorable),
            "available": len(available), "total": len(criteria),
            "ratio": round(ratio, 4)}


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


def collect():
    failures = []
    crypto = fetch_crypto(failures)
    equities = fetch_equities(failures)
    fear_greed = fetch_fear_greed(failures)
    fred = fetch_fred(failures)

    criteria = build_criteria(crypto, equities, fear_greed, fred)
    regime = compute_regime(criteria)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regime": regime,
        "criteria": criteria,
        "crypto": crypto,
        "equities": equities,
        "fear_greed": fear_greed,
        "fred": fred,
        "failures": [{"source": s, "reason": r} for s, r in failures],
    }


def print_report(snapshot):
    regime = snapshot["regime"]
    part = "" if regime["ratio"] is None else f", {regime['ratio'] * 100:.0f} %"
    print(f"\nRegime : {regime['state'].upper()}  "
          f"({regime['favorable']}/{regime['available']} criteres favorables{part})")
    current_group = None
    for item in snapshot["criteria"]:
        if item["group"] != current_group:
            current_group = item["group"]
            print(f"\n  {current_group}")
        mark = "?" if item["ok"] is None else ("oui" if item["ok"] else "non")
        print(f"    [{mark:>3}] {item['label']:<38} {item['value']:>14}  "
              f"({item['reference']})")
    if snapshot["failures"]:
        print(f"\n  {len(snapshot['failures'])} source(s) muette(s) :")
        for failure in snapshot["failures"]:
            print(f"    - {failure['source']} : {failure['reason']}")


def main():
    parser = argparse.ArgumentParser(description="Series macro et regime de marche")
    parser.add_argument("--show", action="store_true",
                        help="Affiche le detail sans rien ecrire sur le disque")
    args = parser.parse_args()

    snapshot = collect()
    print_report(snapshot)

    if args.show:
        return

    # L'historique n'est jamais purge : meme logique que index.json, il
    # constitue la memoire longue des series numeriques.
    previous = load_json(MACRO_PATH, {})
    history = previous.get("history", {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history[today] = {
        "regime": snapshot["regime"]["state"],
        "favorable": snapshot["regime"]["favorable"],
        "available": snapshot["regime"]["available"],
        "btc": (snapshot["crypto"].get("btc") or {}).get("price"),
        "eth": (snapshot["crypto"].get("eth") or {}).get("price"),
        "sp500": (snapshot["equities"].get("sp500") or {}).get("price"),
        "vix": (snapshot["equities"].get("vix") or {}).get("price"),
        "fear_greed": snapshot["fear_greed"].get("value"),
    }
    snapshot["history"] = dict(sorted(history.items(), reverse=True))

    save_json(MACRO_PATH, snapshot)
    print(f"\ndata/macro.json ecrit ({len(snapshot['history'])} jours d'historique).")


if __name__ == "__main__":
    main()
