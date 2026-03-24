"""
Cours 5 - SWRL Reasoning on Family Ontology (family.owl)
Course: Web Mining & Semantics - ESILV

Ce script fait 2 choses :
1. Cree une ontologie familiale (family.owl) avec des individus
2. Definit des regles SWRL pour inferer des relations familiales :
   - hasUncle : hasParent(?x,?y) ^ hasBrother(?y,?z) -> hasUncle(?x,?z)
   - hasGrandparent : hasParent(?x,?y) ^ hasParent(?y,?z) -> hasGrandparent(?x,?z)
   - hasCousin : hasParent(?x,?y) ^ hasSibling(?y,?z) ^ hasChild(?z,?w) -> hasCousin(?x,?w)
3. Execute le raisonnement et affiche les inferences

Requis par le rapport final, section 3 (Reasoning - SWRL).
"""

from owlready2 import (
    get_ontology, Thing, ObjectProperty, Imp,
    sync_reasoner_pellet, default_world
)
import os


# -- Configuration -------------------------------------------------------------

OUTPUT_FILE = "../../kg_artifacts/family.owl"


# -- Creation de l'ontologie ---------------------------------------------------

def create_family_ontology():
    """
    Cree une ontologie familiale avec :
    - Classes : Person, Male, Female
    - Properties : hasParent, hasChild, hasBrother, hasSibling, hasUncle, hasGrandparent, hasCousin
    - Individus : une famille sur 3 generations
    - Regles SWRL pour inferer hasUncle, hasGrandparent, hasCousin
    """
    print("=" * 60)
    print("  SWRL Reasoning on Family Ontology")
    print("=" * 60)

    onto = get_ontology("http://example.org/family.owl#")

    with onto:
        # ── Classes ──
        class Person(Thing):
            pass

        class Male(Person):
            pass

        class Female(Person):
            pass

        # ── Object Properties ──
        class hasParent(ObjectProperty):
            domain = [Person]
            range = [Person]

        class hasChild(ObjectProperty):
            domain = [Person]
            range = [Person]
            inverse_property = hasParent

        class hasBrother(ObjectProperty):
            domain = [Person]
            range = [Male]

        class hasSibling(ObjectProperty):
            domain = [Person]
            range = [Person]

        class hasUncle(ObjectProperty):
            domain = [Person]
            range = [Male]

        class hasGrandparent(ObjectProperty):
            domain = [Person]
            range = [Person]

        class hasCousin(ObjectProperty):
            domain = [Person]
            range = [Person]

        class hasSpouse(ObjectProperty):
            domain = [Person]
            range = [Person]

        # ── SWRL Rules ──

        # Regle 1 : hasUncle
        # Si X a un parent Y, et Y a un frere Z, alors X a un oncle Z
        rule1 = Imp()
        rule1.set_as_rule(
            "Person(?x), hasParent(?x, ?y), hasBrother(?y, ?z) -> hasUncle(?x, ?z)"
        )
        print("\n[*] Regle SWRL 1 : hasParent(?x,?y) ^ hasBrother(?y,?z) -> hasUncle(?x,?z)")

        # Regle 2 : hasGrandparent
        # Si X a un parent Y, et Y a un parent Z, alors X a un grand-parent Z
        rule2 = Imp()
        rule2.set_as_rule(
            "Person(?x), hasParent(?x, ?y), hasParent(?y, ?z) -> hasGrandparent(?x, ?z)"
        )
        print("[*] Regle SWRL 2 : hasParent(?x,?y) ^ hasParent(?y,?z) -> hasGrandparent(?x,?z)")

        # Regle 3 : hasCousin
        # Si X a un parent Y, Y a un sibling Z, et Z a un enfant W, alors X et W sont cousins
        rule3 = Imp()
        rule3.set_as_rule(
            "Person(?x), hasParent(?x, ?y), hasSibling(?y, ?z), hasChild(?z, ?w) -> hasCousin(?x, ?w)"
        )
        print("[*] Regle SWRL 3 : hasParent(?x,?y) ^ hasSibling(?y,?z) ^ hasChild(?z,?w) -> hasCousin(?x,?w)")

        # ── Individus : La famille Dupont ──
        print("\n[*] Creation de la famille Dupont (3 generations)...")

        # Generation 1 : Grands-parents
        jean = Male("Jean")       # Grand-pere
        marie = Female("Marie")   # Grand-mere

        # Generation 2 : Parents + oncle/tante
        pierre = Male("Pierre")   # Pere (fils de Jean et Marie)
        sophie = Female("Sophie") # Mere (epouse de Pierre)
        paul = Male("Paul")       # Oncle (frere de Pierre, fils de Jean et Marie)
        claire = Female("Claire") # Tante (epouse de Paul)

        # Generation 3 : Enfants + cousin
        lucas = Male("Lucas")     # Fils de Pierre et Sophie
        emma = Female("Emma")     # Fille de Pierre et Sophie
        hugo = Male("Hugo")       # Fils de Paul et Claire (cousin de Lucas et Emma)

        # ── Relations explicites ──
        # Parents de Pierre et Paul
        pierre.hasParent.append(jean)
        pierre.hasParent.append(marie)
        paul.hasParent.append(jean)
        paul.hasParent.append(marie)

        # Pierre et Paul sont freres / siblings
        pierre.hasBrother.append(paul)
        paul.hasBrother.append(pierre)
        pierre.hasSibling.append(paul)
        paul.hasSibling.append(pierre)

        # Parents de Lucas et Emma
        lucas.hasParent.append(pierre)
        lucas.hasParent.append(sophie)
        emma.hasParent.append(pierre)
        emma.hasParent.append(sophie)

        # Parents de Hugo
        hugo.hasParent.append(paul)
        hugo.hasParent.append(claire)

        # Mariages
        pierre.hasSpouse.append(sophie)
        paul.hasSpouse.append(claire)
        jean.hasSpouse.append(marie)

        # Enfants (inverse de hasParent, mais on les ajoute explicitement aussi)
        jean.hasChild.extend([pierre, paul])
        marie.hasChild.extend([pierre, paul])
        pierre.hasChild.extend([lucas, emma])
        sophie.hasChild.extend([lucas, emma])
        paul.hasChild.append(hugo)
        claire.hasChild.append(hugo)

        # Siblings pour la generation 3
        lucas.hasSibling.append(emma)
        emma.hasSibling.append(lucas)

    # Afficher l'etat avant raisonnement
    print("\n" + "-" * 60)
    print("  AVANT raisonnement SWRL :")
    print("-" * 60)
    print(f"  hasUncle         : {[(str(s), str(o)) for s in onto.individuals() for o in s.hasUncle]}")
    print(f"  hasGrandparent   : {[(str(s), str(o)) for s in onto.individuals() for o in s.hasGrandparent]}")
    print(f"  hasCousin        : {[(str(s), str(o)) for s in onto.individuals() for o in s.hasCousin]}")

    # Sauvegarder l'ontologie avant raisonnement
    onto.save(file=OUTPUT_FILE, format="rdfxml")
    print(f"\n[*] Ontologie sauvegardee dans {OUTPUT_FILE}")

    return onto


