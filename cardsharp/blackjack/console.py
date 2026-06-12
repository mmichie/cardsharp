"""Interactive console blackjack on the fast core (beads-i2s.2).

Drives `cardsharp_core.Session` (via cardsharp.fastsim.open_session) and
narrates rounds in the exact line format the retired state-machine
console used, so scripted transcripts diff clean against the old flow
(tests/blackjack/test_console_transcript_parity.py). Differences from
the old console are deliberate and few:

- Cards print as bare ranks ("T", "A", "9") -- the core deals ranks;
  suits were cosmetic.
- "{name} got a blackjack!" prints only on an actual natural (the old
  state machine printed it for every player whenever the dealer
  peeked -- an indentation bug).
- Insurance is actually offered when the dealer shows an ace (the old
  console crashed: it required a strategy object to answer).

Input still flows through the IOInterface contract, so
ConsoleIOInterface gives real prompts and TestIOInterface scripts them.
"""

from types import SimpleNamespace

from cardsharp.blackjack.action import Action

RANK_NAMES = {1: "A", 10: "T", 11: "J", 12: "Q", 13: "K"}

_ACTIONS_BY_NAME = {a.value: a for a in Action}


def card_name(code: int) -> str:
    """Display name for a rank code (Ace=1 .. King=13)."""
    return RANK_NAMES.get(code, str(code))


def hand_value(codes) -> int:
    """Blackjack hand value with the usual flexible ace."""
    total = 0
    aces = 0
    for code in codes:
        if code == 1:
            aces += 1
            total += 11
        else:
            total += min(code, 10)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def _cards_text(codes) -> str:
    return ", ".join(card_name(c) for c in codes)


