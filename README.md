# Web Datamining - Cinema Knowledge Graph

Projet ESILV A4 S8 - Web Mining & Semantics

Yanis Denizot - Mars 2026

## Description

Projet qui construit un knowledge graph sur le domaine du cinema a partir de Wikipedia, puis fait du raisonnement SWRL, des embeddings (KGE) et un chatbot RAG.

Le pipeline :
1. Crawling de pages Wikipedia cinema (BFS depth 2, ~150 pages)
2. Extraction d'entites et relations avec spaCy
3. Construction d'une KB en RDF/OWL + alignement Wikidata
4. Expansion via SPARQL sur Wikidata (~72K triples)
5. Raisonnement SWRL (family.owl + cinema KB)
6. Embeddings KGE : TransE et ComplEx (PyKEEN)
7. RAG : questions en langage naturel -> SPARQL via Ollama

## Resultats

KB finale : **72 409 triples**, 20 158 entites, 39 relations

| Modele | MRR | Hits@10 |
|--------|-----|---------|
| TransE | 0.133 | 25.1% |
| ComplEx | 0.009 | 1.7% |

TransE marche beaucoup mieux car notre KB a surtout des relations 1-to-1 / 1-to-N.

## Structure du projet

```
src/
  crawl/       -> crawler Wikipedia
  ie/          -> extraction NER + relations
  kg/          -> construction KB, linking, expansion
  reason/      -> SWRL (family.owl + cinema)
  kge/         -> embeddings TransE/ComplEx
  rag/         -> pipeline RAG (Ollama + SPARQL)
data/          -> splits train/valid/test
kg_artifacts/  -> fichiers RDF, ontologie, alignements
results/       -> modeles entraines, metriques
figures/       -> visualisations t-SNE
reports/       -> rapport final
```

## Installation

Prerequis : Python 3.10+, Java (optionnel, pour Pellet), Ollama

```bash
git clone https://github.com/yandenesilv/web-datamining-cinema-kg.git
cd web-datamining-cinema-kg

python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
python -m spacy download en_core_web_lg
```

Pour le RAG il faut Ollama (https://ollama.ai/download) :
```bash
ollama serve
ollama pull qwen2.5:3b
```

## Utilisation

Chaque module se lance depuis son dossier :

```bash
# 1. Crawling
cd src/crawl && python crawler.py

# 2. Extraction NER
cd src/ie && python extractor.py

# 3. Construction + expansion KB
cd src/kg
python kb_builder.py
python entity_linker.py
python kb_expander.py

# 4. SWRL
cd src/reason
python swrl_family.py
python swrl_vs_embedding.py

# 5. KGE
cd src/kge
python step1_data_preparation.py
python step2_train_embeddings.py
python step3_kb_size_sensitivity.py
python step4_embedding_analysis.py

# 6. RAG (Ollama doit tourner)
cd src/rag
python lab_rag_sparql_gen.py        # demo interactive
python evaluation.py                # evaluation 7 questions
```

## Demo RAG

```
Question : Who directed The Godfather?

--- Baseline (LLM seul) ---
Francis Ford Coppola directed "The Godfather." Released in 1972...

--- RAG (SPARQL sur la KB) ---
SELECT ?director ?directorLabel WHERE {
  ?film rdfs:label ?label . FILTER(CONTAINS(?label, "Godfather"))
  ?film wdt:P57 ?director .
}
=> Q56094 | Francis Ford Coppola
```

## Hardware

- 8 GB RAM minimum
- ~10 min par modele KGE sur CPU
- ~2 GB pour le modele Ollama (qwen2.5:3b)
- Java pour Pellet (sinon le script simule le raisonnement)
