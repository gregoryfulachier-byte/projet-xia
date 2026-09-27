"""Contrôle de la colle, avec évaluations et décisions simulées sans crédit."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.agent import Agent
from app.colle import decider_suite
from app.profil import Profil
from app.test_agent import appel, sortie


class ColleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.path = Path(dossier.name) / "profil.json"
        self.exercices = [{"id": str(i), "chapitre": "17 — Série de réels ou de complexes", "difficulte": i,
                           "enonce": f"Question {i}", "corrige": "Référence privée"} for i in (1, 2, 3)]
        self.agent = Agent(self.path, self.exercices)
        self.agent.sources["def"] = {"chapitre": "17 — Série de réels ou de complexes", "texte": "Définition source", "page_source": 12, "type": "définition"}
        self.agent.sources["th"] = {"chapitre": "17 — Série de réels ou de complexes", "texte": "Théorème et preuve", "type": "théorème", "contient_preuve": True}
        self.agent.sources["ex"] = {"chapitre": "17 — Série de réels ou de complexes", "texte": "Exemple résolu", "type": "exemple"}
        self.verdict = {"verdict": "correcte", "type_erreur": "aucune", "explication": "Justifié."}
        self.decision = {"action": "avancer", "acquise": True, "raison": "Autonomie démontrée."}
        evaluateur = patch.object(self.agent, "evaluer_reponse", AsyncMock(return_value=self.verdict))
        self.eval = evaluateur.start()
        self.addCleanup(evaluateur.stop)
        progression = patch("app.colle.decider_suite", AsyncMock(return_value=self.decision))
        self.suite = progression.start()
        self.addCleanup(progression.stop)

    def preparer(self, nature="definition"):
        source = {"definition": "def", "theoreme": "th", "demonstration": "th", "applications": "ex"}[nature]
        return self.agent.preparer_tache("17 — Série de réels ou de complexes", "Question du cours", source, nature)

    async def observer(self, texte="Ma réponse", **flags):
        self.agent.tour_colle += 1
        self.agent.message_courant = texte
        valeurs = {k: "non" for k in ("tentative", "indice_demande", "indice_donne", "rappel_cours",
                                      "blocage", "fini", "correction", "reformulation")}
        valeurs.update(intuition="pertinente", notions="convergence;hypothèses", **flags)
        return await self.agent.observer_tour(**valeurs)

    async def test_quatre_etapes_et_aucun_saut_meme_sur_demande(self):
        with self.assertRaises(ValueError):
            await self.agent.proposer_exercice("17 — Série de réels ou de complexes")
        self.preparer()
        await self.observer("Passons aux exercices")
        with self.assertRaises(ValueError):
            self.preparer("theoreme")
        await self.observer(tentative="oui", fini="oui")
        self.assertEqual(self.agent.etape, "cours")
        self.preparer("theoreme")
        await self.observer(tentative="oui", fini="oui")
        self.assertEqual(self.agent.etape, "demonstration")
        # Une répétition d'appel ne peut pas sauter la démonstration.
        await self.agent.evaluer_tache()
        self.assertEqual(self.agent.etape, "demonstration")
        self.preparer("demonstration")
        await self.observer(tentative="oui", fini="oui")
        self.assertEqual(self.agent.etape, "applications")
        self.preparer("applications")
        await self.observer(tentative="oui", fini="oui")
        self.assertEqual(self.agent.etape, "exercices")
        with patch("app.agent.verifier_enonce", AsyncMock(return_value="Question 1")):
            exercice = await self.agent.proposer_exercice("17 — Série de réels ou de complexes")
        self.assertEqual(exercice["id"], "2")
        self.assertEqual(len(Profil.charger(self.path).taches), 5)
        self.assertEqual(Profil.charger(self.path).exercices_vus, [])

    async def test_reponse_corrigee_acquise_sans_decision_supplementaire(self):
        self.agent.etape = "applications"
        self.preparer("applications")
        self.eval.return_value = {**self.verdict, "verdict": "incorrecte", "type_erreur": "hypothese_ou_domaine"}
        await self.observer(tentative="oui", fini="oui")
        self.assertTrue(self.agent.tache["erreur_a_reformuler"])
        self.assertFalse(self.agent.nouvelle_tache_autorisee)
        self.eval.return_value = self.verdict
        await self.observer("Je veux avancer", fini="oui")
        self.assertEqual(self.agent.etape, "exercices")
        self.assertTrue(self.agent.tache["acquise"])
        self.assertFalse(self.agent.tache["erreur_a_reformuler"])

    async def test_demande_exercice_ne_reouvre_pas_une_question_validee(self):
        self.preparer()
        await self.observer(tentative="oui", fini="oui")
        derniere_tache = self.agent.tache
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=[
            sortie(appels=[appel("preparer_tache", chapitre="Series numeriques",
                                enonce="Définissez une série convergente.", source="def", nature="definition")]),
            sortie(appels=[appel("preparer_tache", chapitre="Series numeriques",
                                enonce="Énoncez le théorème.", source="th", nature="theoreme")]),
            sortie("Énoncez le théorème.")])))

        await self.agent.repondre("Donne-moi un exercice", client)

        etat = json.loads(client.responses.create.call_args_list[0].kwargs["instructions"].split("État de la colle : ")[1])
        self.assertEqual([t["source"] for t in etat["taches_validees"]], ["def"])
        retour = json.loads(next(v["output"] for v in self.agent.historique if v.get("type") == "function_call_output"))
        self.assertIn("déjà validée", retour["erreur"])
        self.assertIsNot(self.agent.tache, derniere_tache)
        self.assertFalse(self.agent.nouvelle_tache_autorisee)
        self.assertEqual(len(Profil.charger(self.path).taches), 2)
        with self.assertRaises(ValueError):
            await self.agent.proposer_exercice("Series numeriques")

    async def test_acquis_persistants_et_preuve_distincte_du_theoreme(self):
        self.preparer()
        await self.observer(tentative="oui", fini="oui")
        self.preparer("theoreme")
        await self.observer(tentative="oui", fini="oui")
        self.preparer("demonstration")  # Même source, autre nature.
        self.suite.return_value = {**self.decision, "action": "revenir_au_cours", "acquise": False}
        await self.observer(tentative="oui", fini="oui")
        self.assertEqual(self.agent.etape, "applications")
        sources = self.agent.sources.copy()
        self.agent.initialiser_colle()
        self.agent.sources = sources
        self.agent.selectionner_chapitre(self.exercices[0]["chapitre"])
        self.agent.reprendre_progression()
        self.assertEqual(len(self.agent.taches_validees()), 3)
        self.assertEqual(self.agent.etape, "applications")
        self.agent.etape = "cours"
        with self.assertRaisesRegex(ValueError, "déjà validée"):
            self.preparer()

    async def test_demande_explicite_sans_tentative_declenche_correction(self):
        self.preparer()
        self.eval.return_value = {**self.verdict, "verdict": "incomplete"}
        result = await self.observer("Corrige-moi maintenant", correction="oui")
        self.eval.assert_awaited_once_with("Question du cours", "Corrige-moi maintenant")
        self.assertIn("evaluation", result)
        self.assertEqual(self.agent.tache["tentatives"], 0)
        self.assertFalse(self.agent.nouvelle_tache_autorisee)

    async def test_blocage_durable_et_plusieurs_indices(self):
        self.preparer()
        self.eval.return_value = {**self.verdict, "verdict": "incomplete"}
        await self.observer("Je bloque", blocage="oui")
        self.eval.assert_not_awaited()
        await self.observer("Toujours bloqué", blocage="oui")
        self.assertEqual(self.eval.await_count, 1)
        for _ in range(3):
            await self.observer("Un indice", indice_demande="oui", indice_donne="oui")
        self.assertEqual(self.eval.await_count, 2)
        self.assertEqual(self.agent.tache["indices_demandes"], 3)
        self.assertEqual(self.agent.tache["tentatives"], 0)

    async def test_signaux_persistes_et_observation_idempotente(self):
        self.preparer()
        await self.observer(tentative="oui", indice_demande="oui", rappel_cours="oui")
        # Un second appel du modèle au même tour ne double pas les compteurs.
        await self.agent.observer_tour(*(["oui"] * 10))
        await self.observer("Nouvelle piste", tentative="oui")
        t = next(iter(Profil.charger(self.path).taches.values()))
        self.assertEqual((t["tentatives"], t["indices_demandes"], t["rappels_cours"]), (2, 1, 1))
        self.assertEqual(t["intuition_initiale"], "pertinente")
        self.assertEqual(t["notions"], ["convergence", "hypothèses"])
        self.assertEqual(t["enonce"], "Question du cours")

    async def test_retour_au_cours_et_changement_exercice(self):
        self.agent.etape = "exercices"
        with patch("app.agent.verifier_enonce", AsyncMock(side_effect=lambda enonce, *args: enonce)):
            await self.agent.proposer_exercice("17 — Série de réels ou de complexes")
            self.suite.return_value = {**self.decision, "action": "changer_exercice", "acquise": False}
            self.eval.return_value = {**self.verdict, "verdict": "incomplete"}
            await self.observer(fini="oui")
            await self.agent.proposer_exercice("17 — Série de réels ou de complexes")
            self.suite.return_value = {**self.decision, "action": "revenir_au_cours", "acquise": False}
            await self.observer(fini="oui")
        self.assertEqual(self.agent.etape, "cours")
        self.assertTrue(self.agent.nouvelle_tache_autorisee)

    async def test_reussite_augmente_difficulte_catalogue(self):
        self.agent.etape = "exercices"
        with patch("app.agent.verifier_enonce", AsyncMock(side_effect=lambda enonce, *args: enonce)):
            premier = await self.agent.proposer_exercice("17 — Série de réels ou de complexes")
            await self.observer(tentative="oui", fini="oui")
            suivant = await self.agent.proposer_exercice("17 — Série de réels ou de complexes")
        self.assertGreater(suivant["difficulte"], premier["difficulte"])

    async def test_decision_en_panne_conserve_correction_et_etape(self):
        self.preparer()
        self.suite.side_effect = RuntimeError("réseau")
        result = await self.observer(correction="oui")
        self.assertEqual(result["evaluation"], self.verdict)
        self.suite.assert_not_awaited()
        self.assertEqual(self.agent.etape, "cours")
        self.assertTrue(self.agent.nouvelle_tache_autorisee)
        self.assertTrue(self.agent.tache["acquise"])
        self.assertEqual(len(Profil.charger(self.path).taches[self.agent.tache["id"]]["evaluations"]), 1)

    async def test_indeterminable_interdit_transition(self):
        self.preparer()
        self.eval.return_value = {**self.verdict, "verdict": "indeterminable"}
        await self.observer(correction="oui")
        self.assertFalse(self.agent.nouvelle_tache_autorisee)
        self.assertEqual(self.agent.etape, "cours")

    async def test_source_absente_ou_autre_chapitre_refusee(self):
        self.agent.sources["def"]["chapitre"] = "Autre"
        with self.assertRaises(ValueError):
            self.preparer()
        self.assertIsNone(self.agent.tache)

    async def test_preuve_et_exemple_doivent_exister_dans_source(self):
        self.agent.etape = "demonstration"
        self.agent.sources["th"]["contient_preuve"] = False
        with self.assertRaises(ValueError):
            self.preparer("demonstration")
        self.agent.etape = "applications"
        with self.assertRaises(ValueError):
            self.agent.preparer_tache("17 — Série de réels ou de complexes", "Inventer un exercice", "th", "applications")
        self.assertIsNone(self.agent.tache)

    async def test_cours_series_relie_au_chapitre_catalogue(self):
        chapitre = "17 — Série de réels ou de complexes"
        self.agent.chapitres = [chapitre]
        self.agent.sources["def"]["chapitre"] = "16 — Séries numériques"
        resultat = self.agent.preparer_tache(chapitre, "Définir une série", "def", "definition")
        self.assertEqual(resultat["etape"], "cours")
        self.assertEqual(self.agent.chapitre, chapitre)

    async def test_nom_public_relie_cours_exercices_et_profil(self):
        source = {"chapitre": "16 — Séries numériques", "passages": [
            {"identifiant": "def", "texte": "Définition source", "type": "définition",
             "page_source": {"pdf": [139]}}]}
        with patch("app.agent.recherche_cours", AsyncMock(return_value=source)):
            resultat = await self.agent.chercher_dans_cours("Série convergente")
        self.assertEqual(resultat["chapitre"], "Series numeriques")
        self.assertEqual(resultat["passages"], source["passages"])
        self.agent.preparer_tache("Series numeriques", "Définir une série", "def", "definition")
        etat = self.agent.etat_colle()
        self.assertEqual(etat["chapitre"], "Series numeriques")
        self.assertEqual(etat["tache"]["chapitre"], "Series numeriques")
        profil = Profil.charger(self.path)
        profil.niveaux[self.agent.chapitre] = 3.2
        profil.sauvegarder(self.path)
        self.assertEqual(self.agent.consulter_niveau("Series numeriques"),
                         {"chapitre": "Series numeriques", "niveau": 3.2})
        self.agent.etape = "exercices"
        self.agent.nouvelle_tache_autorisee = True
        with patch("app.agent.verifier_enonce", AsyncMock(side_effect=lambda texte, *args: texte)):
            exercice = await self.agent.proposer_exercice("Series numeriques")
        self.assertEqual(exercice["chapitre"], "Series numeriques")

    async def test_dialogue_observation_forcee_et_verdict_automatique(self):
        self.preparer()
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=[
            sortie(appels=[appel("preparer_tache", chapitre="Series numeriques", enonce="Énoncez le théorème.",
                                source="th", nature="theoreme")]), sortie("Énoncez le théorème.")])))
        await self.agent.repondre("Ma réponse complète", client)
        self.assertEqual(client.responses.create.call_args_list[0].kwargs["tool_choice"]["name"], "chercher_dans_cours")
        self.eval.assert_awaited_once()
        self.assertEqual(self.agent.messages[0]["content"], "Ma réponse complète")
        self.suite.assert_not_awaited()
        premiere = next(iter(Profil.charger(self.path).taches.values()))
        self.assertTrue(premiere["acquise"])
        self.assertEqual(premiere["echanges"], ["Ma réponse complète"])

    async def test_contrat_pipelex_rejette_decision_malformee(self):
        performance = dict(etape="cours", indices_demandes=0, indices_donnes=0, tentatives=1,
                           rappels_cours=0, intuition_initiale="bonne", notions=[], type_erreur="aucune",
                           verdict="correcte", erreur_reformulee=False, historique="[]")
        with patch("app.colle.PipelexAPIClient") as classe:
            client = AsyncMock()
            classe.return_value.__aenter__.return_value = client
            client.start_and_wait.return_value.main_stuff = {**self.decision, "action": "sauter"}
            with self.assertRaises(ValueError):
                await decider_suite(performance)
            self.assertEqual(client.start_and_wait.call_args.kwargs["inputs"], {"performance": performance})

    async def test_citation_complete_utilise_identifiant_canonique(self):
        self.agent.sources["16.1.5"] = self.agent.sources["def"]
        self.agent.preparer_tache(self.exercices[0]["chapitre"], "Définir la convergence",
                                 "Définition 16.1.5, page PDF 140", "definition")
        await self.observer(fini="oui")
        self.assertEqual(self.agent.tache["source"], "16.1.5")
        with self.assertRaisesRegex(ValueError, "déjà validée"):
            self.agent.preparer_tache(self.exercices[0]["chapitre"], "Une autre formulation",
                                     "16.1.5", "definition")

    async def test_echec_evaluation_interdit_verdict_du_tuteur(self):
        self.preparer()
        self.eval.side_effect = RuntimeError("Service indisponible")
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=sortie("Correct !"))))
        with self.assertRaises(RuntimeError):
            await self.agent.repondre("Ma réponse", client)
        client.responses.create.assert_not_awaited()
        tache = next(iter(Profil.charger(self.path).taches.values()))
        self.assertEqual(tache["evaluations"], [])
        self.assertFalse(tache.get("acquise", False))

    async def test_enregistrement_impose_avant_premiere_question(self):
        self.agent.selectionner_chapitre(self.exercices[0]["chapitre"])
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=[
            sortie("Question non enregistrée"),
            sortie(appels=[appel("preparer_tache", chapitre="Series numeriques", enonce="Question enregistrée",
                                source="def", nature="definition")]), sortie("Question différente inventée par le tuteur")])))
        resultat = await self.agent.repondre("Chapitre sélectionné", client)
        self.assertEqual(resultat, "Question enregistrée")
        self.assertEqual(len(Profil.charger(self.path).taches), 1)
        self.assertNotIn("Question non enregistrée", str(self.agent.messages))


if __name__ == "__main__":
    unittest.main()
