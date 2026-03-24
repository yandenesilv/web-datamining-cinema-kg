"""
Cours 5 - Step 2, 3, 4: Train KGE Models + Evaluate Link Prediction
Course: Web Mining & Semantics - ESILV

Ce script fait :
1. Charge les splits train/valid/test
2. Entraine 2 modeles : TransE et ComplEx (avec PyKEEN)
3. Evalue en link prediction : MRR, Hits@1, Hits@3, Hits@10
4. Compare les resultats des 2 modeles

Les hyperparametres sont identiques pour une comparaison equitable.
"""

import os
import json
import torch
from pykeen.triples import TriplesFactory
from pykeen.pipeline import pipeline
from pykeen.models import TransE, ComplEx


# -- Configuration ------------------------------------------------------------

DATA_DIR = "../../data"
RESULTS_DIR = "../../results"
RANDOM_SEED = 42

# Hyperparametres (identiques pour les 2 modeles = comparaison equitable)
EMBEDDING_DIM = 100        # Dimension des embeddings
LEARNING_RATE = 0.001      # Taux d'apprentissage
BATCH_SIZE = 256           # Taille du batch
NUM_EPOCHS = 100           # Nombre d'epoques
NEG_SAMPLES = 10           # Nombre d'echantillons negatifs par triple positif

# Modeles a entrainer
MODELS = ["TransE", "ComplEx"]


# -- Chargement des donnees ----------------------------------------------------

def load_triples():
    """Charge les fichiers train/valid/test et cree les TriplesFactory PyKEEN."""
    print("\n[*] Chargement des triples...")

    # Charger le training set en premier (il definit le mapping entites/relations)
    training = TriplesFactory.from_path(
        os.path.join(DATA_DIR, "train.txt"),
        create_inverse_triples=False,
    )

    # Charger valid et test avec le meme mapping que le training
    validation = TriplesFactory.from_path(
        os.path.join(DATA_DIR, "valid.txt"),
        entity_to_id=training.entity_to_id,
        relation_to_id=training.relation_to_id,
    )

    testing = TriplesFactory.from_path(
        os.path.join(DATA_DIR, "test.txt"),
        entity_to_id=training.entity_to_id,
        relation_to_id=training.relation_to_id,
    )

    print(f"  Training :   {training.num_triples} triples")
    print(f"  Validation : {validation.num_triples} triples")
    print(f"  Testing :    {testing.num_triples} triples")
    print(f"  Entites :    {training.num_entities}")
    print(f"  Relations :  {training.num_relations}")

    return training, validation, testing


# -- Entrainement --------------------------------------------------------------

def train_model(model_name, training, validation, testing):
    """
    Entraine un modele KGE avec PyKEEN.

    PyKEEN fait tout automatiquement :
    - Cree le modele (TransE ou ComplEx)
    - Entraine avec negative sampling
    - Evalue en link prediction (MRR, Hits@k)
    """
    print(f"\n{'='*60}")
    print(f"  Entrainement : {model_name}")
    print(f"{'='*60}")
    print(f"  Embedding dim : {EMBEDDING_DIM}")
    print(f"  Learning rate : {LEARNING_RATE}")
    print(f"  Batch size :    {BATCH_SIZE}")
    print(f"  Epochs :        {NUM_EPOCHS}")
    print(f"  Neg samples :   {NEG_SAMPLES}")

    # Lancer le pipeline PyKEEN
    # Le pipeline fait : creation modele + entrainement + evaluation
    result = pipeline(
        model=model_name,
        training=training,
        validation=validation,
        testing=testing,
        model_kwargs={
            "embedding_dim": EMBEDDING_DIM,
        },
        optimizer="Adam",
        optimizer_kwargs={
            "lr": LEARNING_RATE,
        },
        training_kwargs={
            "num_epochs": NUM_EPOCHS,
            "batch_size": BATCH_SIZE,
        },
        negative_sampler_kwargs={
            "num_negs_per_pos": NEG_SAMPLES,
        },
        # Evaluation en link prediction (filtered = on enleve les vrais triples du ranking)
        evaluation_kwargs={
            "batch_size": 128,
        },
        random_seed=RANDOM_SEED,
        device="cpu",  # CPU car on est sur un laptop
    )

    return result


