"""
Cours 6 - RAG Evaluation: Baseline vs SPARQL-generation RAG
Course: Web Mining & Semantics - ESILV

Evalue le pipeline RAG sur un ensemble de questions cinema.
Pour chaque question :
- Baseline : reponse directe du LLM (sans KB)
- RAG : generation SPARQL + execution sur la KB
- Comparaison et verdict

Produit un tableau d'evaluation et un rapport JSON.

Usage:
    python evaluation.py [model_name]
    python evaluation.py gemma:2b
    python evaluation.py qwen2.5:0.5b
"""

import sys
import json
import time
from lab_rag_sparql_gen import (
    load_graph, build_schema_summary,
    answer_no_rag, answer_with_sparql_rag,
    MODEL, TTL_FILE
)


# -- Questions d'evaluation ---------------------------------------------------

EVAL_QUESTIONS = [
    {
        "id": 1,
        "question": "Who directed The Godfather?",
        "expected": "Francis Ford Coppola",
        "category": "simple lookup",
    },
    {
        "id": 2,
        "question": "What awards did Parasite receive?",
        "expected": "Academy Award / Palme d'Or / multiple awards",
        "category": "multi-value",
    },
    {
        "id": 3,
        "question": "List some films directed by Martin Scorsese",
        "expected": "Goodfellas, Taxi Driver, The Departed, etc.",
        "category": "reverse lookup",
    },
    {
        "id": 4,
        "question": "What is the genre of Inception?",
        "expected": "Science fiction / Action / Thriller",
        "category": "property lookup",
    },
    {
        "id": 5,
        "question": "Which directors are from the United States?",
        "expected": "Multiple US directors (Spielberg, Scorsese, etc.)",
        "category": "filter query",
    },
    {
        "id": 6,
        "question": "How many films are in the knowledge base?",
        "expected": "Count of films (varies)",
        "category": "aggregation",
    },
    {
        "id": 7,
        "question": "Which films won the Academy Award for Best Picture?",
        "expected": "List of Best Picture winners",
        "category": "specific lookup",
    },
]


# -- Evaluation ----------------------------------------------------------------

def evaluate_question(g, schema, question_data, model):
    """Evalue une seule question en baseline et RAG."""
    q = question_data["question"]
    result = {
        "id": question_data["id"],
        "question": q,
        "expected": question_data["expected"],
        "category": question_data["category"],
    }

    # Baseline
    print(f"\n  Baseline...")
    try:
        t0 = time.time()
        baseline_answer = answer_no_rag(q, model=model)
        result["baseline_answer"] = baseline_answer[:500]
        result["baseline_time"] = round(time.time() - t0, 2)
        result["baseline_error"] = None
    except Exception as e:
        result["baseline_answer"] = ""
        result["baseline_time"] = 0
        result["baseline_error"] = str(e)

    # RAG
    print(f"  RAG...")
    try:
        t0 = time.time()
        rag_result = answer_with_sparql_rag(g, schema, q, model=model)
        result["rag_query"] = rag_result["query"]
        result["rag_rows"] = rag_result["rows"][:10]  # Limiter pour le rapport
        result["rag_row_count"] = len(rag_result["rows"])
        result["rag_repaired"] = rag_result["repaired"]
        result["rag_repair_count"] = rag_result["repair_count"]
        result["rag_error"] = rag_result["error"]
        result["rag_time"] = round(time.time() - t0, 2)

        # Determiner si le RAG a produit des resultats utiles
        if rag_result["rows"] and not rag_result["error"]:
            result["rag_success"] = True
        else:
            result["rag_success"] = False
    except Exception as e:
        result["rag_query"] = ""
        result["rag_rows"] = []
        result["rag_row_count"] = 0
        result["rag_repaired"] = False
        result["rag_repair_count"] = 0
        result["rag_error"] = str(e)
        result["rag_time"] = 0
        result["rag_success"] = False

    return result


