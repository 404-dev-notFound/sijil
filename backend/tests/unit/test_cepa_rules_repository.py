from app.repositories.cepa_rules_repository import CepaRulesRepository


def test_india_network_switch_matches_uae_india_cepa() -> None:
    rule = CepaRulesRepository().find_matching(
        hs_code="8517.62", origin_country="India", destination_country="UAE"
    )

    assert rule is not None
    assert rule.agreement == "UAE-India CEPA"


def test_indonesia_laptop_matches_uae_indonesia_cepa() -> None:
    rule = CepaRulesRepository().find_matching(
        hs_code="8471.30", origin_country="Indonesia", destination_country="UAE"
    )

    assert rule is not None
    assert rule.agreement == "UAE-Indonesia CEPA"


def test_wrong_origin_country_does_not_match_even_with_covered_hs_code() -> None:
    """A network switch is covered under UAE-India CEPA, but not when the origin
    country is actually China — the agreement is origin-country-specific."""
    rule = CepaRulesRepository().find_matching(
        hs_code="8517.62", origin_country="China", destination_country="UAE"
    )

    assert rule is None


def test_uncovered_hs_code_does_not_match_even_with_a_covered_country_pair() -> None:
    rule = CepaRulesRepository().find_matching(
        hs_code="0101.21", origin_country="India", destination_country="UAE"
    )

    assert rule is None


def test_missing_origin_country_yields_no_match() -> None:
    rule = CepaRulesRepository().find_matching(
        hs_code="8517.62", origin_country=None, destination_country="UAE"
    )

    assert rule is None


def test_matching_is_case_insensitive_on_country_names() -> None:
    rule = CepaRulesRepository().find_matching(
        hs_code="8517.62", origin_country="india", destination_country="uae"
    )

    assert rule is not None
    assert rule.agreement == "UAE-India CEPA"
