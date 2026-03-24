"""
Steps 2 & 3 - Entity Linking + Predicate Alignment with Wikidata
Course: Web Mining & Semantics - ESILV

Step 2: Links the top 200 most frequent entities to Wikidata via API,
        adds owl:sameAs links to the KB, saves alignment_table.csv.
Step 3: Aligns predicates with Wikidata properties, saves predicate_alignment.csv.
"""

import csv
import time
import re
from collections import Counter
from difflib import SequenceMatcher

import requests
from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef


# ── Configuration ──────────────────────────────────────────────────────────────

KB_FILE = "../../kg_artifacts/private_kb.ttl"
KB_OUTPUT = "../../kg_artifacts/private_kb.ttl"
ALIGNMENT_FILE = "../../kg_artifacts/alignment_table.csv"
PREDICATE_FILE = "../../kg_artifacts/predicate_alignment.csv"
TOP_ENTITIES = 200
SIMILARITY_THRESHOLD = 0.7
API_DELAY = 0.3

# ── Namespaces ─────────────────────────────────────────────────────────────────

EX = Namespace("http://cinema-kb.org/")
WD = Namespace("http://www.wikidata.org/entity/")
WDT = Namespace("http://www.wikidata.org/prop/direct/")


# ── Helpers ────────────────────────────────────────────────────────────────────

