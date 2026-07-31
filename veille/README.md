# Veille economique

Outil personnel de veille macro et reglementaire pour quatre actifs :
S&P 500, MSCI World, Bitcoin, Ethereum.

Usage strictement personnel. Aucun ordre n'est passe, aucune connexion a un
compte de courtage. L'outil informe, il ne decide pas.

## Structure

```
veille/
  sources.py        registre des 18 flux RSS surveilles
  collector.py       collecte, dedoublonnage, stockage
  data/
    articles.json    articles des 90 derniers jours
    index.json       serie quotidienne (conservee indefiniment)
  requirements.txt
```

## Sources

18 flux repartis en 3 niveaux :

- **Tier 1** (sources primaires officielles, poids 1.0) : BCE, Federal
  Reserve, Bank of England, BRI (discours de banques centrales).
- **Tier 2** (regulateurs et statistiques, poids 0.6) : BLS, FMI, CERS, SEC,
  ESMA, AMF.
- **Tier 3** (presse economique et financiere, poids 0.3) : CoinDesk, The
  Block, Yahoo Finance, Investing.com, MarketWatch.

Le detail (URL, actifs concernes, categorie) est dans `sources.py`.

## Utilisation

Installer les dependances :

```bash
pip install -r requirements.txt
```

Tester l'etat des flux (aucune ecriture sur le disque) :

```bash
python collector.py --check
```

Affiche un tableau OK/KO par flux avec la date du dernier element publie. Un
flux mort n'interrompt jamais la collecte : il est simplement marque KO.

Lancer une passe de collecte :

```bash
python collector.py
```

Cette commande :

1. recupere les entrees de chaque flux,
2. dedoublonne par hash de `(url + titre)`,
3. nettoie le HTML des resumes et les tronque a 600 caracteres,
4. met a jour `data/articles.json` (fenetre glissante de 90 jours),
5. met a jour `data/index.json` (serie quotidienne, jamais purgee).

## Format des donnees

Chaque article dans `articles.json` contient :

| champ          | description                                   |
|-----------------|------------------------------------------------|
| `id`            | hash court `(url + titre)`, sert de cle unique |
| `source`        | identifiant de la source (`sources.py`)        |
| `tier`          | 1, 2 ou 3                                      |
| `weight`        | poids numerique de la source                   |
| `category`      | categorie (`politique_monetaire`, `statistiques`, `reglementation`, `marche`, `crypto`) |
| `assets`        | liste des actifs concernes                     |
| `title`         | titre nettoye                                  |
| `url`           | lien vers l'article                            |
| `summary`       | resume nettoye, tronque a 600 caracteres        |
| `published_at`  | date de publication (ISO 8601, UTC)            |
| `collected_at`  | date de collecte (ISO 8601, UTC)               |

`index.json` est un dictionnaire `date -> statistiques du jour` (nombre
d'articles, repartition par tier, par actif, total pondere). Contrairement a
`articles.json`, il n'est jamais purge : c'est la memoire longue de l'outil.

## Pourquoi du JSON et pas SQLite

Le JSON se versionne proprement dans git (diffs lisibles, historique clair)
et reste consultable directement depuis un telephone, sans outil
supplementaire. Le volume reste faible (90 jours d'articles + une serie
quotidienne), ce qui rend une base de donnees inutile a ce stade.
