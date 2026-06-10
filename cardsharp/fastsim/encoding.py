"""Encoders that bridge cardsharp objects to the cardsharp_core extension.

The Rust core consumes strategy charts as a flat 370-byte table -- 18 hard
rows (totals 4-21), 9 soft rows (13-21), and 10 pair rows (2-9, ten-value,
ace), each with 10 dealer-upcard columns (2-9, ten, ace). Cell bytes:
0=Hit, 1=Stand, 2=Double, 3=DoubleStand, 4=Split, 5=Surrender.

The CSV charts and the solver remain the single source of truth for what
the strategy says; this module only flattens the tables BasicStrategy has
already built.
"""

from cardsharp.blackjack.action import Action

try:
    import cardsharp_core

    CORE_AVAILABLE = True
except ImportError:  # extension not built; pure-Python engine still works
    cardsharp_core = None
    CORE_AVAILABLE = False

STRATEGY_TABLE_BYTES = 370

_CELL_CODES = {
    Action.HIT: 0,
    Action.STAND: 1,
    Action.DOUBLE: 2,
    "DS": 3,  # BasicStrategy's _DOUBLE_STAND string sentinel
    Action.SPLIT: 4,
    Action.SURRENDER: 5,
}


def encode_strategy_table(strategy, rules=None) -> bytes:
    """Flatten a BasicStrategy-shaped table for the Rust core.

    If ``rules`` is provided and the game is S17, the strategy's S17
    overrides are applied first, mirroring the lazy patch that
    ``BasicStrategy.decide_action`` performs on its first call.
    """
    if rules is not None and not rules.dealer_hit_soft_17 and not strategy._s17_applied:
        strategy._apply_s17_overrides()

    out = bytearray()
    for table, expected_rows in (
        (strategy.hard_table, 18),
        (strategy.soft_table, 9),
        (strategy.pair_table, 10),
    ):
        if len(table) != expected_rows:
            raise ValueError(
                f"strategy table has {len(table)} rows, expected {expected_rows}"
            )
        for row in table:
            if len(row) != 10:
                raise ValueError(f"strategy row has {len(row)} columns, expected 10")
            for cell in row:
                out.append(_CELL_CODES[cell])

    assert len(out) == STRATEGY_TABLE_BYTES
    return bytes(out)


def rules_kwargs(rules) -> dict:
    """Map a cardsharp Rules object onto cardsharp_core.Rules arguments.

    The core implements the classic variant only; other variants stay on
    the pure-Python engine (they need their own validators and payout
    calculators, not just deck composition).
    """
    if getattr(rules, "variant_name", "classic") != "classic":
        raise ValueError(
            f"cardsharp_core supports the classic variant only, got "
            f"'{rules.variant_name}'"
        )

    return {
        "blackjack_payout": rules.blackjack_payout,
        "dealer_hit_soft_17": rules.dealer_hit_soft_17,
        "allow_split": rules.allow_split,
        "allow_double_down": rules.allow_double_down,
        "allow_insurance": rules.allow_insurance,
        "allow_surrender": rules.allow_surrender,
        "allow_early_surrender": rules.allow_early_surrender,
        "allow_double_after_split": rules.allow_double_after_split,
        "allow_resplitting": rules.allow_resplitting,
        "dealer_peek": rules.dealer_peek,
        "num_decks": rules.num_decks,
        "min_bet": rules.min_bet,
        "max_bet": rules.max_bet,
        "max_splits": rules.max_splits,
        "insurance_payout": rules.insurance_payout,
        "five_card_charlie": rules.five_card_charlie,
        "penetration": rules.penetration,
        "burn_cards": rules.burn_cards,
        "resplit_aces": rules.resplit_aces,
        "hit_split_aces": rules.hit_split_aces,
        "allow_obo": getattr(rules, "allow_obo", True),
        "use_csm": rules.is_using_csm(),
        "double_on": rules.double_on,
    }


def make_core_rules(rules):
    """Build a cardsharp_core.Rules from a cardsharp Rules object."""
    if not CORE_AVAILABLE:
        raise RuntimeError(
            "cardsharp_core extension is not installed (uv sync --extra fast)"
        )
    return cardsharp_core.Rules(**rules_kwargs(rules))


_DEVIATION_CODES = {Action.HIT: 0, Action.STAND: 1, Action.DOUBLE: 2}


def encode_counting_config(strategy):
    """Build a cardsharp_core.CountingConfig from a CountingStrategy.

    The Illustrious 18 deviation table crosses the boundary as data, so
    cardsharp.blackjack.strategy stays the single source of truth: edits
    to _COUNTING_DEVIATIONS reach the core without touching Rust.
    """
    if not CORE_AVAILABLE:
        raise RuntimeError(
            "cardsharp_core extension is not installed (uv sync --extra fast)"
        )
    from cardsharp.blackjack.strategy import _COUNTING_DEVIATIONS

    deviations = [
        (
            hand_value,
            is_soft,
            dealer_value,
            float(threshold),
            _DEVIATION_CODES[above] if above else None,
            _DEVIATION_CODES[below] if below else None,
        )
        for hand_value, is_soft, dealer_value, threshold, above, below in _COUNTING_DEVIATIONS
    ]
    return cardsharp_core.CountingConfig(deviations, float(strategy.initial_decks))