def similarity(a: str, b: str) -> float:
    """Compute string similarity between two strings."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def uri_to_label(uri: str) -> str:
    """Extract a readable label from a URI (PascalCase -> words)."""
    name = uri.split("/")[-1]
    # Insert space before capitals
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return words


# ══════════════════════════════════════════════════════════════════════════════
#   STEP 2: Entity Linking
# ══════════════════════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": "ESILV-WebMining-Bot/1.0 (student project; contact: yanis.denizot@edu.devinci.fr)",
}


def search_wikidata(entity_label: str, retries: int = 3) -> list[dict]:
    """Search Wikidata for an entity by label."""
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities",
        "search": entity_label,
        "language": "en",
        "format": "json",
        "limit": 5,
    }
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
            if resp.status_code == 429:
                wait = max(1.0, API_DELAY * (attempt + 2))
                print(f"    [429] Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json().get("search", [])
        except requests.RequestException as e:
            print(f"    [ERROR] {e}")
            time.sleep(1.0)
    return []


def link_entities():
    """Step 2: Link top entities to Wikidata."""
    print("=" * 60)
    print("  Step 2: Entity Linking with Wikidata")
    print("=" * 60)

    # Load the KB
    print("\n[*] Loading private_kb.ttl...")
    g = Graph()
    g.parse(KB_FILE, format="turtle")
    print(f"[+] KB loaded: {len(g)} triples.")

    # Count entity frequency (as subjects and objects in data triples)
    entity_freq = Counter()
    for s, p, o in g:
        s_str = str(s)
        o_str = str(o)
        if s_str.startswith(str(EX)) and str(p) != str(RDF.type) and str(p) != str(RDFS.label):
            entity_freq[s_str] += 1
        if o_str.startswith(str(EX)) and str(p) != str(RDF.type) and str(p) != str(RDFS.label):
            entity_freq[o_str] += 1

    # Get top entities
    top = entity_freq.most_common(TOP_ENTITIES)
    print(f"[+] Top {len(top)} entities by frequency.")

    # Link each to Wikidata
    alignments = []
    linked = 0
    not_found = 0

    for i, (entity_uri, freq) in enumerate(top):
        # Get label from KB
        label = None
        for _, _, obj in g.triples((URIRef(entity_uri), RDFS.label, None)):
            label = str(obj)
            break
        if not label:
            label = uri_to_label(entity_uri)

        print(f"  [{i+1}/{len(top)}] {label} (freq={freq})...", end=" ")
        time.sleep(API_DELAY)

        results = search_wikidata(label)

        best_match = None
        best_score = 0.0
        for result in results:
            wd_label = result.get("label", "")
            score = similarity(label, wd_label)
            if score > best_score:
                best_score = score
                best_match = result

        if best_match and best_score >= SIMILARITY_THRESHOLD:
            wd_id = best_match["id"]
            wd_label = best_match.get("label", "")
            wd_desc = best_match.get("description", "")
            wd_uri = f"http://www.wikidata.org/entity/{wd_id}"

            # Add owl:sameAs to KB
            g.add((URIRef(entity_uri), OWL.sameAs, URIRef(wd_uri)))

            alignments.append({
                "private_entity": entity_uri,
                "label": label,
                "wikidata_uri": wd_uri,
                "wikidata_id": wd_id,
                "wikidata_label": wd_label,
                "wikidata_description": wd_desc,
                "confidence": round(best_score, 3),
            })
            linked += 1
            print(f"-> {wd_id} ({wd_label}) [{best_score:.2f}]")
        else:
            # Keep in ontology with just a label
            alignments.append({
                "private_entity": entity_uri,
                "label": label,
                "wikidata_uri": "",
                "wikidata_id": "",
                "wikidata_label": "",
                "wikidata_description": "",
                "confidence": round(best_score, 3) if best_match else 0.0,
            })
            not_found += 1
            score_str = f" (best={best_score:.2f})" if best_match else ""
            print(f"-> NOT LINKED{score_str}")

    # Save alignment table
    with open(ALIGNMENT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "private_entity", "label", "wikidata_uri", "wikidata_id",
            "wikidata_label", "wikidata_description", "confidence"
        ])
        writer.writeheader()
        writer.writerows(alignments)

    # Save updated KB
    g.bind("ex", EX)
    g.bind("wd", WD)
    g.bind("owl", OWL)
    g.serialize(destination=KB_OUTPUT, format="turtle")

    print("\n" + "=" * 60)
    print(f"  Step 2 Complete!")
    print(f"  Entities linked:      {linked}")
    print(f"  Entities not found:   {not_found}")
    print(f"  KB triples (updated): {len(g)}")
    print(f"  Alignment saved to:   {ALIGNMENT_FILE}")
    print("=" * 60)

    return alignments


# ══════════════════════════════════════════════════════════════════════════════
#   STEP 3: Predicate Alignment
# ══════════════════════════════════════════════════════════════════════════════

# Hardcoded mappings after inspection of Wikidata properties
PREDICATE_WIKIDATA_MAP = {
    "directedBy": ("P57", "director"),
    "starring": ("P161", "cast member"),
    "wonAward": ("P166", "award received"),
    "nominatedFor": ("P1411", "nominated for"),
    "receivedAward": ("P166", "award received"),
    "producedBy": ("P162", "producer"),
    "releasedIn": ("P577", "publication date"),
    "bornIn": ("P19", "place of birth"),
    "diedIn": ("P20", "place of death"),
    "locatedIn": ("P131", "located in"),
    "basedIn": ("P159", "headquarters location"),
    "basedOn": ("P144", "based on"),
    "writtenBy": ("P58", "screenwriter"),
    "honoredBy": ("P166", "award received"),
    "includes": ("P527", "has part"),
    "playedRole": ("P453", "character role"),
    "composedFor": ("P86", "composer"),
    "foundedBy": ("P112", "founded by"),
    "featuring": ("P161", "cast member"),
    "adaptedFrom": ("P144", "based on"),
    "selectedFor": ("P1411", "nominated for"),
}


def align_predicates():
    """Step 3: Align predicates with Wikidata properties."""
    print("\n" + "=" * 60)
    print("  Step 3: Predicate Alignment with Wikidata")
    print("=" * 60)

    # Load KB to get used predicates
    g = Graph()
    g.parse(KB_FILE, format="turtle")

    # Find predicates used in data triples (under EX namespace)
    predicates_used = set()
    for s, p, o in g:
        p_str = str(p)
        if p_str.startswith(str(EX)):
            pred_name = p_str.replace(str(EX), "")
            # Skip ontology-level predicates
            if pred_name[0].islower():
                predicates_used.add(pred_name)

    print(f"\n[*] Found {len(predicates_used)} predicates in KB:")
    for p in sorted(predicates_used):
        print(f"    - {p}")

    # Build alignment
    alignments = []
    for pred in sorted(predicates_used):
        if pred in PREDICATE_WIKIDATA_MAP:
            wd_prop, wd_label = PREDICATE_WIKIDATA_MAP[pred]
            wd_uri = f"http://www.wikidata.org/prop/direct/{wd_prop}"

            # Add owl:equivalentProperty to KB
            g.add((EX[pred], OWL.equivalentProperty, URIRef(wd_uri)))

            alignments.append({
                "private_predicate": pred,
                "wikidata_property": wd_prop,
                "wikidata_label": wd_label,
                "wikidata_uri": wd_uri,
                "status": "aligned",
            })
            print(f"  {pred} -> {wd_prop} ({wd_label})")
        else:
            alignments.append({
                "private_predicate": pred,
                "wikidata_property": "",
                "wikidata_label": "",
                "wikidata_uri": "",
                "status": "no match",
            })
            print(f"  {pred} -> NO MATCH (kept as private predicate)")

    # Save alignment CSV
    with open(PREDICATE_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "private_predicate", "wikidata_property", "wikidata_label",
            "wikidata_uri", "status"
        ])
        writer.writeheader()
        writer.writerows(alignments)

    # Save updated KB
    g.bind("ex", EX)
    g.bind("wd", WD)
    g.bind("wdt", WDT)
    g.bind("owl", OWL)
    g.serialize(destination=KB_OUTPUT, format="turtle")

    aligned_count = sum(1 for a in alignments if a["status"] == "aligned")
    print(f"\n" + "=" * 60)
    print(f"  Step 3 Complete!")
    print(f"  Predicates aligned:     {aligned_count}/{len(predicates_used)}")
    print(f"  KB triples (updated):   {len(g)}")
    print(f"  Predicate alignment:    {PREDICATE_FILE}")
    print("=" * 60)


# ══════════════════════════════════════════════════════════════════════════════
#   Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    link_entities()
    align_predicates()