class ConsoleSession:
    """One interactive table: a persistent core session narrated to an
    IOInterface in the old console's voice."""

    def __init__(
        self,
        rules,
        io_interface,
        bankroll: float = 1000.0,
        player_name: str = "Player1",
        seed=None,
        cards=None,
        shuffle_type: str = "perfect",
        shuffle_count=None,
    ):
        from cardsharp.fastsim import open_session

        self.rules = rules
        self.io = io_interface
        self.name = player_name
        # IOInterface.get_player_action only reads .name from the actor.
        self._actor = SimpleNamespace(name=player_name)
        self.session = open_session(
            rules,
            n_players=1,
            bankroll=bankroll,
            seed=seed,
            cards=cards,
            shuffle_type=shuffle_type,
            shuffle_count=shuffle_count,
        )

    @property
    def money(self) -> float:
        return self.session.money[0]

    def close(self):
        self.session.close()

    def play_round(self) -> bool:
        """Play one narrated round. Returns False when the bankroll can
        no longer cover the table minimum (session over)."""
        out = self.io.output
        bet = self.rules.min_bet
        if self.money < bet:
            out(f"{self.name} cannot cover the minimum bet. Game over.")
            return False

        out(f"{self.name} has joined the game.")
        out("Changing state to PlacingBetsState.")
        out(f"{self.name} has placed a bet of {bet}.")
        out("Changing state to DealingState.")

        self._insured = False
        self._early_surrendered = False
        step = self.session.begin_round([float(bet)])

        # The deal: announce the player's two cards (the old console never
        # announced the dealer's). Snapshot hands are present from the
        # first step regardless of its phase.
        first_two = list(step.players[0].hands[0][:2])
        for code in first_two:
            out(f"Dealt {card_name(code)} to {self.name}.")

        out("Changing state to OfferInsuranceState.")
        out(f"Dealer shows {card_name(step.dealer_cards[0])}.")

        step = self._insurance_and_early_phases(step)

        dealer_blackjack = (
            step.phase == "round_over"
            and len(step.result.dealer_cards) == 2
            and hand_value(step.result.dealer_cards) == 21
            and not self._early_surrendered
        )

        if self._player_natural(step) and not dealer_blackjack:
            out(f"{self.name} got a blackjack!")

        if dealer_blackjack:
            # The peek resolves everything: no player or dealer turn.
            out("Dealer has blackjack!")
            if self._insured:
                payout = (bet / 2.0) * (1.0 + self.rules.insurance_payout)
                out(f"{self.name} wins insurance bet of ${payout:.2f}.")
            else:
                out(f"{self.name} did not take insurance.")
            hand0 = step.result.players[0].hands[0]
            if len(hand0) == 2 and hand_value(hand0) == 21:
                out(f"{self.name} and dealer both have blackjack. Push.")
            else:
                out(f"{self.name} loses to dealer's blackjack.")
            record = step.result
        else:
            out("Changing state to PlayersTurnState.")
            step = self._players_turn(step)
            out("Changing state to DealersTurnState.")
            record = step.result
            for code in record.dealer_cards[2:]:
                out(f"Dealer hits and gets {card_name(code)}.")
            out("Dealer stands.")

        out("Changing state to EndRoundState.")
        self._announce_results(record)
        out("Updating statistics...")
        out("Changing state to PlacingBetsState.")
        return True

    def _player_natural(self, step) -> bool:
        """Natural 21 on the original two cards (peek already confirmed
        no dealer blackjack when the round continued)."""
        if step.phase == "round_over":
            return step.result.players[0].blackjack
        seat = step.players[0]
        return (
            len(seat.hands) == 1
            and seat.hand_done[0]
            and len(seat.hands[0]) == 2
            and hand_value(seat.hands[0]) == 21
        )

    def _insurance_and_early_phases(self, step):
        while step.phase in ("insurance", "early_surrender"):
            if step.phase == "insurance":
                answer = self.io.input(
                    f"{self.name}, dealer shows an Ace. Buy insurance? (yes/no): "
                )
                insure = str(answer).strip().lower() in ("y", "yes")
                step = self.session.apply("insure" if insure else "decline")
                self._insured = insure
                if insure:
                    self.io.output(f"{self.name} has bought insurance.")
                else:
                    self.io.output(f"{self.name} declines insurance.")
            else:
                valid = [_ACTIONS_BY_NAME[a] for a in step.valid_actions]
                action = self.io.get_player_action(
                    self._actor, valid, self.rules.get_time_limit()
                )
                if action == Action.SURRENDER:
                    step = self.session.apply("surrender")
                    self._early_surrendered = True
                    self.io.output(f"{self.name} takes early surrender.")
                else:
                    # Anything else declines; the regular turn follows.
                    step = self.session.apply("stand")
        return step

    def _players_turn(self, step):
        out = self.io.output
        turn_announced = False
        hands_announced = set()
        while step.phase != "round_over":
            if step.phase in ("insurance", "early_surrender"):
                # Defensive: phases normally precede the turn.
                step = self._insurance_and_early_phases(step)
                continue
            if not turn_announced:
                out(f"{self.name}'s turn.")
                turn_announced = True
            hand_index = step.hand_index
            if hand_index not in hands_announced:
                out(f"Playing hand {hand_index + 1}")
                hands_announced.add(hand_index)

            valid = [_ACTIONS_BY_NAME[a] for a in step.valid_actions]
            action = self.io.get_player_action(
                self._actor, valid, self.rules.get_time_limit()
            )
            if action not in valid:
                # The old console forced a stand after repeated invalid
                # input; the IOInterface already retries, so a bad return
                # here just stands the hand.
                action = Action.STAND

            step = self.session.apply(action.value)
            self._announce_action(action, hand_index, step)
        # A natural that ends the round without decisions still got a
        # turn announcement in the old flow.
        if not turn_announced:
            out(f"{self.name}'s turn.")
        return step

    def _hands_after(self, step):
        """Hands as plain lists, from a live step or the final record."""
        if step.phase == "round_over":
            return [list(h) for h in step.result.players[0].hands]
        return [list(h) for h in step.players[0].hands]

    def _announce_action(self, action, hand_index, step):
        out = self.io.output
        hands_now = self._hands_after(step)
        if action == Action.HIT:
            new_card = hands_now[hand_index][-1]
            out(f"{self.name} hits and gets {card_name(new_card)}.")
            if hand_value(hands_now[hand_index]) > 21:
                out(f"{self.name} has busted.")
        elif action == Action.STAND:
            out(f"{self.name} stands.")
        elif action == Action.DOUBLE:
            new_card = hands_now[hand_index][-1]
            out(f"{self.name} doubles down and gets {card_name(new_card)}.")
        elif action == Action.SPLIT:
            out(f"{self.name} splits.")
            new_index = len(hands_now) - 1
            out(
                f"{self.name}'s hand {hand_index + 1} gets "
                f"{card_name(hands_now[hand_index][-1])}."
            )
            out(
                f"{self.name}'s hand {new_index + 1} gets "
                f"{card_name(hands_now[new_index][-1])}."
            )
        elif action == Action.SURRENDER:
            out(f"{self.name} surrenders.")

    def _announce_results(self, record):
        out = self.io.output
        dealer = list(record.dealer_cards)
        player = record.players[0]
        out(f"Dealer's final cards: {_cards_text(dealer)}")
        out(f"Dealer's final hand value: {hand_value(dealer)}")
        for i, hand in enumerate(player.hands):
            out(f"{self.name}'s hand {i + 1} final cards: {_cards_text(hand)}")
            out(f"{self.name}'s hand {i + 1} final hand value: {hand_value(hand)}")
            winner = player.winners[i]
            if winner == "dealer":
                out(f"{self.name}'s hand {i + 1} loses. Dealer wins!")
            elif winner == "player":
                out(f"{self.name}'s hand {i + 1} wins the round!")
            else:
                out(f"{self.name}'s hand {i + 1} and Dealer tie! It's a push.")


def run_console_game(
    rules,
    io_interface,
    num_games: int,
    bankroll: float,
    seed=None,
    shuffle_type: str = "perfect",
    shuffle_count=None,
) -> None:
    """The --console entry point on the fast core."""
    table = ConsoleSession(
        rules,
        io_interface,
        bankroll=bankroll,
        seed=seed,
        shuffle_type=shuffle_type,
        shuffle_count=shuffle_count,
    )
    try:
        for _ in range(num_games):
            if not table.play_round():
                break
    finally:
        table.close()
