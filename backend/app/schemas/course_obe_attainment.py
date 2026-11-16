from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, field_validator

_INPUT_FIELDS = ("a", "b", "c", "university", "g")
_NumericInput = StrictInt | StrictFloat | None


class CourseCOAttainmentInputRow(BaseModel):
    a: _NumericInput
    b: _NumericInput
    c: _NumericInput
    university: _NumericInput
    g: _NumericInput

    model_config = ConfigDict(extra="forbid")

    @field_validator(*_INPUT_FIELDS)
    @classmethod
    def require_finite_numbers(cls, value):
        if value is not None and not Decimal(str(value)).is_finite():
            raise ValueError("Input values must be finite numbers or blank.")
        return value


class CourseCOAttainmentWrite(BaseModel):
    inputs: list[CourseCOAttainmentInputRow]

    model_config = ConfigDict(extra="forbid")

    @field_validator("inputs")
    @classmethod
    def require_five_co_rows(cls, inputs):
        if len(inputs) != 5:
            raise ValueError("Exactly five CO input rows are required.")
        return inputs


class CourseCOAttainmentResult(BaseModel):
    average: Optional[float] = None
    attainment: Optional[int] = None
    university_attainment: Optional[int] = None
    d: Optional[float] = None
    e: Optional[float] = None
    f: Optional[float] = None
    ninety_percent_f: Optional[float] = None
    ten_percent_g: Optional[float] = None
    overall_co: Optional[float] = None


class CourseCOAttainmentRead(BaseModel):
    subject_id: int
    section_id: int
    inputs: list[CourseCOAttainmentInputRow]
    results: list[CourseCOAttainmentResult]


class CoursePOAttainmentRead(BaseModel):
    subject_id: int
    section_id: int
    values: list[list[Optional[float]]]
    overall_values: list[Optional[float]]