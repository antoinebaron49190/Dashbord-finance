#!/usr/bin/env python3
"""Calendrier des echeances qui deplacent les marches.

Savoir que le FOMC tombe mercredi change une decision d'entree en position
bien plus surement qu'un indice de tonalite. C'est l'information la plus
actionnable du tableau de bord, et la seule qui porte sur l'avenir plutot
que sur le present — sans rien predire pour autant : une date de reunion
est un fait, pas une prevision.

Deux sources, toutes deux publiques et gratuites :
  - Federal Reserve : calendrier des reunions du FOMC
  - BCE             : reunions de politique monetaire du Conseil des gouverneurs

Le BLS (CPI, emploi americain) manque volontairement : son site refuse les
adresses des runners GitHub, verifie en conditions reelles. Mieux vaut une
absence assumee qu'une source qui echoue en silence.

Comme partout ailleurs dans ce projet, une source muette est journalisee et
n'interrompt jamais rien.

Usage:
    python agenda.py
    python agenda.py --show    Affiche sans rien ecrire
"""

import argparse
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
AGENDA_PATH = DATA_DIR / "agenda.json"

HTTP_TIMEOUT = 15
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36")

FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
ECB_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"

NEXT_COUNT = 3      # nombre d'echeances affichees
IMMINENT_DAYS = 7   # en deca, l'echeance est signalee comme proche

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]
JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi",
            "dimanche"]


def fetch_html(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return response.read().decode("utf-8", "ignore")


# --- Federal Reserve --------------------------------------------------------

def parse_fomc(html_text):
    """Extrait les reunions du FOMC.

    La page groupe les reunions par annee dans des panneaux
    « <h4>2026 FOMC Meetings</h4> », puis chaque ligne porte un mois et une
    plage de jours (« 27-28 », « 17-18* »). La decision tombe le dernier
    jour de la plage : c'est celui qu'on retient.
    """
    events = []
    blocks = re.split(r">(\d{4}) FOMC Meetings<", html_text)
    # blocks = [avant, annee1, contenu1, annee2, contenu2, ...]
    for i in range(1, len(blocks) - 1, 2):
        year = int(blocks[i])
        rows = re.findall(
            r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>.*?'
            r'fomc-meeting__date[^>]*>\s*([^<]+?)\s*<',
            blocks[i + 1], re.DOTALL)
        for month_text, day_text in rows:
            months = [m.strip().lower() for m in month_text.split("/")]
            days = re.findall(r"\d+", day_text)
            if not days or months[-1] not in MONTHS:
                continue
            month = MONTHS[months[-1]]
            day = int(days[-1])
            # Une reunion a cheval sur decembre et janvier bascule d'annee.
            actual_year = year + 1 if len(months) > 1 and months[0] == "december" \
                and months[-1] == "january" else year
            try:
                date = datetime(actual_year, month, day).date()
            except ValueError:
                continue
            events.append({
                "date": date.isoformat(),
                "label": "Réunion du FOMC (Fed) — décision de taux",
                "source": "Federal Reserve",
                "importance": 3,
            })
    return events


def fetch_fomc(failures):
    try:
        return parse_fomc(fetch_html(FOMC_URL))
    except Exception as exc:
        failures.append(("fomc", str(exc)[:120]))
        return []


# --- BCE --------------------------------------------------------------------

def parse_ecb(html_text):
    """Extrait les reunions de politique monetaire du Conseil des gouverneurs.

    La page liste des couples « <dt>JJ/MM/AAAA</dt><dd>description</dd> ».
    On ne garde que les reunions de politique monetaire, et on ecarte le
    premier jour d'une reunion en deux temps : la decision tombe le second.
    """
    events = []
    pairs = re.findall(r"<dt>\s*(\d{2}/\d{2}/\d{4})\s*</dt>\s*<dd>(.*?)</dd>",
                       html_text, re.DOTALL)
    for date_text, description in pairs:
        plain = re.sub(r"<[^>]+>", " ", description)
        plain = re.sub(r"\s+", " ", plain).strip()
        if "monetary policy meeting" not in plain.lower():
            continue
        if "(day 1)" in plain.lower():
            continue
        try:
            date = datetime.strptime(date_text, "%d/%m/%Y").date()
        except ValueError:
            continue
        events.append({
            "date": date.isoformat(),
            "label": "Conseil des gouverneurs de la BCE — décision de taux",
            "source": "BCE",
            "importance": 3,
        })
    return events


def fetch_ecb(failures):
    try:
        return parse_ecb(fetch_html(ECB_URL))
    except Exception as exc:
        failures.append(("bce", str(exc)[:120]))
        return []


# --- Assemblage -------------------------------------------------------------

def french_date(iso):
    date = datetime.strptime(iso, "%Y-%m-%d").date()
    return f"{JOURS_FR[date.weekday()]} {date.day} {MOIS_FR[date.month - 1]}"


def upcoming(events, count=NEXT_COUNT):
    """Les `count` prochaines echeances, quelle que soit leur distance.

    Une fenetre fixe ne marche pas : entre la reunion de juillet et celle de
    septembre, les banques centrales font relache et un horizon a 21 jours
    n'afficherait rien pendant six semaines. « Prochaine echeance dans 41
    jours » reste une information utile ; « rien a signaler » n'en est pas
    une, elle laisse croire que le calendrier est vide alors qu'il est juste
    plus lointain.
    """
    today = datetime.now(timezone.utc).date()
    seen = set()
    kept = []
    for event in sorted(events, key=lambda e: e["date"]):
        date = datetime.strptime(event["date"], "%Y-%m-%d").date()
        if date < today:
            continue
        key = (event["date"], event["source"])
        if key in seen:
            continue
        seen.add(key)
        delta = (date - today).days
        if delta == 0:
            quand = "aujourd'hui"
        elif delta == 1:
            quand = "demain"
        else:
            quand = f"dans {delta} jours"
        kept.append({**event, "when": quand, "days": delta,
                     "imminent": delta <= IMMINENT_DAYS,
                     "date_fr": french_date(event["date"])})
        if len(kept) >= count:
            break
    return kept


def collect():
    failures = []
    events = fetch_fomc(failures) + fetch_ecb(failures)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "upcoming": upcoming(events),
        "all_known": len(events),
        "failures": [{"source": s, "reason": r} for s, r in failures],
    }


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main():
    parser = argparse.ArgumentParser(description="Calendrier des echeances")
    parser.add_argument("--show", action="store_true",
                        help="Affiche sans rien ecrire")
    args = parser.parse_args()

    agenda = collect()
    print(f"{agenda['all_known']} echeances connues, "
          f"{len(agenda['upcoming'])} prochaines :")
    for event in agenda["upcoming"]:
        print(f"  {event['date']}  {event['date_fr']:<22} ({event['when']:<14}) "
              f"{event['label']}")
    if agenda["failures"]:
        print("Sources muettes :")
        for failure in agenda["failures"]:
            print(f"  - {failure['source']} : {failure['reason']}")

    if not args.show:
        save_json(AGENDA_PATH, agenda)
        print(f"\ndata/agenda.json ecrit.")


if __name__ == "__main__":
    main()
