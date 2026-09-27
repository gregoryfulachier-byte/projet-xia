"""Interface locale avec comptes élèves : python -m app.web."""

import asyncio
import os
import secrets
from collections import OrderedDict
from pathlib import Path
from threading import Lock

from flask import Flask, abort, g, redirect, render_template, request, session, url_for
from pipelex_sdk.client import PipelexAPIClient

from app.web.auth import auth
from app.evaluation import evaluer_reponse
from app.agent import Agent
from app.bilan import terminer_colle
from app.chapitres import nom_chapitre
from app.profil import GAINS, Profil, charger_exercices, choisir_exercice

ROOT = Path(__file__).resolve().parents[2]
VERDICTS = {
    "correcte": "Réponse correcte",
    "incorrecte": "Réponse incorrecte",
    "incomplete": "Réponse incomplète",
    "indeterminable": "Évaluation indéterminable",
}


async def corriger(enonce, reponse, corrige):
    async with PipelexAPIClient() as client:
        resultat = await evaluer_reponse(client, enonce, reponse, corrige)
    evaluation = resultat.main_stuff
    if (not isinstance(evaluation, dict)
            or evaluation.get("verdict") not in GAINS
            or not isinstance(evaluation.get("type_erreur"), str)
            or not isinstance(evaluation.get("explication"), str)):
        raise ValueError("Format d'évaluation invalide.")
    return evaluation


