from app.repositories.permit_rules_repository import PermitRulesRepository


def test_telecom_hs_code_matches_tdra() -> None:
    """The Phase 5 definition of done: a shipment containing a telecom device
    correctly surfaces the TDRA requirement."""
    matches = PermitRulesRepository().find_matching("8517.12")

    regulators = {rule.regulator for rule in matches}
    assert "TDRA" in regulators


def test_medical_device_hs_code_matches_both_esma_moiat_and_mohap() -> None:
    """implementation plan Section 8's explicit example: medical devices ->
    ESMA/MoIAT + MOHAP (both regulators apply to the same HS code)."""
    matches = PermitRulesRepository().find_matching("9018.90")

    regulators = {rule.regulator for rule in matches}
    assert "ESMA/MoIAT" in regulators
    assert "MOHAP" in regulators


def test_food_hs_code_matches_moccae() -> None:
    matches = PermitRulesRepository().find_matching("0803.90")

    regulators = {rule.regulator for rule in matches}
    assert "MOCCAE" in regulators


def test_non_regulated_hs_code_matches_nothing() -> None:
    """The Phase 5 definition of done: a shipment of ordinary non-regulated goods
    (t-shirts) yields no matching permit rules at all."""
    matches = PermitRulesRepository().find_matching("6109.10")

    assert matches == []


def test_matching_is_insensitive_to_hs_code_dot_formatting() -> None:
    dotted = PermitRulesRepository().find_matching("8517.12")
    undotted = PermitRulesRepository().find_matching("851712")

    assert {rule.regulator for rule in dotted} == {rule.regulator for rule in undotted}
