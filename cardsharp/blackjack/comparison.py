"""Common Random Numbers (CRN) for blackjack rule comparison.

When estimating the EV difference between two rule sets via Monte Carlo,
running each rule set on the same shuffled shoes (rather than independent
streams) makes the variance of the difference proportional to the strategy
divergence between the rules, not the deck-shuffle noise. In practice
this tightens the CI on (HE_A - HE_B) by 10-100x compared with two
independent runs of the same total budget.

This module compares N rule sets across N_rounds shared shoe-shuffles and
returns per-rule house-edge estimates with their independent CIs plus
paired-difference estimates with much tighter CIs.

The strategy used for all rule sets is BasicStrategy (stateless). CRN
with stateful strategies like card counting would require a different
design: counters need continuous shoe state across rounds, which is
exactly what per-round CRN reset destroys.
"""

import math
import random
from dataclasses import dataclass
from statistics import NormalDist
from typing import Dict, Optional, Tuple

from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.state import _state_placing_bets
from cardsharp.blackjack.stats import SimulationStats
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.common.io_interface import DummyIOInterface
from cardsharp.common.shoe import Shoe


@dataclass
class PairedDiff:
    """Welford accumulator for one paired-sample difference series."""

    n: int = 0
    mean: float = 0.0
    M2: float = 0.0

    def update(self, diff: float):
        self.n += 1
        delta = diff - self.mean
        self.mean += delta / self.n
        self.M2 += delta * (diff - self.mean)

    def confidence_interval(
        self, confidence: float = 0.95
    ) -> Optional[Tuple[float, float, float, float]]:
        """Return (mean, lo, hi, half_width) for a normal-approx CI on
        the paired-sample mean. None if n<2."""
        if self.n < 2:
            return None
        var = self.M2 / (self.n - 1)
        se = math.sqrt(var / self.n)
        z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
        half = z * se
        return self.mean, self.mean - half, self.mean + half, half


@dataclass
class ComparisonResult:
    """Output of compare_rules.

    per_rule_stats: independent house-edge accumulator per rule label.
    paired_diffs: paired-sample diff per ordered pair (a, b) with a<b
        in iteration order. Diff is HE_a - HE_b in fraction units.
    """

    per_rule_stats: Dict[str, SimulationStats]
    paired_diffs: Dict[Tuple[str, str], PairedDiff]
    num_rounds: int
    seed: int

    def print_report(self, confidence: float = 0.95):
        ci_pct = int(round(confidence * 100))
        print(
            f"CRN comparison ({self.num_rounds:,} rounds, seed={self.seed})"
        )
        print()
        print("Per-rule house edge (independent CIs):")
        for label, stats in self.per_rule_stats.items():
            res = stats.house_edge_with_ci(confidence)
            if res is None:
                print(f"  {label}: insufficient data")
                continue
            he, lo, hi, half = res
            print(
                f"  {label}: {he * 100:+.4f}% +/- {half * 100:.4f}% "
                f"({ci_pct}% CI: [{lo * 100:+.4f}%, {hi * 100:+.4f}%])"
            )
        print()
        print("Paired differences (CRN, tighter CIs):")
        for (a, b), diff in self.paired_diffs.items():
            res = diff.confidence_interval(confidence)
            if res is None:
                print(f"  {a} - {b}: insufficient data")
                continue
            m, lo, hi, half = res
            print(
                f"  {a} - {b}: {m * 100:+.4f}% +/- {half * 100:.4f}% "
                f"({ci_pct}% CI: [{lo * 100:+.4f}%, {hi * 100:+.4f}%])"
            )


