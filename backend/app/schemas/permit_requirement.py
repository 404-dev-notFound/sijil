import uuid

from pydantic import BaseModel, ConfigDict


class PermitRequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    regulator: str
    permit_type: str
    applies_to_line_items: list[str]
    estimated_processing_time_days: int
    reference_link: str


class PermitsResponse(BaseModel):
    items: list[PermitRequirementOut]
    no_permits_required: bool
