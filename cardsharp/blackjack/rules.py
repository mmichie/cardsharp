from cardsharp.common.hand import Hand


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
        """
        self.blackjack_payout = blackjack_payout
        self.dealer_hit_soft_17 = dealer_hit_soft_17
        self.allow_split = allow_split
        self.allow_double_down = allow_double_down
        self.allow_insurance = allow_insurance
        self.allow_surrender = allow_surrender
        self.num_decks = num_decks
        self.min_bet = min_bet
        self.max_bet = max_bet
        self.allow_late_surrender = allow_late_surrender
        self.allow_double_after_split = allow_double_after_split
        self.allow_resplitting = allow_resplitting
        self.dealer_peek = dealer_peek
        self.use_csm = use_csm
        self.allow_early_surrender = allow_early_surrender
        self.bonus_payouts = bonus_payouts
        self.time_limit = time_limit

        self.blackjack_payout = blackjack_payout
        self.dealer_hit_soft_17 = dealer_hit_soft_17
        self.allow_split = allow_split
        self.allow_double_down = allow_double_down
        self.allow_insurance = allow_insurance
        self.allow_surrender = allow_surrender
        self.num_decks = num_decks
        self.min_bet = min_bet
        self.max_bet = max_bet
        self.allow_late_surrender = allow_late_surrender
        self.allow_double_after_split = allow_double_after_split
        self.allow_resplitting = allow_resplitting
        self.dealer_peek = dealer_peek
        self.use_csm = use_csm
        self.allow_early_surrender = allow_early_surrender
        self.bonus_payouts = bonus_payouts or {}
        self.time_limit = time_limit

    def is_blackjack(self, hand: Hand) -> bool:
        """
        Check if a hand is a blackjack.

        Args:
            hand (Hand): The hand to check.

        Returns:
            bool: True if the hand is a blackjack, False otherwise.
        """
        return hand.calculate_score() == 21 and len(hand.cards) == 2

    def should_dealer_hit(self, hand: Hand) -> bool:
        """
        Determine if the dealer should hit based on the game rules.

        Args:
            hand (Hand): The dealer's hand.

        Returns:
            bool: True if the dealer should hit, False otherwise.
        """
        score = hand.calculate_score()
        is_soft_17 = score == 17 and any(card.rank == "A" for card in hand.cards)
        return score < 17 or (is_soft_17 and self.dealer_hit_soft_17)

    def can_split(self, hand: Hand) -> bool:
        """
        Check if the hand can be split.

        Args:
            hand (Hand): The player's hand.

        Returns:
            bool: True if the hand can be split, False otherwise.
        """
        if len(hand.cards) == 2 and self.allow_split:
            return hand.cards[0].rank == hand.cards[1].rank
        return False

    def can_double_down(self, hand: Hand) -> bool:
        """
        Check if the hand can be doubled down.

        Args:
            hand (Hand): The player's hand.

        Returns:
            bool: True if the hand can be doubled down, False otherwise.
        """
        if len(hand.cards) == 2 and self.allow_double_down:
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
            and dealer_hand.cards[0].rank == "A"
            and len(dealer_hand.cards) == 2
        ):
            return True
        return False

    def can_surrender(self, player_hand: Hand) -> bool:
        """
        Check if the player can surrender.

        Args:
            player_hand (Hand): The player's hand.

        Returns:
            bool: True if surrender is allowed, False otherwise.
        """
        if self.allow_surrender and len(player_hand.cards) == 2:
            return True
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
