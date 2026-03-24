"""
Cours 5 - Step 8: Comparison between Rule-based and Embedding-based Reasoning
Course: Web Mining & Semantics - ESILV

Ce script fait 2 choses :

PARTIE A - SWRL Rule (avec OWLReady2) :
  On cree une ontologie cinema avec une regle SWRL :
  Film(?f) ^ directedBy(?f, ?p) ^ wonAward(?f, ?a) -> awardWinningDirector(?p)
  (Un realisateur dont le film a gagne un prix est un "realisateur prime")

PARTIE B - Embedding Analogy :
  On verifie si vector(directedBy) + vector(wonAward) ~= vector(awardWinningDirector)
  en utilisant les embeddings TransE entraines.

L'idee : comparer le raisonnement logique (regles SWRL) avec le raisonnement
par analogie vectorielle (embeddings KGE).
"""

import os
import json
import numpy as np
import torch
from sklearn.metrics.pairwise import cosine_similarity


# -- Configuration -------------------------------------------------------------

RESULTS_DIR = "../../results"
DATA_DIR = "../../data"


# ==============================================================================
#   PARTIE A : SWRL Rule with OWLReady2
# ==============================================================================

def run_swrl_reasoning():
    """
    Cree une mini-ontologie cinema et applique une regle SWRL.

    Regle : Film(?f) ^ directedBy(?f, ?p) ^ wonAward(?f, ?a) -> awardWinningDirector(?p)

    En francais : Si un film est realise par une personne ET ce film a gagne un prix,
    alors cette personne est un "realisateur prime" (awardWinningDirector).
    """
    print("=" * 60)
    print("  PARTIE A : SWRL Reasoning with OWLReady2")
    print("=" * 60)

    try:
        from owlready2 import get_ontology, Thing, ObjectProperty, Imp, sync_reasoner_pellet
    except ImportError:
        print("\n  [!] OWLReady2 n'est pas installe.")
        print("  Installation : pip install owlready2")
        print("  On continue avec une simulation...")
        return run_swrl_simulation()

    # Creer l'ontologie
    print("\n[*] Creation de l'ontologie cinema...")
    onto = get_ontology("http://cinema-kb.org/ontology#")

    with onto:
        # Classes
        class Person(Thing): pass
        class Film(Thing): pass
        class Award(Thing): pass
        class AwardWinningDirector(Person): pass

        # Object Properties
        class directedBy(Film >> Person): pass
        class wonAward(Film >> Award): pass

        # Regle SWRL :
        # Film(?f) ^ directedBy(?f, ?p) ^ wonAward(?f, ?a) -> AwardWinningDirector(?p)
        rule = Imp()
        rule.set_as_rule(
            "Film(?f), directedBy(?f, ?p), wonAward(?f, ?a) -> AwardWinningDirector(?p)"
        )
        print(f"  Regle SWRL : Film(?f) ^ directedBy(?f, ?p) ^ wonAward(?f, ?a) -> AwardWinningDirector(?p)")

        # Ajouter des individus (exemples du cinema)
        # Films
        inception = Film("Inception")
        godfather = Film("TheGodfather")
        parasite = Film("Parasite")
        pulp_fiction = Film("PulpFiction")
        dark_knight = Film("TheDarkKnight")

        # Personnes
        nolan = Person("ChristopherNolan")
        coppola = Person("FrancisFordCoppola")
        bong = Person("BongJoonHo")
        tarantino = Person("QuentinTarantino")

        # Prix
        oscar = Award("AcademyAwardBestPicture")
        palme = Award("PalmeDOr")

        # Relations
        inception.directedBy.append(nolan)
        godfather.directedBy.append(coppola)
        parasite.directedBy.append(bong)
        pulp_fiction.directedBy.append(tarantino)
        dark_knight.directedBy.append(nolan)

        # Films primes
        godfather.wonAward.append(oscar)      # The Godfather a gagne l'Oscar
        parasite.wonAward.append(oscar)        # Parasite a gagne l'Oscar
        parasite.wonAward.append(palme)        # Parasite a gagne la Palme d'Or
        pulp_fiction.wonAward.append(palme)    # Pulp Fiction a gagne la Palme d'Or
        # Inception et Dark Knight n'ont PAS gagne Best Picture

    # Avant raisonnement
    print("\n[*] Avant raisonnement SWRL :")
    awd_before = list(onto.AwardWinningDirector.instances())
    print(f"  AwardWinningDirector instances : {[str(x) for x in awd_before]}")
    print(f"  (devrait etre vide)")

    # Raisonnement
    print("\n[*] Execution du raisonnement (Pellet)...")
    try:
        sync_reasoner_pellet(infer_property_values=True, infer_data_property_values=True)

        # Apres raisonnement
        print("\n[*] Apres raisonnement SWRL :")
        awd_after = list(onto.AwardWinningDirector.instances())
        print(f"  AwardWinningDirector instances : {[str(x) for x in awd_after]}")

        # Verification
        print("\n  Resultats attendus :")
        print("    - Coppola  -> AwardWinningDirector (Godfather a gagne l'Oscar)")
        print("    - Bong     -> AwardWinningDirector (Parasite a gagne Oscar + Palme)")
        print("    - Tarantino -> AwardWinningDirector (Pulp Fiction a gagne la Palme)")
        print("    - Nolan    -> PAS AwardWinningDirector (ses films ici n'ont pas gagne Best Picture)")

        inferred = [str(x).split(".")[-1] for x in awd_after]
        return inferred

    except Exception as e:
        print(f"  [!] Erreur Pellet : {e}")
        print("  Pellet necessite Java. Simulation a la place...")
        return run_swrl_simulation()


