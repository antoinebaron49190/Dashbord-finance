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
  macro.py           series numeriques et regime de marche
  agenda.py          calendrier des echeances (Fed, BCE)
  backtest.py        ce que les signaux ont reellement valu
  alerte.py          detection des faits qui meritent une notification
  build_site.py      generation de la page statique
  data/
    articles.json    articles des 90 derniers jours
    index.json       serie quotidienne (conservee indefiniment)
    macro.json       dernier releve chiffre + historique quotidien
    agenda.json      prochaines echeances de banques centrales
    synthese.json    synthese redigee du jour (si cle Claude)
    backtest.json    verdict par marche + reperes historiques (1x/jour)
    alerte.json      faits notables et empreintes deja notifiees
  requirements.txt

docs/                 page publiee par GitHub Pages (generee)
```

Les deux etages sont separes : `collector.py` rassemble la matiere et n'ecrit
que `articles.json`, `analyzer.py` la score et ecrit `index.json`. On peut
donc reanalyser tout l'historique sans retoucher a la collecte.

## Sources

21 flux repartis en 3 niveaux, **tous verifies joignables** :

- **Tier 1** (sources primaires officielles, poids 1.0) : BCE (×2), Federal
  Reserve (×3), Bank of England, **Banque du Japon**, BRI.
- **Tier 2** (regulateurs et statistiques, poids 0.6) : **Commission
  europeenne**, **CSF**, CERS, SEC, ESMA, AMF.
- **Tier 3** (presse economique et financiere, poids 0.3) : CoinDesk, The
  Block, **Nikkei Asia**, **CNBC Economie**, Yahoo Finance, Investing.com,
  MarketWatch.

Le detail (URL, marches concernes, categorie) est dans `sources.py`.

### Deux flux retires, cinq ajoutes

Le **BLS** et le **FMI** repondaient `403 Forbidden` a toute adresse
d'hebergeur, la nôtre comme celle des runners GitHub. Ce n'etait pas une
panne passagere : ils ont ete retires, parce qu'une source qui echoue en
silence vaut moins qu'une absence assumee. Leur role est repris par la
Commission europeenne (indicateurs), le CSF (stabilite financiere
internationale) et CNBC (qui *reprend* les chiffres du BLS le jour de leur
publication).

La **Banque du Japon** et **Nikkei Asia** comblent un trou franc : l'outil
suivait le Nikkei, le Hang Seng et Shanghai sans aucune source asiatique.
L'Asie est passee de 11 a 97 articles rattaches, l'Europe de 29 a 82.

### Les marches declares par une source ne servent que de repli

Et uniquement pour les tiers 1 et 2, quand le texte ne nomme aucun marche.
Ils doivent donc rester etroits. La premiere version declarait les quatre
actifs partout, ce qui rattachait **chaque communique de la BCE au
Bitcoin** et gonflait le decompte crypto de la page avec des articles qui ne
parlaient pas de crypto. Chaque source ne declare plus que sa zone : la Fed
`sp500`, la BCE et la BoE `europe`, la BoJ `asie`, la SEC et l'ESMA aussi
`btc`/`eth` parce qu'elles legiferent dessus.

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

Six cles : `sp500`, `europe`, `asie`, `msci_world`, `btc`, `eth`. Les trois
premieres portent les memes noms que les zones de la page, ce qui permet de
mettre l'actualite en face du marche qu'elle concerne.

S'y ajoute une liste generique (`crypto`, `cryptocurrency`, `digital asset`,
`stablecoin`, `blockchain`, `MiCA`...) qui rattache l'article a la fois a BTC
et a ETH.

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

## Les series numeriques et le regime

`macro.py` recupere des series chiffrees gratuites, calcule un **regime de
marche en trois etats**, et ecrit `data/macro.json`.

```bash
python macro.py           # recupere et ecrit
python macro.py --show    # affiche le detail sans rien ecrire
```

### Sources

| source | ce qu'elle fournit | compte requis |
|--------|--------------------|---------------|
| `ccxt` | BTC et ETH : prix, MM50, MM200, decote sur le plus haut 1 an, volatilite 30 jours, taux de financement des perpetuels | non |
| `yfinance` | `^GSPC`, `URTH`, `^VIX`, `DX-Y.NYB` | non |
| `alternative.me` | indice Fear & Greed crypto | non |
| FRED | `DGS10`, `DFF` | oui, `FRED_API_KEY` — sinon ignore |

**ccxt utilise une chaine de repli** : Kraken, Coinbase, OKX, KuCoin,
Bitstamp, la premiere qui repond gagne. Binance en est volontairement
absente : elle renvoie `451 Unavailable For Legal Reasons` depuis une bonne
partie des hebergeurs, dont les runners GitHub.

**yfinance a un repli `urllib`** sur l'API publique de Yahoo. yfinance
s'appuie sur `curl_cffi`, qui echoue derriere certains proxies ; le repli
evite que la moitie de la section disparaisse pour cette seule raison.

### Le regime

Trois etats — **favorable au risque**, **neutre**, **defavorable au risque** —
obtenus en comptant les criteres favorables :

| part de criteres favorables | regime |
|-----------------------------|--------|
| 60 % ou plus                | favorable au risque |
| entre 35 % et 60 %          | neutre |
| 35 % ou moins               | defavorable au risque |

**Le denominateur ne compte que les criteres reellement calcules.** Une
source muette retire ses criteres du decompte au lieu de les compter comme
defavorables — sans quoi une panne reseau se lirait comme un marche baissier.
La page affiche toujours combien de criteres etaient disponibles, et signale
ceux qui ne l'etaient pas.

Les onze criteres (treize avec FRED) sont affiches un par un avec **leur
valeur et leur seuil**, pour que le calcul se verifie d'un coup d'oeil sans
relire le code :

| groupe | criteres |
|--------|----------|
| Crypto | BTC > MM200, BTC > MM50, ETH > MM200, decote 1 an < 25 %, volatilite 30j < 60 %, financement positif |
| Actions et devises | S&P 500 > MM200, MSCI World > MM200, dollar < MM50, VIX < 20 |
| Sentiment | Fear & Greed >= 50 |
| Taux (si FRED) | 10 ans en detente, taux directeur en detente |

Les seuils sont des conventions de lecture, pas des verites : ils vivent en
haut de `build_criteria()` dans `macro.py` et sont faits pour etre ajustes.

### Deux sections, jamais melangees

La page separe nettement **Actualite** (ce que raconte la presse, mesure par
le lexique) et **Marche** (ce que font les prix). Les deux repondent a des
questions differentes et ne doivent pas se lire comme un seul bloc : elles
sont separees par un filet, un titre et un fond distinct.

`macro.json` conserve aussi un `history` quotidien, jamais purge, sur le
meme principe que `index.json`.

## Les quatre zones de marche

`macro.py` suit dix indices, regroupes en quatre zones. Une carte par zone,
pas par indice : dix cartes rallongeraient la page pour rien.

| zone | indices |
|------|---------|
| Amerique | S&P 500, Nasdaq |
| Europe | Euro Stoxx 50, CAC 40, DAX |
| Asie | Nikkei 225, Hang Seng, Shanghai |
| Crypto | Bitcoin, Ethereum |

Le MSCI World est affiche en une ligne sous les zones, comme reference
mondiale. Le VIX et le dollar alimentent les criteres du regime.

Une ligne d'**ampleur** precede les cartes : combien des dix marches sont
au-dessus de leurs deux moyennes. Quatre cartes lues separement repondent mal
a la question « le mouvement est-il general ou isole ? ».

Chaque carte porte enfin **l'actualite de sa zone** sur 7 jours, comptee et
non moyennee. C'est ce a quoi servent les cles `europe` et `asie` ajoutees a
`ASSET_KEYWORDS` : sans elles, « Asie : tendance haussiere » restait une ligne
de cours sans un mot d'explication a cote.

Le verdict d'une zone vient de la tendance de chacun de ses indices :
tous au-dessus de leurs moyennes 50 et 200 jours donne « Tendance
haussiere », tous en dessous « Tendance baissiere », le reste
« Marches partages » avec le decompte. La regle est calculee **une seule
fois**, dans `macro.py`, et stockee ; la page ne fait que la mettre en
forme.

## Le calendrier des echeances

`agenda.py` recupere les prochaines decisions de taux des **quatre banques
centrales** qui portent les zones suivies :

| banque | source | zone concernee |
|--------|--------|----------------|
| Federal Reserve (FOMC) | calendrier officiel | Amerique |
| BCE (Conseil des gouverneurs) | calendrier officiel | Europe |
| Bank of England (MPC) | page des dates a venir | Europe |
| Banque du Japon (MPM) | page des reunions | Asie |

Savoir qu'une decision de taux tombe mercredi change une decision d'entree en
position bien plus surement qu'un indice de tonalite — et une date de reunion
est un fait, pas une prevision.

Les deux nouvelles sources ont chacune leur piege d'analyse, traite dans le
code : la BoE n'ecrit pas l'annee dans ses dates (elle se lit dans l'URL de
la ligne, puis se deduit du passage a un mois anterieur), et la BoJ note ses
reunions de deux jours « Sept. 17 (Thurs.), 18 (Fri.) » — la decision tombe
le second jour.

L'affichage montre **les quatre prochaines echeances, quelle que soit leur
distance**. Une fenetre fixe a 21 jours n'afficherait rien pendant les six
semaines de pause estivale des banques centrales : « prochaine echeance dans
41 jours » est une information, « rien a signaler » n'en est pas une.

> Le BLS (CPI, emploi americain) manque volontairement. Verifie en
> conditions reelles : son site refuse les adresses des runners GitHub,
> exactement comme son flux RSS. Mieux vaut une absence assumee qu'une
> source qui echoue en silence.

## La synthese redigee

Si `ANTHROPIC_API_KEY` existe, `analyzer.py` demande a Claude les **cinq
points a connaitre**, rediges en francais a partir des 30 elements les plus
importants des 72 dernieres heures.

C'est le seul endroit du projet ou un modele de langage apporte ce qu'un
lexique ne peut pas donner : transformer cent depeches en cinq phrases
hierarchisees. Sans cle, la page retombe sur le resume mecanique et le dit
explicitement. Une panne d'API, un paquet absent ou une reponse malformee
sont journalises et n'interrompent rien.

Le modele se regle avec `VEILLE_CLAUDE_MODEL` (defaut `claude-sonnet-4-6`).

## Ce que valent les signaux

C'est la section qui manque a toutes les applications de finance grand
public : celle qui dit quand l'indicateur affiche du vide.

```bash
python backtest.py            # recalcule si le fichier a plus de 20 h
python backtest.py --force    # recalcule quoi qu'il arrive
python backtest.py --show     # affiche sans rien ecrire
```

`backtest.py` **rejoue la regle affichee sur la page** — la position du cours
face a ses moyennes 50 et 200 jours — sur cinq ans d'historique pour les
indices, deux ans pour les cryptos (limite des bourses). Pour chaque marche,
il compare ce qui s'est passe dans les **20 seances suivantes** selon que la
journee etait classee haussiere ou baissiere.

La regle rejouee est `annotate_trend()` de `macro.py`, **importee et non
recopiee** : mesurer une autre regle que celle affichee ne mesurerait rien.

| ecart entre les deux etats | verdict affiche |
|----------------------------|-----------------|
| 2 points ou plus           | signal utile |
| entre 0,5 et 2 points      | signal faible |
| 0,5 point ou moins         | sans valeur |
| 2 points ou plus, a l'envers | signal inverse |

### La reference qui manquait

Chaque marche porte aussi sa **ligne de base** : ce qu'a fait une seance
quelconque, sans regarder aucun signal. C'est le denominateur sans lequel les
autres chiffres ne veulent rien dire — « +1,2 % apres un signal haussier »
est un mauvais resultat si la moyenne generale est de +1,5 %.

### Les situations comparables

L'ecart de chaque marche a sa moyenne 200 jours est decoupe en **cinq
quintiles** sur tout l'historique. La seance d'aujourd'hui tombe dans l'un
d'eux, et la page affiche ce qu'ont fait les autres seances du meme paquet
dans les 20 seances suivantes, **a cote de la moyenne generale**.

Le decoupage est fait par les donnees, sans aucun seuil choisi a la main :
une regle affinee jusqu'a bien marcher sur le passe ne mesure plus que sa
propre mise au point. Un paquet de moins de 60 seances n'est pas affiche.

Trois precautions, dites sur la page et pas seulement ici :

- **Les fenetres se chevauchent.** Deux jours consecutifs partagent 19 des 20
  seances mesurees. Le nombre affiche est un nombre de *jours observes*, pas
  d'experiences independantes.
- **La mesure est faite apres coup, sur les memes donnees.** Elle dit ce qui
  s'est passe, pas ce qui se passera.
- **Moins de 60 jours dans l'un des deux etats : aucun verdict.** L'echantillon
  ne permet rien.

### La mesure en direct, tenue en reserve

`macro.py` continue d'enregistrer chaque jour **la cloture et le signal cote
a cote**. Cette mesure-la n'est pas affichee : le backtest la devance sur tous
les points, il porte sur des annees plutot que sur quelques jours. Elle a
pourtant une qualite que le backtest n'aura jamais — elle est enregistree en
direct, sans connaitre la suite. Le jour ou elle aura assez d'observations,
elle pourra contredire le backtest, et c'est elle qui aura raison.

### Les phases et leur duree habituelle

Le module releve aussi **depuis combien de seances chaque marche est dans son
etat**, et **combien de temps ces phases durent d'habitude** sur ce marche
(mediane des phases passees, celle en cours exclue puisqu'elle n'est pas
finie). La page signale les phases qui durent au moins deux fois la normale.

Ce n'est ni une alerte ni une prevision : une phase longue ne se retourne pas
parce qu'elle est longue. C'est ce qui repond a « haussier depuis 72 jours,
c'est beaucoup ou pas ? », question que le tableau posait sans y repondre.

### Une seule passe au lieu de trois

Les moyennes mobiles etaient recalculees depuis le debut de l'historique a
chaque journee rejouee, et ce travail etait refait par chacune des mesures —
des dizaines de millions d'additions pour un resultat identique. Les moyennes
et les etats de tendance sont desormais calcules **une fois par marche** par
somme glissante, puis partages. L'etape est passee de plusieurs secondes a
un temps non mesurable.

## Ce qui bouge avec quoi

Correlation des variations quotidiennes sur les **90 dernieres seances
communes** aux deux marches : Bitcoin/Nasdaq, Bitcoin/S&P 500,
Ethereum/Bitcoin.

Question rarement posee et pourtant decisive quand on detient a la fois des
actions et des cryptos : est-ce que ces deux paris sont le meme ? Proche de
1, les deux marches montent et descendent ensemble et ne se diversifient donc
pas l'un l'autre.

**Seules les dates presentes des deux cotes sont comparees.** Les cryptos
cotent le week-end, pas les indices ; aligner les series par position
reviendrait a comparer un mouvement du samedi a un jour ferie.

## Les reperes historiques

Le meme module situe quatre chiffres du jour dans **leur propre histoire**.
« VIX a 16 » ne dit rien a personne ; « VIX a 16, plus calme que 78 % des cinq
dernieres annees » se lit d'un coup d'oeil.

| repere | fenetre de comparaison |
|--------|------------------------|
| VIX | 5 ans |
| Fear & Greed crypto | toute l'histoire de l'indice |
| Volatilite BTC 30 jours | 2 ans |
| Decote BTC sous son plus haut | 2 ans |

## Les alertes qui viennent te chercher

Une page qu'il faut penser a ouvrir ne sert a rien : au moment ou un marche
bascule, personne ne se dit « tiens, je vais consulter mon tableau de bord ».

```bash
python alerte.py --show    # affiche sans rien marquer comme envoye
```

`alerte.py` ne declenche que sur des **faits**, jamais sur des
interpretations :

| declencheur | condition |
|-------------|-----------|
| Basculement de tendance | un actif change d'etat entre deux releves |
| Changement de regime | le regime general passe d'un etat a un autre |
| Echeance imminente | decision Fed ou BCE sous 2 jours |
| Extreme historique | un repere au-dela du 90e ou sous le 10e percentile |

Le canal est **gratuit et deja installe** : le workflow ouvre une issue
GitHub, l'application GitHub sur iPhone la transforme en notification. Aucun
service tiers, aucun compte supplementaire, aucune cle. L'issue mentionne le
proprietaire du depot (`github.repository_owner`) pour que la notification
parte a coup sur.

**Chaque alerte porte une empreinte**, et une empreinte deja envoyee ne repart
pas. Sans cette memoire, un basculement de tendance notifierait toutes les
heures jusqu'au suivant, et l'outil serait desinstalle en une journee. Les
300 dernieres empreintes sont conservees dans `data/alerte.json`.

Les extremes ont un traitement a part, appris en conditions reelles : leur
premiere version datait l'empreinte du jour, et une decote de 50 % qui dure
des mois se serait donc rappelee tous les matins. La liste des extremes en
cours est desormais conservee d'un tour a l'autre, et **seule l'entree dans
l'extreme est signalee**. Un indicateur qui en sort puis y revient est
signale de nouveau — c'est bien le comportement voulu.

Un tour qui ne detecte rien de neuf **ne reecrit meme pas le fichier** : son
horodatage suffirait a declencher un commit par heure.

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

La page repond a huit questions, dans cet ordre, et rien d'autre :

1. **Qu'est-ce qui a change ?** Les basculements de tendance des 45 derniers
   jours, du plus recent au plus ancien. C'est ce qui justifie d'ouvrir la
   page aujourd'hui plutot qu'hier.
2. **Ou en est chaque zone ?** Une ligne d'ampleur, puis quatre cartes —
   Amerique, Europe, Asie, Crypto — avec la tendance, sa justification
   chiffree, les cours et l'actualite propre a la zone.
3. **Que dit l'actualite ?** La synthese redigee (ou le resume mecanique) et
   le fait marquant des dernieres 48 h, plus les prochaines echeances.
4. **C'est deja arrive, et ensuite ?** Les seances passees ressemblant a
   celle d'aujourd'hui, et ce qui les a suivies.
5. **Cette phase dure-t-elle depuis longtemps ?** Les marches dont l'etat
   dure au moins deux fois plus que d'habitude.
6. **Ces signaux valent-ils quelque chose ?** Le verdict mesure marche par
   marche.
7. **Mes paris sont-ils le meme pari ?** Les correlations entre cryptos et
   actions.
8. **Ces chiffres sont-ils rares ?** Quatre reperes replaces dans leur propre
   histoire.

« Ce qui a change » vient des **historiques longs**, pas de la memoire de
l'outil : la section est donc complete des le premier jour, au lieu de rester
vide plusieurs semaines le temps que les releves s'accumulent. C'est la meme
lecon que la mesure de fiabilite, appliquee cette fois avant de livrer.

### La tendance n'est pas une prevision

Chaque carte affiche « Tendance haussiere / baissiere / Sans direction
nette », derive d'une regle mecanique : la position du cours face a ses
moyennes 50 et 200 jours, plus la decote sur un an pour les cryptos.

C'est un **etat present, verifiable**, pas une prediction. La page n'ecrit
jamais « acheter », « vendre », ni « va monter » : le calcul ne le supporte
pas, et le bandeau permanent dit exactement cela.

### On compte, on ne moyenne pas

L'actualite par actif est un **decompte** d'articles favorables et
defavorables, pas une moyenne. La raison est concrete : une semaine a 14
articles favorables et 9 defavorables donne une moyenne de 0,00. Afficher
« neutre » laisserait croire qu'il ne se passe rien, alors que l'actualite
est nourrie mais partagee. Le decompte dit la verite la ou la moyenne
l'efface — et la meme methode sert pour le resume general, pour que la page
ne se contredise pas d'une section a l'autre.

### Ce qui a ete retire

Le graphique 90 jours, la liste des 11 criteres et les 40 titres d'articles
ont ete supprimes de la page : un tableau de bord qu'on ne lit pas en dix
secondes sur un telephone ne sert a rien. Le code reste dans l'historique
git (commit `da89e9f`) si le besoin revient. Les donnees, elles, continuent
d'etre collectees et conservees dans `data/`.

### Mobile

Une seule colonne, aucun defilement horizontal, zones tactiles de 44 pt
minimum, theme sombre, aucun texte sous 14 px. Verifie au rendu dans un
navigateur en 390x844.

## Execution continue (GitHub Actions)

`.github/workflows/veille.yml` enchaine les etapes toutes les heures :
collecte, analyse, series numeriques, calendrier, backtest (une fois par
jour), detection des alertes, generation de la page, puis commit et push si
quelque chose a change. Le telephone ne fait tourner aucun processus.

> Depuis l'ajout de `macro.py`, les prix bougent a chaque tour : le depot
> recoit donc environ un commit par heure, avec de vraies donnees dedans. Si
> c'est trop, passe le cron a `0 */4 * * *`.

| point | choix |
|-------|-------|
| Declencheurs | cron horaire (`0 * * * *`, en UTC) + `workflow_dispatch` |
| Droits | `GITHUB_TOKEN` par defaut, `contents: write` + `issues: write` |
| Duree max | `timeout-minutes: 20` (le tour quotidien du backtest est le plus long) |
| Simultaneite | `concurrency: veille`, sans annulation du tour en cours |
| Secrets | `ANTHROPIC_API_KEY` et `FRED_API_KEY`, absents = ignores |

**Un flux mort n'echoue jamais le workflow.** `collector.py` isole chaque
source *et* chaque entree, attrape `Exception` sans filtrer par type, et sort
toujours en code 0. Verifie en simulant coupure de connexion, reponse
tronquee, erreur TLS et les 18 flux morts d'un coup : la collecte se termine
proprement en journalisant les sources muettes.

**Pas de commit inutile.** La page porte son heure de generation, elle change
donc a chaque tour meme sans actualite. Le workflow ne publie que si les
donnees ont bouge, ou si la page a change pour autre chose que son horodatage
— sinon on accumulerait un commit vide par heure, soit environ 8 700 par an.

> `FRED_API_KEY` est lu par `macro.py` (series `DGS10` et `DFF`). Sans la cle,
> l'etape est ignoree en silence et les deux criteres de taux sortent du
> decompte du regime au lieu de compter comme defavorables.

## Marche a suivre depuis un iPhone

Tout se fait dans Safari : `github.com` fonctionne entierement sur mobile.
L'app GitHub est pratique pour suivre les executions, mais ne permet ni de
creer un depot ni de regler Pages — passe par Safari pour ces etapes.

### 1. Creer le depot public

1. Safari, aller sur **github.com/new**.
2. Nom : `Dashbord-finance` (ou ce que tu veux).
3. Cocher **Public** — c'est ce qui donne les minutes GitHub Actions
   illimitees. Un depot prive consommerait ton quota gratuit.
4. Ne rien cocher d'autre, puis **Create repository**.
5. Pousser le code sur la branche `main`.

### 2. Activer GitHub Pages

1. Dans le depot : **Settings** (roue dentee), puis **Pages** dans la
   colonne de gauche.
2. Sous *Build and deployment*, **Source** : `Deploy from a branch`.
3. **Branch** : `main`, dossier **`/docs`**. Puis **Save**.
4. Au bout d'une a deux minutes, l'adresse s'affiche en haut de la page :
   `https://<ton-compte>.github.io/Dashbord-finance/`

