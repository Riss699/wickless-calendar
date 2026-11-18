#!/usr/bin/env python3
"""Wickless : met à jour data.json à partir du calendrier public Forex Factory.

Aucune dépendance externe (Python 3.9+). Utilisation :
    python3 scripts/update.py                     # télécharge le flux et met à jour data.json
    python3 scripts/update.py --feed test.json    # utilise un fichier local (tests)
    python3 scripts/update.py --dry-run           # affiche le résultat sans écrire

Le script n'écrit data.json que si le contenu a changé (hors date de mise à jour).
En cas d'erreur (flux injoignable, format inattendu, validation ratée), il s'arrête
avec un code d'erreur et ne touche pas au data.json existant.
"""
import argparse
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CCYS = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"]
NY = ZoneInfo("America/New_York")
WINDOWS = {
    "data": {"before": 5, "after": 15},
    "speech": {"before": 5, "after": None},
    "minutes": {"before": 5, "after": 30},
    "rate": {"before": 5, "after": 90},
}
LANGS = ("fr", "en")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch_feed():
    req = urllib.request.Request(
        FEED_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; WicklessCalendar/1.0)", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Le flux Forex Factory n'a pas le format attendu (liste d'événements).")
    return data


def parse_dt(text):
    t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=NY)  # le flux JSON est exprimé à l'heure de New York
    return t


