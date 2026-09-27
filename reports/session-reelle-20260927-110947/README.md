# Vérification réelle du profil — 27 septembre 2026

Session HTTP locale exécutée avec `python -m scripts.session_reelle_profil` :
application Flask réelle, compte créé par le formulaire, vrais appels OpenAI
(dialogue et recherche) et Pipelex (évaluation). Aucun service simulé et aucune
écriture manuelle dans le profil. Réponse élève saisie dans le terminal.

1. Inscription de `verification-profil` et sélection du chapitre par le formulaire
   du bouton existant (`action=chapitre`, `chapitre=0`).
2. Question : « Donnez-moi la définition d'une série convergente. »
3. Réponse sur la limite finie des sommes partielles, évaluée `correcte` par Pipelex.
4. Nouvelle question affichée sur le théorème de convergence absolue.
5. Déconnexion, connexion au même compte et sélection du même chapitre.
6. Nouvelle question affichée : « Donnez-moi la définition d'une série semi-convergente. »
   Le journal d'exécution a montré un essai du modèle de préparer à nouveau
   `16.1.5`, refusé par le serveur : « Cette tâche est déjà validée dans le profil. »

Le fichier [profils/verification-profil.json](profils/verification-profil.json)
est le fichier directement écrit par l'application et relu après la reconnexion.
Il contient trois tâches, une évaluation réelle et un acquis (`16.1.5`). Les deux
autres tâches sont seulement posées, sans réponse ni validation. `historique`
et `exercices_vus` concernent les exercices du catalogue et restent donc vides.
Les deux identifiants de session distincts attestent la création d'une nouvelle
colle à la reconnexion, tout en conservant la tâche acquise.

[session.json](session.json) conserve les routes, les statuts HTTP finaux (tous
200 après redirection) et les échanges effectivement affichés. Le test utilise
un serveur HTTP et les formulaires de l'application ; il ne vérifie pas le rendu
visuel dans un navigateur. Les 63 tests hors réseau passent également.
