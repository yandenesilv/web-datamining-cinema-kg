"""
Cours 6 - RAG with Knowledge Graphs: NL -> SPARQL Generation
Course: Web Mining & Semantics - ESILV

Pipeline RAG qui :
1. Charge la KB cinema expandee (expanded_kb.ttl) avec rdflib
2. Construit un schema summary (prefixes, predicates, classes, exemples)
3. Utilise un LLM local (Ollama) pour convertir des questions en SPARQL
4. Execute le SPARQL sur la KB et retourne les resultats
5. Implemente un mecanisme de self-repair si le SPARQL echoue
6. Compare baseline (LLM seul) vs RAG (LLM + KB)
7. Interface CLI interactive

Prerequis :
- Ollama installe et lance (http://localhost:11434)
- Un modele telecharge : ollama pull gemma:2b (ou qwen2.5:0.5b, llama3.2:1b)
- La KB expandee : ../TD1/expanded_kb.ttl
"""

import re
import sys
import json
import requests
from typing import List, Tuple, Optional
from rdflib import Graph

# -- Configuration -------------------------------------------------------------

TTL_FILE = "../../kg_artifacts/expanded_kb.ttl"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma:2b"  # Modele par defaut, peut etre change

MAX_PREDICATES = 80
MAX_CLASSES = 40
SAMPLE_TRIPLES = 25
MAX_REPAIR_ATTEMPTS = 2


# -- 0) Utilitaire : appel au LLM local (Ollama) -----------------------------

def ask_local_llm(prompt: str, model: str = MODEL) -> str:
    """
    Envoie un prompt au LLM local via l'API Ollama.
    Retourne la reponse complete en texte.

    Le parametre stream=False permet de recuperer toute la reponse d'un coup.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    except requests.ConnectionError:
        raise RuntimeError(
            "Impossible de se connecter a Ollama.\n"
            "Assurez-vous qu'Ollama est lance : ollama serve\n"
            "Et qu'un modele est installe : ollama pull gemma:2b"
        )

    if response.status_code != 200:
        raise RuntimeError(f"Ollama API erreur {response.status_code}: {response.text}")

    data = response.json()
    return data.get("response", "")


# -- 1) Charger le graphe RDF -------------------------------------------------

def load_graph(ttl_path: str) -> Graph:
    """Charge le graphe RDF depuis un fichier Turtle."""
    g = Graph()
    g.parse(ttl_path, format="turtle")
    print(f"[+] Charge {len(g)} triples depuis {ttl_path}")
    return g


# -- 2) Construire le schema summary ------------------------------------------

def get_prefix_block(g: Graph) -> str:
    """Collecte les prefixes du graphe pour les inclure dans le prompt."""
    defaults = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "wd": "http://www.wikidata.org/entity/",
        "wdt": "http://www.wikidata.org/prop/direct/",
    }
    ns_map = {p: str(ns) for p, ns in g.namespace_manager.namespaces()}
    for k, v in defaults.items():
        ns_map.setdefault(k, v)

    lines = [f"PREFIX {p}: <{ns}>" for p, ns in ns_map.items()]
    return "\n".join(sorted(lines))


def list_distinct_predicates(g: Graph, limit=MAX_PREDICATES) -> List[str]:
    """Liste les predicats uniques du graphe."""
    q = f"""
    SELECT DISTINCT ?p WHERE {{
      ?s ?p ?o .
    }} LIMIT {limit}
    """
    return [str(row.p) for row in g.query(q)]


def list_distinct_classes(g: Graph, limit=MAX_CLASSES) -> List[str]:
    """Liste les classes (rdf:type) du graphe."""
    q = f"""
    SELECT DISTINCT ?cls WHERE {{
      ?s a ?cls .
    }} LIMIT {limit}
    """
    return [str(row.cls) for row in g.query(q)]


def sample_triples(g: Graph, limit=SAMPLE_TRIPLES) -> List[Tuple[str, str, str]]:
    """Recupere un echantillon de triples pour le prompt."""
    q = f"""
    SELECT ?s ?p ?o WHERE {{
      ?s ?p ?o .
      FILTER(isURI(?o))
    }} LIMIT {limit}
    """
    return [(str(r.s), str(r.p), str(r.o)) for r in g.query(q)]


def build_schema_summary(g: Graph) -> str:
    """
    Construit un resume du schema du graphe RDF.
    Ce resume est fourni au LLM pour qu'il genere des requetes SPARQL valides.
    """
    prefixes = get_prefix_block(g)
    preds = list_distinct_predicates(g)
    clss = list_distinct_classes(g)
    samples = sample_triples(g)

    pred_lines = "\n".join(f"- {p}" for p in preds)
    cls_lines = "\n".join(f"- {c}" for c in clss) if clss else "- (no explicit rdf:type found)"
    sample_lines = "\n".join(f"- <{s}> <{p}> <{o}>" for s, p, o in samples)

    summary = f"""
{prefixes}

# Predicates used in this Knowledge Graph (sampled, up to {MAX_PREDICATES}):
{pred_lines}

