"""
Cours 5 - Step 6: Embedding Analysis
Course: Web Mining & Semantics - ESILV

Avec le meilleur modele entraine, ce script fait :
6.1 - Nearest Neighbors : trouve les voisins les plus proches dans l'espace d'embedding
6.2 - Clustering (t-SNE) : reduit en 2D et plot colore par type ontologique
6.3 - Relation Behavior : analyse relations symetriques, inverses, composition
"""

import os
import json
import numpy as np
import torch
import matplotlib
matplotlib.use('Agg')  # Backend sans GUI pour eviter les erreurs
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE
from sklearn.metrics.pairwise import cosine_similarity
from pykeen.triples import TriplesFactory
from pykeen.models import TransE, ComplEx


# -- Configuration -------------------------------------------------------------

RESULTS_DIR = "../../results"
FIGURES_DIR = "../../figures"
DATA_DIR = "../../data"
RANDOM_SEED = 42


# -- Helpers -------------------------------------------------------------------

def load_best_model():
    """Charge le meilleur modele depuis les resultats."""
    # Lire la comparaison pour trouver le meilleur
    comp_file = os.path.join(RESULTS_DIR, "comparison_results.json")
    if os.path.exists(comp_file):
        with open(comp_file, "r") as f:
            reports = json.load(f)
        best = max(reports, key=lambda r: r["MRR"])
        model_name = best["model"].lower()
        print(f"[*] Meilleur modele : {best['model']} (MRR={best['MRR']:.4f})")
    else:
        model_name = "transe"
        print("[*] Pas de comparaison trouvee, utilisation de TransE par defaut")

    # Charger le modele PyKEEN (format pickle)
    model_dir = os.path.join(RESULTS_DIR, model_name)
    model_path = os.path.join(model_dir, "trained_model.pkl")
    model = torch.load(model_path, map_location="cpu", weights_only=False)

    return model, model_name


def get_entity_embeddings(model):
    """Extrait les embeddings des entites du modele."""
    # PyKEEN stocke les embeddings dans model.entity_representations
    entity_repr = model.entity_representations[0]
    embeddings = entity_repr(indices=None).detach().numpy()
    return embeddings


def get_relation_embeddings(model):
    """Extrait les embeddings des relations du modele."""
    relation_repr = model.relation_representations[0]
    embeddings = relation_repr(indices=None).detach().numpy()
    return embeddings


# -- 6.1 Nearest Neighbors ----------------------------------------------------

def analyze_nearest_neighbors(model, training_tf):
    """Trouve les voisins les plus proches pour des entites selectionnees."""
    print(f"\n{'='*60}")
    print(f"  6.1 - Nearest Neighbors Analysis")
    print(f"{'='*60}")

    embeddings = get_entity_embeddings(model)
    id_to_entity = {v: k for k, v in training_tf.entity_to_id.items()}

    # Trouver des entites cinema interessantes
    # On cherche des entites Wikidata connues ou des entites cinema-kb
    interesting_keywords = [
        "Q7836",      # Nolan (Christopher Nolan)
        "Q41148",     # Scorsese
        "Q3772",      # Tarantino
        "Inception",
        "Godfather",
        "Parasite",
        "Q174769",    # Cate Blanchett
        "Q103916",    # Palme d'Or
    ]

    # Trouver les entites qui matchent
    selected = []
    for keyword in interesting_keywords:
        for entity_str, idx in training_tf.entity_to_id.items():
            if keyword in entity_str:
                selected.append((entity_str, idx))
                break

    if not selected:
        # Fallback : prendre les 5 entites les plus connectees
        print("  Pas d'entites cinema trouvees, utilisation des plus connectees...")
        # Compter les apparitions
        from collections import Counter
        counter = Counter()
        for s, p, o in training_tf.triples:
            counter[s] += 1
            counter[o] += 1
        top5 = counter.most_common(10)
        for entity_str, count in top5[:5]:
            idx = training_tf.entity_to_id.get(entity_str)
            if idx is not None:
                selected.append((entity_str, idx))

    print(f"\n  Entites selectionnees : {len(selected)}")

    # Calculer la similarite cosinus
    sim_matrix = cosine_similarity(embeddings)

    results = []
    for entity_str, idx in selected:
        # Nom court
        short_name = entity_str.split("/")[-1]

        # Trouver les 5 plus proches (excluant soi-meme)
        similarities = sim_matrix[idx]
        # Mettre soi-meme a -inf
        similarities[idx] = -np.inf
        top_indices = np.argsort(similarities)[-5:][::-1]

        neighbors = []
        for n_idx in top_indices:
            n_entity = id_to_entity[n_idx]
            n_short = n_entity.split("/")[-1]
            n_sim = similarities[n_idx]
            neighbors.append((n_short, n_sim))

        print(f"\n  Voisins de {short_name}:")
        for i, (name, sim) in enumerate(neighbors):
            print(f"    {i+1}. {name} (sim={sim:.4f})")

        results.append({
            "entity": short_name,
            "neighbors": [{"name": n, "similarity": float(s)} for n, s in neighbors]
        })

    return results


