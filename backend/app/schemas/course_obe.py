from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictInt, field_validator

CO_ROW_COUNT = 5
MAPPING_COLUMN_COUNT = 14
MappingCell = StrictInt | Literal["", "-"] | None


class CourseCOPOMappingWrite(BaseModel):
    values: list[list[MappingCell]]

    model_config = ConfigDict(extra="forbid")

    @field_validator("values", mode="before")
    @classmethod
    def validate_and_normalize_values(cls, values):
        if not isinstance(values, list) or len(values) != CO_ROW_COUNT:
            raise ValueError(f"Mapping must contain exactly {CO_ROW_COUNT} CO rows.")

        normalized = []
        for row in values:
            if not isinstance(row, list) or len(row) != MAPPING_COLUMN_COUNT:
                raise ValueError(f"Each CO row must contain exactly {MAPPING_COLUMN_COUNT} mapping cells.")

            normalized_row = []
            for cell in row:
                if cell is None or cell == "" or cell == "-":
                    normalized_row.append(None)
                elif type(cell) is int and cell in (1, 2, 3):
                    normalized_row.append(cell)
                else:
                    raise ValueError("Mapping cells may only contain 1, 2, 3, blank, or '-'.")
            normalized.append(normalized_row)
        return normalized


class CourseCOPOMappingRead(BaseModel):
    subject_id: int
    section_id: int
    values: list[list[StrictInt | None]]

    model_config = ConfigDict(from_attributes=True)