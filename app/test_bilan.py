"""Tests du bilan : preuves, sauvegarde et reprise, sans API externe."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.bilan import dernier_bilan, terminer_colle
from app.profil import Profil


class BilanTests(unittest.TestCase):
    def setUp(self):
        dossier = TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.path = Path(dossier.name) / "profil.json"
        self.profil = Profil("eleve")
        self.agent = SimpleNamespace(session_colle="seance-1", chapitre="Series",
                                     debut_colle="2026-09-27T10:00:00+00:00", etape="cours",
                                     messages=[{"role": "user", "content": "Ma preuve"},
                                               {"role": "assistant", "content": "Justifiez cette étape."}])

    def tache(self, identifiant="q1", verdict="correcte", **champs):
        tache = {"id": identifiant, "session": self.agent.session_colle,
                 "chapitre": self.agent.chapitre, "enonce": "Une question",
                 "etape": "cours", "nature": "definition", "echanges": ["Ma preuve"],
                 "evaluations": [{"reponse": "Ma preuve", "verdict": verdict,
                                  "explication": "Justification de l'évaluation"}],
                 "acquise": verdict == "correcte", "indices_donnes": 0, "rappels_cours": 0}
        tache.update(champs)
        self.profil.taches[identifiant] = tache
        return tache

    def terminer(self):
        self.profil.sauvegarder(self.path)
        return terminer_colle(self.path, self.agent)

    def test_bilan_separe_les_statuts_et_les_sessions(self):
        self.tache()
        self.tache("q2", "incorrecte", indices_donnes=1)
        self.tache("q3", "indeterminable")
        self.tache("q4", evaluations=[], echanges=[])
        self.tache("autre-session", session="autre")
        self.tache("autre-chapitre", chapitre="Algebre")
        bilan = self.terminer()
        self.assertEqual(bilan["compteurs"], {"valide": 1, "a_retravailler": 1,
                                             "a_confirmer": 1, "non_evalue": 1})
        self.assertEqual(len(bilan["points"]), 4)
        self.assertEqual(bilan["points"][0]["reponses"], ["Ma preuve"])
        self.assertEqual(bilan["messages"], self.agent.messages)

    def test_zero_indice_ne_prouve_pas_autonomie(self):
        self.tache(tentatives=0)
        self.assertEqual(self.terminer()["points"][0]["autonomie"], "non_mesuree")

    def test_aide_et_reformulation_sont_tracees(self):
        self.tache(indices_donnes=2, erreur_reformulee=True)
        point = self.terminer()["points"][0]
        self.assertEqual(point["autonomie"], "avec_aide")
        self.assertEqual(point["indices_donnes"], 2)
        self.assertTrue(point["erreur_reformulee"])

    def test_ancienne_evaluation_ne_valide_pas_une_reponse_plus_recente(self):
        self.tache(echanges=["Ma preuve", "Une nouvelle réponse encore non évaluée"])
        point = self.terminer()["points"][0]
        self.assertEqual(point["statut"], "non_evalue")
        self.assertIsNone(point["verdict"])

    def test_bilan_ne_cloture_pas_une_tache_non_acquise(self):
        self.tache(verdict="incorrecte", cloturee=False)
        self.terminer()
        tache = Profil.charger(self.path).taches["q1"]
        self.assertFalse(tache["acquise"])
        self.assertFalse(tache["cloturee"])

    def test_evaluation_correcte_mais_non_validee_reste_a_confirmer(self):
        self.tache(acquise=False, cloturee=False)
        self.assertEqual(self.terminer()["points"][0]["statut"], "a_confirmer")

    def test_double_fin_est_idempotente_et_archive_independante(self):
        self.tache()
        premier = self.terminer()
        self.agent.messages.append({"role": "user", "content": "Après clôture"})
        second = terminer_colle(self.path, self.agent)
        self.assertEqual(premier, second)
        self.assertEqual(len(Profil.charger(self.path).bilans), 1)
        premier["points"].clear()
        self.assertEqual(len(Profil.charger(self.path).bilans["seance-1"]["points"]), 1)

    def test_sans_chapitre_refuse_mais_aucune_reponse_n_est_pas_echec(self):
        self.profil.sauvegarder(self.path)
        self.agent.chapitre = None
        with self.assertRaises(ValueError):
            terminer_colle(self.path, self.agent)
        self.agent.chapitre = "Series"
        bilan = terminer_colle(self.path, self.agent)
        self.assertEqual(bilan["points"], [])
        self.assertEqual(sum(bilan["compteurs"].values()), 0)

    def test_ancien_profil_charge_et_conserve_ses_champs(self):
        self.path.write_text(json.dumps({"nom": "eleve", "niveaux": {"Series": 3},
                                        "historique": [{"verdict": "correcte"}]}))
        profil = Profil.charger(self.path)
        self.assertEqual(profil.bilans, {})
        profil.sauvegarder(self.path)
        self.assertEqual(Profil.charger(self.path).niveaux, {"Series": 3})

    def test_echec_remplacement_ne_detruit_pas_le_profil(self):
        self.profil.sauvegarder(self.path)
        ancien = self.path.read_bytes()
        self.profil.bilans = {"test": {"points": []}}
        with patch("pathlib.Path.replace", side_effect=OSError("disque")):
            with self.assertRaises(OSError):
                self.profil.sauvegarder(self.path)
        self.assertEqual(self.path.read_bytes(), ancien)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_reprise_utilise_derniere_seance_du_meme_chapitre(self):
        self.tache(verdict="incorrecte")
        bilan = self.terminer()
        self.profil = Profil.charger(self.path)
        self.profil.bilans["autre"] = {**bilan, "session_id": "autre", "chapitre": "Algebre",
                                       "fin": "2027-01-01T00:00:00+00:00"}
        contexte = dernier_bilan(self.profil, "Series", "nouvelle")
        self.assertEqual(contexte["session_id"], "seance-1")
        self.assertEqual(contexte["priorites"][0]["statut"], "a_retravailler")
        self.assertNotIn("messages", contexte)
        self.assertIsNone(dernier_bilan(self.profil, "Series", "seance-1"))


if __name__ == "__main__":
    unittest.main()
