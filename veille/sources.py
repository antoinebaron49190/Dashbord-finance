"""Registre des flux RSS surveilles par l'outil de veille.

Tier 1 : source primaire officielle (banque centrale, institution monetaire)
Tier 2 : regulateur ou organisme de statistiques
Tier 3 : presse economique et financiere

Chaque source precise les zones et actifs concernes parmi :
  sp500, europe, asie, msci_world, btc, eth

Ces declarations ne servent QUE de repli, et uniquement pour les tiers 1 et 2 :
quand le texte d'un article ne nomme aucun marche, il est rattache aux marches
declares par sa source. Elles doivent donc rester etroites. Declarer les six
cles partout — ce que faisait la premiere version — revenait a rattacher
chaque communique de la BCE au Bitcoin, et gonflait le decompte crypto de la
page avec des articles qui ne parlaient pas de crypto.

Deux flux ont ete retires apres verification en conditions reelles : le BLS
et le FMI repondent 403 aux adresses des runners GitHub comme a celles de
n'importe quel hebergeur. Ce n'est pas une panne passagere, et une source qui
echoue en silence vaut moins qu'une absence assumee. Leur role est repris par
des sources joignables : la Commission europeenne pour les indicateurs, le
CSF pour la stabilite financiere internationale, CNBC pour la reprise des
statistiques americaines.
"""

ASSETS = ["sp500", "europe", "asie", "msci_world", "btc", "eth"]

ALL_ASSETS = ASSETS

