"""Type stubs for the cardsharp_core Rust extension."""

STRATEGY_TABLE_BYTES: int

def engine_version() -> str: ...
def ping(value: int) -> int: ...

class Rules:
    blackjack_payout: float
    dealer_hit_soft_17: bool
    allow_split: bool
    allow_double_down: bool
    allow_insurance: bool
    allow_surrender: bool
    allow_early_surrender: bool
    allow_double_after_split: bool
    allow_resplitting: bool
    dealer_peek: bool
    num_decks: int
    min_bet: float
    max_bet: float
    max_splits: int
    insurance_payout: float
    five_card_charlie: bool
    penetration: float
    burn_cards: int
    resplit_aces: bool
    hit_split_aces: bool
    allow_obo: bool
    use_csm: bool
    double_on: str

    def __init__(
        self,
        blackjack_payout: float = 1.5,
        dealer_hit_soft_17: bool = True,
        allow_split: bool = True,
        allow_double_down: bool = True,
        allow_insurance: bool = True,
        allow_surrender: bool = True,
        allow_early_surrender: bool = False,
        allow_double_after_split: bool = False,
        allow_resplitting: bool = False,
        dealer_peek: bool = False,
        num_decks: int = 1,
        min_bet: float = 1.0,
        max_bet: float = 100.0,
        max_splits: int = 3,
        insurance_payout: float = 2.0,
        five_card_charlie: bool = False,
        penetration: float = 0.75,
        burn_cards: int = 0,
        resplit_aces: bool = False,
        hit_split_aces: bool = False,
        allow_obo: bool = True,
        use_csm: bool = False,
        double_on: str = "any",
    ) -> None: ...

class CountingConfig:
    def __init__(
        self,
        deviations: list[tuple[int, bool, int, float, int | None, int | None]],
        initial_decks: float,
    ) -> None: ...

class PlayerRecord:
    hands: list[list[int]]
    actions: list[list[str]]
    winners: list[str]
    first_cards: list[int]
    bets: list[float]
    original_bets: list[float]
    net: float
    initial_bet: float
    total_bet: float
    blackjack: bool
    money: float

class RoundRecord:
    players: list[PlayerRecord]
    dealer_cards: list[int]
    cards_consumed: int
    conditional_net: float | None

def simulate_batch(
    rules: Rules,
    table: bytes,
    n_rounds: int,
    seed: int,
    n_players: int = 1,
    initial_bankroll: float = 1000.0,
    always_insure: bool = False,
    threads: int = 0,
    counting: CountingConfig | None = None,
    shuffle_type: str = "perfect",
    shuffle_count: int | None = None,
    conditional_settlement: bool = False,
    per_deal: bool = False,
) -> dict: ...

# True when the extension was compiled with the gpu feature; runtime
# usability is reported by gpu_probe().
GPU_SUPPORT: bool

def gpu_probe() -> tuple[bool, str]: ...
def simulate_batch_gpu(
    rules: Rules,
    table: bytes,
    n_rounds: int,
    seed: int,
    n_players: int = 1,
    initial_bankroll: float = 1000.0,
    always_insure: bool = False,
    threads: int = 0,
    counting: CountingConfig | None = None,
    shuffle_type: str = "perfect",
    shuffle_count: int | None = None,
) -> dict: ...
def simulate_paired(
    rules_a: Rules,
    table_a: bytes,
    rules_b: Rules,
    table_b: bytes,
    n_rounds: int,
    seed: int,
    n_players: int = 1,
    initial_bankroll: float = 10_000_000.0,
    threads: int = 0,
    conditional_settlement: bool = False,
) -> dict: ...
def play_card_stream(
    rules: Rules,
    table: bytes,
    cards: bytes,
    n_players: int = 1,
    initial_bankroll: float = 1000.0,
    always_insure: bool = False,
    max_rounds: int | None = None,
    counting: CountingConfig | None = None,
    conditional_settlement: bool = False,
) -> list[RoundRecord]: ...
def trace_shoe(
    num_decks: int,
    penetration: float,
    burn_cards: int,
    deals_per_round: list[int],
    seed: int = 0,
) -> list[tuple[int, int]]: ...

class SeatSnapshot:
    hands: list[list[int]]
    actions: list[list[str]]
    bets: list[float]
    hand_done: list[bool]
    insurance: float
    money: float

class SessionStep:
    phase: str  # "insurance" | "early_surrender" | "decision" | "round_over"
    seat: int | None
    hand_index: int | None
    valid_actions: list[str]
    players: list[SeatSnapshot]
    dealer_cards: list[int]  # upcard only until round_over
    result: RoundRecord | None

class Session:
    money: list[float]
    n_players: int
    round_active: bool

    def __init__(
        self,
        rules: Rules,
        n_players: int = 1,
        bankroll: float = 1000.0,
        seed: int = 0,
        cards: bytes | None = None,
        shuffle_type: str = "perfect",
        shuffle_count: int | None = None,
    ) -> None: ...
    def begin_round(self, bets: list[float]) -> SessionStep: ...
    def apply(self, action: str) -> SessionStep: ...
    def close(self) -> None: ...
