"""Informations déclaratives de l'élève, distinctes des acquis observés."""

FILIERES = ("MP", "MPI", "PC", "PSI")
CHAMPS = ("prepa", "filiere", "rang_maths", "effectif", "objectifs")


def lire_projet(donnees):
    """Valide un formulaire complet ; les champs peuvent rester vides."""
    projet = {cle: str(donnees.get(cle, "")).strip() for cle in CHAMPS}
    if len(projet["prepa"]) > 160 or len(projet["objectifs"]) > 2000:
        raise ValueError("Limitez la prépa à 160 caractères et vos objectifs à 2 000 caractères.")
    if projet["filiere"] and projet["filiere"] not in FILIERES:
        raise ValueError("Choisissez MP, MPI, PC ou PSI, ou laissez la filière vide.")
    rang, effectif = projet["rang_maths"], projet["effectif"]
    if rang or effectif:
        if not (rang.isascii() and rang.isdigit() and effectif.isascii() and effectif.isdigit()):
            raise ValueError("Indiquez à la fois votre rang en maths et l’effectif de la classe, en nombres entiers.")
        if not 1 <= int(rang) <= int(effectif) <= 1000:
            raise ValueError("Le rang doit être compris entre 1 et l’effectif de la classe (maximum 1 000).")
        projet.update(rang_maths=int(rang), effectif=int(effectif))
    return {cle: valeur for cle, valeur in projet.items() if valeur != ""}
