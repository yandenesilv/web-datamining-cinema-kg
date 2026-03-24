"""
Cours 5 - Step 5.2: KB Size Sensitivity Analysis
Course: Web Mining & Semantics - ESILV

Ce script teste l'impact de la taille de la KB sur les embeddings.
On entraine TransE (le plus rapide) sur 3 tailles differentes :
- 20K triples (petit)
- Full dataset (~55K triples)

Et on compare les metriques MRR, Hits@1, Hits@3, Hits@10.
"""

import os
import json
import random
import torch
from pykeen.triples import TriplesFactory
from pykeen.pipeline import pipeline


# -- Configuration -------------------------------------------------------------

DATA_DIR = "../../data"
RESULTS_DIR = "../../results"
RANDOM_SEED = 42

# Hyperparametres (memes que step2 pour comparaison equitable)
EMBEDDING_DIM = 100
LEARNING_RATE = 0.001
BATCH_SIZE = 256
NUM_EPOCHS = 100
NEG_SAMPLES = 10

# Tailles a tester
KB_SIZES = [20000, None]  # None = full dataset


# -- Helpers -------------------------------------------------------------------

def load_triples_from_file(filepath):
    """Charge les triples depuis un fichier TSV."""
    triples = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) == 3:
                triples.append(tuple(parts))
    return triples


def subsample_triples(triples, size, seed=42):
    """
    Sous-echantillonne les triples en gardant la connectivite.
    On garde les triples aleatoirement mais on s'assure que
    chaque entite selectionnee a au moins 1 triple.
    """
    random.seed(seed)
    if size >= len(triples):
        return triples

    # Melanger et prendre les N premiers
    shuffled = list(triples)
    random.shuffle(shuffled)
    return shuffled[:size]


def make_splits(triples, seed=42):
    """Split en 80/10/10 avec verification de leakage."""
    random.seed(seed)
    shuffled = list(triples)
    random.shuffle(shuffled)

    n = len(shuffled)
    n_valid = n // 10
    n_test = n // 10

    # Identifier les triples obligatoires pour le train (entites rares)
    entity_indices = {}
    for i, (s, p, o) in enumerate(shuffled):
        entity_indices.setdefault(s, []).append(i)
        entity_indices.setdefault(o, []).append(i)

    must_train = set()
    for entity, indices in entity_indices.items():
        if len(indices) <= 2:
            must_train.add(indices[0])

    forced = [shuffled[i] for i in must_train]
    remaining = [shuffled[i] for i in range(n) if i not in must_train]

    valid = remaining[:n_valid]
    test = remaining[n_valid:n_valid + n_test]
    train = forced + remaining[n_valid + n_test:]

    # Verifier et corriger le leakage
    train_entities = set()
    for s, p, o in train:
        train_entities.add(s)
        train_entities.add(o)

    new_valid = []
    for t in valid:
        if t[0] not in train_entities or t[2] not in train_entities:
            train.append(t)
        else:
            new_valid.append(t)

    new_test = []
    for t in test:
        if t[0] not in train_entities or t[2] not in train_entities:
            train.append(t)
        else:
            new_test.append(t)

    return train, new_valid, new_test


# -- Main ----------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Step 5.2: KB Size Sensitivity Analysis")
    print("=" * 60)

    # Charger tous les triples (train + valid + test)
    all_triples = []
    for f in ["train.txt", "valid.txt", "test.txt"]:
        all_triples.extend(load_triples_from_file(os.path.join(DATA_DIR, f)))

    print(f"\n[*] Total triples disponibles : {len(all_triples)}")

    results = []

    for size in KB_SIZES:
        size_label = f"{size//1000}K" if size else "Full"
        print(f"\n{'='*60}")
        print(f"  Test avec {size_label} triples")
        print(f"{'='*60}")

        # Sous-echantillonner
        if size:
            subset = subsample_triples(all_triples, size)
        else:
            subset = all_triples

        print(f"  Triples selectionnes : {len(subset)}")

        # Faire les splits
        train, valid, test = make_splits(subset)
        print(f"  Train: {len(train)} | Valid: {len(valid)} | Test: {len(test)}")

        # Creer les TriplesFactory
        # Sauver temporairement les splits
        for name, data in [("_tmp_train.txt", train), ("_tmp_valid.txt", valid), ("_tmp_test.txt", test)]:
            with open(name, "w", encoding="utf-8") as f:
                for s, p, o in data:
                    f.write(f"{s}\t{p}\t{o}\n")

        training_tf = TriplesFactory.from_path("_tmp_train.txt")
        validation_tf = TriplesFactory.from_path(
            "_tmp_valid.txt",
            entity_to_id=training_tf.entity_to_id,
            relation_to_id=training_tf.relation_to_id,
        )
        testing_tf = TriplesFactory.from_path(
            "_tmp_test.txt",
            entity_to_id=training_tf.entity_to_id,
            relation_to_id=training_tf.relation_to_id,
        )

        print(f"  Entites: {training_tf.num_entities} | Relations: {training_tf.num_relations}")

        # Entrainer TransE
        result = pipeline(
            model="TransE",
            training=training_tf,
            validation=validation_tf,
            testing=testing_tf,
            model_kwargs={"embedding_dim": EMBEDDING_DIM},
            optimizer="Adam",
            optimizer_kwargs={"lr": LEARNING_RATE},
            training_kwargs={"num_epochs": NUM_EPOCHS, "batch_size": BATCH_SIZE},
            negative_sampler_kwargs={"num_negs_per_pos": NEG_SAMPLES},
            evaluation_kwargs={"batch_size": 128},
            random_seed=RANDOM_SEED,
            device="cpu",
        )

        # Extraire les metriques (format nested dict de PyKEEN)
        metrics = result.metric_results.to_dict()
        b = metrics["both"]["realistic"]
        report = {
            "size": size_label,
            "num_triples": len(subset),
            "num_entities": training_tf.num_entities,
            "num_relations": training_tf.num_relations,
            "MRR": b.get("inverse_harmonic_mean_rank", 0),
            "Hits@1": b.get("hits_at_1", 0),
            "Hits@3": b.get("hits_at_3", 0),
            "Hits@10": b.get("hits_at_10", 0),
        }
        results.append(report)

        print(f"\n  Resultats {size_label}:")
        print(f"    MRR:     {report['MRR']:.4f}")
        print(f"    Hits@1:  {report['Hits@1']:.4f}")
        print(f"    Hits@3:  {report['Hits@3']:.4f}")
        print(f"    Hits@10: {report['Hits@10']:.4f}")

    # Nettoyer les fichiers temporaires
    for f in ["_tmp_train.txt", "_tmp_valid.txt", "_tmp_test.txt"]:
        if os.path.exists(f):
            os.remove(f)

    # Tableau comparatif
    print(f"\n\n{'='*60}")
    print(f"  COMPARAISON PAR TAILLE DE KB")
    print(f"{'='*60}")
    print(f"\n  {'Taille':<10} {'Triples':>10} {'Entites':>10} {'MRR':>10} {'Hits@1':>10} {'Hits@10':>10}")
    print(f"  {'-'*60}")
    for r in results:
        print(f"  {r['size']:<10} {r['num_triples']:>10} {r['num_entities']:>10} "
              f"{r['MRR']:>10.4f} {r['Hits@1']:>10.4f} {r['Hits@10']:>10.4f}")

    # Sauvegarder
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, "kb_size_sensitivity.json"), "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n  Resultats sauvegardes dans {RESULTS_DIR}/kb_size_sensitivity.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