def run_swrl_simulation():
    """Simulation de la regle SWRL sans reasoner (pour quand Java n'est pas dispo)."""
    print("\n[*] Simulation du raisonnement SWRL (sans reasoner) :")

    # Donnees
    directed_by = {
        "Inception": "Nolan",
        "TheGodfather": "Coppola",
        "Parasite": "Bong",
        "PulpFiction": "Tarantino",
        "TheDarkKnight": "Nolan",
    }
    won_award = {
        "TheGodfather": ["Oscar"],
        "Parasite": ["Oscar", "PalmeDOr"],
        "PulpFiction": ["PalmeDOr"],
    }

    # Appliquer la regle :
    # Film(?f) ^ directedBy(?f, ?p) ^ wonAward(?f, ?a) -> AwardWinningDirector(?p)
    award_winning_directors = set()
    for film, director in directed_by.items():
        if film in won_award:
            award_winning_directors.add(director)
            for award in won_award[film]:
                print(f"  REGLE: {film} directedBy {director} ^ {film} wonAward {award}")
                print(f"         -> {director} est AwardWinningDirector")

    print(f"\n  Resultat : AwardWinningDirector = {sorted(award_winning_directors)}")
    print(f"  Nolan n'est PAS infere (ses films n'ont pas wonAward dans nos donnees)")

    return sorted(award_winning_directors)


# ==============================================================================
#   PARTIE B : Embedding Analogy
# ==============================================================================

