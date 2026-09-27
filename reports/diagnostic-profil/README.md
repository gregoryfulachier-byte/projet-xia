# Diagnostic du profil et de la progression

Diagnostic effectué avant les modifications du comportement.

Le profil web local vide inspecté contenait `niveaux: {}`, `exercices_vus: []`,
`historique: []`, `taches: {}`. Aucun journal de conversation n'étant enregistré
dans ce fichier, il ne permet pas de reconstituer la session du testeur.
Le profil terminal `data/profil.json` est distinct des profils web.

## Reproduction avant correction

Un Agent neuf, avec un profil temporaire, a reçu dix messages et dix réponses
simulées « Correct, nous pouvons continuer. », sans appel d'outil. Les dix réponses
ont été publiées. Aucun fichier profil n'a été créé ; sa lecture par défaut donnait :

```json
{"nom":"eleve","niveaux":{},"exercices_vus":[],"historique":[],"taches":{}}
```

La préparation de tâche était laissée au modèle. Sans `preparer_tache`, aucune
tâche n'existait et l'observation obligatoire ne s'activait jamais. De plus,
une tentative avec `fini=non` n'imposait pas d'évaluation. Enfin, les acquis
étaient filtrés par l'identifiant de la session courante.

## Session après correction

Reproduction : `.venv/Scripts/python.exe -m scripts.diagnostiquer_session`.
Les services de dialogue, recherche, évaluation et progression sont simulés.
Le vrai Agent exécute les outils, transitions et écritures/lectures du profil.
Les sources `diagnostic-*` sont synthétiques, pas des références au cours réel.

- 10 échanges, 3 tâches, 2 évaluations sauvegardées.
- Définition de convergence : correcte, clôturée.
- Théorème de convergence absolue : correct, clôturé.
- Démonstration : enregistrée, en attente de réponse.
- Un nouvel Agent relit les deux acquis depuis le même fichier.

Le profil complet est dans [profil-apres.json](profil-apres.json) ; le dialogue,
les compteurs et les acquis relus dans [session.json](session.json).
`historique` reste vide car il concerne le catalogue d'exercices ; les deux
évaluations du cours sont dans `taches[*].evaluations`.

Les tests vérifient le refus des questions validées, y compris après création
d'un nouvel Agent, l'isolation entre profils et l'affichage de la question
enregistrée. Le choix d'une question pédagogiquement plus avancée et la
classification d'un message comme tentative restent confiés au modèle.
Aucune validation ancienne non enregistrée n'est inventée ou ajoutée aux profils.

Validation hors réseau : 68 tests de la suite documentée réussis. La vérification
supplémentaire `app.test_chapitres` révèle 8 échecs préexistants de sous-tests
sur les alias de noms de chapitres ; ces fichiers ne sont pas modifiés ici.
