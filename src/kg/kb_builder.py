"""
Step 1 - Build Initial Private KB in RDF
Course: Web Mining & Semantics - ESILV

Loads extracted_knowledge.csv, keeps the top 10,000 most frequent triplets,
converts to RDF using rdflib with a private namespace, defines ontology
classes and properties, and saves as private_kb.ttl.
"""

import csv
import re
from collections import Counter

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, XSD, URIRef


# ── Configuration ──────────────────────────────────────────────────────────────

INPUT_FILE = "../../data/extracted_knowledge.csv"
OUTPUT_FILE = "../../kg_artifacts/private_kb.ttl"
TOP_K = 10000

# ── Namespaces ─────────────────────────────────────────────────────────────────

EX = Namespace("http://cinema-kb.org/")
SCHEMA = Namespace("http://schema.org/")


# ── Helpers ────────────────────────────────────────────────────────────────────

def to_uri_name(text: str) -> str:
    """Convert a text string to a valid URI-safe name (PascalCase for entities)."""
    # Remove parentheses content, strip
    text = re.sub(r"\([^)]*\)", "", text).strip()
    # Replace non-alphanumeric with spaces, then PascalCase
    words = re.sub(r"[^a-zA-Z0-9]", " ", text).split()
    return "".join(w.capitalize() for w in words if w)


def to_predicate_name(relation: str) -> str:
    """Convert a relation string to camelCase predicate."""
    words = re.sub(r"[^a-zA-Z0-9]", " ", relation).split()
    if not words:
        return "relatedTo"
    result = words[0].lower() + "".join(w.capitalize() for w in words[1:])
    return result


# ── Predicate normalization mapping ───────────────────────────────────────────

PREDICATE_MAP = {
    # Direction / creation
    "direct": "directedBy",
    "directed": "directedBy",
    "direct by": "directedBy",
    "directed by": "directedBy",
    "direct based": "directedBy",
    # Starring / acting
    "star": "starring",
    "starring": "starring",
    "star in": "starring",
    "star based": "starring",
    "feature": "featuring",
    "reprise": "starring",
    # Awards
    "win": "wonAward",
    "won": "wonAward",
    "award": "wonAward",
    "honor": "honoredBy",
    "honor during": "honoredBy",
    "nominate": "nominatedFor",
    "nominated": "nominatedFor",
    "receive": "receivedAward",
    "select for": "selectedFor",
    "compete with for": "competedFor",
    # Production / writing
    "produce": "producedBy",
    "produced": "producedBy",
    "produce by": "producedBy",
    "write": "writtenBy",
    "novel by": "basedOnWorkBy",
    "base on": "basedOn",
    "adopt": "adaptedFrom",
    # Release / dates
    "release": "releasedIn",
    "released": "releasedIn",
    "release in": "releasedIn",
    # Location / origin
    "bear": "bornIn",
    "bear in": "bornIn",
    "born": "bornIn",
    "locate": "locatedIn",
    "locate in": "locatedIn",
    "base": "basedIn",
    "base in": "basedIn",
    # Roles / performance
    "play": "playedRole",
    "portray": "portrayed",
    "compose": "composedFor",
    "found": "foundedBy",
    "establish": "establishedIn",
    # Death
    "die": "diedIn",
    # General
    "include": "includes",
    "have": "hasAssociation",
    "become": "became",
    "say": "statedBy",
    "take": "involvedIn",
    "take in": "tookPlaceIn",
    "see": "relatedTo",
    "lose": "lostTo",
    "lose at": "lostAt",
    "read": "relatedTo",
    "ask for at": "requestedAt",
    "dress": "relatedTo",
    "dress for": "relatedTo",
    "intimidate as": "relatedTo",
    "retrieve": "relatedTo",
    "need": "relatedTo",
    "stand": "relatedTo",
    "betray": "relatedTo",
    # Co-occurrence
    "co-occurs with": "relatedTo",
    "co-occur with": "relatedTo",
}


def normalize_predicate(relation: str) -> str:
    """Normalize a raw relation string to a clean predicate."""
    rel_lower = relation.lower().strip()
    # Direct match
    if rel_lower in PREDICATE_MAP:
        return PREDICATE_MAP[rel_lower]
    # Partial match
    for key, value in PREDICATE_MAP.items():
        if key in rel_lower:
            return value
    # Fallback: convert to camelCase
    return to_predicate_name(relation)


# ── Entity type to ontology class ─────────────────────────────────────────────

TYPE_TO_CLASS = {
    "PERSON": "Person",
    "ORG": "Organization",
    "GPE": "Place",
    "DATE": "Date",
    "WORK_OF_ART": "CreativeWork",
}

# Cinema-specific subclasses
CINEMA_CLASSES = {
    "Film": "CreativeWork",
    "Director": "Person",
    "Actor": "Person",
    "Award": "CreativeWork",
    "Festival": "Organization",
}


# ── Main ───────────────────────────────────────────────────────────────────────

