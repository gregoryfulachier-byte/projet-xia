"""Tests HTTP des bilans avec de vrais profils temporaires, sans API."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.agent import Agent
from app.chapitres import CHAPITRE_SERIES
from app.profil import Profil
from app.web import create_app


class BilansWebTests(unittest.TestCase):
    def setUp(self):
        dossier = TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.root = Path(dossier.name)
        exercices = self.root / "exercices.json"
        exercices.write_text(json.dumps([{"id": "17.1", "chapitre": CHAPITRE_SERIES,
                                          "enonce": "Question", "difficulte": 1}]))
        self.config = {"TESTING": True, "SECRET_KEY": "test-bilans", "EXERCICES_PATH": exercices,
                       "UTILISATEURS_PATH": self.root / "utilisateurs.json", "PROFILS_DIR": self.root / "profils"}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.inscrire(self.client, "eleve")
        self.profil_path = self.root / "profils/eleve.json"

    def inscrire(self, client, nom):
        client.get("/inscription")
        with client.session_transaction() as session:
            csrf = session["csrf"]
        client.post("/inscription", data={"csrf": csrf, "identifiant": nom, "mot_de_passe": "test"})
        client.get("/")

    def envoyer(self, **data):
        with self.client.session_transaction() as session:
            tokens = {k: session[k] for k in ("csrf", "tour")}
        return self.client.post("/", data={**tokens, **data})

    def preparer(self):
        async def question(agent, message):
            self.agent = agent
            agent.ouvrir_tache({"id": "test", "enonce": "<script>question</script>"})
            agent.tache.update(nature="definition", echanges=["Ma preuve"],
                               evaluations=[{"reponse": "Ma preuve", "verdict": "correcte", "explication": "Preuve vérifiée"}],
                               acquise=True, cloturee=True)
            agent.sauver_tache()
            agent.messages = [{"role": "user", "content": "Ma preuve"},
                              {"role": "assistant", "content": "<script>relance</script>"}]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch.object(Agent, "repondre", autospec=True, side_effect=question):
            self.assertEqual(self.envoyer(action="chapitre", chapitre="0").status_code, 302)

    def test_fin_sans_api_persiste_et_echappe_les_echanges(self):
        self.preparer()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "PIPELEX_API_KEY": ""}), patch.object(Agent, "repondre") as repondre:
            resultat = self.envoyer(action="terminer")
            self.assertEqual(resultat.status_code, 302)
            repondre.assert_not_called()
        page = self.client.get(resultat.location).get_data(as_text=True)
        self.assertIn("Bilan de votre khôlle", page)
        self.assertIn("&lt;script&gt;relance", page)
        self.assertNotIn("<script>relance</script>", page)
        self.assertIn("Preuve vérifiée", page)
        self.assertEqual(len(Profil.charger(self.profil_path).bilans), 1)

    def test_double_clic_ne_duplique_pas_et_reponse_apres_fin_refusee(self):
        self.preparer()
        premier = self.envoyer(action="terminer")
        self.assertEqual(self.envoyer(action="terminer").location, premier.location)
        with patch.object(Agent, "repondre") as repondre:
            self.assertEqual(self.envoyer(message="Encore une réponse").location, premier.location)
            repondre.assert_not_called()
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Cette khôlle est terminée", page)
        self.assertNotIn('id="chat-form"', page)

    def test_csrf_tour_et_session_vide(self):
        self.assertEqual(self.envoyer(action="terminer").status_code, 400)
        self.preparer()
        self.assertEqual(self.envoyer(action="terminer", csrf="faux").status_code, 400)
        self.assertEqual(self.envoyer(action="terminer", tour="ancien").status_code, 409)
        self.assertEqual(Profil.charger(self.profil_path).bilans, {})

    def test_un_autre_compte_ne_peut_pas_lire_le_bilan(self):
        self.preparer()
        url = self.envoyer(action="terminer").location
        autre = self.app.test_client()
        self.inscrire(autre, "autre")
        self.assertEqual(autre.get(url).status_code, 404)
        self.assertIn("Aucun bilan", autre.get("/bilans").get_data(as_text=True))
        self.assertEqual(self.app.test_client().get(url).status_code, 302)

    def test_relecture_apres_redemarrage_et_reconnexion(self):
        self.preparer()
        url = self.envoyer(action="terminer").location
        nouveau = create_app(self.config).test_client()
        nouveau.get("/connexion")
        with nouveau.session_transaction() as session:
            csrf = session["csrf"]
        nouveau.post("/connexion", data={"csrf": csrf, "identifiant": "eleve", "mot_de_passe": "test"})
        self.assertEqual(nouveau.get(url).status_code, 200)
        self.assertIn(url, nouveau.get("/bilans").get_data(as_text=True))

    def test_nouvel_agent_recoit_bilan_sans_modifier_les_acquis(self):
        self.preparer()
        self.envoyer(action="terminer")
        nouveau = Agent(self.profil_path, [{"id": "17.1", "chapitre": CHAPITRE_SERIES}])
        nouveau.chapitre = CHAPITRE_SERIES
        etat = nouveau.etat_colle()
        self.assertEqual(etat["bilan_precedent"]["session_id"], self.agent.session_colle)
        self.assertEqual(len(etat["bilan_precedent"]["questions_validees"]), 1)
        self.assertNotIn("messages", etat["bilan_precedent"])

    def test_echec_sauvegarde_reessayable(self):
        self.preparer()
        with patch("app.bilan.Profil.sauvegarder", side_effect=OSError("disque")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                self.assertEqual(self.envoyer(action="terminer").status_code, 503)
        self.assertEqual(Profil.charger(self.profil_path).bilans, {})
        self.assertEqual(self.envoyer(action="terminer").status_code, 302)

    def test_nouvelle_discussion_redevient_active_sans_perdre_bilan(self):
        self.preparer()
        url = self.envoyer(action="terminer").location
        self.assertEqual(self.envoyer(action="nouvelle").status_code, 302)
        page = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("Cette khôlle est terminée", page)
        self.assertEqual(self.client.get(url).status_code, 200)


if __name__ == "__main__":
    unittest.main()
