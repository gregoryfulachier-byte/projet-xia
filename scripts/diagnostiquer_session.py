"""Session reproductible hors réseau ; les réponses des services sont simulées.

Exécution : python -m scripts.diagnostiquer_session
Le vrai Agent, ses outils et la sauvegarde JSON sont utilisés. Aucun profil
élève n'est modifié ; le résultat est copié depuis un répertoire temporaire.
"""
import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.agent import Agent, CHAPITRE_SERIES
from app.profil import Profil
from app.test_agent import appel, observation, sortie


async def session():
    with tempfile.TemporaryDirectory() as dossier:
        chemin = Path(dossier) / "profil.json"
        agent = Agent(chemin, [{"id": "diagnostic", "chapitre": CHAPITRE_SERIES}])
        sources = {
            "diagnostic-definition": {"type": "définition", "texte": "Une série converge si ses sommes partielles ont une limite finie."},
            "diagnostic-theoreme": {"type": "théorème", "contient_preuve": True,
                                   "texte": "La convergence absolue implique la convergence. Preuve : critère de Cauchy et inégalité triangulaire."},
        }
        recherche = {"chapitre": CHAPITRE_SERIES, "passages": [
            {"identifiant": cle, "page_source": {"pdf": [1]}, **valeur}
            for cle, valeur in sources.items()]}
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock()))

        def preparer(nature, source, enonce):
            return sortie(appels=[appel("preparer_tache", chapitre="Series numeriques",
                                       nature=nature, source=source, enonce=enonce)])

        async def tour(message, reponses):
            client.responses.create.side_effect = reponses
            await agent.repondre(message, client)

        verdict = {"verdict": "correcte", "type_erreur": "aucune", "explication": "Réponse correcte (évaluateur simulé)."}
        decision = {"action": "avancer", "acquise": True, "raison": "Acquisition (décideur simulé)."}
        with (patch("app.agent.recherche_cours", AsyncMock(return_value=recherche)),
              patch.object(agent, "evaluer_reponse", AsyncMock(return_value=verdict)),
              patch("app.colle.decider_suite", AsyncMock(return_value=decision))):
            await tour("Series numeriques", [
                sortie(appels=[appel("chercher_dans_cours", question="Définition et convergence absolue")]),
                preparer("definition", "diagnostic-definition", "Définissez une série convergente."),
                sortie("Définissez une série convergente.")])
            await tour("Ses sommes partielles ont une limite finie.", [
                sortie(appels=[observation(tentative="oui")]),  # fini volontairement absent
                preparer("theoreme", "diagnostic-theoreme", "Que peut-on conclure de la convergence absolue ?"),
                sortie("Correct. Que peut-on conclure de la convergence absolue ?")])
            for _ in range(7):
                await tour("Je cherche encore.", [sortie(appels=[observation()]), sortie("Prenez le temps de formuler votre réponse.")])
            await tour("La convergence absolue implique la convergence.", [
                sortie(appels=[observation(tentative="oui")]),
                preparer("demonstration", "diagnostic-theoreme", "Démontrez cette implication avec le critère de Cauchy."),
                sortie("Correct. Démontrez cette implication avec le critère de Cauchy.")])
        profil = Profil.charger(chemin).to_dict()
        nouveau = Agent(chemin, agent.exercices)
        return profil, {"simulation": True, "echanges": len(agent.messages) // 2,
                        "taches": len(profil["taches"]),
                        "evaluations": sum(len(t["evaluations"]) for t in profil["taches"].values()),
                        "acquis_nouvelle_session": nouveau.taches_validees(), "dialogue": agent.messages}


if __name__ == "__main__":
    profil, trace = asyncio.run(session())
    destination = Path("reports/diagnostic-profil")
    destination.mkdir(parents=True, exist_ok=True)
    for nom, contenu in (("profil-apres.json", profil), ("session.json", trace)):
        (destination / nom).write_text(json.dumps(contenu, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: trace[k] for k in ("simulation", "echanges", "taches", "evaluations")}, indent=2))
    print(destination / "profil-apres.json")
