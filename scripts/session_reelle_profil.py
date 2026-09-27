"""Session HTTP interactive avec les vrais services, sans mock.

python -m scripts.session_reelle_profil
Saisir les réponses, puis /reconnexion et /fin. Les fichiers du compte
et les échanges réels restent sous reports/session-reelle-<date>/.
"""
import html
import json
import logging
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread

import httpx
from werkzeug.serving import make_server
from app.web import create_app


def main():
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("app.agent").setLevel(logging.DEBUG)
    dossier = Path("reports") / ("session-reelle-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    dossier.mkdir(parents=True)
    app = create_app({"UTILISATEURS_PATH": dossier / "utilisateurs.json", "PROFILS_DIR": dossier / "profils"})
    serveur = make_server("127.0.0.1", 0, app)
    Thread(target=serveur.serve_forever, daemon=True).start()
    trace = []
    with httpx.Client(base_url=f"http://127.0.0.1:{serveur.server_port}", follow_redirects=True, timeout=600) as client:
        page = client.get("/inscription").text

        def poster(url, **champs):
            nonlocal page
            tokens = dict(re.findall(r'name="(csrf|tour)" value="([^"]+)"', page))
            response = client.post(url, data={**tokens, **champs})
            page = response.text
            messages = [html.unescape(m) for m in re.findall(r'<div class="math prose">(.*?)</div>', page, re.S)]
            trace.append({"route": url, "action": champs.get("action"), "message": champs.get("message"),
                          "statut": response.status_code, "dialogue": messages})
            (dossier / "session.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
            response.raise_for_status()
            if messages:
                print(messages[-1], flush=True)

        password = secrets.token_urlsafe(24)
        poster("/inscription", identifiant="verification-profil", mot_de_passe=password)
        poster("/", action="chapitre", chapitre="0")
        print(f"PROFIL: {dossier / 'profils/verification-profil.json'}", flush=True)
        while True:
            message = input("Réponse (/reconnexion, /fin) : ")
            if message == "/fin":
                break
            if message == "/reconnexion":
                poster("/deconnexion")
                poster("/connexion", identifiant="verification-profil", mot_de_passe=password)
                poster("/", action="chapitre", chapitre="0")
            else:
                poster("/", message=message)
    serveur.shutdown()
    print((dossier / "profils/verification-profil.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