# -- Extraction des metriques --------------------------------------------------

def extract_metrics(result, model_name):
    """Extrait les metriques de link prediction du resultat PyKEEN."""
    metrics = result.metric_results.to_dict()

    # Les metriques cles
    report = {
        "model": model_name,
        "MRR": metrics.get("both.realistic.inverse_harmonic_mean_rank", 0),
        "Hits@1": metrics.get("both.realistic.hits_at_1", 0),
        "Hits@3": metrics.get("both.realistic.hits_at_3", 0),
        "Hits@10": metrics.get("both.realistic.hits_at_10", 0),
        "Head_MRR": metrics.get("head.realistic.inverse_harmonic_mean_rank", 0),
        "Tail_MRR": metrics.get("tail.realistic.inverse_harmonic_mean_rank", 0),
        "Head_Hits@10": metrics.get("head.realistic.hits_at_10", 0),
        "Tail_Hits@10": metrics.get("tail.realistic.hits_at_10", 0),
    }
    return report


def print_report(report):
    """Affiche un rapport lisible des metriques."""
    print(f"\n  Resultats {report['model']}:")
    print(f"  {'Metrique':<20} {'Both':>10} {'Head':>10} {'Tail':>10}")
    print(f"  {'-'*50}")
    print(f"  {'MRR':<20} {report['MRR']:>10.4f} {report['Head_MRR']:>10.4f} {report['Tail_MRR']:>10.4f}")
    print(f"  {'Hits@1':<20} {report['Hits@1']:>10.4f}")
    print(f"  {'Hits@3':<20} {report['Hits@3']:>10.4f}")
    print(f"  {'Hits@10':<20} {report['Hits@10']:>10.4f} {report['Head_Hits@10']:>10.4f} {report['Tail_Hits@10']:>10.4f}")


# -- Main ----------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Steps 2-4: KGE Training & Link Prediction Evaluation")
    print("=" * 60)

    # Creer le dossier de resultats
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Charger les donnees
    training, validation, testing = load_triples()

    # Entrainer et evaluer chaque modele
    all_reports = []
    all_results = {}

    for model_name in MODELS:
        result = train_model(model_name, training, validation, testing)
        report = extract_metrics(result, model_name)
        print_report(report)
        all_reports.append(report)
        all_results[model_name] = result

        # Sauvegarder le modele
        model_dir = os.path.join(RESULTS_DIR, model_name.lower())
        os.makedirs(model_dir, exist_ok=True)
        result.save_to_directory(model_dir)
        print(f"\n  Modele sauvegarde dans : {model_dir}/")

    # -- Tableau comparatif --
    print(f"\n\n{'='*60}")
    print(f"  COMPARAISON DES MODELES")
    print(f"{'='*60}")
    print(f"\n  {'Metrique':<15}", end="")
    for r in all_reports:
        print(f" {r['model']:>12}", end="")
    print()
    print(f"  {'-'*40}")

    for metric in ["MRR", "Hits@1", "Hits@3", "Hits@10"]:
        print(f"  {metric:<15}", end="")
        for r in all_reports:
            print(f" {r[metric]:>12.4f}", end="")
        print()

    # Meilleur modele
    best = max(all_reports, key=lambda r: r["MRR"])
    print(f"\n  >> Meilleur modele (MRR) : {best['model']}")

    # Sauvegarder les resultats en JSON
    with open(os.path.join(RESULTS_DIR, "comparison_results.json"), "w") as f:
        json.dump(all_reports, f, indent=2)

    print(f"\n  Resultats sauvegardes dans {RESULTS_DIR}/comparison_results.json")
    print("=" * 60)

    return all_results, all_reports


if __name__ == "__main__":
    all_results, all_reports = main()