# -- Raisonnement SWRL --------------------------------------------------------

def run_reasoning(onto):
    """Execute le raisonnement SWRL avec Pellet (ou simulation si Java absent)."""

    print("\n[*] Execution du raisonnement SWRL...")

    try:
        sync_reasoner_pellet(infer_property_values=True, infer_data_property_values=True)
        print("[+] Raisonnement Pellet termine avec succes.")
        pellet_ok = True
    except Exception as e:
        print(f"[!] Pellet a echoue : {e}")
        print("[*] Pellet necessite Java. Simulation manuelle...")
        pellet_ok = False

    if pellet_ok:
        # Afficher les inferences
        print("\n" + "-" * 60)
        print("  APRES raisonnement SWRL (inferences Pellet) :")
        print("-" * 60)

        uncles = [(str(s).split(".")[-1], str(o).split(".")[-1])
                  for s in onto.individuals() for o in s.hasUncle]
        grandparents = [(str(s).split(".")[-1], str(o).split(".")[-1])
                        for s in onto.individuals() for o in s.hasGrandparent]
        cousins = [(str(s).split(".")[-1], str(o).split(".")[-1])
                   for s in onto.individuals() for o in s.hasCousin]

        print(f"\n  hasUncle (infere) :")
        for s, o in uncles:
            print(f"    {s} hasUncle {o}")

        print(f"\n  hasGrandparent (infere) :")
        for s, o in grandparents:
            print(f"    {s} hasGrandparent {o}")

        print(f"\n  hasCousin (infere) :")
        for s, o in cousins:
            print(f"    {s} hasCousin {o}")

        return uncles, grandparents, cousins

    else:
        return run_simulation()


