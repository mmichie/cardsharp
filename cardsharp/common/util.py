def calculate_chi_square(observed_values, expected_values):
    chi_square_stat = sum(
        (o - e) ** 2 / e for o, e in zip(observed_values, expected_values)
    )
    return chi_square_stat
