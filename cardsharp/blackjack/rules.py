from cardsharp.common.hand import Hand
from cardsharp.common.card import Rank


class Rules:
    def __init__(
        self,
        blackjack_payout: float = 1.5,
        dealer_hit_soft_17: bool = True,
        allow_split: bool = True,
        allow_double_down: bool = True,
        allow_insurance: bool = True,
        allow_surrender: bool = True,
        num_decks: int = 1,
        min_bet: float = 1.0,
        max_bet: float = 100.0,
        allow_late_surrender: bool = False,
        allow_double_after_split: bool = False,
        allow_resplitting: bool = False,
        dealer_peek: bool = False,
        use_csm: bool = False,
        allow_early_surrender: bool = False,
        bonus_payouts: dict = {},
        time_limit: int = 0,
        max_splits: int = 3,
    ):
        """
        Initialize the game rules.

        Args:
            blackjack_payout (float, optional): Payout multiplier for
            a blackjack. Defaults to 1.5.

            dealer_hit_soft_17 (bool, optional): Flag indicating if the dealer
            hits on soft 17. Defaults to True.

            allow_split (bool, optional): Flag indicating if splitting pairs is
            allowed. Defaults to True.

            allow_double_down (bool, optional): Flag indicating if doubling down
            is allowed. Defaults to True.

            allow_insurance (bool, optional): Flag indicating if insurance is
            allowed. Defaults to True.

            allow_surrender (bool, optional): Flag indicating if surrender is
            allowed. Defaults to True.

            num_decks (int, optional): Number of decks used in the game. Defaults to 1.

            min_bet (float, optional): Minimum bet allowed in the game. Defaults to 1.0.

            max_bet (float, optional): Maximum bet allowed in the game. Defaults to 100.0.

            allow_late_surrender (bool, optional): Flag indicating if late
            surrender is allowed. Defaults to False.

            allow_double_after_split (bool, optional): Flag indicating if
            doubling down after splitting is allowed. Defaults to False.

            allow_resplitting (bool, optional): Flag indicating if resplitting
            is allowed. Defaults to False.

            dealer_peek (bool, optional): Flag indicating if the dealer checks
            for blackjack. Defaults to False.

            use_csm (bool, optional): Flag indicating if a Continuous Shuffling
            Machine (CSM) is used. Defaults to False.

            allow_early_surrender (bool, optional): Flag indicating if early
            surrender is allowed. Defaults to False.

            bonus_payouts (dict, optional): Dictionary defining bonus payouts
            for specific card combinations. Defaults to an empty dictionary.

            time_limit (int, optional): Time limit in seconds for player
            decisions. Defaults to 0 (no time limit).

            max_splits (int, optional): Maximum number of times a player can split their hand.
            Defaults to 3 (resulting in up to 4 hands).

        """
        self.allow_double_after_split = allow_double_after_split
        self.allow_double_down = allow_double_down
        self.allow_early_surrender = allow_early_surrender
        self.allow_insurance = allow_insurance
        self.allow_late_surrender = allow_late_surrender
        self.allow_resplitting = allow_resplitting
        self.allow_split = allow_split
        self.allow_surrender = allow_surrender
        self.blackjack_payout = blackjack_payout
        self.bonus_payouts = bonus_payouts or {}
        self.dealer_hit_soft_17 = dealer_hit_soft_17
        self.dealer_peek = dealer_peek
        self.max_bet = max_bet
        self.min_bet = min_bet
        self.num_decks = num_decks
        self.time_limit = time_limit
        self.use_csm = use_csm
        self.max_splits = max_splits

    def should_dealer_hit(self, hand: Hand) -> bool:
        """Determine if the dealer should hit based on the game rules."""
        score = hand.value()
        is_soft_17 = score == 17 and hand.is_soft
        return score < 17 or (is_soft_17 and self.dealer_hit_soft_17)

    def is_blackjack(self, hand: Hand) -> bool:
        """Check if a hand is a blackjack."""
        return hand.value() == 21 and len(hand.cards) == 2

    def can_split(self, hand: Hand) -> bool:
        """
        Check if the hand can be split.

        Args:
            hand (Hand): The player's hand.

        Returns:
            bool: True if the hand can be split, False otherwise.
        """
        if not self.allow_split:
            return False

        # Check if hand has exactly two cards of the same rank
        if len(hand.cards) == 2 and hand.cards[0].rank == hand.cards[1].rank:
            # If resplitting is not allowed, this implicitly means only the first split is allowed
            if not self.allow_resplitting and hand.is_split:
                return False
            return True

        return False

    def get_max_splits(self) -> int:
        """
        Get the maximum number of splits allowed per hand.

        Returns:
            int: Maximum number of splits allowed.
        """
        return self.max_splits

    def can_split_more(self, current_num_hands: int) -> bool:
        """
        Check if a player can split again based on their current number of hands.

        Args:
            current_num_hands (int): The player's current number of hands.

        Returns:
            bool: True if the player can split again, False otherwise.
        """
        return current_num_hands < (self.max_splits + 1)

    def can_double_down(self, hand: Hand) -> bool:
        """
        Check if the hand can be doubled down based on the rules.

        Args:
            hand (Hand): The player's hand.

        Returns:
            bool: True if the hand can be doubled down, False otherwise.
        """
        if not self.allow_double_down or len(hand.cards) != 2:
            return False

        hand_value = hand.value()
        # Allow doubling on hard 9, 10, or 11
        if not hand.is_soft and hand_value in [9, 10, 11]:
            return True
        return False

    def can_insure(self, dealer_hand: Hand, player_hand: Hand) -> bool:
        """
        Check if the player can opt for insurance.

        Args:
            dealer_hand (Hand): The dealer's hand.
            player_hand (Hand): The player's hand.

        Returns:
            bool: True if insurance is allowed, False otherwise.
        """
        if (
            self.allow_insurance
            and dealer_hand.cards[0].rank == Rank.ACE
            and len(dealer_hand.cards) == 2
        ):
            return True
        return False

    def can_surrender(self, hand: Hand, is_first_action: bool) -> bool:
        """
        Check if the player can surrender based on the rules and game state.

        Args:
            hand (Hand): The player's hand.
            is_first_action (bool): True if it's the player's first action on this hand.

        Returns:
            bool: True if surrender is allowed, False otherwise.
        """
        if not self.allow_surrender or not is_first_action:
            return False

        if len(hand.cards) != 2:
            return False

        if self.allow_early_surrender:
            return True  # Early surrender allowed before dealer checks for blackjack

        if self.allow_late_surrender and not hand.is_split:
            return True  # Late surrender allowed on first action and not on split hands

        return False

    def get_num_decks(self) -> int:
        """
        Get the number of decks used in the game.

        Returns:
            int: Number of decks used in the game.
        """
        return self.num_decks

    def get_min_bet(self) -> float:
        """
        Get the minimum bet allowed in the game.

        Returns:
            float: Minimum bet allowed in the game.
        """
        return self.min_bet

    def get_max_bet(self) -> float:
        """
        Get the maximum bet allowed in the game.

        Returns:
            float: Maximum bet allowed in the game.
        """
        return self.max_bet

    def can_late_surrender(self) -> bool:
        """
        Check if late surrender is allowed.

        Returns:
            bool: True if late surrender is allowed, False otherwise.
        """
        return self.allow_late_surrender

    def can_double_after_split(self) -> bool:
        """
        Check if doubling down after splitting is allowed.

        Returns:
            bool: True if doubling down after splitting is allowed, False otherwise.
        """
        return self.allow_double_after_split

    def can_resplit(self, hand: Hand) -> bool:
        """
        Check if the hand can be resplit.

        Args:
            hand (Hand): The player's hand.

        Returns:
            bool: True if the hand can be resplit, False otherwise.
        """
        if (
            self.allow_resplitting
            and len(hand.cards) == 2
            and hand.cards[0].rank == hand.cards[1].rank
        ):
            return True
        return False

    def should_dealer_peek(self) -> bool:
        """
        Determine if the dealer checks for blackjack.

        Returns:
            bool: True if the dealer checks for blackjack, False otherwise.
        """
        return self.dealer_peek

    def is_using_csm(self) -> bool:
        """
        Check if a Continuous Shuffling Machine (CSM) is used.

        Returns:
            bool: True if a CSM is used, False otherwise.
        """
        return self.use_csm

    def can_early_surrender(self) -> bool:
        """
        Check if early surrender is allowed.

        Returns:
            bool: True if early surrender is allowed, False otherwise.
        """
        return self.allow_early_surrender

    def get_bonus_payout(self, card_combination: str) -> float:
        """
        Get the bonus payout for a specific card combination.

        Args:
            card_combination (str): The specific card combination.

        Returns:
            float: Bonus payout for the card combination. Returns 0.0 if not defined.
        """
        return self.bonus_payouts.get(card_combination, 0.0)

    def get_time_limit(self) -> int:
        """
        Get the time limit in seconds for player decisions.

        Returns:
            int: Time limit in seconds. Returns 0 if no time limit.
        """
        return self.time_limit
