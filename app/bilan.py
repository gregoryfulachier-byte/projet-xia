"""Bilans de séance fondés sur les évaluations enregistrées, sans appel IA.

Le bilan ne réévalue pas les mathématiques : chaque constat conserve sa preuve
et son verdict d'origine. Une information absente reste explicitement inconnue.
"""
from copy import deepcopy
from datetime import datetime, timezone

from app.profil import Profil


def maintenant():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _point(tache):
    evaluations = tache.get("evaluations", [])
    evaluation = evaluations[-1] if evaluations else None
    echanges = tache.get("echanges", [])
    a_jour = bool(evaluation) and evaluation.get("reponse") == "\n".join(echanges)
    verdict = evaluation.get("verdict") if a_jour else None
    if verdict == "correcte" and (tache.get("acquise") or tache.get("cloturee")):
        statut = "valide"
    elif verdict in ("incorrecte", "incomplete"):
        statut = "a_retravailler"
    elif verdict is not None:
        statut = "a_confirmer"
    else:
        statut = "non_evalue"
    aides = sum(tache.get(k, 0) for k in ("indices_donnes", "rappels_cours"))
    return {
        "tache_id": tache["id"],
        "question": tache.get("enonce", ""),
        "etape": tache.get("etape", ""),
        "nature": tache.get("nature", "exercice"),
        "source": tache.get("source", ""),
        "notions": list(tache.get("notions", [])),
        "statut": statut,
        "verdict": verdict,
        "justification": evaluation.get("explication", "") if a_jour else "",
        "reponses": list(echanges),
        "indices_donnes": tache.get("indices_donnes", 0),
        "indices_demandes": tache.get("indices_demandes", 0),
        "rappels_cours": tache.get("rappels_cours", 0),
        # Zéro indice enregistré ne prouve pas une réussite autonome :
        # l'observateur actuel peut ne pas avoir vu le tour déjà validé.
        "autonomie": "avec_aide" if aides else "non_mesuree",
        "erreur_reformulee": bool(tache.get("erreur_reformulee")),
    }


def terminer_colle(chemin_profil, agent):
    """Archiver une seule fois la séance du compte courant, sans changer ses acquis."""
    profil = Profil.charger(chemin_profil)
    identifiant = agent.session_colle
    if identifiant in profil.bilans:
        return deepcopy(profil.bilans[identifiant])
    if not agent.chapitre:
        raise ValueError("Choisissez un chapitre avant de terminer la khôlle.")
    taches = [t for t in profil.taches.values()
              if t.get("session") == identifiant and t.get("chapitre") == agent.chapitre]
    points = [_point(t) for t in taches]
    compteurs = {statut: sum(p["statut"] == statut for p in points)
                for statut in ("valide", "a_retravailler", "a_confirmer", "non_evalue")}
    priorites = [{"question": p["question"], "notions": p["notions"],
                  "source": p["source"], "statut": p["statut"]}
                 for statut in ("a_retravailler", "a_confirmer", "non_evalue")
                 for p in points if p["statut"] == statut][:5]
    bilan = {
        "version": 1, "session_id": identifiant, "chapitre": agent.chapitre,
        "debut": agent.debut_colle, "fin": maintenant(), "etape_atteinte": agent.etape,
        "points": points, "compteurs": compteurs, "priorites": priorites,
        "messages": [{"role": m["role"], "content": m["content"]}
                     for m in agent.messages if m.get("role") in ("user", "assistant")],
    }
    profil.bilans[identifiant] = bilan
    profil.sauvegarder(chemin_profil)
    return deepcopy(bilan)


def dernier_bilan(profil, chapitre, session_courante=None):
    """Contexte court de la dernière séance terminée du même chapitre."""
    candidats = [b for b in profil.bilans.values()
                 if b.get("chapitre") == chapitre and b.get("session_id") != session_courante]
    if not candidats:
        return None
    bilan = max(candidats, key=lambda b: b["fin"])
    return deepcopy({
        "session_id": bilan["session_id"], "fin": bilan["fin"],
        "priorites": bilan["priorites"],
        "questions_validees": [p["question"] for p in bilan["points"] if p["statut"] == "valide"][:10],
    })
