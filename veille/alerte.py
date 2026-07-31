#!/usr/bin/env python3
"""Detecte les faits qui meritent de deranger, et rien d'autre.

Une page qu'il faut penser a ouvrir ne sert a rien : au moment ou un marche
bascule, personne ne se dit « tiens, je vais consulter mon tableau de bord ».
L'outil tourne toutes les heures et garde la memoire de l'heure d'avant.
C'est sa seule vraie superiorite sur n'importe quel site de cotations, et
elle ne vaut quelque chose que s'il sait venir chercher son lecteur.

Le canal est gratuit et deja installe : le workflow ouvre une issue GitHub,
l'application GitHub sur iPhone envoie la notification. Aucun service tiers,
aucun compte supplementaire, aucune cle.

Ne declenchent une alerte que des faits, jamais des interpretations :
  - un actif change d'etat de tendance ;
  - le regime general bascule ;
  - une decision de banque centrale tombe dans les deux jours ;
  - un indicateur atteint un extreme rare dans son propre historique.

Chaque alerte porte une empreinte. Une empreinte deja envoyee ne repart pas :
sans cette memoire, un basculement de tendance notifierait toutes les heures
jusqu'au basculement suivant, et l'outil serait desinstalle en une journee.

Usage:
    python alerte.py
    python alerte.py --show    Affiche sans rien ecrire ni marquer comme envoye
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
ALERTE_PATH = DATA_DIR / "alerte.json"

# Nombre d'empreintes conservees. Largement de quoi couvrir plusieurs mois
# d'alertes sans laisser le fichier grossir indefiniment.
MEMORY = 300

# En deca de ce delai, une echeance de banque centrale est signalee.
IMMINENT_DAYS = 2

# Percentile a partir duquel un indicateur est dit a un extreme.
EXTREME_HIGH = 90
EXTREME_LOW = 10

TREND_WORDS = {
    "haussiere": "haussière",
    "baissiere": "baissière",
    "indecise": "sans direction nette",
}

# Libelles lisibles pour les cles techniques de macro.json.
ASSET_LABELS = {
    "btc": "Bitcoin", "eth": "Ethereum", "sp500": "S&P 500",
    "nasdaq": "Nasdaq", "eurostoxx": "Euro Stoxx 50", "cac40": "CAC 40",
    "dax": "DAX", "nikkei": "Nikkei 225", "hangseng": "Hang Seng",
    "shanghai": "Shanghai", "msci_world": "MSCI World", "vix": "VIX",
    "dxy": "Dollar (DXY)",
}

# Ces series ne sont pas des actifs a detenir : leur tendance n'a pas de sens
# comme signal, elles ne declenchent donc pas d'alerte de basculement.
NOT_ASSETS = {"vix", "dxy"}


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


def alert(fingerprint, title, body, kind):
    return {"fingerprint": fingerprint, "title": title, "body": body,
            "kind": kind, "detected_at": datetime.now(timezone.utc).isoformat()}


# --- Detections --------------------------------------------------------------

def trend_changes(macro):
    """Compare l'etat du jour a l'etat du dernier jour enregistre avant lui.

    L'historique est journalier : deux tours d'une meme journee lisent la meme
    paire de jours et produisent la meme empreinte, donc une seule alerte.
    """
    history = (macro or {}).get("history") or {}
    days = sorted(history)
    if len(days) < 2:
        return []

    before = (history[days[-2]] or {}).get("assets") or {}
    after = (history[days[-1]] or {}).get("assets") or {}

    found = []
    for key, entry in after.items():
        if key in NOT_ASSETS:
            continue
        new = entry.get("trend")
        old = (before.get(key) or {}).get("trend")
        if not new or not old or new == old:
            continue
        label = ASSET_LABELS.get(key, key)
        found.append(alert(
            f"trend:{key}:{old}->{new}:{days[-1]}",
            f"{label} : tendance {TREND_WORDS[new]}",
            f"{label} passe de « {TREND_WORDS[old]} » à « {TREND_WORDS[new]} ». "
            f"Position du cours face à ses moyennes 50 et 200 jours, "
            f"relevée le {days[-1]}.",
            "tendance"))
    return found


def regime_change(macro):
    history = (macro or {}).get("history") or {}
    days = sorted(history)
    if len(days) < 2:
        return []
    old = (history[days[-2]] or {}).get("regime")
    new = (history[days[-1]] or {}).get("regime")
    if not old or not new or old == new or new == "indisponible":
        return []
    favorable = (history[days[-1]] or {}).get("favorable")
    available = (history[days[-1]] or {}).get("available")
    return [alert(
        f"regime:{old}->{new}:{days[-1]}",
        f"Régime de marché : {new}",
        f"Le régime passe de « {old} » à « {new} » "
        f"({favorable} critères favorables sur {available} calculés).",
        "regime")]


def imminent_events(agenda):
    found = []
    for event in (agenda or {}).get("upcoming") or []:
        if event.get("days") is None or event["days"] > IMMINENT_DAYS:
            continue
        found.append(alert(
            f"agenda:{event['date']}:{event['source']}",
            f"{event['label']} — {event['when']}",
            f"{event['label']}, {event.get('date_fr', event['date'])}. "
            "Une date de réunion est un fait, pas une prévision : "
            "l'outil ne dit pas ce qui en sortira.",
            "agenda"))
    return found


def extremes(backtest):
    """Un indicateur au bout de sa propre distribution historique.

    L'empreinte inclut le jour : un extreme qui dure plusieurs semaines ne
    notifie qu'une fois, puis se tait — sauf s'il ressort d'un extreme et y
    revient plus tard.
    """
    found = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for item in (backtest or {}).get("context") or []:
        rank = item.get("percentile")
        if rank is None:
            continue
        if rank >= EXTREME_HIGH:
            side = "haut"
        elif rank <= EXTREME_LOW:
            side = "bas"
        else:
            continue
        found.append(alert(
            f"extreme:{item['label']}:{side}:{today}",
            f"{item['label']} : {item['value']}",
            f"{item['label']} à {item['value']} — {item.get('sentence', '')}. "
            "Un extrême historique décrit le présent ; il ne dit rien de la suite.",
            "extreme"))
    return found


# --- Assemblage --------------------------------------------------------------

def collect():
    macro = load_json(DATA_DIR / "macro.json", {})
    agenda = load_json(DATA_DIR / "agenda.json", {})
    backtest = load_json(DATA_DIR / "backtest.json", {})

    candidates = (trend_changes(macro) + regime_change(macro)
                  + imminent_events(agenda) + extremes(backtest))

    state = load_json(ALERTE_PATH, {})
    already = set(state.get("sent") or [])
    pending = [a for a in candidates if a["fingerprint"] not in already]
    return state, candidates, pending


# Repris tel quel du bandeau de la page. Une alerte qui reveille quelqu'un
# doit porter la meme mise en garde que le tableau de bord, sinon la mise en
# garde ne protege que ceux qui lisent la page en entier.
DISCLAIMER = ("Ces indicateurs décrivent l'actualité. Ils ne prédisent rien. "
              "Aucune valeur prédictive n'a été démontrée à ce jour.")


def render_issue(pending, mention=None):
    """Titre et corps d'une issue GitHub unique regroupant les faits du tour.

    Une issue par fait donnerait une volee de notifications simultanees ; une
    seule issue en donne une, ce qui est deja le maximum supportable.
    """
    if len(pending) == 1:
        title = f"Veille : {pending[0]['title']}"
    else:
        title = f"Veille : {len(pending)} faits notables"

    lines = []
    if mention:
        lines.append(f"@{mention}\n")
    for item in pending:
        lines.append(f"**{item['title']}**\n\n{item['body']}\n")
    lines.append("---\n")
    lines.append(f"_{DISCLAIMER}_")
    return title, "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Detecte les faits notables")
    parser.add_argument("--show", action="store_true",
                        help="Affiche sans rien ecrire ni marquer comme envoye")
    parser.add_argument("--emit", metavar="DOSSIER",
                        help="Ecrit titre.txt et corps.md pour l'etape GitHub")
    parser.add_argument("--mention", metavar="COMPTE",
                        help="Compte a mentionner dans l'issue, pour la "
                             "notification sur telephone")
    args = parser.parse_args()

    state, candidates, pending = collect()

    print(f"{len(candidates)} fait(s) notable(s), {len(pending)} nouveau(x) :")
    for item in pending:
        print(f"  [{item['kind']}] {item['title']}")
    if not pending and candidates:
        print("  (tous deja signales)")

    if args.show:
        return

    # Sans rien de neuf, le fichier n'est pas reecrit. Il porte un horodatage,
    # et le reecrire a chaque tour ferait croire au workflow qu'une donnee a
    # change : un commit par heure, pour rien.
    if not pending and not (state.get("pending") or []):
        print("Rien de neuf : data/alerte.json laisse tel quel.")
        return

    # Les empreintes sont marquees comme envoyees des maintenant. Une alerte
    # perdue vaut mieux qu'une alerte repetee en boucle : dans le premier cas
    # l'information reste sur la page, dans le second l'outil devient
    # insupportable et finit desinstalle.
    sent = (state.get("sent") or []) + [a["fingerprint"] for a in pending]
    save_json(ALERTE_PATH, {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "pending": pending,
        "sent": sent[-MEMORY:],
    })
    print(f"\ndata/alerte.json ecrit ({len(pending)} a notifier).")

    if args.emit and pending:
        folder = Path(args.emit)
        folder.mkdir(parents=True, exist_ok=True)
        title, body = render_issue(pending, args.mention)
        (folder / "titre.txt").write_text(title, encoding="utf-8")
        (folder / "corps.md").write_text(body, encoding="utf-8")
        print(f"Issue preparee dans {folder}.")


if __name__ == "__main__":
    main()
