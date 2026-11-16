from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class CustomExamPatternGroup(BaseModel):
    quantity: StrictInt = Field(..., gt=0)
    marks_per_question: float = Field(..., gt=0)

    model_config = ConfigDict(extra="forbid")


class CustomExamPatternWrite(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    groups: list[CustomExamPatternGroup] = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Pattern name cannot be empty.")
        return name


class CustomExamPatternRead(BaseModel):
    id: int
    name: str
    groups: list[CustomExamPatternGroup]

    model_config = ConfigDict(from_attributes=True)