"""Tests HTTP du chat, sans services externes."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.web import create_app
from app.chapitres import CHAPITRE_SERIES
from app.profil import Profil


class ChatTests(unittest.TestCase):
    def setUp(self):
        repertoire = tempfile.TemporaryDirectory()
        self.addCleanup(repertoire.cleanup)
        root = Path(repertoire.name)
        exercices = root / "exercices.json"
        exercices.write_text(json.dumps([
            {"id": "17.1", "chapitre": CHAPITRE_SERIES, "enonce": "Question", "difficulte": 1}
        ]), encoding="utf-8")
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test",
                               "PROFILS_DIR": root / "profils", "UTILISATEURS_PATH": root / "utilisateurs.json", "EXERCICES_PATH": exercices})
        self.client = self.app.test_client()
        self.client.get("/inscription")
        with self.client.session_transaction() as session:
            csrf = session["csrf"]
        self.client.post("/inscription", data={"csrf": csrf, "identifiant": "test", "mot_de_passe": "secret"})
        self.client.get("/")
        with self.client.session_transaction() as session:
            self.tokens = {cle: session[cle] for cle in ("csrf", "tour")}

    def envoyer(self, **valeurs):
        return self.client.post("/", data={**self.tokens, "message": "Bonjour", **valeurs})

    def test_accueil_et_ancienne_interface(self):
        self.assertIn(b'/classique', self.client.get("/").data)
        self.assertEqual(self.client.get("/classique").status_code, 200)

    def test_chapitre_series_affiche_sous_un_seul_nom(self):
        chapitre = "17 — Série de réels ou de complexes"
        self.app.config["EXERCICES_PATH"].write_text(json.dumps([
            {"id": "17.1", "chapitre": chapitre, "enonce": "Question", "difficulte": 1}
        ]), encoding="utf-8")
        self.envoyer(action="nouvelle")
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Choisissez votre chapitre", page)
        self.assertIn('name="chapitre" value="0">Series numeriques</button>', page)
        self.assertNotIn('name="message"', page)
        self.assertNotIn(chapitre, page)
        self.assertNotIn("16 —", page)

    @patch("app.agent.Agent.repondre", autospec=True)
    def test_validation_avant_api(self, repondre):
        for valeurs in ({"csrf": "faux"}, {"message": " "}, {"message": "x" * 12001}):
            self.assertEqual(self.envoyer(**valeurs).status_code, 400)
        self.assertEqual(self.envoyer(tour="ancien").status_code, 409)
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            self.assertEqual(self.envoyer(action="chapitre", chapitre="0").status_code, 503)
        for valeurs in ({"message": "Series numeriques"},
                        {"action": "chapitre", "chapitre": "Series numeriques"},
                        {"action": "chapitre", "chapitre": "99"}):
            self.assertEqual(self.envoyer(**valeurs).status_code, 400)
        repondre.assert_not_called()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test"})
    @patch("app.agent.Agent.repondre", autospec=True)
    def test_dialogue_isole_echappement_et_nouvelle_discussion(self, repondre):
        async def parler(agent, message):
            self.assertEqual(agent.chapitre, CHAPITRE_SERIES)
            agent.messages.extend([{"role": "user", "content": message},
                                   {"role": "assistant", "content": "<script>secret</script>"}])
        repondre.side_effect = parler
        ancien_cookie = self.client.get_cookie("session").value
        self.assertEqual(self.envoyer(action="chapitre", chapitre="0", message="Un autre chapitre").status_code, 302)
        self.assertEqual(repondre.call_args.args[1], "Chapitre sélectionné : Series numeriques")
        page = self.client.get("/")
        self.assertIn(b"&lt;script&gt;secret", page.data)
        self.assertNotIn(b"<script>secret", page.data)
        self.assertEqual(self.envoyer().status_code, 409)
        # Même une requête concurrente avec l'ancien cookie doit être refusée.
        self.client.set_cookie("session", ancien_cookie)
        self.assertEqual(self.envoyer().status_code, 409)
        self.assertEqual(repondre.call_count, 1)
        with self.app.test_client() as autre:
            self.assertNotIn(b"secret", autre.get("/").data)
        with self.client.session_transaction() as session:
            self.tokens["tour"] = session["tour"]
        self.assertEqual(self.envoyer(action="nouvelle").status_code, 302)
        self.assertNotIn(b"secret", self.client.get("/").data)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test"})
    @patch("app.agent.Agent.repondre", autospec=True)
    def test_echec_conserve_brouillon(self, repondre):
        self.assertEqual(self.envoyer(action="chapitre", chapitre="0").status_code, 302)
        with self.client.session_transaction() as session:
            self.tokens["tour"] = session["tour"]
        repondre.side_effect = RuntimeError("réseau")
        with self.assertLogs(self.app.logger, level="ERROR"):
            page = self.envoyer(message="Mon raisonnement")
        self.assertEqual(page.status_code, 502)
        self.assertIn(b"Mon raisonnement", page.data)

    def test_correction_uniquement_dans_dialogue(self):
        page = self.client.get("/").data
        self.assertNotIn(b'correction-form', page)
        self.assertNotIn(b'correct-message', page)
        self.assertEqual(self.envoyer(action="corriger").status_code, 400)


if __name__ == "__main__":
    unittest.main()
