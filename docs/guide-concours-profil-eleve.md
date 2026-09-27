# Guide des concours et profil élève

Branche : `gregory/guide-concours-profil-eleve`, issue de `gregory/guide-reussir-kholle` (commit `2516eb4`). Le bilan de fin de khôlle reste dans sa branche et sa PR séparées.

## Comportement

- La page `/reussir-sa-kholle` conserve les deux logos en fond ; les inscriptions « Road to » et « X/ENS » ont été retirées.
- `/guide-concours` est publique et propose le PDF de neuf pages pour MP, MPI, PC et PSI. Le PDF et son source LaTeX sont dans `app/web/static/guides/guide-concours-oraux-2026.*`.
- L'inscription propose la prépa, la filière, le rang en maths et l'effectif, ainsi qu'un texte d'objectifs. Tout est facultatif. Un rang renseigné exige un effectif et doit être compris entre 1 et cet effectif.
- `/mon-profil` permet de compléter, modifier ou effacer ces informations. L'accès nécessite une session valide ; la modification est protégée par CSRF et utilise le verrou de l'application.
- Le champ JSON `projet_eleve` est enregistré dans le profil privé. Les anciens profils restent lisibles sans migration ; les niveaux, tâches et historiques sont conservés.
- L'agent relit le profil au début de chaque tour. Il transmet le contexte comme un message de données, sans l'insérer dans ses instructions et sans accumuler d'anciennes copies dans l'historique. Les réponses observées priment sur le rang déclaré ; aucune capacité n'est inférée du lycée.
- Les relances sont orientées vers les objectifs dans le chapitre et les supports disponibles. Cette évolution n'ajoute ni de corpus de physique, ni un simulateur complet de chaque concours, ni une mesure de vitesse de réponse.

## Références du guide

Notices 2026, rapports 2025 lorsqu'ils servent à décrire le déroulement ; 23 liens dans le PDF. Les tableaux ENS des versions des 10 et 12 février ont été comparés : ils sont identiques pour les quatre filières retenues. Les pourcentages sont calculés sur le total des coefficients retenus pour le concours complet, hors bonus ; ils ne mesurent pas l'effet sur le classement.

Les durées d'interrogation de maths ENS PC et PSI non précisées par les rapports consultés sont explicitement laissées à confirmer sur convocation. Pour Mines-Télécom, le calcul écrit + oral et les règles de reprise des notes ont été lus dans une copie de la notice 2026 ; le PDF fournit aussi le lien vers la documentation de l'organisateur. Le guide distingue le cas des bi-admissibles.

Compiler avec XeLaTeX ou `tectonic app/web/static/guides/guide-concours-oraux-2026.tex`. Vérifier le rendu de chaque page après modification. Le PDF a été contrôlé sur neuf pages, ses liens vérifiés dans les annotations et les fractions explicites recalculées.

## Vérification

Depuis la racine du dépôt, avec Python 3.12 et les dépendances installées :

```sh
python -m unittest app.test_colle app.test_agent app.test_enonces app.test_evaluation app.test_cours app.test_chapitres app.web.test_web app.web.test_chat app.web.test_auth app.web.test_projet_eleve scripts.test_lister_formules_coupees
```

Résultat du 27 septembre 2026 : **75 méthodes exécutées, 74 réussies**. `app.test_chapitres.ChapitresTests.test_variantes_et_alias_internes` échoue sur huit sous-cas. L'échec est reproduit avec les fichiers extraits du commit parent `2516eb4` : il préexiste à cette branche et concerne les alias libres de « séries », non le profil. Tous les tests ajoutés ici passent. Les appels des tests sont simulés ; ils prouvent la transmission du contexte, pas la qualité pédagogique du modèle réel.

Contrôles manuels effectués dans le navigateur local avec un compte de démonstration : inscription complète, relecture et modification du profil, confirmation de sauvegarde, navigation, affichage des deux logos sans le texte supprimé. Les pages publiques et le PDF renvoient HTTP 200 ; le PDF est servi en `application/pdf`.

Pour une validation pédagogique réelle : créer deux profils aux objectifs différents, choisir le même chapitre, faire plusieurs tours et comparer les relances. Vérifier que les objectifs orientent les questions sans imposer un verdict ou contourner une étape. Ce contrôle nécessite les clés et consomme des crédits API ; il n'a pas été exécuté dans cette livraison.
