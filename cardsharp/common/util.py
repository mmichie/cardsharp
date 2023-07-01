from typing import List


def calculate_chi_square(
    observed_values: List[float], expected_values: List[float]
) -> float:
    """
    Calculate the chi-square statistic given lists of observed and expected values.

    :param observed_values: A list of observed values
    :param expected_values: A list of expected values
    :return: The calculated chi-square statistic
    :raises ValueError: If the observed_values and expected_values lists do not have the same length

    """
    if len(observed_values) != len(expected_values):
        raise ValueError("Observed and expected value lists must have the same length.")

    chi_square_stat = sum(
        (o - e) ** 2 / e for o, e in zip(observed_values, expected_values)
    )
    return chi_square_stat