# Classes / rdf:type (sampled, up to {MAX_CLASSES}):
{cls_lines}

# Sample triples (up to {SAMPLE_TRIPLES}):
{sample_lines}

# Important notes about this Knowledge Graph:
- This is a CINEMA knowledge graph with films, directors, actors, awards
- Wikidata properties are used: P57 (director), P161 (cast), P166 (award), P136 (genre), P495 (country), P577 (publication date)
- Entities use Wikidata URIs like <http://www.wikidata.org/entity/Q12345>
- Some entities use private URIs like <http://cinema-kb.org/entity/EntityName>
- Use FILTER with regex() or CONTAINS() for text matching on entity URIs
"""
    return summary.strip()


# -- 3) Prompting : NL -> SPARQL ----------------------------------------------

SPARQL_INSTRUCTIONS = """
You are a SPARQL generator for a cinema knowledge graph. Convert the user QUESTION into a valid SPARQL 1.1 SELECT query.

STRICT RULES:
- Use ONLY the IRIs/prefixes visible in the SCHEMA SUMMARY
- Prefer readable SELECT projections with descriptive variable names
- Do NOT invent new predicates or classes
- Return ONLY the SPARQL query in a single fenced code block labeled ```sparql
- No explanations or extra text outside the code block
- For text matching, use FILTER with regex() on the URI or rdfs:label
- Wikidata properties: P57=director, P161=cast member, P166=award received, P136=genre, P495=country of origin, P577=publication date, P27=country of citizenship
- Use rdfs:label when available, otherwise extract entity name from URI
"""

def make_sparql_prompt(schema_summary: str, question: str) -> str:
    """Construit le prompt pour la generation SPARQL."""
    return f"""{SPARQL_INSTRUCTIONS}

SCHEMA SUMMARY:
{schema_summary}

QUESTION:
{question}

Return only the SPARQL query in a code block.
"""


CODE_BLOCK_RE = re.compile(r"```(?:sparql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)

def extract_sparql_from_text(text: str) -> str:
    """Extrait la requete SPARQL du bloc de code dans la reponse du LLM."""
    m = CODE_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    # Fallback : chercher une ligne qui commence par SELECT
    for line in text.split("\n"):
        if line.strip().upper().startswith("SELECT") or line.strip().upper().startswith("PREFIX"):
            # Prendre tout a partir de cette ligne
            idx = text.index(line)
            return text[idx:].strip()
    return text.strip()


def generate_sparql(question: str, schema_summary: str, model: str = MODEL) -> str:
    """Genere une requete SPARQL a partir d'une question en langage naturel."""
    prompt = make_sparql_prompt(schema_summary, question)
    raw = ask_local_llm(prompt, model=model)
    query = extract_sparql_from_text(raw)
    return query


# -- 4) Execution SPARQL + Self-repair ----------------------------------------

def run_sparql(g: Graph, query: str) -> Tuple[List[str], List[Tuple]]:
    """Execute une requete SPARQL sur le graphe et retourne les resultats."""
    res = g.query(query)
    vars_ = [str(v) for v in res.vars] if res.vars else []
    rows = [tuple(str(cell) for cell in r) for r in res]
    return vars_, rows


REPAIR_INSTRUCTIONS = """
The previous SPARQL query failed to execute on the RDF graph. Using the SCHEMA SUMMARY and ERROR MESSAGE,
return a corrected SPARQL 1.1 SELECT query.

STRICT RULES:
- Use only known prefixes and IRIs from the schema
- Keep it as simple and robust as possible
- Common fixes: check PREFIX declarations, property URIs, syntax
- Return only a single code block with the corrected SPARQL
"""

def repair_sparql(schema_summary: str, question: str, bad_query: str,
                  error_msg: str, model: str = MODEL) -> str:
    """Demande au LLM de reparer une requete SPARQL qui a echoue."""
    prompt = f"""{REPAIR_INSTRUCTIONS}

SCHEMA SUMMARY:
{schema_summary}

ORIGINAL QUESTION:
{question}

FAILED SPARQL:
{bad_query}

ERROR MESSAGE:
{error_msg}

Return only the corrected SPARQL in a code block.
"""
    raw = ask_local_llm(prompt, model=model)
    return extract_sparql_from_text(raw)


# -- 5) Orchestration : RAG avec self-repair ----------------------------------

