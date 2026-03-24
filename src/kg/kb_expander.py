"""
Steps 4 & 5 - KB Expansion via SPARQL + Clean & Export
Course: Web Mining & Semantics - ESILV

Step 4: Expands the KB by querying Wikidata SPARQL for 1-hop and 2-hop triples
        around aligned entities.
Step 5: Cleans, deduplicates, and exports the final KB as N-Triples + stats.
"""

import csv
import time
from collections import Counter

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef
from SPARQLWrapper import SPARQLWrapper, JSON


# ── Configuration ──────────────────────────────────────────────────────────────

KB_FILE = "../../kg_artifacts/private_kb.ttl"
ALIGNMENT_FILE = "../../kg_artifacts/alignment_table.csv"
OUTPUT_NT = "../../kg_artifacts/expanded_kb.nt"
STATS_FILE = "../../kg_artifacts/statistics_report.txt"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
API_DELAY = 0.5  # seconds between SPARQL calls
CONFIDENCE_THRESHOLD = 0.7
USER_AGENT = "ESILV-WebMining-Bot/1.0 (student project; contact: yanis.denizot@edu.devinci.fr)"

# Cinema-relevant Wikidata properties for expansion
TARGET_PROPS_SPARQL = """wdt:P57 wdt:P161 wdt:P166 wdt:P577 wdt:P162
    wdt:P495 wdt:P136 wdt:P58 wdt:P344 wdt:P86 wdt:P19 wdt:P20
    wdt:P27 wdt:P106 wdt:P569 wdt:P570 wdt:P800 wdt:P144 wdt:P31"""

# Award entities for 2-hop expansion
AWARD_IDS = ["Q19020", "Q103360", "Q103916", "Q194536", "Q486970",
             "Q1011547", "Q30024093"]
AWARD_NAMES = {
    "Q19020": "Academy Award for Best Picture",
    "Q103360": "Academy Award for Best Director",
    "Q103916": "Palme d'Or",
    "Q194536": "Golden Globe Award for Best Motion Picture - Drama",
    "Q486970": "Golden Bear",
    "Q1011547": "Golden Lion",
    "Q30024093": "Academy Award for Best International Feature Film",
}

# ── Namespaces ─────────────────────────────────────────────────────────────────

EX = Namespace("http://cinema-kb.org/")
WD = Namespace("http://www.wikidata.org/entity/")
WDT = Namespace("http://www.wikidata.org/prop/direct/")


# ── SPARQL Helpers ─────────────────────────────────────────────────────────────