def run_evaluation(model=MODEL):
    """Execute l'evaluation complete sur toutes les questions."""
    print("=" * 70)
    print("  RAG Evaluation: Baseline vs SPARQL-generation RAG")
    print(f"  Modele : {model}")
    print("=" * 70)

    # Charger le graphe
    print(f"\n[*] Chargement de la KB...")
    g = load_graph(TTL_FILE)

    print(f"[*] Construction du schema summary...")
    schema = build_schema_summary(g)

    # Evaluer chaque question
    results = []
    for qdata in EVAL_QUESTIONS:
        print(f"\n{'='*70}")
        print(f"  Q{qdata['id']}: {qdata['question']}")
        print(f"  Categorie: {qdata['category']}")
        print(f"  Attendu: {qdata['expected']}")
        print(f"{'='*70}")

        result = evaluate_question(g, schema, qdata, model)
        results.append(result)

    # Afficher le tableau recapitulatif
    print_evaluation_table(results)

    # Sauvegarder le rapport
    report = {
        "model": model,
        "kb_file": TTL_FILE,
        "kb_triples": len(g),
        "questions_count": len(EVAL_QUESTIONS),
        "results": results,
        "summary": {
            "rag_success_count": sum(1 for r in results if r["rag_success"]),
            "rag_repair_count": sum(1 for r in results if r["rag_repaired"]),
            "avg_baseline_time": round(sum(r["baseline_time"] for r in results) / len(results), 2),
            "avg_rag_time": round(sum(r["rag_time"] for r in results) / len(results), 2),
        },
    }

    output_file = "evaluation_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n[+] Rapport sauvegarde dans {output_file}")

    return report


def print_evaluation_table(results):
    """Affiche un tableau recapitulatif de l'evaluation."""
    print("\n\n" + "=" * 90)
    print("  TABLEAU D'EVALUATION : Baseline vs RAG")
    print("=" * 90)

    print(f"\n  {'Q#':<4} {'Question':<40} {'Baseline':<12} {'RAG':<12} {'Repare?':<10} {'Resultats'}")
    print(f"  {'-'*4} {'-'*40} {'-'*12} {'-'*12} {'-'*10} {'-'*10}")

    for r in results:
        q_short = r["question"][:38]
        baseline_status = "Erreur" if r.get("baseline_error") else "Repondu"
        rag_status = "OK" if r["rag_success"] else "Echec"
        repaired = f"Oui({r['rag_repair_count']})" if r["rag_repaired"] else "Non"
        row_count = str(r["rag_row_count"]) + " rows"

        print(f"  Q{r['id']:<3} {q_short:<40} {baseline_status:<12} {rag_status:<12} {repaired:<10} {row_count}")

    # Resume
    success = sum(1 for r in results if r["rag_success"])
    repaired = sum(1 for r in results if r["rag_repaired"])
    total = len(results)

    print(f"\n  Resume :")
    print(f"    RAG succes     : {success}/{total}")
    print(f"    Self-repair    : {repaired}/{total} questions ont necessite une reparation")
    print(f"    Temps moyen baseline : {sum(r['baseline_time'] for r in results)/total:.1f}s")
    print(f"    Temps moyen RAG      : {sum(r['rag_time'] for r in results)/total:.1f}s")

    print("\n" + "=" * 90)
    print("  ANALYSE")
    print("=" * 90)
    print("""
  Baseline (LLM seul) :
    - Le LLM repond avec ses connaissances pre-entrainees
    - Peut halluciner ou donner des reponses incorrectes
    - Pas d'acces aux donnees specifiques de notre KB

  RAG (LLM + KB SPARQL) :
    - Le LLM genere du SPARQL qui est execute sur la KB reelle
    - Les resultats sont fondes sur des donnees verifiables (grounded)
    - Le mecanisme de self-repair corrige les erreurs de syntaxe SPARQL
    - Limite : depend de la qualite du schema summary et de la capacite
      du LLM a generer du SPARQL correct

  Conclusion :
    - Le RAG fournit des reponses factuelles et verifiables
    - Le baseline peut donner des reponses plus fluides mais potentiellement fausses
    - La combinaison des deux approches serait ideale :
      RAG pour les faits, LLM pour la mise en forme
""")


# -- Main ----------------------------------------------------------------------

if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else MODEL
    run_evaluation(model)