# -- 6.2 Clustering (t-SNE) ---------------------------------------------------

def analyze_clustering(model, training_tf):
    """t-SNE 2D avec coloration par type ontologique."""
    print(f"\n{'='*60}")
    print(f"  6.2 - Clustering Analysis (t-SNE)")
    print(f"{'='*60}")

    os.makedirs(FIGURES_DIR, exist_ok=True)

    embeddings = get_entity_embeddings(model)
    id_to_entity = {v: k for k, v in training_tf.entity_to_id.items()}

    print(f"  Nombre d'entites : {len(embeddings)}")

    # Sous-echantillonner pour t-SNE (trop d'entites = trop lent)
    max_entities = 3000
    if len(embeddings) > max_entities:
        # Prendre les entites les plus connectees
        from collections import Counter
        counter = Counter()
        for h, r, t in training_tf.mapped_triples.numpy():
            counter[int(h)] += 1
            counter[int(t)] += 1
        top_ids = [idx for idx, _ in counter.most_common(max_entities)]
        subset_embeddings = embeddings[top_ids]
        subset_entities = [id_to_entity[i] for i in top_ids]
        print(f"  Sous-echantillon : {len(subset_embeddings)} entites (les plus connectees)")
    else:
        subset_embeddings = embeddings
        subset_entities = [id_to_entity[i] for i in range(len(embeddings))]
        top_ids = list(range(len(embeddings)))

    # Determiner le type de chaque entite
    # On regarde les prefixes des URIs et les relations pour deviner le type
    entity_types = []
    for entity_str in subset_entities:
        if "cinema-kb.org" in entity_str:
            entity_types.append("Private KB")
        elif "wikidata.org" in entity_str:
            entity_types.append("Wikidata")
        else:
            entity_types.append("Other")

    # Pour un meilleur clustering, essayons de deviner par les relations
    # On va chercher les types dans le graphe original
    # Charger les types depuis le fichier NT original
    type_map = {}
    nt_file = "../TD1/expanded_kb.nt"
    rdf_type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
    if os.path.exists(nt_file):
        with open(nt_file, "r", encoding="utf-8") as f:
            for line in f:
                if rdf_type in line:
                    import re
                    match = re.match(r'^<([^>]+)>\s+<[^>]+>\s+<([^>]+)>', line)
                    if match:
                        entity = match.group(1)
                        etype = match.group(2).split("/")[-1]
                        type_map[entity] = etype

    # Re-assigner les types avec les vrais types RDF
    refined_types = []
    for entity_str in subset_entities:
        if entity_str in type_map:
            rdf_t = type_map[entity_str]
            if rdf_t in ("Person", "Director", "Actor"):
                refined_types.append("Person")
            elif rdf_t in ("Film", "CreativeWork"):
                refined_types.append("Film/CreativeWork")
            elif rdf_t in ("Organization", "Festival"):
                refined_types.append("Organization")
            elif rdf_t in ("Place"):
                refined_types.append("Place")
            elif rdf_t in ("Date"):
                refined_types.append("Date")
            else:
                refined_types.append("Other")
        else:
            refined_types.append("Unknown")

    # t-SNE
    print("  Calcul t-SNE en cours...")
    tsne = TSNE(n_components=2, random_state=RANDOM_SEED, perplexity=30, max_iter=1000)
    coords = tsne.fit_transform(subset_embeddings)

    # Plot
    print("  Generation du plot...")
    fig, ax = plt.subplots(figsize=(14, 10))

    # Couleurs par type
    type_colors = {
        "Person": "#e74c3c",
        "Film/CreativeWork": "#3498db",
        "Organization": "#2ecc71",
        "Place": "#f39c12",
        "Date": "#9b59b6",
        "Other": "#95a5a6",
        "Unknown": "#bdc3c7",
        "Private KB": "#e67e22",
        "Wikidata": "#1abc9c",
    }

    for etype in set(refined_types):
        mask = [i for i, t in enumerate(refined_types) if t == etype]
        if not mask:
            continue
        color = type_colors.get(etype, "#95a5a6")
        ax.scatter(
            coords[mask, 0], coords[mask, 1],
            c=color, label=f"{etype} ({len(mask)})",
            alpha=0.5, s=8,
        )

    ax.set_title("t-SNE Visualization of Entity Embeddings\n(colored by ontology class)", fontsize=14)
    ax.set_xlabel("t-SNE 1")
    ax.set_ylabel("t-SNE 2")
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "tsne_clustering.png"), dpi=150, bbox_inches='tight')
    print(f"  -> Sauvegarde dans {FIGURES_DIR}/tsne_clustering.png")

    # Statistiques de clustering
    print(f"\n  Distribution des types :")
    from collections import Counter
    type_counts = Counter(refined_types)
    for t, c in type_counts.most_common():
        print(f"    {t:<20} : {c}")


