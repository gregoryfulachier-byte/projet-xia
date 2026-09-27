"""Comptes locaux et authentification par session Flask."""

import json
import re
import secrets
from pathlib import Path
from threading import Lock

from flask import Blueprint, current_app, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.profil import Profil
from app.projet_eleve import CHAMPS, FILIERES, lire_projet

auth = Blueprint("auth", __name__)
verrou_comptes = Lock()
IDENTIFIANT = re.compile(r"[a-z0-9_-]{1,64}")
RESERVES = {"con", "prn", "aux", "nul", "conin$", "conout$"} | {
    f"{prefix}{n}" for prefix in ("com", "lpt") for n in range(1, 10)
}


def charger_comptes():
    chemin = Path(current_app.config["UTILISATEURS_PATH"])
    return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else {}


def csrf_valide():
    return secrets.compare_digest(request.form.get("csrf", "").encode(), session["csrf"].encode())


@auth.before_app_request
def authentifier():
    if request.endpoint == "static":
        return
    session.setdefault("csrf", secrets.token_urlsafe(32))
    identifiant = session.get("utilisateur")
    g.profil_path = None
    if identifiant and IDENTIFIANT.fullmatch(identifiant) and identifiant not in RESERVES:
        with verrou_comptes:
            if identifiant in charger_comptes():
                g.profil_path = Path(current_app.config["PROFILS_DIR"]) / f"{identifiant}.json"
    if g.profil_path is None:
        session.pop("utilisateur", None)
        if request.endpoint not in ("auth.connexion", "auth.inscription", "guide_kholle", "guide_concours", None):
            return redirect(url_for("auth.connexion"))


def formulaire(inscription=False):
    if g.profil_path is not None:
        return redirect(url_for("chat"))
    erreur, statut = None, 200
    identifiant = request.form.get("identifiant", "").strip().lower()
    projet = {cle: request.form.get(cle, "") for cle in CHAMPS}
    projet_valide = {}
    if inscription and request.method == "POST":
        try:
            projet_valide = lire_projet(projet)
        except ValueError as exc:
            erreur, statut = str(exc), 400
    if request.method == "POST":
        mot_de_passe = request.form.get("mot_de_passe", "")
        if not csrf_valide():
            erreur, statut = "La session a expiré. Rechargez la page.", 400
        elif not IDENTIFIANT.fullmatch(identifiant) or identifiant in RESERVES:
            erreur, statut = "Utilisez 1 à 64 lettres sans accent, chiffres, tirets ou underscores (hors noms réservés).", 400
        elif not 1 <= len(mot_de_passe) <= 1024:
            erreur, statut = "Le mot de passe doit contenir entre 1 et 1 024 caractères.", 400
        elif erreur is None:
            with verrou_comptes:
                comptes = charger_comptes()
                if inscription:
                    if identifiant in comptes:
                        erreur, statut = "Cet identifiant est déjà utilisé.", 409
                    else:
                        comptes[identifiant] = {"mot_de_passe": generate_password_hash(mot_de_passe)}
                        dossier = Path(current_app.config["PROFILS_DIR"])
                        dossier.mkdir(parents=True, exist_ok=True)
                        profil = Profil(identifiant)
                        profil.projet_eleve = projet_valide
                        profil.sauvegarder(dossier / f"{identifiant}.json")
                        chemin = Path(current_app.config["UTILISATEURS_PATH"])
                        chemin.parent.mkdir(parents=True, exist_ok=True)
                        temporaire = chemin.with_suffix(".json.tmp")
                        try:
                            temporaire.write_text(json.dumps(comptes, indent=2), encoding="utf-8")
                            temporaire.replace(chemin)
                        finally:
                            temporaire.unlink(missing_ok=True)
                elif identifiant not in comptes or not check_password_hash(comptes[identifiant]["mot_de_passe"], mot_de_passe):
                    erreur, statut = "Identifiant ou mot de passe incorrect.", 401
            if erreur is None:
                session.clear()
                session["utilisateur"] = identifiant
                session["csrf"] = secrets.token_urlsafe(32)
                return redirect(url_for("chat"))
    return render_template("auth.html", inscription=inscription, identifiant=identifiant,
                           erreur=erreur, projet=projet, filieres=FILIERES), statut


@auth.route("/connexion", methods=["GET", "POST"])
def connexion():
    return formulaire()


@auth.route("/inscription", methods=["GET", "POST"])
def inscription():
    return formulaire(inscription=True)


@auth.post("/deconnexion")
def deconnexion():
    if not csrf_valide():
        return "La session a expiré. Rechargez la page.", 400
    session.clear()
    return redirect(url_for("auth.connexion"))
