"""
TD1 - Phase 2: NER & Relation Extraction for Cinema Domain
Course: Web Mining & Semantics - ESILV

Loads crawler_output.jsonl, runs spaCy NER (en_core_web_trf),
extracts entity pairs and relations using dependency parsing,
and saves triplets to extracted_knowledge.csv.
"""

import json
import csv
import spacy

# ── Configuration ──────────────────────────────────────────────────────────────

INPUT_FILE = "../../data/crawler_output.jsonl"
OUTPUT_FILE = "../../data/extracted_knowledge.csv"
TARGET_ENTITY_TYPES = {"PERSON", "ORG", "GPE", "DATE", "WORK_OF_ART"}

# Generic entities to filter out (not domain-specific)
GENERIC_FILTER = {
    "wikipedia", "wikimedia", "isbn", "ref", "http", "https",
    "the", "a", "an", "one", "two", "three", "first", "second",
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "january", "february", "today", "yesterday",
}


# ── Load crawled data ─────────────────────────────────────────────────────────

def load_documents(filepath: str) -> list[dict]:
    """Load documents from JSONL file."""
    docs = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    print(f"[+] Loaded {len(docs)} documents from {filepath}")
    return docs


# ── Entity filtering ──────────────────────────────────────────────────────────

def is_valid_entity(ent) -> bool:
    """Filter out generic or noisy entities."""
    text = ent.text.strip()

    # Too short or too long
    if len(text) < 2 or len(text) > 100:
        return False

    # Mostly digits (except dates)
    if ent.label_ != "DATE" and text.replace(" ", "").isdigit():
        return False

    # Generic words
    if text.lower() in GENERIC_FILTER:
        return False

    # Contains only special characters
    if not any(c.isalnum() for c in text):
        return False

    return True


# ── Relation extraction via dependency parsing ────────────────────────────────

def find_root_verb(token):
    """Walk up the dependency tree to find the governing verb."""
    current = token
    while current.head != current:
        if current.head.pos_ == "VERB":
            return current.head
        current = current.head
    return None


def extract_relation(sent, ent1, ent2):
    """
    Try to find a verb/relation connecting two entities using dependency parsing.
    Looks for nsubj, dobj, pobj patterns.
    """
    # Find tokens that belong to each entity span
    ent1_tokens = [t for t in sent if t.idx >= ent1.start_char and t.idx < ent1.end_char]
    ent2_tokens = [t for t in sent if t.idx >= ent2.start_char and t.idx < ent2.end_char]

    if not ent1_tokens or not ent2_tokens:
        return None

    # Strategy 1: Look for a verb that governs both entities
    for t1 in ent1_tokens:
        verb1 = find_root_verb(t1)
        if verb1:
            for t2 in ent2_tokens:
                verb2 = find_root_verb(t2)
                if verb2 and verb1 == verb2:
                    # Build relation phrase: verb + prepositions
                    relation_parts = [verb1.lemma_]
                    # Check for prepositional children
                    for child in verb1.children:
                        if child.dep_ == "prep" and child.idx < ent2.start_char:
                            relation_parts.append(child.text)
                    return " ".join(relation_parts)

    # Strategy 2: Look for any verb between the two entities
    start = min(ent1.end_char, ent2.end_char)
    end = max(ent1.start_char, ent2.start_char)
    between_tokens = [t for t in sent if t.idx >= start and t.idx < end and t.pos_ == "VERB"]

    if between_tokens:
        verb = between_tokens[0]
        relation_parts = [verb.lemma_]
        for child in verb.children:
            if child.dep_ == "prep":
                relation_parts.append(child.text)
        return " ".join(relation_parts)

    # Strategy 3: Fallback - use "co-occurs with"
    return "co-occurs with"


# ── Main extraction pipeline ─────────────────────────────────────────────────

def extract_knowledge():
    """Main NER + relation extraction pipeline."""
    print("=" * 60)
    print("  NER & Relation Extraction - TD1")
    print("=" * 60)

    # Load spaCy model
    print("\n[*] Loading spaCy en_core_web_lg model...")
    nlp = spacy.load("en_core_web_lg")
    print("[+] Model loaded successfully.")

    # Load documents (limit to first 50)
    documents = load_documents(INPUT_FILE)[:50]
    print(f"[*] Processing first {len(documents)} documents.")

    triplets = []
    total_entities = 0

    for i, doc in enumerate(documents):
        url = doc["url"]
        title = doc["title"]
        text = doc["text"]

        print(f"\n[{i+1}/{len(documents)}] Processing: {title}")

        # Process text with spaCy (limit text length for memory)
        max_chars = 50000
        spacy_doc = nlp(text[:max_chars])

        # Count entities for stats
        entities = [ent for ent in spacy_doc.ents if ent.label_ in TARGET_ENTITY_TYPES and is_valid_entity(ent)]
        total_entities += len(entities)

        entity_counts = {}
        for ent in entities:
            entity_counts[ent.label_] = entity_counts.get(ent.label_, 0) + 1
        print(f"  Entities found: {dict(entity_counts)}")

        # Process sentence by sentence for relation extraction
        doc_triplets = 0
        for sent in spacy_doc.sents:
            # Get entities in this sentence
            sent_entities = [
                ent for ent in entities
                if ent.start_char >= sent.start_char and ent.end_char <= sent.end_char
            ]

            # Need at least 2 entities to form a relation
            if len(sent_entities) < 2:
                continue

            # Extract pairs
            for i_ent in range(len(sent_entities)):
                for j_ent in range(i_ent + 1, len(sent_entities)):
                    ent1 = sent_entities[i_ent]
                    ent2 = sent_entities[j_ent]

                    # Extract relation
                    relation = extract_relation(sent, ent1, ent2)

                    triplet = {
                        "subject": ent1.text.strip(),
                        "subject_type": ent1.label_,
                        "relation": relation,
                        "object": ent2.text.strip(),
                        "object_type": ent2.label_,
                        "source_url": url,
                        "sentence": sent.text.strip()[:500],  # Truncate long sentences
                    }
                    triplets.append(triplet)
                    doc_triplets += 1

        print(f"  Triplets extracted: {doc_triplets}")

    # Write to CSV
    print(f"\n[*] Writing {len(triplets)} triplets to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "subject", "subject_type", "relation", "object", "object_type",
            "source_url", "sentence"
        ])
        writer.writeheader()
        writer.writerows(triplets)

    print("\n" + "=" * 60)
    print(f"  Extraction complete!")
    print(f"  Total entities found: {total_entities}")
    print(f"  Total triplets:       {len(triplets)}")
    print(f"  Output file:          {OUTPUT_FILE}")
    print("=" * 60)

    # Show sample triplets
    print("\n-- Sample triplets --")
    for t in triplets[:10]:
        print(f"  ({t['subject']} [{t['subject_type']}]) "
              f"--[{t['relation']}]--> "
              f"({t['object']} [{t['object_type']}])")


if __name__ == "__main__":
    extract_knowledge()