def compare_rules(
    rules_dict: Dict[str, Rules],
    num_rounds: int,
    seed: Optional[int] = None,
    initial_bankroll: int = 10_000_000,
    use_solver_strategy: bool = False,
    num_players: int = 1,
) -> ComparisonResult:
    """Compare N rule sets via Common Random Numbers.

    For each round k, every rule set is played against a shoe that was
    shuffled from the same seed -- so all rule sets see the same upcard,
    same hole card, same player initial cards, and the same hit-card
    sequence up to the point where their player decisions diverge.

    By default BasicStrategy (the static CSV) is used for every rule
    set. With use_solver_strategy=True, each rule set gets its own
    optimal strategy from the solver, which is required for comparisons
    that only differ in player-decision incentives (e.g. DAS vs no-DAS
    -- the static CSV doesn't branch on DAS, so it would report a zero
    diff). Counting strategies need continuous shoe state, which CRN's
    per-round reset destroys, so they're not supported here either way.

    With num_players > 1 the table seats num_players players each round,
    all using the same strategy; per-round X is the bet-weighted mean
    profit-per-bet across the table. The CRN guarantee still holds:
    every rule set sees the same shoe and so the same per-position deal.

    Returns per-rule SimulationStats plus a PairedDiff for every ordered
    pair (a, b) with a appearing before b in dict iteration order.
    """
    # Avoid circular import at module load
    from cardsharp.blackjack.blackjack import BlackjackGame

    if seed is None:
        seed = random.SystemRandom().randint(0, 2 ** 63 - 1)

    rng = random.Random(seed)
    round_seeds = [rng.randint(0, 2 ** 63 - 1) for _ in range(num_rounds)]

    per_rule_stats = {label: SimulationStats() for label in rules_dict}
    labels = list(rules_dict.keys())
    pairs = [
        (labels[i], labels[j])
        for i in range(len(labels))
        for j in range(i + 1, len(labels))
    ]
    paired_diffs = {pair: PairedDiff() for pair in pairs}

    if use_solver_strategy:
        from cardsharp.blackjack.solver import solve
        from cardsharp.blackjack.strategy import SolverStrategy
        # mode="auto" picks combinatorial for ≤2 decks (matches WoO),
        # exact for 3-4 decks, fast for 5+; tightens ground-truth strategy
        # for small-deck rule comparisons without slowing 6-deck cases.
        strategy_for = {
            label: SolverStrategy(solve(rules, mode="auto"))
            for label, rules in rules_dict.items()
        }
    else:
        shared_strategy = BasicStrategy()
        strategy_for = {label: shared_strategy for label in rules_dict}

    io = DummyIOInterface()

    player_names = (
        ["Sim"] if num_players == 1
        else [f"Sim{i + 1}" for i in range(num_players)]
    )

    for k in range(num_rounds):
        round_he: Dict[str, float] = {}

        for label, rules in rules_dict.items():
            # Re-seed global random so this rule's shoe shuffles the
            # same way as every other rule's shoe in this round.
            random.seed(round_seeds[k])
            shoe = Shoe(
                num_decks=rules.num_decks,
                penetration=rules.penetration,
                burn_cards=rules.burn_cards,
                deck_factory=(
                    rules.variant.create_deck if rules.variant else None
                ),
            )

            game = BlackjackGame(rules, io, shoe)
            players = [
                Player(name, io, strategy_for[label],
                       initial_money=initial_bankroll)
                for name in player_names
            ]
            for player in players:
                game.add_player(player)
            game.set_state(_state_placing_bets)

            money_before = sum(p.money for p in players)
            game.play_round()
            net = sum(p.money for p in players) - money_before
            total_bet = sum(p.total_bets for p in players)
            init_bet = sum(p.initial_bets for p in players)
            if init_bet == 0:
                init_bet = rules.min_bet * num_players

            per_rule_stats[label].record_round(net, init_bet, total_bet)
            round_he[label] = -net / init_bet if init_bet > 0 else 0.0

        for (a, b), diff in paired_diffs.items():
            diff.update(round_he[a] - round_he[b])

    return ComparisonResult(
        per_rule_stats=per_rule_stats,
        paired_diffs=paired_diffs,
        num_rounds=num_rounds,
        seed=seed,
    )