### 3. Ajouter les cles (facultatif)

Utile seulement si tu veux l'etage Claude. Sans cle, tout fonctionne.

**Settings** > **Secrets and variables** > **Actions** > **New repository
secret** : nom `ANTHROPIC_API_KEY`, valeur ta cle. Ne colle jamais une cle
ailleurs que la : le depot est public.

### 4. Declencher le premier tour a la main

1. Onglet **Actions** du depot.
2. Dans la colonne de gauche, choisir le workflow **Veille**.
3. Bouton **Run workflow** a droite, branche `main`, puis **Run workflow**.
4. Le tour dure environ une minute. Une pastille verte = termine.

Sans ce declenchement manuel, il faut attendre le prochain passage du cron
(jusqu'a une heure). Ensuite tout tourne seul.

### 5. Ajouter la page a l'ecran d'accueil

1. Ouvrir l'adresse `github.io` dans **Safari** (pas dans l'app GitHub, sinon
   l'icone et le plein ecran ne fonctionnent pas).
2. Bouton **Partager** (le carre avec la fleche, en bas).
3. Faire defiler, **Sur l'ecran d'accueil**, puis **Ajouter**.

L'icone generee par `build_site.py` apparait sur l'ecran d'accueil, et
l'ouverture se fait en plein ecran, sans barre d'adresse, grace au
`manifest.json` et aux balises `apple-mobile-web-app-*`.

### Bon a savoir

- GitHub desactive les crons d'un depot **inactif depuis 60 jours**. Ici le
  workflow commite regulierement, donc le compteur ne s'epuise pas. Si tu
  recois un mail d'avertissement, un `Run workflow` manuel suffit a relancer.
- Les crons GitHub sont en **UTC** et peuvent etre decales de quelques
  minutes aux heures chargees. L'heure affichee sur la page, elle, est bien
  l'heure de Paris.
- Pour changer la frequence, edite la ligne `cron:` du workflow.

## Confidentialite

**Ce depot est public et ne doit contenir que de la veille d'actualite
publique.** Il ne contient aucun montant investi, aucune position, aucune
donnee personnelle, et il ne doit jamais en contenir.

Ce qui est versionne :

- du code Python et un fichier de workflow ;
- des articles issus de **flux RSS publics** : titre, lien, resume, date,
  plus les scores calcules. Rien qui ne soit deja publie par la BCE, la Fed,
  l'AMF ou la presse ;
- la page generee et ses icones.

Ce qui n'y est pas, et ne doit pas y entrer : montants, positions, taille de
portefeuille, identite, adresse e-mail, cles d'API. Les cles passent
exclusivement par les **GitHub Secrets**, qui ne sont jamais ecrits dans le
depot ni visibles dans les journaux d'execution.

L'outil ne se connecte a aucun compte de courtage et ne passe aucun ordre.
Il lit des flux publics, les score, et affiche le resultat.
