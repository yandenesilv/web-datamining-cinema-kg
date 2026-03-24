# Cinema Knowledge Graph Pipeline

**Course:** Web Mining & Semantics - ESILV A4 S8
**Author:** Yanis Denizot
**Date:** March 2026

End-to-end pipeline that crawls cinema-related Wikipedia pages, builds an RDF knowledge graph, performs knowledge graph embedding (KGE) analysis, and implements a RAG chatbot powered by a local LLM.

## Pipeline Overview

```
1. Crawl       Wikipedia cinema pages (BFS, depth 2)
2. Extract     NER + relation extraction (spaCy)
3. Build KB    RDF/OWL ontology with private namespace
4. Align       Entity linking + predicate alignment with Wikidata
5. Expand      SPARQL expansion via Wikidata endpoint
6. Reason      SWRL rules (OWLReady2 + Pellet)
7. Embed       KGE training (TransE, ComplEx via PyKEEN)
8. RAG         NL -> SPARQL generation with Ollama + self-repair
```

## Final KB Statistics

| Metric | Value |
|--------|-------|
| Total triples | 72,409 |
| Total entities | 20,158 |
| Distinct relations | 39 |
| owl:sameAs links | 183 |

## KGE Results

| Model | MRR | Hits@1 | Hits@3 | Hits@10 |
|-------|-----|--------|--------|---------|
| **TransE** | **0.133** | 0.067 | 0.161 | 0.251 |
| ComplEx | 0.009 | 0.003 | 0.007 | 0.017 |

## Project Structure

```
project-root/
├── src/
│   ├── crawl/          # Web crawler (Wikipedia cinema)
│   ├── ie/             # Information extraction (NER + relations)
│   ├── kg/             # Knowledge graph construction & expansion
│   ├── reason/         # SWRL reasoning (family.owl + cinema KB)
│   ├── kge/            # Knowledge graph embeddings (TransE, ComplEx)
│   └── rag/            # RAG pipeline (NL -> SPARQL + Ollama)
├── data/               # KGE splits (train/valid/test) + samples
├── kg_artifacts/       # RDF files, ontology, alignment tables
├── results/            # Trained models + evaluation results
├── figures/            # t-SNE plots and visualizations
├── reports/            # Final report and reflections
├── README.md
├── requirements.txt
└── .gitignore
```

## Installation

### Prerequisites

- Python 3.10+
- Java (for Pellet SWRL reasoner, optional)
- Ollama (for RAG pipeline)

### Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/web-datamining-cinema-kg.git
cd web-datamining-cinema-kg

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Download spaCy model (for NER)
python -m spacy download en_core_web_lg
```

### Ollama Setup (for RAG)

```bash
# Install Ollama: https://ollama.ai/download
# Start the server
ollama serve

# Pull a model (we used qwen2.5:3b)
ollama pull qwen2.5:3b
# alternatives: ollama pull gemma:2b, ollama pull llama3.2:1b
```

## How to Run Each Module

### 1. Web Crawler
```bash
cd src/crawl
python crawler.py
# Output: data/crawler_output.jsonl (~150 pages)
```

### 2. Information Extraction (NER + Relations)
```bash
cd src/ie
python extractor.py
# Output: data/extracted_knowledge.csv
```

### 3. Knowledge Graph Construction
```bash
cd src/kg
python kb_builder.py        # Build initial RDF KB
python entity_linker.py      # Link entities to Wikidata + align predicates
python kb_expander.py        # Expand via SPARQL queries
# Output: kg_artifacts/expanded_kb.ttl, expanded_kb.nt
```

### 4. SWRL Reasoning
```bash
cd src/reason
python swrl_family.py        # SWRL on family ontology
python swrl_vs_embedding.py  # SWRL on cinema KB + comparison with embeddings
# Output: kg_artifacts/family.owl
```

### 5. Knowledge Graph Embeddings
```bash
cd src/kge
python step1_data_preparation.py  # Prepare train/valid/test splits
python step2_train_embeddings.py  # Train TransE + ComplEx
python step3_kb_size_sensitivity.py  # KB size impact analysis
python step4_embedding_analysis.py   # t-SNE + nearest neighbors
# Output: results/, figures/, data/
```

### 6. RAG Pipeline (Demo)
```bash
# Make sure Ollama is running: ollama serve
cd src/rag
python lab_rag_sparql_gen.py [model_name]
# Interactive CLI: type questions about cinema

# Run evaluation (5+ questions, baseline vs RAG)
python evaluation.py [model_name]
# Output: evaluation_results.json
```

## RAG Demo

Example session with qwen2.5:3b:

```
Question : Who directed The Godfather?

--- BASELINE (LLM seul, sans KB) ---
Francis Ford Coppola directed "The Godfather." This iconic film was
released in 1972 and is considered one of the greatest movies ever made.

--- RAG (LLM + Knowledge Base SPARQL) ---
[Requete SPARQL]
SELECT ?director ?directorLabel WHERE {
  ?film rdfs:label ?label . FILTER(CONTAINS(?label, "Godfather"))
  ?film <http://www.wikidata.org/prop/direct/P57> ?director .
  OPTIONAL { ?director rdfs:label ?directorLabel }
}
[Resultats] (3 lignes)
  Q56094 | Francis Ford Coppola

Question : How many films have a director in the KB?

--- RAG ---
[Resultats] 1678
```

See `reports/rag_screenshot.html` for a full demo visualization.

## Hardware Requirements

- **Minimum:** 8 GB RAM, any modern CPU
- **KGE Training:** ~10 min per model on CPU (TransE 100 epochs)
- **RAG:** Requires Ollama + ~2-4 GB for small LLM (gemma:2b)
- **SWRL:** Requires Java JRE for Pellet reasoner (fallback simulation available)

## Key Dependencies

| Library | Purpose |
|---------|---------|
| spaCy | NER and dependency parsing |
| rdflib | RDF graph manipulation and SPARQL |
| owlready2 | OWL ontology + SWRL reasoning |
| PyKEEN | Knowledge graph embedding training |
| requests | Wikidata API and Ollama API |
| scikit-learn | t-SNE, cosine similarity |
| matplotlib | Visualization |
| trafilatura | Web page text extraction |

## License

MIT License - See [LICENSE](LICENSE) file.