def run_embedding_analogy():
    """
    Verifie si les embeddings capturent la meme logique que la regle SWRL.

    L'idee : en TransE, h + r = t, donc les relations sont des vecteurs.
    Si la regle dit : directedBy + wonAward -> awardWinningDirector,
    on verifie si vector(directedBy) + vector(wonAward) est proche d'un
    vecteur de relation existant.

    On teste aussi d'autres compositions de relations.
    """
    print(f"\n\n{'='*60}")
    print(f"  PARTIE B : Embedding Analogy (TransE)")
    print(f"{'='*60}")

    # Charger le modele TransE
    model_path = os.path.join(RESULTS_DIR, "transe", "trained_model.pkl")
    if not os.path.exists(model_path):
        print("  [!] Modele TransE non trouve. Lancez step2 d'abord.")
        return

    model = torch.load(model_path, map_location="cpu", weights_only=False)

    # Charger le mapping des relations
    from pykeen.triples import TriplesFactory
    training_tf = TriplesFactory.from_path(os.path.join(DATA_DIR, "train.txt"))

    # Extraire les embeddings des relations
    rel_repr = model.relation_representations[0]
    rel_embeddings = rel_repr(indices=None).detach().numpy()

    id_to_rel = {v: k for k, v in training_tf.relation_to_id.items()}
    rel_to_id = training_tf.relation_to_id

    # Noms courts
    rel_names = {}
    for idx in range(len(rel_embeddings)):
        full = id_to_rel[idx]
        short = full.split("/")[-1]
        rel_names[idx] = short
        rel_names[short] = idx  # reverse mapping

    print(f"\n[*] Relations disponibles ({len(rel_embeddings)}) :")
    for idx in range(len(rel_embeddings)):
        print(f"    [{idx}] {rel_names[idx]}")

    # -- Test 1 : directedBy + wonAward ~= ? --
    print(f"\n{'='*60}")
    print(f"  Test 1 : vector(P57/directedBy) + vector(P166/wonAward) ~= ?")
    print(f"  (Correspond a la regle SWRL)")
    print(f"{'='*60}")

    # Trouver les relations (P57 = director, P166 = award received)
    r_director = None
    r_award = None
    for idx, name in [(i, rel_names[i]) for i in range(len(rel_embeddings))]:
        if name == "P57" or name == "directedBy":
            r_director = idx
        if name == "P166" or name == "wonAward":
            r_award = idx

    if r_director is not None and r_award is not None:
        composed = rel_embeddings[r_director] + rel_embeddings[r_award]

        # Trouver la relation la plus proche
        sims = cosine_similarity(composed.reshape(1, -1), rel_embeddings)[0]
        top_indices = np.argsort(sims)[::-1][:5]

        print(f"\n  vector({rel_names[r_director]}) + vector({rel_names[r_award]}) est le plus proche de :")
        for rank, idx in enumerate(top_indices):
            print(f"    {rank+1}. {rel_names[idx]:30s} (cosine sim = {sims[idx]:.4f})")
    else:
        print("  Relations P57/directedBy ou P166/wonAward non trouvees")

    # -- Test 2 : Autres compositions interessantes --
    print(f"\n{'='*60}")
    print(f"  Test 2 : Autres compositions de relations")
    print(f"{'='*60}")

    compositions_to_test = [
        ("P57", "P495", "realisateur + pays du film = ?"),       # director + country
        ("P161", "P106", "cast + occupation = ?"),               # cast + occupation
        ("P57", "P19", "realisateur + lieu naissance = ?"),      # director + birthplace
        ("P136", "P495", "genre + pays = ?"),                    # genre + country
    ]

    for r1_name, r2_name, description in compositions_to_test:
        r1_idx = None
        r2_idx = None
        for idx in range(len(rel_embeddings)):
            if rel_names[idx] == r1_name:
                r1_idx = idx
            if rel_names[idx] == r2_name:
                r2_idx = idx

        if r1_idx is not None and r2_idx is not None:
            composed = rel_embeddings[r1_idx] + rel_embeddings[r2_idx]
            sims = cosine_similarity(composed.reshape(1, -1), rel_embeddings)[0]
            best_idx = np.argmax(sims)
            print(f"\n  {description}")
            print(f"  vector({r1_name}) + vector({r2_name}) ~= vector({rel_names[best_idx]}) (sim={sims[best_idx]:.4f})")

    # -- Test 3 : Entity analogy --
    print(f"\n{'='*60}")
    print(f"  Test 3 : Analogie d'entites")
    print(f"  (ex: Nolan - Inception + Godfather ~= Coppola ?)")
    print(f"{'='*60}")

    ent_repr = model.entity_representations[0]
    ent_embeddings = ent_repr(indices=None).detach().numpy()
    ent_to_id = training_tf.entity_to_id
    id_to_ent = {v: k for k, v in ent_to_id.items()}

    # Chercher des entites connues
    test_entities = {
        "Q7836": "Christopher Nolan",
        "Q41148": "Martin Scorsese",
        "Q3772": "Quentin Tarantino",
        "Q25188": "Inception",
        "Q47703": "The Godfather",
        "Q134773": "Parasite",
    }

    found = {}
    for qid, name in test_entities.items():
        for ent_str, idx in ent_to_id.items():
            if qid in ent_str:
                found[qid] = (name, idx)
                break

    print(f"\n  Entites trouvees : {len(found)}/{len(test_entities)}")
    for qid, (name, idx) in found.items():
        print(f"    {qid} -> {name}")

    # Si on a assez d'entites, faire une analogie
    if "Q7836" in found and "Q25188" in found and "Q47703" in found:
        nolan_vec = ent_embeddings[found["Q7836"][1]]
        inception_vec = ent_embeddings[found["Q25188"][1]]
        godfather_vec = ent_embeddings[found["Q47703"][1]]

        # Nolan - Inception + Godfather ~= Coppola ?
        analogy = nolan_vec - inception_vec + godfather_vec
        sims = cosine_similarity(analogy.reshape(1, -1), ent_embeddings)[0]
        top5 = np.argsort(sims)[::-1][:5]

        print(f"\n  Nolan - Inception + Godfather ~= ?")
        for rank, idx in enumerate(top5):
            ent_name = id_to_ent[idx].split("/")[-1]
            print(f"    {rank+1}. {ent_name} (sim={sims[idx]:.4f})")
    else:
        print("\n  Pas assez d'entites pour l'analogie Nolan/Inception/Godfather")

    # -- Conclusion --
    print(f"\n\n{'='*60}")
    print(f"  CONCLUSION : SWRL vs Embedding")
    print(f"{'='*60}")
    print(f"""
  SWRL (regles logiques) :
    - Raisonnement EXACT et DETERMINISTE
    - Si les premisses sont vraies, la conclusion est GARANTIE
    - Limite : ne peut pas decouvrir de nouvelles relations
    - Necessite de definir les regles manuellement

  Embeddings (KGE) :
    - Raisonnement APPROCHE et PROBABILISTE
    - Peut decouvrir des patterns implicites dans les donnees
    - Les compositions de vecteurs captent des analogies
    - Limite : resultats bruits, pas toujours interpretables
    - Depend fortement de la qualite et taille de la KB

  Comparaison :
    - La regle SWRL infere correctement les realisateurs primes
    - Les embeddings capturent des relations mais de facon approximative
    - Les deux approches sont complementaires :
      SWRL pour les regles metier strictes,
      KGE pour la decouverte de connaissances
""")


# -- Main ----------------------------------------------------------------------

def main():
    # Partie A : SWRL
    swrl_results = run_swrl_reasoning()

    # Partie B : Embedding
    run_embedding_analogy()

    print("=" * 60)
    print("  Step 8 Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
