"""État de la colle et transitions gardées côté serveur."""
import json
import re
from pathlib import Path
from uuid import uuid4

from pipelex_sdk.client import PipelexAPIClient
from app.profil import Profil
from app.chapitres import chapitre_catalogue, donnees_publiques
from app.generated.progression_colle.models import Performance, Decision

ETAPES = ("cours", "demonstration", "applications", "exercices")
BUNDLE = Path(__file__).resolve().parents[1] / "methods/progression_colle"


async def decider_suite(performance):
    performance = Performance.model_validate(performance, strict=True)
    async with PipelexAPIClient() as client:
        resultat = await client.start_and_wait(
            pipe_code="progression_colle.decider_suite",
            mthds_contents=[p.read_text(encoding="utf-8") for p in sorted(BUNDLE.rglob("*.mthds"))],
            inputs={"performance": performance.model_dump()})
    return Decision.model_validate(resultat.main_stuff, strict=True).model_dump()


class Colle:
    def initialiser_colle(self):
        self.etape = "cours"
        self.chapitre = None
        self.tache = None
        self.sources = {}
        self.tour_colle = 0
        self.tour_observe = -1
        self.nouvelle_tache_autorisee = True
        self.session_colle = uuid4().hex

    def etat_colle(self):
        return donnees_publiques({"chapitre": self.chapitre, "etape": self.etape,
                "tache": self.tache, "nouvelle_tache_autorisee": self.nouvelle_tache_autorisee,
                "taches_validees": self.taches_validees()})

    def taches_validees(self):
        profil = Profil.charger(self.chemin_profil)
        return [{k: t.get(k) for k in ("etape", "nature", "source", "enonce")}
                for t in profil.taches.values()
                if t.get("chapitre") == self.chapitre
                and (t.get("acquise") or t.get("cloturee")) and t.get("evaluations")
                and t["evaluations"][-1]["verdict"] == "correcte"]

    def reprendre_progression(self):
        """Reconstituer l'étape depuis les acquis durables du chapitre."""
        acquis = self.taches_validees()
        natures = {t["nature"] for t in acquis if t["etape"] == "cours"}
        self.etape = "cours"
        if {"definition", "theoreme"} <= natures:
            self.etape = "demonstration"
            if any(t["etape"] == "demonstration" for t in acquis):
                self.etape = "applications"
                if any(t["etape"] == "applications" for t in acquis):
                    self.etape = "exercices"

    def sauver_tache(self):
        profil = Profil.charger(self.chemin_profil)
        profil.taches[self.tache["id"]] = json.loads(json.dumps(self.tache))
        profil.sauvegarder(self.chemin_profil)

    def ouvrir_tache(self, exercice):
        self.tache = {"id": uuid4().hex, "exercice_id": exercice["id"],
                      "enonce": exercice["enonce"],
                      "session": self.session_colle,
                      "chapitre": self.chapitre, "etape": self.etape,
                      "indices_demandes": 0, "indices_donnes": 0, "tentatives": 0,
                      "rappels_cours": 0, "intuition_initiale": "non_observee",
                      "type_erreur": "non_determinable", "notions": [],
                      "erreur_a_reformuler": False, "erreur_reformulee": False,
                      "blocages": 0, "echanges": [], "evaluations": []}
        self.nouvelle_tache_autorisee = False
        # Le message qui choisit le chapitre ou clôt la tâche précédente n'est
        # pas une tentative sur la question que nous venons de poser.
        self.tour_observe = self.tour_colle
        self.sauver_tache()

    def preparer_tache(self, chapitre, enonce, source, nature):
        chapitre = chapitre_catalogue(chapitre)
        if not self.nouvelle_tache_autorisee:
            raise ValueError("Terminer la tâche active et sa reformulation avant de continuer.")
        if self.etape == "exercices":
            raise ValueError("Utiliser le catalogue à cette étape.")
        if chapitre not in self.chapitres or (self.chapitre and chapitre != self.chapitre):
            raise ValueError("Conserver le chapitre de cette colle.")
        passage = self.sources.get(source)
        if passage is None:
            # Accepter une citation complète, mais conserver l'identifiant
            # canonique pour que changer le libellé ne contourne pas les acquis.
            references = [identifiant for identifiant in self.sources
                          if re.search(r"(?<![\w.])" + re.escape(identifiant) + r"(?![\w.])", source)]
            if len(references) == 1:
                source = references[0]
                passage = self.sources[source]
        if not passage or chapitre_catalogue(passage["chapitre"]) != chapitre:
            raise ValueError("Rechercher d'abord une source de ce chapitre dans le cours indexé.")
        if nature not in ({"definition", "theoreme"} if self.etape == "cours" else {self.etape}):
            raise ValueError("Nature de tâche incompatible avec l'étape " + self.etape
                             + ". Utiliser definition ou theoreme au cours, sinon " + self.etape + ".")
        types = {"definition": {"définition"}, "theoreme": {"théorème", "proposition", "lemme", "corollaire"},
                 "applications": {"exemple"}}
        if nature in types and passage.get("type") not in types[nature]:
            raise ValueError("Choisir une source du type demandé : définition, théorème ou exemple.")
        if nature == "demonstration" and not passage.get("contient_preuve"):
            raise ValueError("Choisir un passage contenant une preuve du cours.")
        if not enonce.strip():
            raise ValueError("La question doit être non vide.")
        if any(
                t["etape"] == self.etape and t["nature"] == nature and t["source"] == source
                for t in self.taches_validees()):
            raise ValueError("Cette tâche est déjà validée dans le profil. Choisir une autre tâche à l'étape autorisée.")
        self.chapitre = chapitre
        self.exercice = {"id": "cours-" + uuid4().hex, "chapitre": chapitre,
                         "enonce": enonce, "corrige": passage["texte"]}
        self.derniere_reponse = None
        self.ouvrir_tache(self.exercice)
        self.tache["source"] = source
        self.tache["page_source"] = passage.get("page_source")
        self.tache["nature"] = nature
        self.sauver_tache()
        return {"enonce": enonce, "source": source, "etape": self.etape}

    async def observer_tour(self, tentative, indice_demande, indice_donne, rappel_cours,
                            intuition, notions, blocage, fini, correction, reformulation):
        if not self.tache or self.tache.get("cloturee"):
            raise ValueError("Aucune tâche active.")
        if self.tour_observe == self.tour_colle:
            return self.etat_colle()
        flags = (tentative, indice_demande, indice_donne, rappel_cours, blocage, fini, correction, reformulation)
        if any(v not in ("oui", "non") for v in flags):
            raise ValueError("Les indicateurs attendent oui ou non.")
        t = self.tache
        for champ, valeur in (("tentatives", tentative), ("indices_demandes", indice_demande),
                              ("indices_donnes", indice_donne), ("rappels_cours", rappel_cours)):
            t[champ] += valeur == "oui"
        if t["intuition_initiale"] == "non_observee" and tentative == "oui":
            t["intuition_initiale"] = intuition
        t["notions"] = list(dict.fromkeys(t["notions"] + [n.strip() for n in notions.split(";") if n.strip()]))
        t["blocages"] = t["blocages"] + 1 if blocage == "oui" else 0
        if reformulation == "oui" and t["erreur_a_reformuler"]:
            t["erreur_a_reformuler"] = False
            t["erreur_reformulee"] = True
        self.enregistrer_message()
        self.tour_observe = self.tour_colle
        self.sauver_tache()
        if correction == "oui" or fini == "oui" or reformulation == "oui" or t["blocages"] >= 2 or (indice_donne == "oui" and t["indices_donnes"] >= 3):
            return await self.evaluer_tache()
        return self.etat_colle()

    def enregistrer_message(self):
        # L'évaluation serveur et l'observation partagent le même message réel.
        if getattr(self, "tour_enregistre", None) != (self.tache["id"], self.tour_colle):
            self.tache["echanges"].append(self.message_courant)
            self.tour_enregistre = (self.tache["id"], self.tour_colle)
            self.sauver_tache()

    async def evaluer_tache(self):
        if not self.tache:
            raise ValueError("Aucune tâche active à évaluer.")
        t = self.tache
        if t.get("cloturee"):
            return {"evaluation": t["evaluations"][-1], "decision": t["decision"], "etat": self.etat_colle()}
        reponse = "\n".join(t["echanges"])
        cle = (reponse, t["erreur_reformulee"])
        if getattr(self, "derniere_transition", None) == (t["id"], cle):
            return {"evaluation": t["evaluations"][-1], "decision": t["decision"], "etat": self.etat_colle()}
        evaluation = await self.evaluer_reponse(self.exercice["enonce"], reponse)
        if not t["evaluations"] or t["evaluations"][-1]["reponse"] != reponse:
            t["evaluations"].append({"reponse": reponse, **evaluation})
            t["type_erreur"] = evaluation["type_erreur"]
            if evaluation["verdict"] == "incorrecte":
                t["erreur_a_reformuler"] = True
                t["erreur_reformulee"] = False
            self.sauver_tache()
        if t["etape"] != "exercices" and evaluation["verdict"] == "correcte":
            # Une réponse correcte est un acquis, sans décision supplémentaire
            # du tuteur ou du modèle de progression, même si ce dernier tombe.
            t.update(acquise=True, cloturee=True, erreur_a_reformuler=False)
            t["decision"] = {"action": "approfondir", "acquise": True,
                             "raison": "Réponse correcte enregistrée par le serveur."}
            self.sauver_tache()
            if t["etape"] == "cours":
                self.reprendre_progression()
            else:
                self.etape = ETAPES[ETAPES.index(t["etape"]) + 1]
            if self.etape != t["etape"]:
                t["decision"]["action"] = "avancer"
            self.nouvelle_tache_autorisee = True
            self.sauver_tache()
            return {"evaluation": evaluation, "decision": t["decision"], "etat": self.etat_colle()}
        profil = Profil.charger(self.chemin_profil)
        performance = {k: t[k] for k in ("etape", "indices_demandes", "indices_donnes", "tentatives",
                       "rappels_cours", "intuition_initiale", "type_erreur", "notions", "erreur_reformulee")}
        performance.update(verdict=evaluation["verdict"], historique=json.dumps(
            [v for v in profil.taches.values() if v["chapitre"] == self.chapitre], ensure_ascii=False))
        try:
            decision = await decider_suite(performance)
        except Exception:
            # La correction reste disponible même si la seconde méthode échoue.
            # Aucun droit de changer de tâche n'est accordé ; l'appel est réessayable.
            return {"evaluation": evaluation, "erreur": "Décision de progression indisponible ; étape conservée.",
                    "etat": self.etat_colle()}
        if t["erreur_a_reformuler"] or evaluation["verdict"] == "indeterminable":
            decision = {**decision, "action": "approfondir", "acquise": False}
        if decision["action"] == "avancer" and (not decision["acquise"] or evaluation["verdict"] != "correcte"):
            decision = {**decision, "action": "approfondir", "acquise": False}
        if decision["action"] == "avancer" and self.etape == "cours":
            acquis = {v.get("nature") for v in profil.taches.values()
                      if v.get("chapitre") == self.chapitre and v["etape"] == "cours"
                      and v["evaluations"] and v["evaluations"][-1]["verdict"] == "correcte"}
            if not {"definition", "theoreme"} <= acquis:
                decision = {**decision, "action": "approfondir", "acquise": False,
                            "raison": "Vérifier une définition et un énoncé de théorème avant la démonstration."}
        t["decision"] = decision
        self.sauver_tache()
        action = decision["action"]
        if action == "avancer":
            self.etape = ETAPES[min(ETAPES.index(self.etape) + 1, 3)]
        elif action == "revenir_au_cours":
            self.etape = "cours"
        self.nouvelle_tache_autorisee = not t["erreur_a_reformuler"] and (
            action in ("avancer", "revenir_au_cours") or
            (action == "changer_exercice" and self.etape == "exercices") or
            (action == "approfondir" and evaluation["verdict"] == "correcte"))
        t["cloturee"] = self.nouvelle_tache_autorisee
        self.derniere_transition = (t["id"], (reponse, t["erreur_reformulee"]))
        self.sauver_tache()
        return {"evaluation": evaluation, "decision": decision, "etat": self.etat_colle()}