def build_kb():
    print("=" * 60)
    print("  Step 1: Build Initial Private KB in RDF")
    print("=" * 60)

    # Load CSV
    print("\n[*] Loading extracted_knowledge.csv...")
    rows = []
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    print(f"[+] Loaded {len(rows)} raw triplets.")

    # Group rows by normalized predicate
    from collections import defaultdict
    by_predicate = defaultdict(list)
    for row in rows:
        pred = normalize_predicate(row["relation"])
        by_predicate[pred].append(row)

    # Show predicate distribution
    print(f"[*] Predicate distribution:")
    for pred, pred_rows in sorted(by_predicate.items(), key=lambda x: -len(x[1]))[:15]:
        print(f"    {pred}: {len(pred_rows)}")

    # Select top K with diversity: allocate proportionally but cap per predicate
    # to ensure variety. Max 2000 per predicate, fill rest proportionally.
    MAX_PER_PRED = 700
    top_rows = []
    remaining_budget = TOP_K

    # First pass: take up to MAX_PER_PRED from each predicate (sorted by frequency)
    freq = Counter()
    for row in rows:
        key = (row["subject"].strip(), row["object"].strip(), normalize_predicate(row["relation"]))
        freq[key] += 1

    for pred in sorted(by_predicate.keys(), key=lambda p: -len(by_predicate[p])):
        pred_rows = by_predicate[pred]
        # Score by (subject, object, pred) frequency and deduplicate
        seen_keys = set()
        scored = []
        for row in pred_rows:
            key = (row["subject"].strip(), row["object"].strip(), normalize_predicate(row["relation"]))
            if key not in seen_keys:
                seen_keys.add(key)
                scored.append((freq[key], row))
        scored.sort(key=lambda x: -x[0])
        take = min(MAX_PER_PRED, len(scored), remaining_budget)
        top_rows.extend(r for _, r in scored[:take])
        remaining_budget -= take
        if remaining_budget <= 0:
            break

    print(f"[+] Kept {len(top_rows)} triplets with predicate diversity.")

    # Build RDF graph
    print("[*] Building RDF graph...")
    g = Graph()
    g.bind("ex", EX)
    g.bind("schema", SCHEMA)
    g.bind("owl", OWL)

    # ── Define ontology classes ──
    for cls in ["Film", "Director", "Actor", "Award", "Festival",
                "Person", "Organization", "Place", "Date", "CreativeWork"]:
        g.add((EX[cls], RDF.type, OWL.Class))
        g.add((EX[cls], RDFS.label, Literal(cls)))

    # Subclass relations
    for subclass, superclass in CINEMA_CLASSES.items():
        g.add((EX[subclass], RDFS.subClassOf, EX[superclass]))

    # ── Define properties with domain/range ──
    property_definitions = {
        "directedBy": ("Film", "Director"),
        "starring": ("Film", "Actor"),
        "wonAward": ("Person", "Award"),
        "nominatedFor": ("Person", "Award"),
        "receivedAward": ("Person", "Award"),
        "producedBy": ("Film", "Person"),
        "releasedIn": ("Film", "Date"),
        "bornIn": ("Person", "Place"),
        "locatedIn": ("Organization", "Place"),
        "basedIn": ("Organization", "Place"),
        "playedRole": ("Actor", "CreativeWork"),
        "relatedTo": ("CreativeWork", "CreativeWork"),
    }
    for prop, (domain, range_) in property_definitions.items():
        prop_uri = EX[prop]
        g.add((prop_uri, RDF.type, OWL.ObjectProperty))
        g.add((prop_uri, RDFS.domain, EX[domain]))
        g.add((prop_uri, RDFS.range, EX[range_]))
        g.add((prop_uri, RDFS.label, Literal(prop)))

    # ── Add triplets ──
    entities = set()
    predicates_used = set()
    triples_added = 0
    seen = set()

    for row in top_rows:
        subj_text = row["subject"].strip()
        obj_text = row["object"].strip()
        pred_text = normalize_predicate(row["relation"])
        subj_type = row.get("subject_type", "")
        obj_type = row.get("object_type", "")

        subj_name = to_uri_name(subj_text)
        obj_name = to_uri_name(obj_text)

        if not subj_name or not obj_name:
            continue

        # Dedup
        triple_key = (subj_name, pred_text, obj_name)
        if triple_key in seen:
            continue
        seen.add(triple_key)

        subj_uri = EX[subj_name]
        obj_uri = EX[obj_name]
        pred_uri = EX[pred_text]

        # Add the triple
        g.add((subj_uri, pred_uri, obj_uri))
        triples_added += 1

        # Add type information
        if subj_type in TYPE_TO_CLASS:
            g.add((subj_uri, RDF.type, EX[TYPE_TO_CLASS[subj_type]]))
        if obj_type in TYPE_TO_CLASS:
            g.add((obj_uri, RDF.type, EX[TYPE_TO_CLASS[obj_type]]))

        # Add labels
        g.add((subj_uri, RDFS.label, Literal(subj_text)))
        g.add((obj_uri, RDFS.label, Literal(obj_text)))

        entities.add(subj_name)
        entities.add(obj_name)
        predicates_used.add(pred_text)

    # Serialize
    print(f"[*] Saving to {OUTPUT_FILE}...")
    g.serialize(destination=OUTPUT_FILE, format="turtle")

    print("\n" + "=" * 60)
    print(f"  Step 1 Complete!")
    print(f"  RDF triples in graph: {len(g)}")
    print(f"  Data triplets added:  {triples_added}")
    print(f"  Unique entities:      {len(entities)}")
    print(f"  Unique predicates:    {len(predicates_used)}")
    print(f"  Predicates used:      {sorted(predicates_used)}")
    print(f"  Output:               {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    build_kb()