# -- 6.3 Relation Behavior ---------------------------------------------------

def analyze_relations(model, training_tf):
    """Analyse les types de relations : symetriques, inverses, composition."""
    print(f"\n{'='*60}")
    print(f"  6.3 - Relation Behavior Analysis")
    print(f"{'='*60}")

    rel_embeddings = get_relation_embeddings(model)
    id_to_rel = {v: k for k, v in training_tf.relation_to_id.items()}

    # Noms courts des relations
    rel_names = {}
    for idx in range(len(rel_embeddings)):
        full = id_to_rel[idx]
        short = full.split("/")[-1]
        rel_names[idx] = short

    print(f"\n  Relations ({len(rel_embeddings)}):")
    for idx, name in rel_names.items():
        print(f"    [{idx}] {name}")

    # -- Analyse de symetrie --
    # Une relation symetrique : r(a,b) => r(b,a)
    # En TransE : h + r = t, donc si symetrique, r devrait etre ~0
    print(f"\n  -- Analyse de symetrie --")
    print(f"  (Une relation symetrique a un vecteur proche de 0)")
    norms = np.linalg.norm(rel_embeddings, axis=1)
    sorted_by_norm = sorted(range(len(norms)), key=lambda i: norms[i])
    print(f"  Relations les plus symetriques (norme la plus faible) :")
    for idx in sorted_by_norm[:5]:
        print(f"    {rel_names[idx]:30s} norm={norms[idx]:.4f}")
    print(f"  Relations les moins symetriques (norme la plus elevee) :")
    for idx in sorted_by_norm[-5:]:
        print(f"    {rel_names[idx]:30s} norm={norms[idx]:.4f}")

    # -- Analyse de relations inverses --
    # r1 est l'inverse de r2 si r1 ~= -r2
    print(f"\n  -- Analyse de relations inverses --")
    print(f"  (Deux relations inverses ont des vecteurs opposes)")
    inverse_pairs = []
    for i in range(len(rel_embeddings)):
        for j in range(i + 1, len(rel_embeddings)):
            # Cosine similarity entre r_i et -r_j
            cos_sim = cosine_similarity(
                rel_embeddings[i:i+1], -rel_embeddings[j:j+1]
            )[0][0]
            if cos_sim > 0.5:
                inverse_pairs.append((rel_names[i], rel_names[j], cos_sim))

    inverse_pairs.sort(key=lambda x: -x[2])
    if inverse_pairs:
        print(f"  Paires potentiellement inverses :")
        for r1, r2, sim in inverse_pairs[:5]:
            print(f"    {r1} <-> {r2} (cos_sim avec oppose = {sim:.4f})")
    else:
        print(f"  Aucune paire inverse forte detectee")

    # -- Analyse de composition --
    # r1 + r2 ~= r3 (ex: hasFather + hasBrother ~= hasUncle)
    print(f"\n  -- Analyse de composition --")
    print(f"  (r1 + r2 ~= r3 indique une composition)")
    compositions = []
    for i in range(len(rel_embeddings)):
        for j in range(len(rel_embeddings)):
            if i == j:
                continue
            composed = rel_embeddings[i] + rel_embeddings[j]
            for k in range(len(rel_embeddings)):
                if k == i or k == j:
                    continue
                cos_sim = cosine_similarity(
                    composed.reshape(1, -1), rel_embeddings[k:k+1]
                )[0][0]
                if cos_sim > 0.7:
                    compositions.append((rel_names[i], rel_names[j], rel_names[k], cos_sim))

    compositions.sort(key=lambda x: -x[3])
    if compositions:
        print(f"  Compositions detectees :")
        for r1, r2, r3, sim in compositions[:5]:
            print(f"    {r1} + {r2} ~= {r3} (sim={sim:.4f})")
    else:
        print(f"  Aucune composition forte detectee (normal pour un domaine cinema)")


# -- Main ----------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Step 6: Embedding Analysis")
    print("=" * 60)

    # Charger le modele
    model, model_name = load_best_model()

    # Charger les donnees d'entrainement pour le mapping
    training_tf = TriplesFactory.from_path(os.path.join(DATA_DIR, "train.txt"))

    # 6.1 Nearest Neighbors
    nn_results = analyze_nearest_neighbors(model, training_tf)

    # 6.2 t-SNE Clustering
    analyze_clustering(model, training_tf)

    # 6.3 Relation Behavior
    analyze_relations(model, training_tf)

    # Sauvegarder les resultats
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, "embedding_analysis.json"), "w") as f:
        json.dump({"nearest_neighbors": nn_results}, f, indent=2)

    print(f"\n\n{'='*60}")
    print(f"  Step 6 Complete!")
    print(f"  Figures dans : {FIGURES_DIR}/")
    print(f"  Resultats dans : {RESULTS_DIR}/embedding_analysis.json")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
