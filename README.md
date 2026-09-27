# Agent tuteur pour la prépa scientifique

Projet Python d’agent tuteur destiné aux élèves de classes préparatoires scientifiques.
Il vise à accompagner les élèves dans la compréhension des cours et la résolution d’exercices.

- `methods/` : méthodes Pipelex.
- `app/` : profil élève, tuteur en terminal et interface web.
- `.env.example` : variables d’environnement à renseigner dans un fichier `.env` local.

## Installation sur Windows

Prérequis : Git et Python **3.12 64 bits**, avec le lanceur `py`, ainsi que des
clés API OpenAI et Pipelex pour utiliser toutes les fonctions du tuteur.
Une connexion Internet est nécessaire pour installer les dépendances et appeler
les API.

Dans PowerShell, cloner le dépôt puis créer un environnement Python isolé :

```powershell
git clone https://github.com/youssefabid1234/projet-xia.git
cd projet-xia
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Le `requirements.txt` racine regroupe les dépendances de l'application web,
du tuteur en terminal, des scripts d'extraction et d'indexation des cours et des
tests hors ligne. Il réutilise les listes de `app/web/requirements.txt` et de
`scripts/requirements-cours.txt` ; pip installe aussi leurs dépendances transitives.
Les commandes appellent directement le Python de `.venv` : aucune activation ni
modification de la politique d'exécution PowerShell n'est nécessaire.

### Configuration

Dans la même fenêtre PowerShell, remplacer les valeurs ci-dessous par vos clés :

```powershell
$env:PIPELEX_API_KEY = "votre-cle"
$env:OPENAI_API_KEY = "votre-cle-openai"
# Facultatif : modèle du dialogue et de la vérification des tentatives.
$env:OPENAI_MODEL = "gpt-4.1-mini"
# Remplacer par une valeur secrète personnelle et conserver la même aux relancements.
$env:FLASK_SECRET_KEY = "remplacer-par-une-longue-valeur-secrete-aleatoire"
```

Ces variables sont valables pour la fenêtre PowerShell courante ; les redéfinir
dans chaque nouvelle fenêtre avant de lancer le serveur. `.env.example` sert
de modèle, mais l'application **ne charge pas automatiquement de fichier `.env`**.
Ne pas publier vos clés dans le dépôt.

Les exercices et l'index du cours sont fournis dans `data/` : aucune extraction
PDF ni génération d'embeddings n'est nécessaire pour démarrer.

## Lancement sur Windows

Depuis la racine du projet, dans la fenêtre PowerShell configurée ci-dessus :

```powershell
.\.venv\Scripts\python.exe -m app.web
```

Ouvrir http://127.0.0.1:5000, créer un compte avec le formulaire d'inscription,
puis se connecter pour discuter en français avec le tuteur.
Arrêter le serveur avec `Ctrl+C`. Pour le relancer, reprendre la configuration
des variables si nécessaire puis la commande ci-dessus ; inutile de réinstaller
les dépendances à chaque lancement. Ce serveur local utilise le port 5000 ;
si ce port est occupé, arrêter l'autre serveur avant de relancer l'application.

Pour utiliser le tuteur en terminal (clé Pipelex requise) :

```powershell
.\.venv\Scripts\python.exe -m app.tuteur
```

## Interface web

Choisir un chapitre pour une colle : questions de cours (définitions et théorèmes),
démonstration courte, applications des exemples, puis exercices du catalogue.
L’agent pilote les étapes et refuse de passer à la suite tant que l’acquisition
n’est pas établie. Il questionne face au blocage, demande de justifier la méthode
et exige la reformulation d’une erreur avant de poursuivre.

Pour les tâches de cours, démonstration et application, le serveur évalue chaque
message avant la réponse du tuteur, sans attendre un signal du modèle. Une réponse
correcte clôt la tâche et enregistre `acquise: true` dans le profil, indépendamment
du modèle de progression. L'identifiant du passage et la nature de la tâche
empêchent de la reposer, y compris après déconnexion ou redémarrage. Le serveur
reconstitue l'étape depuis ces acquis et impose l'enregistrement de chaque
nouvelle question avant son affichage.

Pour les exercices du catalogue, la correction se déclenche quand le travail semble terminé, après deux tours de
blocage, à partir du troisième indice donné, ou sur demande dans le dialogue
(même sans tentative). Le bouton de correction a été supprimé du chat.
Les demandes d’aide ne comptent pas comme tentatives ; un blocage durable peut
néanmoins faire l’objet d’une évaluation incomplète.

Le cours actuellement indexé couvre les séries numériques, reliées explicitement
au chapitre « 17 — Série de réels ou de complexes » du catalogue. Les autres
chapitres nécessitent un cours indexé pour mener la colle complète ; l’agent
signale ce manque et ne saute pas directement aux exercices.

L’ancienne interface reste accessible sur http://127.0.0.1:5000/classique,
avec le même formulaire, les mêmes corrections et la même progression.
Le tuteur en terminal (`python -m app.tuteur`) reste également disponible.

L’interface Flask se trouve dans `app/web/`. L’agent dans `app/agent.py` utilise
l’API Responses OpenAI et les outils de recherche, de préparation de tâche,
d’observation du tour, d’évaluation et de sélection d’exercice.
`app/colle.py` contrôle les transitions côté serveur. Une observation est imposée
au modèle à chaque nouveau message sur une tâche active. La classification des
signaux et le jugement pédagogique restent probabilistes.
La recherche utilise les 80 passages de séries numériques dans
`data/cours_index.json` et renvoie leurs pages sources. Elle combine embeddings
OpenAI et recherche lexicale ; voir [les commandes et tests du cours](scripts/COURS.md).
Les instructions du tuteur imposent cette recherche avant toute réponse sur une
notion, définition, méthode ou théorème, avec citation du passage et de sa page PDF.
Tout complément absent des extraits doit porter la mention « Hors du cours extrait : ».
Avant chaque proposition dans le chat, `app/enonces.py` vérifie l'énoncé avec le
corrigé du catalogue dans un appel OpenAI privé. Il remet les formules en LaTeX
uniquement si leur lecture est certaine ; sinon l'agent passe silencieusement au
candidat suivant, selon le même ordre de niveau. La vérification par modèle reste
probabiliste, avec consigne de refuser au moindre doute.
Les exercices écartés restent exclus pour cette conversation sans être comptés
comme vus. Le catalogue n'est pas modifié et le corrigé n'entre pas dans
l'historique du dialogue. Une panne de vérification laisse le candidat réessayable.
L'énoncé validé est conservé dans l'exercice actif : la correction utilise ce
texte exact et ne relance jamais la vérification ou la reconstruction.
Cette préparation consomme un appel OpenAI par candidat examiné.
Le choix et la lecture du niveau utilisent `app/profil.py`, l’évaluation réutilise
la méthode existante via `app/evaluation.py`. Le function calling suit la
[documentation officielle OpenAI](https://developers.openai.com/api/docs/guides/function-calling).
L'évaluation reçoit `enonce`, `reponse_eleve` et le champ `corrige` du catalogue
(ou le passage source du cours pour les trois premières étapes),
réservé aux appels privés de vérification et d'évaluation. Elle compare la copie à ce corrigé vérifié ; elle ne
reconstruit plus de référence. Un corrigé absent ou vide bloque l'appel ; une
ambiguïté empêchant la comparaison doit produire `indeterminable`.
L’évaluation porte sur les interventions réelles de l’élève dans la tâche, en
tenant compte de ses rectifications. Le modèle ne fournit pas de copie réécrite
à l’évaluateur.

Le profil conserve chaque tâche sous `taches` : énoncé, étape, source, demandes
d’indices, indices donnés, tentatives, rappels de cours, intuition initiale,
types d’erreur, notions, évaluations successives et décision. Les anciens profils
restent compatibles. Les tâches de cours ne sont pas ajoutées aux exercices vus.

`methods/progression_colle/main.mthds` reçoit ces signaux et l’historique du
chapitre, puis décide `avancer`, `approfondir`, `revenir_au_cours` ou
`changer_exercice`, avec un jugement d’acquisition et une justification.
Le serveur exige au minimum une définition et un théorème acquis dans le profil
avant la démonstration. Pour le cours, une nouvelle réponse évaluée correcte
valide directement l'acquisition. Pour le catalogue, il refuse une avance sans
réponse correcte et acquisition, et bloque toute transition tant qu'une erreur
reste à reformuler. Une réussite au catalogue
cible une difficulté supérieure ; un changement pour blocage cible plus facile,
avec repli sur le niveau disponible le plus proche.
Si la décision Pipelex échoue, la correction reste disponible et l’étape est conservée.
Cette décision n'est pas appelée pour valider une réponse de cours correcte.

Les types Python générés sont dans `app/generated/progression_colle` (ne pas les
modifier à la main). Après une modification de la méthode, les régénérer avec
Pipelex puis vérifier leur cohérence depuis la racine :

```powershell
.venv/Scripts/python.exe scripts/codegen_check.py app/generated/progression_colle
```

Exemple d’entrée de la méthode de progression :

```json
{"performance":{"etape":"cours","indices_demandes":1,"indices_donnes":1,"tentatives":2,"rappels_cours":0,"intuition_initiale":"pertinente","type_erreur":"aucune","notions":["convergence"],"verdict":"correcte","erreur_reformulee":false,"historique":"[]"}}
```

Chaque échange consomme du crédit OpenAI ; chaque évaluation et décision de
progression consomme aussi du crédit Pipelex. Les clés restent côté serveur ; le fichier
`.env` n’est pas chargé automatiquement. Sans clé OpenAI, l’ancienne interface
reste utilisable avec la clé Pipelex seule.

Les conversations sont isolées par session de navigateur et conservées en mémoire
(au plus 100 discussions, 60 échanges par discussion). Un redémarrage les efface.
« Nouvelle discussion » efface le dialogue courant, sans effacer le profil.

L’interface web demande une inscription ou une connexion. Les comptes sont dans
`data/utilisateurs.json`, avec des mots de passe hachés par Werkzeug. Chaque élève
a son profil dans `data/profils/<identifiant>.json`. Ces données sont ignorées par Git.
La session Flask conserve la connexion ; « Se déconnecter » la termine.
Définir `FLASK_SECRET_KEY` avec une valeur secrète stable pour conserver les sessions
au redémarrage (sinon une clé aléatoire est créée à chaque lancement).
Utiliser un seul processus serveur pour ce stockage JSON local.
Le tuteur en terminal conserve son fichier `data/profil.json` indépendant.
Le profil web est sauvegardé à chaque tâche, observation et correction
valide ; les exercices déjà traités ne sont plus proposés. Dans le chat,
retravailler un exercice déjà enregistré ne modifie pas à nouveau le niveau.

Les formules des énoncés et explications sont rendues avec
[KaTeX auto-render](https://katex.org/docs/autorender), chargé depuis un CDN
(connexion Internet nécessaire). Les délimiteurs `$…$`, `$$…$$`, `\(…\)`
et `\[…\]` sont pris en charge. Le texte reste lisible si le CDN est inaccessible.

Tests hors ligne, avec Pipelex simulé et un profil temporaire :

```powershell
.venv/Scripts/python.exe -m unittest app.test_colle app.test_agent app.test_enonces app.test_evaluation app.test_cours app.web.test_web app.web.test_chat app.web.test_auth scripts.test_lister_formules_coupees
```

## Repérer les formules coupées dans les énoncés

```powershell
python scripts/lister_formules_coupees.py --sortie data/enonces_a_verifier.md
```

Le rapport contient les identifiants, pages sources, lignes suspectes et énoncés
complets numérotés. Le script ne modifie pas `data/exercices.json` : corriger son
champ `enonce` à la main en consultant le PDF. La détection est heuristique et peut
signaler une formule multiligne valide. Ajouter `--tous-multilignes` pour inclure
tous les énoncés multilignes, ou `--format json` pour un rapport exploitable en code.
