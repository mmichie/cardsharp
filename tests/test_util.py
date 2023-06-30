import pytest
from cardsharp.common.util import calculate_chi_square


def test_calculate_chi_square():
    observed_values = [10, 20, 30, 40]
    expected_values = [15, 25, 35, 45]
    chi_square_stat = calculate_chi_square(observed_values, expected_values)
    expected_chi_square_stat = sum(
        (o - e) ** 2 / e for o, e in zip(observed_values, expected_values)
    )
    assert chi_square_stat == expected_chi_square_stat

    # Test with empty lists
    observed_values = []
    expected_values = []
    chi_square_stat = calculate_chi_square(observed_values, expected_values)
    assert chi_square_stat == 0

    # Test with different lengths of observed and expected values
    observed_values = [10, 20, 30, 40]
    expected_values = [15, 25]
    with pytest.raises(ValueError) as exc_info:
        calculate_chi_square(observed_values, expected_values)
    assert (
        str(exc_info.value)
        == "Observed and expected value lists must have the same length."
    )