def iso_z(t):
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Keep(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def fill(text, ctx):
    return text.format_map(_Keep(ctx))


def cap(text):
    return text[:1].upper() + text[1:] if text else text


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "event"


def country_ctx(lex, ccy, extra=None):
    ctx = dict(lex["countries"][ccy])
    ctx["ccy"] = ccy
    if extra:
        ctx.update(extra)
    return ctx


def explain_block(texts, labels, ctx):
    return {
        lang: [{"label": labels[lang][i], "text": cap(fill(t, ctx))} for i, t in enumerate(texts[lang])]
        for lang in LANGS
    }


def classify(title, ccy, lex):
    for rule in lex["rules"]:
        if rule.get("only") and ccy not in rule["only"]:
            continue
        m = re.search(rule["match"], title, re.IGNORECASE)
        if m:
            return rule["topic"], m.groupdict()
    return "generic", {}


def build(feed, lex, hours, prev, now):
    labels = {"fr": lex["labels"]["fr"], "en": lex["labels"]["en"]}
    note_labels = {"fr": lex["labels"]["note_fr"], "en": lex["labels"]["note_en"]}

    raw_events = []
    ff_holidays = []
    feed_dates = []
    for item in feed:
        ds = item.get("date")
        if not ds:
            continue
        try:
            t = parse_dt(ds)
        except ValueError:
            continue
        feed_dates.append(t.astimezone(NY).date())
        ccy = (item.get("country") or "").upper()
        if ccy not in CCYS:
            continue
        impact = (item.get("impact") or "").strip().lower()
        title = (item.get("title") or "").strip()
        if impact == "holiday":
            ff_holidays.append((ccy, t.astimezone(NY).date().isoformat(), title))
        elif impact == "high":
            raw_events.append((ccy, t, title))

    if not feed_dates:
        raise ValueError("Le flux ne contient aucun événement daté.")
    cov_from, cov_to = min(feed_dates), max(feed_dates)

    # Regroupe les annonces d'une même devise publiées à la même minute.
    groups = {}
    for ccy, t, title in raw_events:
        groups.setdefault((ccy, iso_z(t)), []).append(title)

    events = []
    for (ccy, when), titles in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        classified = [(classify(ti, ccy, lex), ti) for ti in titles]
        (topic, gd), main_title = max(classified, key=lambda c: lex["topics"][c[0][0]].get("priority", 1))
        T = lex["topics"][topic]
        speaker = (gd or {}).get("speaker") or ""
        ctx = country_ctx(lex, ccy, {"title": main_title, "speaker": speaker.split()[-1] if speaker else ""})
        kind = T["kind"]
        ev = {
            "id": "{}-{}-{}-{}".format(when[:10], when[11:16].replace(":", ""), ccy.lower(), slug(topic if topic != "generic" else main_title)),
            "time": when,
            "ccy": ccy,
            "kind": kind,
            "major": any(lex["topics"][c[0][0]].get("major", False) for c in classified),
            "window": WINDOWS[kind],
            "title": {lang: cap(fill(T["title"][lang], ctx)) for lang in LANGS},
            "short": {lang: fill(T["short"][lang], ctx) for lang in LANGS},
            "assets": {"fr": ctx["assets_fr"], "en": ctx["assets_en"]},
            "explain": explain_block(T["explain"], labels, ctx),
            "source": titles,
        }
        if len(titles) > 1:
            ev["note"] = {
                "fr": "{} chiffres publiés en même temps : {}.".format(len(titles), ", ".join(titles)),
                "en": "{} figures at once: {}.".format(len(titles), ", ".join(titles)),
            }
        events.append(ev)

    # Jours fériés et horaires spéciaux (semaine du flux + 7 jours).
    start, end = cov_from, cov_to + timedelta(days=7)
    notes = []
    seen = set()
    for d, names in hours["closed"].items():
        if start <= date.fromisoformat(d) <= end:
            X = hours["texts"]["closed"]
            notes.append({
                "id": d + "-usd-closed", "date": d, "ccy": "USD", "closed": True, "short": False,
                "kind": X["kind"], "title": names, "sub": X["sub"],
                "explain": explain_block(X["explain"], note_labels, {}),
            })
            seen.add(("USD", d))
    for d, hm in hours["early_close"].items():
        dd = date.fromisoformat(d)
        if start <= dd <= end:
            h, m = (int(x) for x in hm.split(":"))
            X = hours["texts"]["early"]
            notes.append({
                "id": d + "-usd-early-close", "time": iso_z(datetime(dd.year, dd.month, dd.day, h, m, tzinfo=NY)),
                "ccy": "USD", "closed": False, "short": True,
                "kind": X["kind"], "title": X["title"], "sub": X["sub"],
                "explain": explain_block(X["explain"], note_labels, {"close": hm}),
            })
    H = lex["holiday"]
    for ccy, d, _title in ff_holidays:
        if (ccy, d) in seen:
            continue
        seen.add((ccy, d))
        ctx = country_ctx(lex, ccy)
        notes.append({
            "id": "{}-{}-holiday".format(d, ccy.lower()), "date": d, "ccy": ccy, "closed": False, "short": False,
            "kind": {lang: fill(H["kind"][lang], ctx) for lang in LANGS},
            "title": {lang: cap(fill(H["title"][lang], ctx)) for lang in LANGS},
            "sub": {lang: cap(fill(H["sub"][lang], ctx)) for lang in LANGS},
            "explain": explain_block(H["explain"], note_labels, ctx),
        })
    notes.sort(key=lambda n: n.get("time") or n["date"])

    today = now.astimezone(timezone.utc).date().isoformat()
    upcoming = [u for u in (prev.get("upcoming") or []) if not u.get("until") or u["until"] >= today]

    return {
        "version": 1,
        "generatedAt": iso_z(now),
        "coverage": {"from": cov_from.isoformat(), "to": cov_to.isoformat()},
        "events": events,
        "notes": notes,
        "upcoming": upcoming,
    }


def validate(out):
    problems = []
    for ev in out["events"]:
        for key in ("id", "time", "ccy", "kind", "major", "window", "title", "short", "assets", "explain"):
            if key not in ev:
                problems.append("{} : champ manquant {}".format(ev.get("id"), key))
        if ev.get("ccy") not in CCYS:
            problems.append("{} : devise inconnue".format(ev.get("id")))
        if not str(ev.get("time", "")).endswith("Z"):
            problems.append("{} : heure non UTC".format(ev.get("id")))
        for lang in LANGS:
            for key in ("title", "short", "assets"):
                if not (ev.get(key) or {}).get(lang):
                    problems.append("{} : {}.{} vide".format(ev.get("id"), key, lang))
            if len((ev.get("explain") or {}).get(lang) or []) != 3:
                problems.append("{} : explain.{} doit avoir 3 éléments".format(ev.get("id"), lang))
            if re.search(r"\{[a-z_]+\}", json.dumps(ev.get("title", {}), ensure_ascii=False) + json.dumps(ev.get("explain", {}), ensure_ascii=False)):
                problems.append("{} : variable non remplacée dans les textes".format(ev.get("id")))
    for n in out["notes"]:
        if not (n.get("date") or n.get("time")):
            problems.append("{} : note sans date ni heure".format(n.get("id")))
    if problems:
        raise ValueError("Validation impossible :\n- " + "\n- ".join(problems))


def strip_meta(d):
    return {k: v for k, v in d.items() if k != "generatedAt"}


def main():
    ap = argparse.ArgumentParser(description="Met à jour data.json pour Wickless.")
    ap.add_argument("--feed", help="fichier JSON local à utiliser à la place du flux en ligne")
    ap.add_argument("--now", help="date/heure de référence ISO (tests)")
    ap.add_argument("--dry-run", action="store_true", help="affiche le résultat sans écrire data.json")
    args = ap.parse_args()

    lex = load_json(ROOT / "scripts" / "lexicon.json")
    hours = load_json(ROOT / "scripts" / "us_market_hours.json")
    data_path = ROOT / "data.json"
    prev = load_json(data_path) if data_path.exists() else {}
    feed = load_json(args.feed) if args.feed else fetch_feed()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    out = build(feed, lex, hours, prev, now)
    validate(out)

    if args.dry_run:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if prev and strip_meta(prev) == strip_meta(out):
        print("Aucun changement : data.json conservé.")
        return 0
    data_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("data.json mis à jour : {} annonces, {} fériés/horaires spéciaux.".format(len(out["events"]), len(out["notes"])))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # le workflow échoue proprement, l'ancien data.json reste en ligne
        print("Erreur : {}".format(exc), file=sys.stderr)
        sys.exit(1)
