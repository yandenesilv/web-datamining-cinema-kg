# 7 - Critical Reflection

## 7.1 Impact of Predicate Alignment Quality

Our KB contains 29 distinct relations, split between two namespaces:
- **Wikidata properties** (P57, P161, P166, etc.) — well-defined, standardized
- **Private KB predicates** (directedBy, starring, wonAward, etc.) — extracted via NLP

This dual-namespace issue creates a significant problem: `P57` (Wikidata director) and `directedBy` (private KB) encode the **same semantic meaning** but are treated as **different relations** by the embedding model. This effectively splits the training signal, reducing the model's ability to learn strong representations for either relation.

Evidence: in our relation behavior analysis, `P57` and `directedBy` did not appear as inverse or equivalent relations in the embedding space, even though they should be semantically identical. A better predicate alignment in the previous lab (merging these into a single relation) would have produced stronger embeddings.

The predicate alignment step (Step 3 of the previous lab) mapped 19 private predicates to Wikidata properties using `owl:equivalentProperty`, but these OWL-level equivalences were stripped during the KGE data preparation (we removed metadata triples). A better approach would have been to **physically merge** equivalent predicates into a single URI before training.

## 7.2 Impact of Noisy Expansion

The KB expansion via SPARQL (Step 4 of the previous lab) introduced both valuable structure and noise:

**Positive impact:**
- The expansion brought the KB from ~10K to ~72K triples, well within the recommended 50K-200K range
- KB Size Sensitivity analysis confirmed that the full dataset (55K triples, MRR=0.137) vastly outperforms the 20K subset (MRR=0.042) — a **3.3x improvement**
- New relations from Wikidata (P136/genre, P495/country, P27/nationality) enriched the graph connectivity

**Negative impact:**
- The dominant relation `P161` (cast member) accounts for **47% of all triples** (25,783 out of 55,294). This extreme imbalance biases the embedding model toward learning cast-related patterns at the expense of rarer but more informative relations
- Some expanded triples connect entities with weak semantic relevance (e.g., linking all films to generic categories like "drama film" or "United States"), creating hub nodes that distort the embedding space
- The entity "United States" has 1,669 connections — it acts as a "super-hub" that pulls many unrelated entities close together in the embedding space

## 7.3 Effect of Ontology Modeling Choices

Our ontology defines cinema-specific classes (Film, Director, Actor, Award, Festival) as subclasses of general types (Person, CreativeWork, Organization). However, since `rdf:type` triples were excluded from KGE training (they are metadata, not relational facts), **the embedding model has no direct access to ontology class information**.

This explains our t-SNE clustering results: while some semantic clusters emerge (entities connected by similar relations tend to cluster), the clustering does not cleanly separate ontology classes. Out of 3,000 sampled entities, 2,452 (82%) were classified as "Unknown" because they lacked explicit `rdf:type` in the original KB.

An alternative approach would have been to **include type triples as regular relations** (e.g., treating `rdf:type Film` as a relation), which would let the embedding model learn type-aware representations. This is a trade-off: including types adds useful structure but also increases the number of relations and may introduce noise from overly generic types like "human" (258 connections in our KB).

## 7.4 Open-World Assumption vs Embedding Assumptions

**OWA (Open-World Assumption)** — used in ontologies and SWRL reasoning:
- Absence of a triple does not mean it is false
- If we don't know that "Nolan wonAward Oscar", it simply means we don't have that information
- Our SWRL rule correctly did NOT infer Nolan as an AwardWinningDirector (Inception didn't have a wonAward triple)

**CWA (Closed-World Assumption)** — implicitly used in KGE training:
- During negative sampling, the model treats **any non-existing triple as false**
- If (Nolan, wonAward, Oscar) is not in the training set, it is used as a negative example
- This creates a bias: the model learns that missing links are likely false, even when they are simply unknown

This fundamental mismatch explains why KGE evaluation metrics (MRR=0.133) are modest: the model is penalized for ranking true-but-missing triples highly. The **filtered evaluation** protocol (used by PyKEEN) partially mitigates this by removing known true triples from the ranking, but it cannot account for true triples that exist in reality but are absent from our KB.

## 7.5 How the Previous Lab Design Influenced Embedding Performance

Several design decisions from the previous lab directly impacted our KGE results:

1. **Crawler scope (cinema domain)**: By focusing on Wikipedia cinema pages, we obtained a thematically coherent KB. This helps embeddings because entities share a common semantic space. However, the limited scope also means many real-world connections are missing.

2. **NER + Relation Extraction quality**: The spaCy-based extraction used dependency parsing with a "co-occurs with" fallback. The fallback relation (`relatedTo`) accounts for 587 triples — these are essentially noise that the model must work around.

3. **Entity linking threshold (0.7 confidence)**: This threshold balanced precision and recall. Higher thresholds would have produced fewer but more accurate Wikidata alignments, leading to cleaner but smaller expansion. Lower thresholds would have introduced more errors.

4. **SPARQL expansion strategy**: Bulk queries for cinema-relevant properties (P57, P161, P166, etc.) were effective but created the P161 dominance problem mentioned above. A more balanced expansion strategy (capping triples per relation type) would have produced a more uniform distribution.

5. **Graph connectivity**: The top-10 most connected entities are dominated by generic nodes (United States, drama film, GB). These hub nodes reduce the discriminative power of embeddings by pulling many unrelated entities into the same region of the embedding space. Pre-processing to remove or downsample such hubs would likely improve performance.

## 7.6 Model-Specific Observations

**TransE (MRR=0.133)** performed well because:
- Cinema relations are mostly **functional** (a film has one director, one release date)
- TransE's translational assumption (h + r = t) is well-suited for 1-to-1 and 1-to-N relations
- Tail prediction (Hits@10=30.2%) significantly outperformed head prediction (Hits@10=20.0%), indicating the model is better at predicting "what object relates to this subject" than the reverse

**ComplEx (MRR=0.009)** performed poorly because:
- ComplEx uses complex-valued embeddings designed for handling symmetric/antisymmetric relations
- With only 100 epochs and the default configuration, ComplEx requires more training time to converge
- The relatively small number of relations (29) does not fully leverage ComplEx's ability to model complex relation patterns
- ComplEx would likely benefit from hyperparameter tuning (higher embedding dimension, more epochs, different learning rate)

These observations align with the expected outcomes stated in the lab:
- "TransE struggles with complex relations" — partially confirmed, but our KB has mostly simple relations
- "ComplEx handles asymmetric relations better" — not observed due to insufficient training
- "Larger KB improves stability" — strongly confirmed (MRR 0.042 vs 0.137)