def create_app(config=None):
    app = Flask(__name__)
    app.jinja_env.filters["nom_chapitre"] = nom_chapitre
    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
        UTILISATEURS_PATH=ROOT / "data" / "utilisateurs.json",
        PROFILS_DIR=ROOT / "data" / "profils",
        EXERCICES_PATH=ROOT / "data" / "exercices.json",
        MAX_CONTENT_LENGTH=64 * 1024,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if config:
        app.config.update(config)
    app.register_blueprint(auth)
    verrou = Lock()
    conversations = OrderedDict()

    @app.route("/", methods=["GET", "POST"])
    def chat():
        session.setdefault("csrf", secrets.token_urlsafe(32))
        session.setdefault("conversation", secrets.token_urlsafe(32))
        erreur, statut = None, 200
        message = request.form.get("message", "")
        with verrou:
            identifiant = (session["utilisateur"], session["conversation"])
            if identifiant not in conversations:
                conversations[identifiant] = {
                    "agent": Agent(g.profil_path, charger_exercices(app.config["EXERCICES_PATH"])),
                    "tour": secrets.token_urlsafe(24),
                }
                # L'application locale conserve au plus 100 conversations en mémoire.
                if len(conversations) > 100:
                    conversations.popitem(last=False)
            conversations.move_to_end(identifiant)
            etat = conversations[identifiant]
            agent = etat["agent"]
            session["tour"] = etat["tour"]
            choix = {str(i): chapitre for i, chapitre in enumerate(agent.chapitres)}
            selection = request.form.get("action") == "chapitre"
            if request.method == "POST":
                if not secrets.compare_digest(request.form.get("csrf", "").encode(), session["csrf"].encode()):
                    erreur, statut = "La session a expiré. Rechargez la page.", 400
                elif request.form.get("tour") != session["tour"]:
                    erreur, statut = "La conversation a changé. Vérifiez les messages puis réessayez.", 409
                elif request.form.get("action") == "nouvelle":
                    conversations.pop(identifiant)
                    session["conversation"] = secrets.token_urlsafe(32)
                    return redirect(url_for("chat"))
                elif request.form.get("action") == "terminer":
                    try:
                        bilan = terminer_colle(g.profil_path, agent)
                    except ValueError as exc:
                        erreur, statut = str(exc), 400
                    except OSError:
                        app.logger.exception("Échec de sauvegarde du bilan")
                        erreur, statut = "Le bilan n’a pas pu être sauvegardé. Réessayez.", 503
                    else:
                        return redirect(url_for("voir_bilan", session_id=bilan["session_id"]))
                elif agent.session_colle in Profil.charger(g.profil_path).bilans:
                    return redirect(url_for("voir_bilan", session_id=agent.session_colle))
                elif selection and (agent.chapitre is not None or request.form.get("chapitre") not in choix):
                    erreur, statut = "Choix de chapitre indisponible.", 400
                elif request.form.get("action") and not selection:
                    erreur, statut = "Action indisponible. Écrivez votre demande dans le dialogue.", 400
                elif not selection and agent.chapitre is None:
                    erreur, statut = "Choisissez votre chapitre avec un bouton.", 400
                elif not selection and (not message.strip() or len(message) > 12000):
                    erreur, statut = "Écrivez un message de 1 à 12 000 caractères.", 400
                elif len(agent.messages) >= 120:
                    erreur, statut = "Cette discussion est longue. Commencez une nouvelle discussion pour continuer.", 400
                elif not os.environ.get("OPENAI_API_KEY", "").strip():
                    erreur, statut = "Le chat est indisponible : configurez OPENAI_API_KEY sur le serveur.", 503
                else:
                    try:
                        if selection:
                            agent.selectionner_chapitre(choix[request.form["chapitre"]])
                            message = "Chapitre sélectionné : " + nom_chapitre(agent.chapitre)
                        asyncio.run(agent.repondre(message))
                    except Exception:
                        app.logger.exception("Échec du dialogue avec le tuteur")
                        erreur, statut = "Le tuteur est indisponible. Votre message est conservé ; réessayez.", 502
                    else:
                        etat["tour"] = secrets.token_urlsafe(24)
                        session["tour"] = etat["tour"]
                        return redirect(url_for("chat"))
            return render_template("chat.html", messages=agent.messages, chapitres=list(map(nom_chapitre, agent.chapitres)),
                                   chapitre_selectionne=agent.chapitre is not None,
                                   message=message, erreur=erreur, etape=agent.etape,
                                   bilan_id=agent.session_colle if agent.session_colle in
                                   Profil.charger(g.profil_path).bilans else None), statut

    @app.get("/bilans")
    def bilans():
        with verrou:
            anciens = sorted(Profil.charger(g.profil_path).bilans.values(),
                             key=lambda b: b["fin"], reverse=True)
        return render_template("bilans.html", bilans=anciens)

    @app.get("/bilans/<session_id>")
    def voir_bilan(session_id):
        with verrou:
            bilan = Profil.charger(g.profil_path).bilans.get(session_id)
        if bilan is None:
            abort(404)
        return render_template("bilan.html", bilan=bilan)

    @app.route("/classique", methods=["GET", "POST"])
    def index():
        exercices = charger_exercices(app.config["EXERCICES_PATH"])
        chapitres = list(dict.fromkeys(ex["chapitre"] for ex in exercices))
        chapitre = request.values.get("chapitre", chapitres[0] if chapitres else "")
        session.setdefault("csrf", secrets.token_urlsafe(32))
        erreur, evaluation, reponse, statut = None, None, "", 200
        # Sérialise les corrections et la sauvegarde du profil connecté.
        with verrou:
            profil = Profil.charger(g.profil_path)
            exercice = choisir_exercice(profil, chapitre, exercices)
            if chapitre not in chapitres and chapitres:
                erreur, statut = "Chapitre inconnu. Choisissez un chapitre de la liste.", 400
            elif request.method == "POST":
                reponse = request.form.get("reponse", "")
                if not secrets.compare_digest(request.form.get("csrf", "").encode(), session["csrf"].encode()):
                    erreur, statut = "La session a expiré. Rechargez la page.", 400
                elif exercice is None or request.form.get("exercice_id") != exercice["id"]:
                    erreur, statut = "Cet exercice a déjà été traité ou a changé. Rechargez la page.", 409
                elif len(reponse) > 12000:
                    erreur, statut = "Votre réponse doit contenir au maximum 12 000 caractères.", 400
                elif not os.environ.get("PIPELEX_API_KEY", "").strip():
                    erreur, statut = "La correction est indisponible : configurez PIPELEX_API_KEY sur le serveur.", 503
                else:
                    try:
                        evaluation = asyncio.run(corriger(exercice["enonce"], reponse, exercice.get("corrige", "")))
                        profil.enregistrer(exercice["id"], chapitre,
                                           evaluation["verdict"], evaluation["type_erreur"])
                        profil.sauvegarder(g.profil_path)
                    except Exception:
                        app.logger.exception("Échec de la correction ou de sa sauvegarde")
                        profil = Profil.charger(g.profil_path)
                        evaluation = None
                        erreur, statut = "La correction n’a pas pu être enregistrée. Votre réponse est conservée ; réessayez.", 502
            return render_template(
                "index.html", chapitres=chapitres, chapitre=chapitre,
                profil=profil, exercice=exercice, reponse=reponse,
                evaluation=evaluation, erreur=erreur, verdicts=VERDICTS,
            ), statut

    return app
