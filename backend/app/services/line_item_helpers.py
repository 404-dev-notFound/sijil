from app.models.line_item import LineItem


def effective_hs_code(line_item: LineItem) -> str | None:
    """The user's override always wins over the AI's suggestion — shared by every
    worker service that needs "which HS code does this line item actually count as
    right now" (PermitTriageService, CEPAOriginService). A line item with no
    classification yet (or hs_code still null, e.g. requires_manual_review) has no
    effective code and callers should skip it rather than guess.
    """
    classification = line_item.classification
    if classification is None:
        return None
    hs_code: str | None = classification.user_override_hs_code or classification.hs_code
    return hs_code
