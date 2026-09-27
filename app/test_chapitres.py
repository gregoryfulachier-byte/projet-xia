"""Reconnaissance tolérante des intitulés, sans substitution de thèmes étrangers."""

import unittest

from app.chapitres import CHAPITRE_SERIES, NOM_SERIES, chapitre_catalogue, nom_chapitre


class ChapitresTests(unittest.TestCase):
    def test_variantes_et_alias_internes(self):
        for nom in ("series", "les series", "series numeriques", "SÉRIES NUMÉRIQUES",
                    "Se\u0301ries nume\u0301riques", " série numérique ", "Les séries numériques !",
                    "series numeriqes", "16 — Séries numériques", CHAPITRE_SERIES):
            with self.subTest(nom=nom):
                self.assertEqual(chapitre_catalogue(nom), CHAPITRE_SERIES)
                self.assertEqual(nom_chapitre(nom), NOM_SERIES)

    def test_demandes_sans_rapport_non_selectionnees(self):
        for nom in ("Topologie", "Algèbre", "Dérivation et intégration", "Bonjour",
                    "", "serres", "nombres complexes", None):
            with self.subTest(nom=nom):
                self.assertEqual(chapitre_catalogue(nom), nom)
                self.assertEqual(nom_chapitre(nom), nom)
