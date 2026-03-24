"""
Cours 5 - Step 1: Data Preparation for Knowledge Graph Embedding
Course: Web Mining & Semantics - ESILV

Ce script fait 4 choses :
1. Charge la KB expandée (expanded_kb.nt)
2. Nettoie : garde seulement les triples entité-relation-entité (pas de labels, dates, métadonnées)
3. Indexe chaque entité et relation avec un numéro unique
4. Split en 80% train / 10% validation / 10% test

Produit : train.txt, valid.txt, test.txt (format TSV : head \t relation \t tail)
"""

import re
import random
from collections import Counter

# ── Configuration ──────────────────────────────────────────────────────────────

INPUT_FILE = "../../kg_artifacts/expanded_kb.nt"
OUTPUT_DIR = "../../data"
RANDOM_SEED = 42

# Prédicats de métadonnées à exclure (ce ne sont pas des "vraies" relations)
META_PREDICATES = {
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",      # rdf:type
    "http://www.w3.org/2000/01/rdf-schema#label",            # rdfs:label
    "http://www.w3.org/2000/01/rdf-schema#subClassOf",       # rdfs:subClassOf
    "http://www.w3.org/2000/01/rdf-schema#domain",           # rdfs:domain
    "http://www.w3.org/2000/01/rdf-schema#range",            # rdfs:range
    "http://www.w3.org/2002/07/owl#sameAs",                  # owl:sameAs
    "http://www.w3.org/2002/07/owl#equivalentProperty",      # owl:equivalentProperty
}


# ── Parsing N-Triples ──────────────────────────────────────────────────────────

