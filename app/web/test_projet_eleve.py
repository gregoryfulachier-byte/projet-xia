"""Parcours d'inscription, édition isolée et compatibilité des anciens profils."""

import json
import unittest

from app.profil import Profil
from app.web import test_auth


class ProjetEleveTests(unittest.TestCase):
    setUp = test_auth.AuthTests.setUp
    csrf = test_auth.AuthTests.csrf
    compte = test_auth.AuthTests.compte
    quitter = test_auth.AuthTests.quitter
    def inscrire(self, **projet):
        self.client.get("/inscription")
        return self.client.post("/inscription", data={
            "csrf": self.csrf(self.client), "identifiant": "alice",
            "mot_de_passe": "secret-test", **projet,
        })

    def test_projet_enregistre_et_formulaire_connexion_simple(self):
        self.assertEqual(self.inscrire(prepa="Lycée de test", filiere="MPI",
                                      rang_maths="12", effectif="40", objectifs="Centrale, justifier mes idées").status_code, 302)
        profil = Profil.charger(self.root / "profils/alice.json")
        self.assertEqual(profil.projet_eleve["rang_maths"], 12)
        self.assertEqual(profil.projet_eleve["filiere"], "MPI")
        self.assertEqual(profil.niveaux, {})
        self.quitter(self.client)
        self.assertNotIn(b'name="objectifs"', self.client.get("/connexion").data)

    def test_validation_sans_creer_de_compte(self):
        for valeurs in ({"filiere": "XX"}, {"rang_maths": "2"},
                        {"rang_maths": "41", "effectif": "40"},
                        {"rang_maths": "0", "effectif": "40"},
                        {"rang_maths": "1.5", "effectif": "40"},
                        {"objectifs": "a" * 2001}, {"prepa": "a" * 161}):
            with self.subTest(valeurs=valeurs):
                self.assertEqual(self.inscrire(**valeurs).status_code, 400)
                self.assertFalse((self.root / "utilisateurs.json").exists())

    def test_edition_conserve_acquis_isole_profils_et_verifie_csrf(self):
        self.compte(self.client)
        chemin = self.root / "profils/alice.json"
        profil = Profil.charger(chemin)
        profil.enregistrer("a", "Analyse", "correcte", "aucune")
        profil.taches = {"Analyse": {"validee": True}}
        profil.sauvegarder(chemin)
        bob = self.app.test_client()
        self.compte(bob, "bob")
        avant = chemin.read_bytes()
        self.assertEqual(self.client.post("/mon-profil", data={"csrf": "faux", "filiere": "PC"}).status_code, 400)
        self.assertEqual(chemin.read_bytes(), avant)
        reponse = self.client.post("/mon-profil", data={"csrf": self.csrf(self.client),
                                  "filiere": "PSI", "objectifs": "<script>test</script>",
                                  "utilisateur": "bob"}, follow_redirects=True)
        self.assertEqual(reponse.status_code, 200)
        self.assertIn(b"&lt;script&gt;", reponse.data)
        self.assertNotIn(b"<script>test</script>", reponse.data)
        apres = Profil.charger(chemin)
        self.assertEqual(apres.historique, profil.historique)
        self.assertEqual(apres.taches, profil.taches)
        self.assertEqual(apres.niveaux, profil.niveaux)
        self.assertEqual(apres.projet_eleve["filiere"], "PSI")
        self.assertEqual(Profil.charger(self.root / "profils/bob.json").projet_eleve, {})
        self.client.post("/mon-profil", data={"csrf": self.csrf(self.client)})
        self.assertEqual(Profil.charger(chemin).projet_eleve, {})

    def test_ancien_profil_sans_migration_et_protection(self):
        self.compte(self.client)
        chemin = self.root / "profils/alice.json"
        ancien = json.loads(chemin.read_text())
        ancien.pop("projet_eleve")
        chemin.write_text(json.dumps(ancien))
        self.assertEqual(self.client.get("/mon-profil").status_code, 200)
        self.quitter(self.client)
        for methode in (self.client.get, self.client.post):
            self.assertEqual(methode("/mon-profil").status_code, 302)
        self.assertEqual(self.client.get("/guide-concours").status_code, 200)
