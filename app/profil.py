"""Suivi du niveau d'un eleve et selection d'exercices adaptes."""

import json
from pathlib import Path

CHEMIN_EXERCICES = Path(__file__).parent.parent / "data" / "exercices.json"

# Variation du niveau selon le verdict rendu par la methode Pipelex.
# La montee est plus rapide que la descente : un echec isole ne doit
# pas faire degringoler un eleve qui progresse.
GAINS = {
    "correcte": 0.3,
    "incomplete": 0.1,
    "incorrecte": -0.2,
    "indeterminable": 0.0,
}

NIVEAU_MIN = 1.0
NIVEAU_MAX = 5.0
NIVEAU_DEPART = 1.5


class Profil:
    """Niveau d'un eleve par chapitre et historique des exercices vus."""

    def __init__(self, nom):
        self.nom = nom
        self.niveaux = {}
        self.exercices_vus = []
        self.historique = []
        self.taches = {}
        self.projet_eleve = {}

    def niveau(self, chapitre):
        return self.niveaux.get(chapitre, NIVEAU_DEPART)

    def enregistrer(self, id_exercice, chapitre, verdict, type_erreur):
        actuel = self.niveau(chapitre)
        nouveau = actuel + GAINS.get(verdict, 0.0)
        self.niveaux[chapitre] = max(NIVEAU_MIN, min(NIVEAU_MAX, nouveau))

        if id_exercice not in self.exercices_vus:
            self.exercices_vus.append(id_exercice)

        self.historique.append({
            "exercice": id_exercice,
            "chapitre": chapitre,
            "verdict": verdict,
            "type_erreur": type_erreur,
        })

    def erreurs_frequentes(self):
        """Compte les types d'erreur rencontres, du plus frequent au moins."""
        compte = {}
        for entree in self.historique:
            t = entree["type_erreur"]
            if t not in ("aucune", "non_determinable"):
                compte[t] = compte.get(t, 0) + 1
        return sorted(compte.items(), key=lambda x: x[1], reverse=True)

    def to_dict(self):
        return {
            "nom": self.nom,
            "niveaux": self.niveaux,
            "exercices_vus": self.exercices_vus,
            "historique": self.historique,
            "taches": self.taches,
            "projet_eleve": self.projet_eleve,
        }

    @classmethod
    def from_dict(cls, donnees):
        profil = cls(donnees["nom"])
        profil.niveaux = donnees.get("niveaux", {})
        profil.exercices_vus = donnees.get("exercices_vus", [])
        profil.historique = donnees.get("historique", [])
        profil.taches = donnees.get("taches", {})
        profil.projet_eleve = donnees.get("projet_eleve", {})
        return profil

    def sauvegarder(self, chemin):
        Path(chemin).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def charger(cls, chemin, nom_defaut="eleve"):
        chemin = Path(chemin)
        if not chemin.exists():
            return cls(nom_defaut)
        return cls.from_dict(json.loads(chemin.read_text(encoding="utf-8")))


def charger_exercices(chemin=CHEMIN_EXERCICES):
    donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
    if isinstance(donnees, dict):
        donnees = donnees.get("exercices", [])
    # Un exercice sans etoile est traite comme une application directe.
    for ex in donnees:
        # Le JSON extrait utilise « identifiant » ; la logique du profil utilise « id ».
        if "id" not in ex:
            ex["id"] = ex["identifiant"]
        if not ex.get("difficulte"):
            ex["difficulte"] = 1
    return donnees


def choisir_exercice(profil, chapitre, exercices, exercices_presentes=()):
    """Retourne l'exercice non vu dont la difficulte colle le mieux au niveau."""
    candidats = [
        ex for ex in exercices
        if ex.get("chapitre") == chapitre
        and ex.get("id") not in profil.exercices_vus
        and ex.get("id") not in exercices_presentes
    ]
    if not candidats:
        return None

    cible = profil.niveau(chapitre)
    return min(candidats, key=lambda ex: (
        abs(ex["difficulte"] - cible), ex["difficulte"] < cible,
    ))
