# Wickless — instructions pour Claude Code

Tu reprends un projet déjà conçu et testé. Lis ce fichier en entier avant d'agir. L'utilisateur est un trader français, pas développeur : explique simplement ce que tu fais, en français, et demande-lui seulement ce qui ne peut pas être fait sans lui (connexion GitHub, choix du nom de dépôt).

## Le projet en une phrase
Wickless est un site web simple pour traders techniques : il montre en 10 secondes quand faire attention (annonces économiques à fort impact, jours fériés, séances courtes) et quand on peut trader tranquille. Il est utilisé par l'utilisateur et ses amis, qui vivent dans plusieurs pays.

## Ton objectif
Mettre le site en ligne sur **GitHub Pages**, avec une **mise à jour automatique toutes les heures par GitHub Actions**, sans aucun agent Claude ni serveur à payer. Puis donner à l'utilisateur le lien à partager.

## Fichiers du kit
- `index.html` — le site complet (HTML/CSS/JS sans dépendance, polices Google Fonts). Il lit `data.json` à côté de lui et le relit toutes les 30 minutes. **Déjà testé, ne le modifie que si c'est nécessaire.**
- `data.json` — les données de la semaine en cours (écrites à la main le 18/11/2026). Le workflow le régénère dès sa première exécution.
- `scripts/update.py` — le script de mise à jour (Python 3.9+, bibliothèque standard uniquement). Il télécharge le flux public Forex Factory, garde l'impact fort et les fériés, regroupe les annonces simultanées, ajoute les textes FR/EN depuis le dictionnaire, ajoute les fermetures de la bourse US, valide, et n'écrit `data.json` que si le contenu a changé.
- `scripts/lexicon.json` — le dictionnaire FR/EN : règles de reconnaissance des titres Forex Factory → « topics » (inflation, emploi, décisions de taux, discours…), avec titres, abréviations et explications « Comprendre ». Un titre inconnu passe par le topic `generic` (titre anglais d'origine + explication générique).
- `scripts/us_market_hours.json` — fermetures et clôtures anticipées des bourses US (NYSE), fin 2026 et 2027.
- `scripts/sample_feed.json` — un exemple de flux pour tester hors ligne (reconstitué à partir de la semaine du 16/11/2026, avec un faux férié EUR le 20/11 pour tester ce cas).
- `.github/workflows/site.yml` — met à jour les données toutes les heures, enregistre `data.json` s'il a changé et publie le site sur GitHub Pages (aussi à chaque push sur `main`).

## Étapes à suivre
1. **Vérifier les outils** : `git --version`, `python3 --version`, `gh --version`, puis `gh auth status`. Si `gh` n'est pas connecté, demande à l'utilisateur de lancer `gh auth login` (GitHub.com, HTTPS, navigateur).
2. **Tester en local** :
   - `python3 scripts/update.py --feed scripts/sample_feed.json --now 2026-11-18T09:16:00Z --dry-run` (doit afficher 9 annonces et 3 notes) ;
   - `python3 scripts/update.py --dry-run` (flux réel). Si le flux réel a un format différent de celui attendu (liste d'objets `title`, `country`, `date` ISO avec décalage New York, `impact`), adapte `fetch_feed`/`build` sans changer le format de sortie ;
   - `python3 -m http.server 8000` puis ouvrir `http://localhost:8000` pour que l'utilisateur voie le site. Ne lance pas `update.py` sans `--dry-run` avant le premier commit si tu veux garder le `data.json` d'origine (ce n'est pas grave sinon).
3. **Vérifier `scripts/us_market_hours.json`** contre le calendrier officiel NYSE (nyse.com/trade/hours-calendars) et corrige si besoin (surtout 2027 et les clôtures anticipées).
4. **Créer le dépôt et publier** : demande à l'utilisateur le nom du dépôt (par défaut `wickless`). Il doit être **public** (GitHub Pages gratuit). Puis :
   - `git init -b main && git add . && git commit -m "Wickless v1"`
   - `gh repo create wickless --public --source=. --remote=origin --push` (si le dépôt existe déjà vide : `git remote add origin …` puis `git push -u origin main`)
   - activer Pages en mode GitHub Actions : `gh api -X POST repos/{owner}/{repo}/pages -f build_type=workflow` (si ça échoue, demande à l'utilisateur : Settings → Pages → Source : GitHub Actions)
   - vérifier que les workflows ont le droit d'écrire : Settings → Actions → General → Workflow permissions → Read and write (ou `gh api -X PUT repos/{owner}/{repo}/actions/permissions/workflow -f default_workflow_permissions=write`)
   - lancer `gh workflow run site.yml` puis `gh run watch` ; corrige jusqu'à ce que les deux jobs passent.
5. **Donner le lien** : `https://{owner}.github.io/{repo}/`. Ouvre-le pour vérifier qu'il s'affiche avec les données.
6. **Prévenir l'utilisateur** qu'il peut maintenant supprimer, sur claude.ai, la tâche programmée « Wickless — mise à jour du calendrier » (elle mettait à jour l'ancienne version hébergée sur Claude) et que l'ancien lien claude.ai n'est plus à jour.

## Format de `data.json` (lu par `index.html`)
```
{
  "version": 1,
  "generatedAt": "2026-11-18T09:17:00Z",          // date de la dernière modification
  "coverage": { "from": "2026-11-15", "to": "2026-11-21" },  // jours couverts par le flux
  "events": [{
    "id": "2026-11-18-0700-gbp-cpi", "time": "2026-11-18T07:00:00Z", "ccy": "GBP",
    "kind": "data|speech|minutes|rate", "major": true,
    "window": { "before": 5, "after": 15 },        // after null = « jusqu'à la fin du discours »
    "title": {"fr","en"}, "short": {"fr","en"}, "assets": {"fr","en"}, "note": {"fr","en"} (facultatif),
    "explain": { "fr": [{label,text}×3], "en": [{label,text}×3] },
    "source": ["CPI y/y"]                           // titres Forex Factory d'origine (non affichés)
  }],
  "notes": [{                                        // fériés et horaires spéciaux
    "id", "ccy", "date": "AAAA-MM-JJ" OU "time": ISO UTC, "closed": bool (bourses US fermées), "short": bool (séance courte),
    "kind": {"fr","en"}, "title": {"fr","en"}, "sub": {"fr","en"}, "explain": {"fr":[…],"en":[…]}
  }],
  "upcoming": [{ "title": {"fr","en"}, "text": {"fr","en"}, "until": "AAAA-MM-JJ" }]
}
```

## Règles du site (déjà codées dans `index.html`)
- Devises : USD, EUR, GBP, JPY, CHF, CAD, AUD, NZD (filtrables, mémorisées dans le navigateur). Crypto exclue.
- Fuseau horaire au choix (fuseau du navigateur par défaut), heures d'été gérées par le navigateur (Intl). Langue FR/EN (langue du navigateur par défaut).
- Niveau d'un jour : « Marché US fermé » si une note `closed` ; « Journée piège » si une annonce `major` ou 3 créneaux horaires ou plus ; « Prudence » s'il y a au moins une annonce ; sinon « Calme » (« Calme · séance courte » si note `short`).
- Vue Semaine par défaut ; clic sur un jour → vue Jour (compte à rebours, frise des sessions Asie/Londres/New York, annonces avec bouton « Comprendre »).
- Le week-end, le site montre la semaine suivante ; tant que Forex Factory ne l'a pas publiée (dimanche), un message l'explique.
- Le graphique en chandeliers 3D est décoratif (« illustration, pas un vrai cours »).
- Design : fond blanc, couleurs pastel par niveau (bleu calme #E7F0FF, pêche prudence #FFF0DB, rose piège #FFE1E6, lilas fermé #EEE9FF), polices Instrument Sans / Instrument Serif / Fragment Mono.

## Règles pour les textes
- Information uniquement : jamais de conseil d'achat ou de vente, jamais de prévision ni de consensus chiffré.
- Phrases courtes, tutoiement en français, anglais naturel ; toujours les deux langues.
- Pour améliorer une annonce reconnue en `generic`, ajoute une règle et un topic dans `lexicon.json` (variables disponibles listées dans `_comment`), puis teste avec `--dry-run`.

## Limites connues / pistes
- Le flux gratuit Forex Factory est adapté à un usage privé entre amis, pas à un usage commercial (il faudra une source sous licence pour vendre).
- Certaines annonces ont un horaire « provisoire » chez Forex Factory ; dans le flux JSON elles peuvent apparaître à minuit (heure de New York). À surveiller.
- GitHub peut mettre en pause les workflows programmés d'un dépôt sans activité pendant longtemps : vérifier de temps en temps que l'onglet Actions tourne.
- Idées pour plus tard (à ne pas faire sans l'accord de l'utilisateur) : nom de domaine personnalisé, PWA installable, alertes Telegram/Discord, news imprévues en temps réel.