SOURCES = [
    # --- Tier 1 : sources primaires officielles ---------------------------
    {
        "id": "bce_press",
        "name": "BCE - Communiques de presse",
        "url": "https://www.ecb.europa.eu/rss/press.html",
        "tier": 1,
        "weight": 1.0,
        "assets": ["europe", "msci_world"],
        "category": "politique_monetaire",
    },
    {
        "id": "bce_pub",
        "name": "BCE - Publications",
        "url": "https://www.ecb.europa.eu/rss/pub.html",
        "tier": 1,
        "weight": 1.0,
        "assets": ["europe", "msci_world"],
        "category": "politique_monetaire",
    },
    {
        "id": "fed_press_all",
        "name": "Federal Reserve - Toutes publications",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "tier": 1,
        "weight": 1.0,
        "assets": ["sp500", "msci_world"],
        "category": "politique_monetaire",
    },
    {
        "id": "fed_press_monetary",
        "name": "Federal Reserve - Politique monetaire",
        "url": "https://www.federalreserve.gov/feeds/press_monetary.xml",
        "tier": 1,
        "weight": 1.0,
        "assets": ["sp500", "msci_world"],
        "category": "politique_monetaire",
    },
    {
        "id": "fed_speeches",
        "name": "Federal Reserve - Discours",
        "url": "https://www.federalreserve.gov/feeds/speeches.xml",
        "tier": 1,
        "weight": 1.0,
        "assets": ["sp500", "msci_world"],
        "category": "politique_monetaire",
    },
    {
        "id": "boe_news",
        "name": "Bank of England - Actualites",
        "url": "https://www.bankofengland.co.uk/rss/news",
        "tier": 1,
        "weight": 1.0,
        # Le Royaume-Uni n'est pas la zone euro, mais une decision de la BoE
        # se lit sur les indices europeens : c'est la carte qui les porte.
        "assets": ["europe", "msci_world"],
        "category": "politique_monetaire",
    },
    {
        "id": "boj_news",
        "name": "Banque du Japon - Actualites",
        "url": "https://www.boj.or.jp/en/rss/whatsnew.xml",
        "tier": 1,
        "weight": 1.0,
        # L'outil suivait le Nikkei sans aucune source japonaise. C'est le
        # trou que ce flux comble.
        "assets": ["asie", "msci_world"],
        "category": "politique_monetaire",
    },
    {
        "id": "bis_cb_speeches",
        "name": "BRI - Discours de banques centrales",
        "url": "https://www.bis.org/doclist/cbspeeches.rss",
        "tier": 1,
        "weight": 1.0,
        "assets": ["msci_world"],
        "category": "politique_monetaire",
    },
    # --- Tier 2 : regulateurs et statistiques -------------------------------
    {
        "id": "ec_press",
        "name": "Commission europeenne - Communiques",
        # Le flux « economie et finances » repond, mais son dernier element
        # datait de dix mois : un flux muet coute la place d'un flux vivant.
        # Celui-ci publie tous les jours.
        "url": ("https://ec.europa.eu/commission/presscorner/api/rss"
                "?language=en&pagesize=30"),
        "tier": 2,
        "weight": 0.6,
        "assets": ["europe", "msci_world"],
        "category": "statistiques",
    },
    {
        "id": "fsb_news",
        "name": "CSF - Conseil de stabilite financiere",
        "url": "https://www.fsb.org/feed/",
        "tier": 2,
        "weight": 0.6,
        "assets": ["msci_world"],
        "category": "statistiques",
    },
    {
        "id": "esrb_press",
        "name": "CERS - Communiques de presse",
        "url": "https://www.esrb.europa.eu/rss/press.xml",
        "tier": 2,
        "weight": 0.6,
        "assets": ["europe", "msci_world"],
        "category": "reglementation",
    },
    {
        "id": "sec_press",
        "name": "SEC - Communiques de presse",
        "url": "https://www.sec.gov/news/pressreleases.rss",
        "tier": 2,
        "weight": 0.6,
        "assets": ["sp500", "btc", "eth"],
        "category": "reglementation",
    },
    {
        "id": "esma_news",
        "name": "ESMA - Actualites",
        "url": "https://www.esma.europa.eu/rss.xml",
        "tier": 2,
        "weight": 0.6,
        "assets": ["europe", "btc", "eth"],
        "category": "reglementation",
    },
    {
        "id": "amf_news",
        "name": "AMF - Actualites",
        "url": "https://www.amf-france.org/fr/flux-rss/display/21",
        "tier": 2,
        "weight": 0.6,
        "assets": ["europe", "btc", "eth"],
        "category": "reglementation",
    },
    # --- Tier 3 : presse -----------------------------------------------------
    {
        "id": "coindesk",
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "tier": 3,
        "weight": 0.3,
        "assets": ["btc", "eth"],
        "category": "crypto",
    },
    {
        "id": "theblock",
        "name": "The Block",
        "url": "https://www.theblock.co/rss.xml",
        "tier": 3,
        "weight": 0.3,
        "assets": ["btc", "eth"],
        "category": "crypto",
    },
    {
        "id": "nikkei_asia",
        "name": "Nikkei Asia",
        "url": "https://asia.nikkei.com/rss/feed/nar",
        "tier": 3,
        "weight": 0.3,
        "assets": ["asie"],
        "category": "marche",
    },
    {
        "id": "cnbc_economy",
        "name": "CNBC - Economie",
        "url": ("https://search.cnbc.com/rs/search/combinedcms/view.xml"
                "?partnerId=wrss01&id=20910258"),
        "tier": 3,
        "weight": 0.3,
        "assets": ["sp500", "msci_world"],
        "category": "statistiques",
    },
    {
        "id": "yahoo_finance",
        "name": "Yahoo Finance - Actualites",
        "url": "https://finance.yahoo.com/news/rssindex",
        "tier": 3,
        "weight": 0.3,
        "assets": ["sp500", "msci_world"],
        "category": "marche",
    },
    {
        "id": "investing_com",
        "name": "Investing.com - Actualites",
        "url": "https://www.investing.com/rss/news.rss",
        "tier": 3,
        "weight": 0.3,
        "assets": ["sp500", "msci_world"],
        "category": "marche",
    },
    {
        "id": "marketwatch",
        "name": "MarketWatch - A la une",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "tier": 3,
        "weight": 0.3,
        "assets": ["sp500", "msci_world"],
        "category": "marche",
    },
]


def get_source_by_id(source_id):
    for source in SOURCES:
        if source["id"] == source_id:
            return source
    return None


if __name__ == "__main__":
    print(f"{len(SOURCES)} sources enregistrees")
    for tier in (1, 2, 3):
        count = sum(1 for s in SOURCES if s["tier"] == tier)
        print(f"  tier {tier}: {count}")
