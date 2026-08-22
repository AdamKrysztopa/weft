from weft_example_graph.extraction import extract_entity_names, extract_graph_data


def test_extract_entity_names_finds_title_case_runs() -> None:
    # Act
    names = extract_entity_names("Acme Corp builds rockets. New York City loves Acme Corp.")

    # Assert
    assert names == ("Acme Corp", "New York City")


def test_extract_entity_names_drops_sentence_initial_stopwords() -> None:
    # Act
    names = extract_entity_names("The Board met Acme Corp on Tuesday. This was expected.")

    # Assert — "The", "This" are stopwords; "Tuesday" is a genuine one-word entity.
    assert names == ("Board", "Acme Corp", "Tuesday")


def test_extract_entity_names_normalises_internal_whitespace() -> None:
    # Act
    names = extract_entity_names("Acme  Corp\nbuilds things.")

    # Assert
    assert names == ("Acme Corp",)


def test_extract_entity_names_empty_text_is_empty() -> None:
    assert extract_entity_names("") == ()
    assert extract_entity_names("lowercase only, no candidates here.") == ()


def test_extract_graph_data_relates_every_pair_once() -> None:
    # Act
    entities, relations = extract_graph_data("Acme Corp met Globex Inc and Initech today.")

    # Assert — three entities, three unordered pairs, each canonically ordered.
    names = {entity.name for entity in entities}
    assert names == {"Acme Corp", "Globex Inc", "Initech"}
    pairs = {(relation.source, relation.target) for relation in relations}
    assert pairs == {
        ("Acme Corp", "Globex Inc"),
        ("Acme Corp", "Initech"),
        ("Globex Inc", "Initech"),
    }
    assert all(relation.source < relation.target for relation in relations)


def test_extract_graph_data_counts_repeated_mentions() -> None:
    # Act
    entities, _ = extract_graph_data("Acme Corp and Acme Corp again, still Acme Corp.")

    # Assert
    assert len(entities) == 1
    assert entities[0].count == 3


def test_extract_graph_data_single_entity_has_no_relations() -> None:
    # Act
    entities, relations = extract_graph_data("Only Acme Corp is mentioned here.")

    # Assert
    assert len(entities) == 1
    assert relations == ()


def test_extract_graph_data_empty_text_produces_nothing() -> None:
    entities, relations = extract_graph_data("")
    assert entities == ()
    assert relations == ()