def run_simulation():
    """Simulation manuelle des regles SWRL (quand Java/Pellet n'est pas disponible)."""

    print("\n" + "-" * 60)
    print("  SIMULATION manuelle des regles SWRL :")
    print("-" * 60)

    # Donnees
    has_parent = {
        "Pierre": ["Jean", "Marie"],
        "Paul": ["Jean", "Marie"],
        "Lucas": ["Pierre", "Sophie"],
        "Emma": ["Pierre", "Sophie"],
        "Hugo": ["Paul", "Claire"],
    }
    has_brother = {
        "Pierre": ["Paul"],
        "Paul": ["Pierre"],
    }
    has_sibling = {
        "Pierre": ["Paul"],
        "Paul": ["Pierre"],
        "Lucas": ["Emma"],
        "Emma": ["Lucas"],
    }
    has_child = {
        "Jean": ["Pierre", "Paul"],
        "Marie": ["Pierre", "Paul"],
        "Pierre": ["Lucas", "Emma"],
        "Sophie": ["Lucas", "Emma"],
        "Paul": ["Hugo"],
        "Claire": ["Hugo"],
    }

    # Regle 1 : hasUncle
    print("\n  Regle 1 : hasParent(?x,?y) ^ hasBrother(?y,?z) -> hasUncle(?x,?z)")
    uncles = []
    for x, parents in has_parent.items():
        for y in parents:
            if y in has_brother:
                for z in has_brother[y]:
                    uncles.append((x, z))
                    print(f"    {x} hasParent {y}, {y} hasBrother {z} => {x} hasUncle {z}")

    # Regle 2 : hasGrandparent
    print("\n  Regle 2 : hasParent(?x,?y) ^ hasParent(?y,?z) -> hasGrandparent(?x,?z)")
    grandparents = []
    for x, parents_x in has_parent.items():
        for y in parents_x:
            if y in has_parent:
                for z in has_parent[y]:
                    grandparents.append((x, z))
                    print(f"    {x} hasParent {y}, {y} hasParent {z} => {x} hasGrandparent {z}")

    # Regle 3 : hasCousin
    print("\n  Regle 3 : hasParent(?x,?y) ^ hasSibling(?y,?z) ^ hasChild(?z,?w) -> hasCousin(?x,?w)")
    cousins = []
    for x, parents_x in has_parent.items():
        for y in parents_x:
            if y in has_sibling:
                for z in has_sibling[y]:
                    if z in has_child:
                        for w in has_child[z]:
                            if w != x:
                                cousins.append((x, w))
                                print(f"    {x} hasParent {y}, {y} hasSibling {z}, {z} hasChild {w} => {x} hasCousin {w}")

    # Resume
    print("\n" + "-" * 60)
    print("  RESUME DES INFERENCES :")
    print("-" * 60)
    print(f"\n  hasUncle : {uncles}")
    print(f"  Attendu  : Lucas et Emma ont Paul comme oncle, Hugo a Pierre comme oncle")
    print(f"\n  hasGrandparent : {grandparents}")
    print(f"  Attendu  : Lucas et Emma ont Jean et Marie comme grands-parents")
    print(f"\n  hasCousin : {cousins}")
    print(f"  Attendu  : Lucas/Emma sont cousins de Hugo")

    return uncles, grandparents, cousins


# -- Verification --------------------------------------------------------------

def verify_results(uncles, grandparents, cousins):
    """Verifie que les inferences sont correctes."""
    print("\n" + "=" * 60)
    print("  VERIFICATION DES RESULTATS")
    print("=" * 60)

    # Verification hasUncle
    expected_uncles = {("Lucas", "Paul"), ("Emma", "Paul"), ("Hugo", "Pierre")}
    actual_uncles = set(uncles)
    uncle_ok = expected_uncles.issubset(actual_uncles)
    print(f"\n  hasUncle : {'CORRECT' if uncle_ok else 'INCORRECT'}")
    if not uncle_ok:
        print(f"    Attendu (subset) : {expected_uncles}")
        print(f"    Obtenu           : {actual_uncles}")

    # Verification hasGrandparent
    expected_gp = {("Lucas", "Jean"), ("Lucas", "Marie"), ("Emma", "Jean"), ("Emma", "Marie")}
    actual_gp = set(grandparents)
    gp_ok = expected_gp.issubset(actual_gp)
    print(f"  hasGrandparent : {'CORRECT' if gp_ok else 'INCORRECT'}")
    if not gp_ok:
        print(f"    Attendu (subset) : {expected_gp}")
        print(f"    Obtenu           : {actual_gp}")

    # Verification hasCousin
    expected_cousins_pairs = {("Lucas", "Hugo"), ("Emma", "Hugo")}
    actual_cousins = set(cousins)
    cousins_ok = expected_cousins_pairs.issubset(actual_cousins)
    print(f"  hasCousin : {'CORRECT' if cousins_ok else 'INCORRECT'}")
    if not cousins_ok:
        print(f"    Attendu (subset) : {expected_cousins_pairs}")
        print(f"    Obtenu           : {actual_cousins}")

    all_ok = uncle_ok and gp_ok and cousins_ok
    print(f"\n  Resultat global : {'TOUS CORRECTS' if all_ok else 'CERTAINS INCORRECTS'}")
    return all_ok


# -- Main ----------------------------------------------------------------------

def main():
    onto = create_family_ontology()
    uncles, grandparents, cousins = run_reasoning(onto)
    verify_results(uncles, grandparents, cousins)

    print("\n" + "=" * 60)
    print("  SWRL Family Reasoning Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
