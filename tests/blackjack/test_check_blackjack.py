"""Test that player blackjack is correctly detected and paid."""

from cardsharp.blackjack.test_support import BlackjackScenario


def test_player_blackjack_payout():
    """Player with A+K gets blackjack, paid 3:2."""
    result = BlackjackScenario(
        player=["As", "Kh"],
        dealer=["Th", "7d"],
        rules={"blackjack_payout": 1.5},
    ).play()

    assert result.player_blackjack
    assert result.player_won
    assert result.player_value == 21
    assert result.money_change == 1.5  # 3:2 on min bet of 1