def parse_nt_line(line: str):
    """
    Parse une ligne N-Triples.
    Format : <sujet> <prédicat> <objet> .

    Retourne (subject, predicate, object) ou None si la ligne n'est pas valide.
    Un objet entre guillemets ("...") est un littéral → on le rejette.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Regex pour extraire les 3 URIs entre < >
    # On veut : <URI1> <URI2> <URI3> .
    # Si l'objet est un littéral "..." on le rejette
    pattern = r'^<([^>]+)>\s+<([^>]+)>\s+<([^>]+)>\s*\.\s*$'
    match = re.match(pattern, line)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None  # Ligne avec littéral ou format invalide


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Step 1: Data Preparation for KGE")
    print("=" * 60)

    # ── 1. Charger et parser les triples ──
    print("\n[1/4] Chargement de la KB expandée...")
    raw_triples = []
    skipped_literals = 0
    skipped_meta = 0
    skipped_parse = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            parsed = parse_nt_line(line)
            if parsed is None:
                # C'est soit un littéral, soit une ligne vide/commentaire
                if '"' in line:
                    skipped_literals += 1
                else:
                    skipped_parse += 1
                continue

            subj, pred, obj = parsed

            # Exclure les prédicats de métadonnées
            if pred in META_PREDICATES:
                skipped_meta += 1
                continue

            raw_triples.append((subj, pred, obj))

    print(f"  Triples entité-relation-entité : {len(raw_triples)}")
    print(f"  Triples littéraux ignorés :      {skipped_literals}")
    print(f"  Triples métadonnées ignorés :    {skipped_meta}")
    print(f"  Lignes non parsées :             {skipped_parse}")

    # ── 2. Dédupliquer ──
    print("\n[2/4] Déduplication...")
    unique_triples = list(set(raw_triples))
    removed = len(raw_triples) - len(unique_triples)
    print(f"  Doublons supprimés : {removed}")
    print(f"  Triples uniques :    {len(unique_triples)}")

    # ── 3. Indexer entités et relations ──
    print("\n[3/4] Indexation des entités et relations...")

    # Collecter toutes les entités et relations
    entities = set()
    relations = set()
    for s, p, o in unique_triples:
        entities.add(s)
        entities.add(o)
        relations.add(p)

    # Trier pour reproductibilité
    entity_list = sorted(entities)
    relation_list = sorted(relations)

    # Créer les mappings ID → nom
    entity2id = {e: i for i, e in enumerate(entity_list)}
    relation2id = {r: i for i, r in enumerate(relation_list)}

    print(f"  Entités uniques :   {len(entity_list)}")
    print(f"  Relations uniques : {len(relation_list)}")

    # Sauvegarder les mappings
    with open(f"{OUTPUT_DIR}/entity2id.txt", "w", encoding="utf-8") as f:
        f.write(f"{len(entity_list)}\n")
        for entity, idx in entity2id.items():
            f.write(f"{entity}\t{idx}\n")

    with open(f"{OUTPUT_DIR}/relation2id.txt", "w", encoding="utf-8") as f:
        f.write(f"{len(relation_list)}\n")
        for relation, idx in relation2id.items():
            f.write(f"{relation}\t{idx}\n")

    # Afficher les relations et leur fréquence
    rel_counter = Counter(p for _, p, _ in unique_triples)
    print("\n  Distribution des relations :")
    for rel, count in rel_counter.most_common():
        # Afficher juste le nom court de la relation
        short_name = rel.split("/")[-1]
        print(f"    {short_name:40s} {count:>6}")

    # ── 4. Split train/valid/test (80/10/10) ──
    print("\n[4/4] Split train/valid/test (80/10/10)...")

    # Mélanger aléatoirement
    random.seed(RANDOM_SEED)
    random.shuffle(unique_triples)

    # On doit s'assurer que chaque entité apparaît au moins dans train
    # Stratégie : d'abord garantir que chaque entité a au moins 1 triple dans train
    # puis distribuer le reste aléatoirement

    # Compter les apparitions de chaque entité
    entity_triples = {}  # entity → list of triple indices
    for i, (s, p, o) in enumerate(unique_triples):
        entity_triples.setdefault(s, []).append(i)
        entity_triples.setdefault(o, []).append(i)

    # Marquer les triples qui DOIVENT être dans train (pour les entités rares)
    must_train = set()
    for entity, indices in entity_triples.items():
        if len(indices) == 1:
            # Cette entité n'apparaît que dans 1 triple → doit être dans train
            must_train.add(indices[0])
        elif len(indices) == 2:
            # Entité dans 2 triples → au moins 1 dans train
            must_train.add(indices[0])

    print(f"  Triples forcés dans train (entités rares) : {len(must_train)}")

    # Séparer les triples forcés et le reste
    forced_train = [unique_triples[i] for i in must_train]
    remaining = [unique_triples[i] for i in range(len(unique_triples)) if i not in must_train]

    # Calculer combien on a besoin pour chaque split
    total = len(unique_triples)
    n_valid = total // 10  # 10%
    n_test = total // 10   # 10%
    n_train = total - n_valid - n_test  # 80%

    # Prendre valid et test du remaining, le reste va dans train
    n_valid_from_remaining = min(n_valid, len(remaining) // 2)
    n_test_from_remaining = min(n_test, len(remaining) // 2)

    valid_triples = remaining[:n_valid_from_remaining]
    test_triples = remaining[n_valid_from_remaining:n_valid_from_remaining + n_test_from_remaining]
    train_triples = forced_train + remaining[n_valid_from_remaining + n_test_from_remaining:]

    print(f"  Train : {len(train_triples)} ({len(train_triples)/total*100:.1f}%)")
    print(f"  Valid : {len(valid_triples)} ({len(valid_triples)/total*100:.1f}%)")
    print(f"  Test  : {len(test_triples)} ({len(test_triples)/total*100:.1f}%)")

    # Vérifier qu'aucune entité n'est SEULEMENT dans valid/test
    train_entities = set()
    for s, p, o in train_triples:
        train_entities.add(s)
        train_entities.add(o)

    valid_only = set()
    for s, p, o in valid_triples:
        if s not in train_entities:
            valid_only.add(s)
        if o not in train_entities:
            valid_only.add(o)

    test_only = set()
    for s, p, o in test_triples:
        if s not in train_entities:
            test_only.add(s)
        if o not in train_entities:
            test_only.add(o)

    print(f"\n  Vérification leakage :")
    print(f"    Entités seulement dans valid : {len(valid_only)}")
    print(f"    Entités seulement dans test :  {len(test_only)}")

    if valid_only or test_only:
        # Déplacer les triples problématiques vers train
        print("  -> Correction en cours...")
        new_valid = []
        moved = 0
        for t in valid_triples:
            if t[0] in valid_only or t[2] in valid_only:
                train_triples.append(t)
                moved += 1
            else:
                new_valid.append(t)
        valid_triples = new_valid

        new_test = []
        for t in test_triples:
            if t[0] in test_only or t[2] in test_only:
                train_triples.append(t)
                moved += 1
            else:
                new_test.append(t)
        test_triples = new_test
        print(f"  -> {moved} triples deplaces vers train")
        print(f"  Train : {len(train_triples)} | Valid : {len(valid_triples)} | Test : {len(test_triples)}")

    # Sauvegarder les splits au format TSV (head \t relation \t tail)
    def save_split(triples, filename):
        with open(f"{OUTPUT_DIR}/{filename}", "w", encoding="utf-8") as f:
            for s, p, o in triples:
                f.write(f"{s}\t{p}\t{o}\n")

    save_split(train_triples, "train.txt")
    save_split(valid_triples, "valid.txt")
    save_split(test_triples, "test.txt")

    # ── Résumé final ──
    print("\n" + "=" * 60)
    print("  Step 1 Complete!")
    print(f"  Fichiers générés :")
    print(f"    train.txt   ({len(train_triples)} triples)")
    print(f"    valid.txt   ({len(valid_triples)} triples)")
    print(f"    test.txt    ({len(test_triples)} triples)")
    print(f"    entity2id.txt   ({len(entity_list)} entités)")
    print(f"    relation2id.txt ({len(relation_list)} relations)")
    print("=" * 60)


if __name__ == "__main__":
    main()
