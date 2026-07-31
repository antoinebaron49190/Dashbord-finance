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
  lexique.py         mots-cles, directions, poids
  analyzer.py        scoring lexical et indice quotidien
  build_site.py      generation de la page statique
  data/
    articles.json    articles des 90 derniers jours
    index.json       serie quotidienne (conservee indefiniment)
  requirements.txt

docs/                 page publiee par GitHub Pages (generee)
```

Les deux etages sont separes : `collector.py` rassemble la matiere et n'ecrit
que `articles.json`, `analyzer.py` la score et ecrit `index.json`. On peut
donc reanalyser tout l'historique sans retoucher a la collecte.

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
4. met a jour `data/articles.json` (fenetre glissante de 90 jours).

Puis scorer et construire l'indice :

```bash
python analyzer.py
```

Options : `--no-claude` pour forcer l'etage lexical seul, `--explain <id>`
pour detailler le calcul d'un article (utile pour verifier le lexique).

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

Apres passage de `analyzer.py`, chaque article porte en plus : `categories`
(intensite par categorie), `assets_detected` / `assets_effective`,
`has_decision_marker`, `importance`, `tone_lexical`, `tone`, `crypto_tone`,
`is_stress` et `scored_by` (`lexique` ou `claude`).

## Le moteur de scoring

Le scoring est **lexical, deterministe et gratuit**. C'est sa propriete
essentielle : un meme article produit toujours le meme score, aujourd'hui
comme dans deux ans. Aucun appel reseau, aucun aleatoire, aucune dependance a
la date d'execution. C'est ce qui rend la serie exploitable plus tard.

### Categories

Sept categories, chacune declinee en anglais et en francais, avec une
direction donnee du point de vue des actifs risques :

| categorie               | direction |
|-------------------------|-----------|
| `monetaire_restrictif`  | -1.0      |
| `monetaire_accommodant` | +1.0      |
| `stress_financier`      | -1.5      |
| `geopolitique`          | -1.0      |
| `croissance`            | +1.0      |
| `crypto_favorable`      | +1.5      |
| `crypto_defavorable`    | -1.5      |

Le detail des termes est dans `lexique.py` — c'est la surface a ajuster si un
signal manque ou si un mot fait trop de bruit.

### Trois regles de calcul

**Frontieres de mots.** La recherche se fait par regex avec `\b` de part et
d'autre du terme. Une correspondance par sous-chaine ferait matcher `ban`
dans `banks` et `eth` dans `ethics` — ce sont de vrais bugs, verifies dans
les deux sens.

**Saturation.** `n` occurrences valent `racine(n)`, pas `n`. Trois mentions de
« contagion » pesent 1,73 et non 3. La saturation s'applique par terme puis
se somme sur la categorie : la diversite du vocabulaire compte plus que la
repetition.

**Bornage.** Le score brut, non borne, est ramene dans `]-1, 1[` par
`x / (1 + |x|)` — monotone, sans seuil arbitraire, comparable d'un jour a
l'autre.

### Importance

`poids de la source x 1.5 si marqueur de decision x 1.3 si tier 1`

Les marqueurs de decision (`decision`, `annonce`, `communique`, `adopte`,
`publie`...) distinguent l'article qui annonce de l'article qui commente.
L'importance va de 0,3 (presse) a 1,95 (decision d'une banque centrale).

### Detection des actifs

Mots-cles par actif, plus une liste generique (`crypto`, `cryptocurrency`,
`digital asset`, `stablecoin`, `blockchain`, `MiCA`...) qui rattache
l'article a la fois a BTC et a ETH.

Quand le texte ne nomme aucun actif, on ne retombe sur les actifs declares
par la source que pour les tiers 1 et 2 : une decision de la BCE concerne
bien les quatre actifs meme sans les nommer, alors qu'une depeche sur une
valeur isolee ne concerne aucun d'entre eux.

## L'indice quotidien

`index.json` est un dictionnaire `date -> mesures du jour`, **jamais purge** :
c'est la memoire longue de l'outil. Seuls les jours encore presents dans
`articles.json` sont recalcules ; les plus anciens restent tels quels.

| champ            | description                                              |
|------------------|----------------------------------------------------------|
| `articles_count` | nombre d'articles du jour                                |
| `signal_count`   | dont ceux portant au moins un terme reconnu              |
| `tone_cb`        | tonalite des banques centrales (tier 1)                  |
| `tone_global`    | tonalite generale                                        |
| `regul_crypto`   | climat reglementaire crypto                              |
| `stress`         | part des sujets de crise dans le flux, entre 0 et 1      |
| `top`            | les 5 elements les plus importants (titre, source, score, tonalite, URL) |

Les trois tonalites sont des moyennes ponderees par l'importance, dans
`[-1, 1]`, et valent `null` quand aucun article ne porte le signal concerne —
un jour sans information n'est pas un jour neutre. Seuls les articles portant
au moins un terme reconnu y votent : la plupart des depeches de presse
portent sur une valeur isolee et les compter comme des zeros diluerait les
series jusqu'a les rendre illisibles. `stress`, qui est une *part* du flux et
non une tonalite, se calcule lui sur l'ensemble des articles.

## L'etape Claude — optionnelle, desactivee par defaut

Si la variable d'environnement `ANTHROPIC_API_KEY` existe, les 25 elements les
plus importants des dernieres 48 h sont requalifies via l'API Anthropic
(modele `claude-sonnet-4-6`, surchargeable par `VEILLE_CLAUDE_MODEL`), avec
une sortie stricte au format `ID|tonalite|actifs|theme`.

Sans cle, l'etape est **ignoree silencieusement** et tout continue de
fonctionner. C'est un bonus, jamais une dependance : une clef absente, un
paquet `anthropic` non installe ou un appel en echec n'interrompent jamais
l'analyse.

Ces scores sont marques `scored_by: "claude"` et le score lexical est
conserve a cote dans `tone_lexical`. La distinction est importante : seul
l'etage lexical est rejouable a l'identique, l'etage Claude ne l'est pas.

## Pourquoi du JSON et pas SQLite

Le JSON se versionne proprement dans git (diffs lisibles, historique clair)
et reste consultable directement depuis un telephone, sans outil
supplementaire. Le volume reste faible (90 jours d'articles + une serie
quotidienne), ce qui rend une base de donnees inutile a ce stade.

## La page

```bash
python build_site.py
```

Genere `docs/` — le dossier servi par GitHub Pages :

| fichier                | role                                              |
|------------------------|---------------------------------------------------|
| `index.html`           | la page entiere : HTML, CSS et JS dans un seul fichier |
| `manifest.json`        | « Ajouter a l'ecran d'accueil », lancement plein ecran |
| `apple-touch-icon.png` | icone iOS (180 px)                                |
| `icon-192.png` / `icon-512.png` | icones du manifest                       |

Les donnees sont **injectees dans le HTML a la generation**. La page ouverte
ne fait aucune requete reseau : elle fonctionne hors ligne, et rien ne fuite
vers un tiers. Aucun framework, aucune etape de compilation.

Les trois icones PNG sont produites par le script lui-meme (`zlib` + `struct`,
sans Pillow) : le depot n'embarque aucun binaire d'origine inconnue.

### Contenu

1. **Quatre cartes** — banques centrales, tonalite globale, reglementaire
   crypto, part de stress. Valeur du jour, variation sur 7 jours, code
   couleur vert / gris / rouge. La couleur ne porte jamais seule
   l'information : chaque valeur est doublee d'un mot (`favorable`,
   `neutre`, `defavorable`, `elevee`...) et chaque variation d'une fleche et
   d'un nombre signe.
2. **Un graphique SVG** des quatre series sur 90 jours, genere cote Python,
   sans bibliotheque. Les series se distinguent par la couleur **et** par le
   style de trait. Les jours sans donnee sont des trous : jamais d'
   interpolation, un jour isole est dessine en point.
3. **Quatre onglets d'actifs** — les 10 elements les plus importants de
   chacun, avec titre, source, date, score et lien vers l'article.
4. **Le bandeau permanent**, fixe en bas de l'ecran.

### Mobile

Pensee pour un iPhone 14 (390 pt) : une seule colonne, aucun defilement
horizontal, zones tactiles de 44 pt au minimum, theme sombre, contenu et
titres a 16 px. Le texte secondaire (metadonnees, legendes) est a 14 px et
les graduations du graphique a 12 px — a 16 px elles couvriraient la courbe.

Verifie au rendu dans un navigateur en 390x844 : pas de debordement
horizontal, aucune zone tactile sous 44 pt, aucune requete reseau, et le
dernier element de chaque onglet reste lisible au-dessus du bandeau.
