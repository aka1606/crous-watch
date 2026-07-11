#!/usr/bin/env python3
import json, os, smtplib, sys, time
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
import requests

TOOL_ID = os.environ.get("CROUS_TOOL_ID", "42")
BOUNDS = os.environ.get("CROUS_BOUNDS", "4.7396309_43.9967419_4.9271468_43.8866492")
LOCATION_NAME = os.environ.get("CROUS_LOCATION_NAME", "Avignon (84000)")
INTERVAL = int(os.environ.get("CROUS_INTERVAL", "300"))
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
MAIL_TO = os.environ.get("MAIL_TO", GMAIL_USER)
STATE_FILE = Path(os.environ.get("CROUS_STATE_FILE", "./seen.json"))
BASE = "https://trouverunlogement.lescrous.fr"
SEARCH_URL = f"{BASE}/api/fr/search/{TOOL_ID}"
ACCO_URL = f"{BASE}/tools/{TOOL_ID}/accommodations"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Origin": BASE,
    "Referer": f"{BASE}/tools/{TOOL_ID}/search"
}

def log(m):
    print("[" + time.strftime("%Y-%m-%d %H:%M:%S") + "] " + str(m), flush=True)

def parse_bounds(s):
    lon1, lat1, lon2, lat2 = (float(x) for x in s.split("_"))
    w, e = min(lon1, lon2), max(lon1, lon2)
    so, n = min(lat1, lat2), max(lat1, lat2)
    return [{"lon": w, "lat": n}, {"lon": e, "lat": so}]

def build_payload():
    return {
        "idTool": int(TOOL_ID),
        "need_aggregation": False,
        "page": 1,
        "pageSize": 100,
        "sector": None,
        "occupationModes": [],
        "location": parse_bounds(BOUNDS),
        "residence": None,
        "precision": 6,
        "equipment": [],
        "price": {"min": 0, "max": 100000}
    }

def fetch_items():
    r = requests.post(
        SEARCH_URL,
        headers=HEADERS,
        json=build_payload(),
        timeout=30
    )
    r.raise_for_status()
    d = r.json()
    return d.get("results", {}).get("items", []), d

def euros(c):
    return "?" if c is None else str(round(c / 100, 2)) + " EUR"

def describe(it):
    res = it.get("residence") or {}
    modes = it.get("occupationModes") or []
    rmin = rmax = None
    mt = []

    for m in modes:
        mt.append(m.get("type", "?"))
        rent = m.get("rent") or {}

        if rent.get("min") is not None:
            rmin = rent["min"] if rmin is None else min(rmin, rent["min"])

        if rent.get("max") is not None:
            rmax = rent["max"] if rmax is None else max(rmax, rent["max"])

    a = it.get("area") or {}

    return {
        "id": str(it.get("id")),
        "label": it.get("label") or "?",
        "residence": res.get("label") or "?",
        "address": res.get("address") or "?",
        "rent_min": rmin,
        "rent_max": rmax,
        "area_min": a.get("min"),
        "area_max": a.get("max"),
        "modes": ", ".join(mt) or "?",
        "url": ACCO_URL + "/" + str(it.get("id")),
        "available": bool(it.get("available"))
    }

def fmt_one(d, reason):
    return (
        "- [" + reason + "] " + d["residence"] + " (" + d["label"] + ")\n"
        "  " + d["address"] + "\n"
        "  Loyer : de " + euros(d["rent_min"]) + " a " + euros(d["rent_max"]) + "\n"
        "  Surface : " + str(d["area_min"]) + "-" + str(d["area_max"]) +
        " m2 | " + d["modes"] + "\n"
        "  " + d["url"]
    )

def format_mail(events):
    lines = [
        str(len(events)) + " evenement(s) CROUS pour " + LOCATION_NAME + ":",
        ""
    ]

    for d, reason in events:
        lines.append(fmt_one(d, reason))
        lines.append("")

    lines.append("-- crous_watch")
    return "\n".join(lines)

def send_mail(subj, body):
    if not (GMAIL_USER and GMAIL_APP_PASSWORD):
        raise RuntimeError("Gmail non configure : mail impossible a envoyer")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subj
    msg["From"] = formataddr(("CROUS Watch", GMAIL_USER))
    msg["To"] = MAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        s.sendmail(GMAIL_USER, [MAIL_TO], msg.as_string())

    log("Mail envoye a " + MAIL_TO)

def load_state():
    if STATE_FILE.exists():
        try:
            raw = json.loads(STATE_FILE.read_text())

            if isinstance(raw, list):
                log("Migration ancien format (liste d'ids) -> nouveau format.")
                return {str(i): {"available": True} for i in raw}

            return {str(k): v for k, v in raw.items()}

        except Exception as e:
            log("State illisible (" + str(e) + "), reset.")

    return {}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))

def run_once(state, first):
    items, raw = fetch_items()

    if first:
        log("=== PREMIER RUN : apercu API ===")
        log("Total annonce : " + str(raw.get("results", {}).get("total")))
        log("Nb items recus : " + str(len(items)))

        if items:
            log("Exemple : " + json.dumps(describe(items[0]), ensure_ascii=False))

        log("=== fin apercu ===")

    current = {d["id"]: d for d in (describe(it) for it in items)}
    events = []

    for vid, d in current.items():
        prev = state.get(vid)

        if prev is None:
            if d["available"]:
                events.append((d, "NOUVEAU"))
        else:
            if d["available"] and not bool(prev.get("available")):
                events.append((d, "REDEVENU DISPO"))

    if events:
        reasons = ", ".join(sorted(set(r for _, r in events)))
        log("EVENEMENTS (" + str(len(events)) + ") : " + reasons)

        try:
            send_mail(
                "[CROUS] " + str(len(events)) + " evenement(s) - " + LOCATION_NAME,
                format_mail(events)
            )
        except Exception as e:
            log("!! Echec mail : " + str(e) + " -- on reessaiera.")
            return state
    else:
        log("Rien de nouveau (" + str(len(current)) + " logement(s) au total).")

    new_state = {}

    for vid, d in current.items():
        new_state[vid] = {
            "available": d["available"],
            "label": d["label"],
            "residence": d["residence"]
        }

    save_state(new_state)
    return new_state

def main():
    log("Demarrage crous_watch")
    log("Zone : " + LOCATION_NAME + " | intervalle=" + str(INTERVAL) + "s")

    if not (GMAIL_USER and GMAIL_APP_PASSWORD):
        log("ATTENTION : Gmail non configure.")

    state = load_state()
    log(str(len(state)) + " logement(s) en memoire.")
    first = True

    while True:
        try:
            state = run_once(state, first)
        except requests.HTTPError as e:
            log("Erreur HTTP : " + str(e))
        except Exception as e:
            log("Erreur : " + str(e))

        first = False
        time.sleep(INTERVAL)

if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once(load_state(), True)
    else:
        main()
