"""Dealer drawing procedure: complete the hand only when a live hand needs it.

Casino procedure: when every player hand is busted, surrendered, or already
settled (e.g. a paid natural), the dealer reveals the hole card but does not
draw. Drawing anyway consumes cards a real game never deals, which distorts
shoe pacing (cut-card effect) and feeds counting strategies cards a real
counter would never see.
"""

from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.blackjack import BlackjackGame
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.state import _state_placing_bets
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.common.io_interface import DummyIOInterface
from cardsharp.common.testing import RiggedShoe


def play_rigged_round(shoe, rules=None, num_players=1):
    rules = rules or Rules(
        num_decks=1,
        dealer_hit_soft_17=True,
        allow_double_down=True,
        allow_split=True,
        allow_surrender=True,
        allow_late_surrender=True,
        dealer_peek=True,
        blackjack_payout=1.5,
        min_bet=10,
        max_bet=1000,
    )
    io = DummyIOInterface()
    game = BlackjackGame(rules, io, shoe)
    players = []
    for i in range(num_players):
        player = Player(f"P{i+1}", io, BasicStrategy(), initial_money=1000)
        game.add_player(player)
        players.append(player)
    game.set_state(_state_placing_bets)
    game.play_round()
    return game, players


class TestDealerDeadHand:
    def test_dealer_does_not_draw_when_player_busts(self):
        """Player busts -> dealer stays on two cards, even below 17."""
        shoe = RiggedShoe.from_hands(
            player=["Th", "6h"],  # hard 16 vs 7: basic strategy hits
            dealer=["7s", "5s"],  # dealer 12 would have to draw if live
            extra=["Kd", "4c", "4d"],  # player hit card busts the 16
        )
        game, (player,) = play_rigged_round(shoe)

        assert player.hands[0].value() > 21
        assert len(game.dealer.current_hand.cards) == 2
        assert game.dealer.current_hand.value() == 12

    def test_dealer_does_not_draw_when_player_surrenders(self):
        """Player surrenders -> dealer reveals but does not draw."""
        shoe = RiggedShoe.from_hands(
            player=["Th", "6h"],  # 16 vs 10: basic strategy surrenders
            dealer=["Ts", "5s"],  # dealer 15 stays two cards
            extra=["4c", "4d"],
        )
        game, (player,) = play_rigged_round(shoe)

        assert player.bets[0] == 0  # surrendered
        assert player.money == 995.0  # half the 10 bet forfeited
        assert len(game.dealer.current_hand.cards) == 2

    def test_dealer_does_not_draw_after_paid_natural(self):
        """Peek game, player blackjack paid immediately -> no dealer draws."""
        shoe = RiggedShoe.from_hands(
            player=["As", "Kh"],
            dealer=["9s", "5s"],
            extra=["4c", "4d"],
        )
        game, (player,) = play_rigged_round(shoe)

        assert player.blackjack
        assert len(game.dealer.current_hand.cards) == 2

    def test_dealer_completes_hand_for_standing_player(self):
        """A live standing hand still gets a fully played dealer hand."""
        shoe = RiggedShoe.from_hands(
            player=["Th", "9h"],  # 19: stands
            dealer=["9s", "5s"],  # 14: must draw to 17+
            extra=["2c", "8d", "4d"],
        )
        game, (player,) = play_rigged_round(shoe)

        assert player.hands[0].value() == 19
        assert game.dealer.current_hand.value() >= 17
        assert len(game.dealer.current_hand.cards) >= 3

    def test_dealer_completes_hand_when_one_split_hand_lives(self):
        """Split where one hand busts and the other stands: dealer plays."""
        shoe = RiggedShoe.from_hands(
            player=["8h", "8d"],  # split 8s vs 9
            dealer=["9s", "5s"],
            # hand1: 8+T=18 -> 8,8 strategy hits 18? no: stands.
            # hand2: 8+4=12 -> hits -> T busts it.
            extra=["Th", "4c", "Td", "8c", "4d"],
        )
        game, (player,) = play_rigged_round(shoe)

        assert len(player.hands) == 2
        values = sorted(h.value() for h in player.hands)
        assert values[1] > 21 or values[0] <= 21  # at least one live
        live = [h for h in player.hands if h.value() <= 21]
        assert live, "test setup should leave a live hand"
        assert game.dealer.current_hand.value() >= 17

    def test_dealer_draws_for_second_player_when_first_busts(self):
        """Multiplayer: one bust does not cancel the dealer's hand."""
        shoe = RiggedShoe.from_hands(
            players=[["Th", "6h"], ["Th", "9h"]],  # P1 16 (hits/busts), P2 19
            dealer=["7s", "5s"],
            extra=["Kd", "8d", "4c", "4d"],  # P1 hit busts; dealer draws 8
        )
        game, players = play_rigged_round(shoe, num_players=2)

        assert players[0].hands[0].value() > 21
        assert players[1].hands[0].value() == 19
        assert game.dealer.current_hand.value() >= 17

    def test_dealer_natural_still_detected_without_draws(self):
        """Dead round vs dealer natural: settlement is still correct."""
        shoe = RiggedShoe.from_hands(
            player=["Th", "6h"],  # 16 vs A in H17: surrender
            dealer=["As", "Kd"],  # dealer natural
            extra=["4c", "4d"],
        )
        game, (player,) = play_rigged_round(shoe)

        # Peek game: dealer BJ resolves before the player acts; the player
        # never surrenders and loses the full bet.
        assert game.dealer.current_hand.is_blackjack
        assert player.money == 990.0
        assert len(game.dealer.current_hand.cards) == 2
