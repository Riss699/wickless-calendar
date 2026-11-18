# Wickless

Calendrier des annonces économiques à fort impact pour traders techniques, en français et en anglais : vue semaine, vue jour, fuseau horaire au choix, jours fériés et séances courtes.

- Site : `index.html` + `data.json` (hébergés sur GitHub Pages)
- Mise à jour : GitHub Actions lance `scripts/update.py` toutes les heures et republie le site si le calendrier a changé
- Source des données : calendrier public Forex Factory (impact fort) et calendrier officiel NYSE

## Mettre en ligne
Ouvre Claude Code dans ce dossier et dis-lui : « Lis CLAUDE.md et mets Wickless en ligne sur GitHub Pages ».

## Tester sur ton ordinateur
```
python3 scripts/update.py --dry-run
python3 -m http.server 8000
```
puis ouvre http://localhost:8000
