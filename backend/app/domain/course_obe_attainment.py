from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.domain.attainment_levels import classify_attainment_level

_ZERO = Decimal("0")
_TWENTY_PERCENT = Decimal("0.20")
_EIGHTY_PERCENT = Decimal("0.80")
_NINETY_PERCENT = Decimal("0.90")
_TEN_PERCENT = Decimal("0.10")


def _decimal_value(value: Any) -> Optional[Decimal]:
    return None if value is None else Decimal(str(value))


def _as_float(value: Optional[Decimal]) -> Optional[float]:
    return None if value is None else float(value)


def calculate_course_overall_co_attainment(
    inputs: List[Dict[str, Any]],
) -> List[Dict[str, Optional[float | int]]]:
    """Calculate Table 2 results without reading or changing exam/marks data."""
    results: List[Dict[str, Optional[float | int]]] = []
    for row in inputs:
        assessment_values = [_decimal_value(row[key]) for key in ("a", "b", "c")]
        entered_assessments = [value for value in assessment_values if value is not None]
        average = (
            sum(entered_assessments, _ZERO) / Decimal(len(entered_assessments))
            if entered_assessments
            else None
        )

        attainment = classify_attainment_level(average) if average is not None else None
        university = _decimal_value(row["university"])
        university_attainment = (
            classify_attainment_level(university) if university is not None else None
        )
        g_value = _decimal_value(row["g"])

        d_value = Decimal(attainment) * _TWENTY_PERCENT if attainment is not None else None
        e_value = (
            Decimal(university_attainment) * _EIGHTY_PERCENT
            if university_attainment is not None
            else None
        )
        f_value = d_value + e_value if d_value is not None and e_value is not None else None
        ninety_percent_f = f_value * _NINETY_PERCENT if f_value is not None else None
        ten_percent_g = g_value * _TEN_PERCENT if g_value is not None else None
        overall_co = (
            ninety_percent_f + ten_percent_g
            if ninety_percent_f is not None and ten_percent_g is not None
            else None
        )

        results.append({
            "average": _as_float(average),
            "attainment": attainment,
            "university_attainment": university_attainment,
            "d": _as_float(d_value),
            "e": _as_float(e_value),
            "f": _as_float(f_value),
            "ninety_percent_f": _as_float(ninety_percent_f),
            "ten_percent_g": _as_float(ten_percent_g),
            "overall_co": _as_float(overall_co),
        })
    return results


def calculate_course_po_attainment(
    mappings: List[List[Optional[int]]],
    overall_results: List[Dict[str, Any]],
) -> List[List[Optional[float]]]:
    """Calculate derived PO/PSO attainment from mapping and Overall CO results."""
    values: List[List[Optional[float]]] = []
    for row_index, mapping_row in enumerate(mappings):
        overall_co = _decimal_value(overall_results[row_index]["overall_co"])
        values.append([
            None
            if mapping is None or overall_co is None
            else float(Decimal(mapping) * overall_co / Decimal("3"))
            for mapping in mapping_row
        ])
    return values


def calculate_course_po_attainment_overall(
    values: List[List[Optional[float]]],
) -> List[Optional[float]]:
    """Average available CO-level PO/PSO values independently by column."""
    if not values:
        return []

    overall_values: List[Optional[float]] = []
    for column_index in range(len(values[0])):
        column_values = [
            _decimal_value(row[column_index])
            for row in values
            if column_index < len(row)
        ]
        entered_values = [value for value in column_values if value is not None]
        average = (
            sum(entered_values, _ZERO) / Decimal(len(entered_values))
            if entered_values
            else None
        )
        overall_values.append(_as_float(average))
    return overall_values