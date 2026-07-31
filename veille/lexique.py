"""Lexique de scoring — deterministe, en anglais et en francais.

La propriete essentielle de ce module : un meme texte produit toujours le
meme score. Aucun appel reseau, aucun aleatoire, aucune dependance a la date
d'execution. Un article score aujourd'hui donnera le meme resultat dans deux
ans, ce qui rend la serie temporelle exploitable.

Tous les termes sont ecrits SANS ACCENT : le texte analyse est lui aussi
desaccentue avant comparaison (voir analyzer.strip_accents), ce qui evite de
dupliquer chaque entree ("reglementaire" / "réglementaire").

La direction est donnee du point de vue des actifs risques : negatif =
defavorable aux actions et aux cryptos, positif = favorable.
"""

# --- Categories de tonalite ------------------------------------------------

DIRECTIONS = {
    "monetaire_restrictif": -1.0,
    "monetaire_accommodant": 1.0,
    "stress_financier": -1.5,
    "geopolitique": -1.0,
    "croissance": 1.0,
    "crypto_favorable": 1.5,
    "crypto_defavorable": -1.5,
}

LEXIQUE = {
    "monetaire_restrictif": [
        # anglais
        "rate hike", "rate hikes", "raise rates", "raising rates", "higher rates",
        "hawkish", "tightening", "tighten", "quantitative tightening",
        "restrictive", "higher for longer", "inflationary pressure",
        "inflation pressures", "overheating", "balance sheet reduction",
        # francais
        "hausse des taux", "remontee des taux", "resserrement",
        "resserrement monetaire", "politique restrictive", "durcissement",
        "tensions inflationnistes", "pressions inflationnistes", "surchauffe",
    ],
    "monetaire_accommodant": [
        # anglais
        "rate cut", "rate cuts", "cut rates", "cutting rates", "lower rates",
        "dovish", "easing", "monetary easing", "accommodative",
        "quantitative easing", "stimulus", "liquidity injection",
        "asset purchases", "disinflation",
        # francais
        "baisse des taux", "assouplissement", "assouplissement monetaire",
        "politique accommodante", "detente monetaire", "relance",
        "injection de liquidites", "rachats d'actifs", "desinflation",
    ],
    "stress_financier": [
        # anglais
        "crisis", "systemic risk", "contagion", "bank run", "default",
        "bankruptcy", "insolvency", "bailout", "liquidity crisis",
        "credit crunch", "financial stability risk", "turmoil", "meltdown",
        "collapse", "stress test", "distress", "fire sale",
        # francais
        "crise", "risque systemique", "faillite", "defaut de paiement",
        "insolvabilite", "sauvetage", "panique", "effondrement", "krach",
        "tensions financieres", "instabilite financiere", "test de resistance",
    ],
    "geopolitique": [
        # anglais
        "war", "warfare", "conflict", "sanctions", "invasion", "tariff",
        "tariffs", "trade war", "embargo", "military", "escalation",
        "geopolitical", "blockade", "strike on", "airstrike",
        # francais
        "guerre", "conflit", "invasion", "droits de douane",
        "tarifs douaniers", "guerre commerciale", "militaire", "escalade",
        "geopolitique", "blocus", "represailles",
    ],
    "croissance": [
        # anglais
        "growth", "expansion", "recovery", "rebound", "strong demand",
        "job gains", "hiring", "upgrade", "resilient", "beat expectations",
        "record high", "surplus", "productivity gains", "soft landing",
        # francais
        "croissance", "expansion", "reprise", "rebond", "demande soutenue",
        "creations d'emplois", "embauches", "resilient", "resiliente",
        "excedent", "atterrissage en douceur", "record historique",
    ],
    "crypto_favorable": [
        # anglais
        "etf approval", "spot etf", "adoption", "institutional adoption",
        "halving", "bullish", "all-time high", "listing", "custody",
        "regulatory clarity", "mica compliant", "approval", "greenlight",
        "inflows", "tokenization",
        # francais
        "adoption", "approbation", "clarte reglementaire", "agrement",
        "cotation", "haussier", "afflux", "tokenisation",
    ],
    "crypto_defavorable": [
        # anglais
        "ban", "crypto ban", "hack", "hacked", "exploit", "rug pull", "fraud",
        "enforcement action", "lawsuit", "delisting", "seizure",
        "money laundering", "laundering", "illicit finance", "bearish",
        "outflows", "sec charges", "criminal charges", "crackdown", "insolvent",
        # francais
        "interdiction", "piratage", "fraude", "blanchiment", "poursuites",
        "retrait de cotation", "saisie", "baissier",
        "sorties de capitaux", "repression",
    ],
}

# --- Detection des actifs ---------------------------------------------------

ASSET_KEYWORDS = {
    "sp500": [
        "s&p 500", "s&p500", "sp500", "wall street", "us equities", "nasdaq",
        "dow jones", "standard & poor", "us stocks", "actions americaines",
        "bourse americaine", "indices americains",
    ],
    "msci_world": [
        "msci world", "msci", "global equities", "developed markets",
        "world index", "actions mondiales", "marches developpes",
        "actions internationales", "indice mondial",
    ],
    "btc": ["bitcoin", "btc", "satoshi"],
    "eth": ["ethereum", "eth", "ether"],
}

# Termes generiques : rattachent l'article a la fois a BTC et a ETH.
CRYPTO_GENERIC = [
    "crypto", "cryptos", "cryptocurrency", "cryptocurrencies", "digital asset",
    "digital assets", "stablecoin", "stablecoins", "blockchain", "mica",
    "crypto-asset", "crypto-assets", "crypto-actifs", "cryptomonnaie",
    "cryptomonnaies", "actifs numeriques",
]

CRYPTO_GENERIC_ASSETS = ["btc", "eth"]

# --- Marqueurs de decision --------------------------------------------------

# Un article qui annonce une decision pese plus qu'un article qui commente.
DECISION_MARKERS = [
    # anglais
    "decision", "decides", "announces", "announced", "announcement",
    "statement", "adopted", "adopts", "publishes", "published", "ruling",
    "approves", "approved",
    # francais
    "decide", "annonce", "annoncee", "communique", "adopte", "adoptee",
    "publie", "publiee", "declaration", "approuve",
]

DECISION_MULTIPLIER = 1.5
TIER1_MULTIPLIER = 1.3