def answer_with_sparql_rag(g: Graph, schema_summary: str, question: str,
                           model: str = MODEL) -> dict:
    """
    Pipeline RAG complet :
    1. Genere un SPARQL a partir de la question
    2. Execute le SPARQL
    3. Si erreur : tente de reparer (jusqu'a MAX_REPAIR_ATTEMPTS fois)
    4. Retourne les resultats ou l'erreur
    """
    sparql = generate_sparql(question, schema_summary, model=model)

    # Tentative d'execution
    try:
        vars_, rows = run_sparql(g, sparql)
        return {
            "query": sparql,
            "vars": vars_,
            "rows": rows,
            "repaired": False,
            "repair_count": 0,
            "error": None,
        }
    except Exception as e:
        last_error = str(e)
        last_query = sparql

    # Self-repair loop
    for attempt in range(MAX_REPAIR_ATTEMPTS):
        repaired_query = repair_sparql(schema_summary, question, last_query, last_error, model=model)
        try:
            vars_, rows = run_sparql(g, repaired_query)
            return {
                "query": repaired_query,
                "vars": vars_,
                "rows": rows,
                "repaired": True,
                "repair_count": attempt + 1,
                "error": None,
            }
        except Exception as e2:
            last_error = str(e2)
            last_query = repaired_query

    # Echec apres toutes les tentatives
    return {
        "query": last_query,
        "vars": [],
        "rows": [],
        "repaired": True,
        "repair_count": MAX_REPAIR_ATTEMPTS,
        "error": last_error,
    }


# -- 6) Baseline : reponse directe du LLM sans KB ----------------------------

def answer_no_rag(question: str, model: str = MODEL) -> str:
    """Pose la question directement au LLM sans aucun contexte KB."""
    prompt = f"Answer the following question about cinema as best as you can:\n\n{question}"
    return ask_local_llm(prompt, model=model)


# -- 7) Affichage des resultats -----------------------------------------------

def pretty_print_result(result: dict):
    """Affiche les resultats d'une requete RAG de facon lisible."""
    if result.get("error"):
        print(f"\n  [Erreur d'execution] {result['error']}")

    print(f"\n  [Requete SPARQL utilisee]")
    print(f"  {result['query']}")

    print(f"\n  [Reparee ?] {'Oui (' + str(result['repair_count']) + ' tentatives)' if result['repaired'] else 'Non'}")

    vars_ = result.get("vars", [])
    rows = result.get("rows", [])

    if not rows:
        print("\n  [Aucun resultat retourne]")
        return

    print(f"\n  [Resultats] ({len(rows)} lignes)")
    print(f"  {' | '.join(vars_)}")
    print(f"  {'-' * 60}")
    for r in rows[:20]:
        # Raccourcir les URIs pour la lisibilite
        short = []
        for cell in r:
            if "wikidata.org/entity/" in cell:
                short.append(cell.split("/")[-1])
            elif "cinema-kb.org/" in cell:
                short.append(cell.split("/")[-1])
            else:
                short.append(cell[:60])
        print(f"  {' | '.join(short)}")
    if len(rows) > 20:
        print(f"  ... ({len(rows)} lignes au total, 20 affichees)")


# -- 8) CLI Interactive --------------------------------------------------------

def run_cli(g: Graph, schema_summary: str, model: str = MODEL):
    """Interface CLI interactive pour poser des questions."""
    print("\n" + "=" * 60)
    print("  RAG Cinema KB - Interface Interactive")
    print("  Modele : " + model)
    print("  Tapez 'quit' pour quitter")
    print("=" * 60)

    while True:
        try:
            question = input("\n  Question : ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not question or question.lower() in ("quit", "exit", "q"):
            print("\n  Au revoir!")
            break

        # Baseline
        print("\n" + "-" * 60)
        print("  BASELINE (LLM seul, sans KB)")
        print("-" * 60)
        try:
            baseline = answer_no_rag(question, model=model)
            print(f"  {baseline[:500]}")
        except Exception as e:
            print(f"  [Erreur baseline] {e}")

        # RAG
        print("\n" + "-" * 60)
        print("  RAG (LLM + Knowledge Base SPARQL)")
        print("-" * 60)
        try:
            result = answer_with_sparql_rag(g, schema_summary, question, model=model)
            pretty_print_result(result)
        except Exception as e:
            print(f"  [Erreur RAG] {e}")


# -- Main ----------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Cours 6 - RAG with Knowledge Graphs")
    print("  NL -> SPARQL Generation with Self-Repair")
    print("=" * 60)

    # Detecter le modele
    model = MODEL
    if len(sys.argv) > 1:
        model = sys.argv[1]
        print(f"\n[*] Modele specifie : {model}")

    # Charger le graphe
    print(f"\n[1/3] Chargement du graphe RDF...")
    g = load_graph(TTL_FILE)

    # Construire le schema summary
    print(f"\n[2/3] Construction du schema summary...")
    schema = build_schema_summary(g)
    print(f"  Schema summary construit ({len(schema)} caracteres)")

    # Verifier Ollama
    print(f"\n[3/3] Verification de la connexion Ollama...")
    try:
        r = requests.get("http://localhost:11434", timeout=5)
        if r.status_code == 200:
            print(f"  [+] Ollama est accessible")
        else:
            print(f"  [!] Ollama repond mais status {r.status_code}")
    except requests.ConnectionError:
        print(f"  [!] Ollama n'est pas accessible sur localhost:11434")
        print(f"  Lancez : ollama serve")
        print(f"  Puis :   ollama pull {model}")
        sys.exit(1)

    # Lancer le CLI
    run_cli(g, schema, model=model)


if __name__ == "__main__":
    main()