def run_sparql(query: str, retries: int = 3) -> list[dict]:
    """Execute a SPARQL query against Wikidata."""
    sparql = SPARQLWrapper(SPARQL_ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.addCustomHttpHeader("User-Agent", USER_AGENT)

    for attempt in range(retries):
        try:
            results = sparql.query().convert()
            return results["results"]["bindings"]
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "Too Many" in err_str:
                wait = max(2.0, API_DELAY * (attempt + 3))
                print(f"    [429] Rate limited. Waiting {wait}s...")
                time.sleep(wait)
            elif "Timeout" in err_str or "timeout" in err_str:
                print(f"    [TIMEOUT] Retrying ({attempt+1}/{retries})...")
                time.sleep(2.0)
            else:
                print(f"    [ERROR] {e}")
                time.sleep(1.0)
    return []


# ══════════════════════════════════════════════════════════════════════════════
#   STEP 4: KB Expansion
# ══════════════════════════════════════════════════════════════════════════════

def add_results_to_graph(g: Graph, results: list[dict],
                         subj_key: str, pred_key: str, obj_key: str,
                         label_keys: dict | None = None):
    """Add SPARQL result rows to the RDF graph. Returns count of triples added."""
    added = 0
    for r in results:
        s_val = r[subj_key]["value"]
        p_val = r[pred_key]["value"] if pred_key in r else None
        o_val = r[obj_key]["value"]

        subj = URIRef(s_val)
        pred = URIRef(p_val) if p_val else None
        obj = URIRef(o_val) if o_val.startswith("http") else Literal(o_val)

        if pred:
            g.add((subj, pred, obj))
            added += 1

        # Add labels
        if label_keys:
            for uri_key, label_key in label_keys.items():
                if label_key in r and r[label_key]["value"]:
                    uri_val = r[uri_key]["value"]
                    if uri_val.startswith("http"):
                        g.add((URIRef(uri_val), RDFS.label, Literal(r[label_key]["value"])))
    return added


def expand_kb():
    print("=" * 60)
    print("  Step 4: KB Expansion via SPARQL (Bulk Queries)")
    print("=" * 60)

    # Load KB
    print("\n[*] Loading private_kb.ttl...")
    g = Graph()
    g.parse(KB_FILE, format="turtle")
    initial_count = len(g)
    print(f"[+] KB loaded: {initial_count} triples.")

    # Load ALL aligned entities (not capped)
    print("[*] Loading alignment_table.csv...")
    alignments = []
    with open(ALIGNMENT_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["wikidata_id"] and float(row["confidence"]) >= CONFIDENCE_THRESHOLD:
                alignments.append(row)
    print(f"[+] {len(alignments)} entities with confidence >= {CONFIDENCE_THRESHOLD}")

    # Build VALUES clause with all Wikidata IDs
    all_wd_ids = [a["wikidata_id"] for a in alignments]
    values_clause = " ".join(f"wd:{qid}" for qid in all_wd_ids)

    # ── Query 1: Bulk 1-hop expansion for all aligned entities ──
    print(f"\n[*] Query 1: Bulk 1-hop expansion ({len(all_wd_ids)} entities)...")
    query1 = f"""
    SELECT ?s ?p ?o ?oLabel WHERE {{
        VALUES ?s {{ {values_clause} }}
        VALUES ?p {{ {TARGET_PROPS_SPARQL} }}
        ?s ?p ?o .
        OPTIONAL {{ ?o rdfs:label ?oLabel . FILTER(LANG(?oLabel) = "en") }}
    }} LIMIT 100000
    """
    results1 = run_sparql(query1)
    n1 = add_results_to_graph(g, results1, "s", "p", "o",
                              label_keys={"o": "oLabel"})
    print(f"[+] Query 1 returned {len(results1)} rows -> {n1} triples added. KB: {len(g)}")

    # ── Query 2: 2-hop award expansion (films + directors + cast for major awards) ──
    time.sleep(1.0)
    award_values = " ".join(f"wd:{qid}" for qid in AWARD_IDS)
    print(f"\n[*] Query 2: Award-winning films + directors + genre + country...")
    query2 = f"""
    SELECT ?film ?filmLabel ?p ?o ?oLabel WHERE {{
        VALUES ?award {{ {award_values} }}
        ?film wdt:P166 ?award .
        ?film wdt:P31 wd:Q11424 .
        VALUES ?p {{ wdt:P57 wdt:P161 wdt:P166 wdt:P577 wdt:P136 wdt:P495 wdt:P162 wdt:P58 }}
        ?film ?p ?o .
        OPTIONAL {{ ?film rdfs:label ?filmLabel . FILTER(LANG(?filmLabel) = "en") }}
        OPTIONAL {{ ?o rdfs:label ?oLabel . FILTER(LANG(?oLabel) = "en") }}
    }} LIMIT 100000
    """
    results2 = run_sparql(query2)
    n2 = add_results_to_graph(g, results2, "film", "p", "o",
                              label_keys={"film": "filmLabel", "o": "oLabel"})
    print(f"[+] Query 2 returned {len(results2)} rows -> {n2} triples added. KB: {len(g)}")

    # ── Query 3: Notable films by aligned directors (people with P106=Q2526255 director) ──
    time.sleep(1.0)
    print(f"\n[*] Query 3: Films by aligned people (notable works, directed, starred in)...")
    query3 = f"""
    SELECT ?person ?film ?filmLabel ?p ?o ?oLabel WHERE {{
        VALUES ?person {{ {values_clause} }}
        ?film wdt:P57 ?person .
        ?film wdt:P31 wd:Q11424 .
        VALUES ?p {{ wdt:P161 wdt:P166 wdt:P577 wdt:P136 wdt:P495 wdt:P57 }}
        ?film ?p ?o .
        OPTIONAL {{ ?film rdfs:label ?filmLabel . FILTER(LANG(?filmLabel) = "en") }}
        OPTIONAL {{ ?o rdfs:label ?oLabel . FILTER(LANG(?oLabel) = "en") }}
    }} LIMIT 100000
    """
    results3 = run_sparql(query3)
    n3 = add_results_to_graph(g, results3, "film", "p", "o",
                              label_keys={"film": "filmLabel", "o": "oLabel"})
    print(f"[+] Query 3 returned {len(results3)} rows -> {n3} triples added. KB: {len(g)}")

    # ── Query 4: Oscar/Cannes/BAFTA/Globe nominees (broader than just winners) ──
    time.sleep(1.0)
    print(f"\n[*] Query 4: Films nominated for major awards (broader net)...")
    query4 = """
    SELECT ?film ?filmLabel ?p ?o ?oLabel WHERE {
        VALUES ?awardType { wd:Q19020 wd:Q103360 wd:Q103916 wd:Q486970
                            wd:Q1011547 wd:Q30024093 wd:Q202018
                            wd:Q106301 wd:Q106291 }
        ?film wdt:P1411 ?awardType .
        ?film wdt:P31 wd:Q11424 .
        VALUES ?p { wdt:P57 wdt:P161 wdt:P166 wdt:P577 wdt:P136 wdt:P495 wdt:P162 wdt:P58 }
        ?film ?p ?o .
        OPTIONAL { ?film rdfs:label ?filmLabel . FILTER(LANG(?filmLabel) = "en") }
        OPTIONAL { ?o rdfs:label ?oLabel . FILTER(LANG(?oLabel) = "en") }
    } LIMIT 100000
    """
    results4 = run_sparql(query4)
    n4 = add_results_to_graph(g, results4, "film", "p", "o",
                              label_keys={"film": "filmLabel", "o": "oLabel"})
    print(f"[+] Query 4 returned {len(results4)} rows -> {n4} triples added. KB: {len(g)}")

    # ── Query 5: Collect all film URIs now in the graph, get director details ──
    time.sleep(1.0)
    # Extract Wikidata film and director URIs already in the graph
    wd_prefix = "http://www.wikidata.org/entity/"
    director_uris = set()
    for s, p, o in g:
        if str(p) == "http://www.wikidata.org/prop/direct/P57" and str(o).startswith(wd_prefix):
            director_uris.add(str(o).replace(wd_prefix, ""))

    # Take up to 200 directors for bulk info query
    director_ids = list(director_uris)[:200]
    dir_values = " ".join(f"wd:{d}" for d in director_ids)
    print(f"\n[*] Query 5: Details for {len(director_ids)} discovered directors...")
    query5 = f"""
    SELECT ?s ?p ?o ?oLabel WHERE {{
        VALUES ?s {{ {dir_values} }}
        VALUES ?p {{ wdt:P19 wdt:P20 wdt:P27 wdt:P106 wdt:P569 wdt:P570
                     wdt:P800 wdt:P166 wdt:P31 wdt:P21 }}
        ?s ?p ?o .
        OPTIONAL {{ ?o rdfs:label ?oLabel . FILTER(LANG(?oLabel) = "en") }}
    }} LIMIT 100000
    """
    results5 = run_sparql(query5)
    n5 = add_results_to_graph(g, results5, "s", "p", "o",
                              label_keys={"o": "oLabel"})
    print(f"[+] Query 5 returned {len(results5)} rows -> {n5} triples added. KB: {len(g)}")

    # Save expanded KB as Turtle too
    g.bind("ex", EX)
    g.bind("wd", WD)
    g.bind("wdt", WDT)
    g.bind("owl", OWL)
    g.serialize(destination="expanded_kb.ttl", format="turtle")

    total_queries = 5
    print("\n" + "=" * 60)
    print(f"  Step 4 Complete!")
    print(f"  Initial KB triples:   {initial_count}")
    print(f"  Final KB triples:     {len(g)}")
    print(f"  New triples added:    {len(g) - initial_count}")
    print(f"  SPARQL queries used:  {total_queries}")
    print("=" * 60)

    return g


# ══════════════════════════════════════════════════════════════════════════════
#   STEP 5: Clean & Export
# ══════════════════════════════════════════════════════════════════════════════

def clean_and_export(g: Graph):
    print("\n" + "=" * 60)
    print("  Step 5: Clean & Export")
    print("=" * 60)

    pre_clean = len(g)
    print(f"\n[*] Pre-cleaning: {pre_clean} triples")

    # ── Remove isolated nodes (entities with only 1 connection) ──
    print("[*] Removing isolated nodes...")
    # Count connections per entity (excluding type/label triples)
    entity_connections = Counter()
    for s, p, o in g:
        p_str = str(p)
        if p_str in (str(RDF.type), str(RDFS.label), str(OWL.sameAs),
                     str(OWL.equivalentProperty), str(RDFS.subClassOf),
                     str(RDFS.domain), str(RDFS.range)):
            continue
        entity_connections[str(s)] += 1
        if isinstance(o, URIRef):
            entity_connections[str(o)] += 1

    isolated = {e for e, c in entity_connections.items() if c <= 1}
    triples_to_remove = []
    for s, p, o in g:
        s_str = str(s)
        o_str = str(o)
        if s_str in isolated or (isinstance(o, URIRef) and o_str in isolated):
            # Only remove data triples, keep ontology
            p_str = str(p)
            if p_str not in (str(RDF.type), str(RDFS.subClassOf),
                             str(RDFS.domain), str(RDFS.range),
                             str(OWL.equivalentProperty)):
                if s_str in isolated:
                    triples_to_remove.append((s, p, o))

    for triple in triples_to_remove:
        g.remove(triple)

    print(f"  Removed {len(triples_to_remove)} triples from isolated nodes")
    print(f"  Post-cleaning: {len(g)} triples")

    # ── Export as N-Triples ──
    print(f"\n[*] Exporting to {OUTPUT_NT}...")
    g.serialize(destination=OUTPUT_NT, format="nt")

    # ── Generate statistics report ──
    print(f"[*] Generating {STATS_FILE}...")

    # Count entities
    entities = set()
    for s, p, o in g:
        if isinstance(s, URIRef):
            entities.add(str(s))
        if isinstance(o, URIRef):
            entities.add(str(o))

    # Count distinct relations
    relations = set()
    for s, p, o in g:
        relations.add(str(p))

    # Count owl:sameAs links
    sameas_count = 0
    for s, p, o in g:
        if str(p) == str(OWL.sameAs):
            sameas_count += 1

    # Top 10 most connected entities
    entity_degree = Counter()
    for s, p, o in g:
        p_str = str(p)
        if p_str in (str(RDF.type), str(RDFS.label), str(RDFS.subClassOf),
                     str(RDFS.domain), str(RDFS.range)):
            continue
        entity_degree[str(s)] += 1
        if isinstance(o, URIRef):
            entity_degree[str(o)] += 1

    # Get labels for top entities
    label_map = {}
    for s, p, o in g:
        if str(p) == str(RDFS.label):
            label_map[str(s)] = str(o)

    top10 = entity_degree.most_common(10)

    # Write report
    report_lines = [
        "=" * 60,
        "  Knowledge Base Statistics Report",
        "  Course: Web Mining & Semantics - ESILV",
        "=" * 60,
        "",
        f"Total triples:            {len(g)}",
        f"Total entities:           {len(entities)}",
        f"Total distinct relations: {len(relations)}",
        f"owl:sameAs links:         {sameas_count}",
        "",
        "Top 10 most connected entities:",
        "-" * 50,
    ]
    for uri, degree in top10:
        label = label_map.get(uri, uri.split("/")[-1])
        report_lines.append(f"  {label:40s}  ({degree} connections)")

    report_lines.extend(["", "-" * 50, ""])

    report_text = "\n".join(report_lines)

    with open(STATS_FILE, "w", encoding="utf-8") as f:
        f.write(report_text)

    # Print report
    print("\n" + report_text)

    print("=" * 60)
    print(f"  Step 5 Complete!")
    print(f"  Exported:  {OUTPUT_NT}")
    print(f"  Stats:     {STATS_FILE}")
    print("=" * 60)


# ══════════════════════════════════════════════════════════════════════════════
#   Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    g = expand_kb()
    clean_and_export(g)
