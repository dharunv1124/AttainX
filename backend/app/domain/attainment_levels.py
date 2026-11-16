from decimal import Decimal
from typing import Optional, Union


def classify_attainment_level(percentage: Union[Decimal, float, int]) -> Optional[int]:
    """Apply the approved workbook bands; exactly 65 percent remains unresolved."""
    value = percentage if isinstance(percentage, Decimal) else Decimal(str(percentage))

    if Decimal("55") <= value < Decimal("60"):
        return 1
    if Decimal("60") <= value < Decimal("65"):
        return 2
    if value > Decimal("65"):
        return 3
    return None