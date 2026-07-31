"""Registre des flux RSS surveilles par l'outil de veille.

Tier 1 : source primaire officielle (banque centrale, institution monetaire)
Tier 2 : regulateur ou organisme de statistiques
Tier 3 : presse economique et financiere

Chaque source precise les actifs concernes parmi :
  sp500, msci_world, btc, eth
"""

ASSETS = ["sp500", "msci_world", "btc", "eth"]

ALL_ASSETS = ASSETS

SOURCES = [
    # --- Tier 1 : sources primaires officielles ---------------------------
    {
        "id": "bce_press",
        "name": "BCE - Communiques de presse",
        "url": "https://www.ecb.europa.eu/rss/press.html",
        "tier": 1,
        "weight": 1.0,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "politique_monetaire",
    },
    {
        "id": "bce_pub",
        "name": "BCE - Publications",
        "url": "https://www.ecb.europa.eu/rss/pub.html",
        "tier": 1,
        "weight": 1.0,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "politique_monetaire",
    },
    {
        "id": "fed_press_all",
        "name": "Federal Reserve - Toutes publications",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "tier": 1,
        "weight": 1.0,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "politique_monetaire",
    },
    {
        "id": "fed_press_monetary",
        "name": "Federal Reserve - Politique monetaire",
        "url": "https://www.federalreserve.gov/feeds/press_monetary.xml",
        "tier": 1,
        "weight": 1.0,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "politique_monetaire",
    },
    {
        "id": "fed_speeches",
        "name": "Federal Reserve - Discours",
        "url": "https://www.federalreserve.gov/feeds/speeches.xml",
        "tier": 1,
        "weight": 1.0,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "politique_monetaire",
    },
    {
        "id": "boe_news",
        "name": "Bank of England - Actualites",
        "url": "https://www.bankofengland.co.uk/rss/news",
        "tier": 1,
        "weight": 1.0,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "politique_monetaire",
    },
    {
        "id": "bis_cb_speeches",
        "name": "BRI - Discours de banques centrales",
        "url": "https://www.bis.org/doclist/cbspeeches.rss",
        "tier": 1,
        "weight": 1.0,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "politique_monetaire",
    },
    # --- Tier 2 : regulateurs et statistiques -------------------------------
    {
        "id": "bls_news",
        "name": "BLS - Communiques statistiques",
        "url": "https://www.bls.gov/feed/news_release.rss",
        "tier": 2,
        "weight": 0.6,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "statistiques",
    },
    {
        "id": "imf_news",
        "name": "FMI - Actualites",
        "url": "https://www.imf.org/en/News/RSS?language=ENG",
        "tier": 2,
        "weight": 0.6,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "statistiques",
    },
    {
        "id": "esrb_press",
        "name": "CERS - Communiques de presse",
        "url": "https://www.esrb.europa.eu/rss/press.xml",
        "tier": 2,
        "weight": 0.6,
        "assets": ["sp500", "msci_world"],
        "category": "reglementation",
    },
    {
        "id": "sec_press",
        "name": "SEC - Communiques de presse",
        "url": "https://www.sec.gov/news/pressreleases.rss",
        "tier": 2,
        "weight": 0.6,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "reglementation",
    },
    {
        "id": "esma_news",
        "name": "ESMA - Actualites",
        "url": "https://www.esma.europa.eu/rss.xml",
        "tier": 2,
        "weight": 0.6,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "reglementation",
    },
    {
        "id": "amf_news",
        "name": "AMF - Actualites",
        "url": "https://www.amf-france.org/fr/flux-rss/display/21",
        "tier": 2,
        "weight": 0.6,
        "assets": ["sp500", "msci_world", "btc", "eth"],
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
        "id": "yahoo_finance",
        "name": "Yahoo Finance - Actualites",
        "url": "https://finance.yahoo.com/news/rssindex",
        "tier": 3,
        "weight": 0.3,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "marche",
    },
    {
        "id": "investing_com",
        "name": "Investing.com - Actualites",
        "url": "https://www.investing.com/rss/news.rss",
        "tier": 3,
        "weight": 0.3,
        "assets": ["sp500", "msci_world", "btc", "eth"],
        "category": "marche",
    },
    {
        "id": "marketwatch",
        "name": "MarketWatch - A la une",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "tier": 3,
        "weight": 0.3,
        "assets": ["sp500", "msci_world", "btc", "eth"],
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
