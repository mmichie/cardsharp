//! One complete round of classic blackjack.
//!
//! This is a straight-line transliteration of the Python engine's state
//! flow (PlacingBets -> Dealing -> OfferInsurance -> PlayersTurn ->
//! DealersTurn -> EndRound) with the classic variant's win resolver and
//! payout calculator. Behavioral quirks of the reference engine are
//! preserved deliberately -- the parity suite (beads-9ro.5) asserts
//! identical decisions, payouts, and card consumption, not idealized rules.

use crate::card::Rank;
use crate::hand::Hand;
use crate::rules::Rules;
use crate::shoe::{DealSource, OutOfCards};
use crate::strategy::{Action, StrategyTable, ValidActions};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Winner {
    Player,
    Dealer,
    Draw,
}

impl Winner {
    pub fn as_str(self) -> &'static str {
        match self {
            Winner::Player => "player",
            Winner::Dealer => "dealer",
            Winner::Draw => "draw",
        }
    }
}

/// Per-player state for one round. Mirrors the round-relevant fields of
/// `cardsharp.blackjack.actor.Player` (which the Python engine rebuilds
/// from scratch every round).
#[derive(Debug, Clone)]
pub struct PlayerRound {
    pub money: f64,
    pub initial_bankroll: f64,
    pub hands: Vec<Hand>,
    pub bets: Vec<f64>,
    pub original_bets: Vec<f64>,
    pub hand_done: Vec<bool>,
    pub action_history: Vec<Vec<Action>>,
    pub insurance: f64,
    pub total_bets: f64,
    pub initial_bets: f64,
    pub total_winnings: f64,
    pub blackjack: bool,
    pub winners: Vec<Winner>,
    must_stand_after_hit: bool,
}

impl PlayerRound {
    fn new(initial_bankroll: f64) -> Self {
        PlayerRound {
            money: initial_bankroll,
            initial_bankroll,
            hands: vec![Hand::new()],
            bets: Vec::new(),
            original_bets: Vec::new(),
            hand_done: vec![false],
            action_history: vec![Vec::new()],
            insurance: 0.0,
            total_bets: 0.0,
            initial_bets: 0.0,
            total_winnings: 0.0,
            blackjack: false,
            winners: Vec::new(),
            must_stand_after_hit: false,
        }
    }

    pub fn net(&self) -> f64 {
        self.money - self.initial_bankroll
    }

    fn can_afford(&self, amount: f64) -> bool {
        self.money >= amount
    }

    fn is_done(&self) -> bool {
        self.hand_done.iter().all(|d| *d)
    }

    fn place_bet(&mut self, amount: f64) {
        self.money -= amount;
        self.bets = vec![amount];
        self.original_bets = vec![amount];
        self.total_bets += amount;
        self.initial_bets += amount;
    }

    fn buy_insurance(&mut self, amount: f64) {
        self.insurance = amount;
        self.money -= amount;
        self.total_bets += amount;
    }

    /// Mirrors `Player.payout`: pays `amount` to the player and closes the
    /// bet on that hand.
    fn payout(&mut self, hand_index: usize, amount: f64) {
        let bet = self.bets[hand_index];
        self.money += amount;
        self.total_winnings += amount - bet;
        self.bets[hand_index] = 0.0;
    }

    fn payout_insurance(&mut self, amount: f64) {
        self.money += amount;
        self.total_winnings += amount - self.insurance;
        self.insurance = 0.0;
    }

    /// Mirrors `Player.hit`: bust ends the hand; a pending forced stand
    /// (from doubling) consumes itself on a non-busting card.
    fn hit(&mut self, hand_index: usize, card: Rank) {
        self.hands[hand_index].add(card);
        if self.hands[hand_index].value() > 21 {
            self.hand_done[hand_index] = true;
        } else if self.must_stand_after_hit {
            self.hand_done[hand_index] = true;
            self.must_stand_after_hit = false;
        }
    }

    /// Mirrors `Player.surrender`: half the bet comes back, the hand closes.
    fn surrender(&mut self, hand_index: usize) {
        let bet = self.bets[hand_index];
        let refund = bet / 2.0;
        self.money += refund;
        self.total_winnings -= bet - refund;
        self.bets[hand_index] = 0.0;
        self.hand_done[hand_index] = true;
    }

    fn double_down(&mut self, hand_index: usize) {
        let bet = self.bets[hand_index];
        self.money -= bet;
        self.total_bets += bet;
        self.bets[hand_index] *= 2.0;
        self.must_stand_after_hit = true;
    }

    /// Mirrors `Player.split`: moves the second card into a new hand and
    /// posts a matching bet. The dealt replacement cards are the caller's
    /// job (as in `PlayersTurnState.player_action`).
    fn split(&mut self, hand_index: usize) {
        let bet = self.bets[hand_index];
        let is_splitting_aces = self.hands[hand_index].ranks()[0] == Rank::Ace;

        self.money -= bet;
        self.total_bets += bet;

        let moved = self.hands[hand_index]
            .pop()
            .expect("split requires a two-card hand");
        let mut new_hand = Hand::new();
        new_hand.mark_split();
        new_hand.add(moved);
        self.hands[hand_index].mark_split();

        self.hands.push(new_hand);
        self.hand_done.push(false);
        self.bets.push(bet);
        self.original_bets.push(bet);
        self.action_history.push(Vec::new());

        if is_splitting_aces {
            self.must_stand_after_hit = true;
        }
    }
}

pub struct RoundConfig {
    pub n_players: usize,
    pub initial_bankroll: f64,
    /// Stand-in for `Strategy.decide_insurance`; basic strategy never
    /// insures, but the insurance machinery is testable with this on.
    pub always_insure: bool,
}

pub struct RoundResult {
    pub players: Vec<PlayerRound>,
    pub dealer: Hand,
}

/// Play one full round. The shoe's `begin_round`/`end_round` bracketing
/// matches `DealingState.deal` and `EndRoundState.handle`.
pub fn play_round<S: DealSource>(
    shoe: &mut S,
    rules: &Rules,
    table: &StrategyTable,
    cfg: &RoundConfig,
) -> Result<RoundResult, OutOfCards> {
    // PlacingBetsState: flat betting at table minimum (BasicStrategy's
    // get_bet_amount).
    let mut players: Vec<PlayerRound> = (0..cfg.n_players)
        .map(|_| PlayerRound::new(cfg.initial_bankroll))
        .collect();
    for player in &mut players {
        player.place_bet(rules.min_bet);
    }

    // DealingState: one card to each player then the dealer, twice. The
    // dealer's first card is the upcard.
    shoe.begin_round();
    let mut dealer = Hand::new();
    for _pass in 0..2 {
        for player in &mut players {
            let card = shoe.deal()?;
            player.hands[0].add(card);
        }
        dealer.add(shoe.deal()?);
    }

    // DealingState.check_blackjack: in no-peek mode, naturals are flagged
    // so they stand automatically; resolution waits for EndRound.
    if !rules.dealer_peek {
        for player in &mut players {
            if player.hands[0].is_blackjack() {
                player.blackjack = true;
                player.hand_done[0] = true;
            }
        }
    }

    let dealer_up = dealer.ranks()[0];
    let mut round_over = false;

    // OfferInsuranceState, in handler order: insurance offers, early
    // surrender, peek (dealer blackjack / insurance loss / natural payout).
    if dealer_up == Rank::Ace && rules.allow_insurance && cfg.always_insure {
        for player in &mut players {
            let insurance_bet = player.bets[0] / 2.0;
            player.buy_insurance(insurance_bet);
        }
    }

    if rules.allow_early_surrender {
        early_surrender_phase(&mut players, dealer_up, rules, table);
    }

    if rules.dealer_peek {
        if (dealer_up == Rank::Ace || dealer_up.bj_value() == 10) && dealer.is_blackjack() {
            handle_dealer_blackjack(&mut players, rules);
            round_over = true;
        }
        if !round_over {
            // Peek confirmed no dealer blackjack: outstanding insurance is
            // lost, and player naturals are paid immediately.
            for player in &mut players {
                if player.insurance > 0.0 {
                    player.insurance = 0.0;
                }
            }
            for player in &mut players {
                if player.hands[0].is_blackjack() {
                    let bet = player.bets[0];
                    let amount = bet + bet * rules.blackjack_payout;
                    player.payout(0, amount);
                    player.blackjack = true;
                    player.hand_done[0] = true;
                }
            }
        }
    }

    if !round_over {
        players_turn(&mut players, dealer_up, shoe, rules, table)?;
        dealers_turn(&players, &mut dealer, shoe, rules)?;
    }

    // EndRoundState.
    calculate_winner(&mut players, &dealer);
    resolve_no_peek_insurance(&mut players, &dealer, rules);
    handle_payouts(&mut players, &dealer, rules);

    shoe.end_round();

    Ok(RoundResult { players, dealer })
}

/// Early surrender offer, before the dealer peeks. The Python engine asks
/// the strategy through `Player.valid_actions` (the property variant, not
/// the state-machine variant) and acts only on a Surrender answer.
fn early_surrender_phase(
    players: &mut [PlayerRound],
    dealer_up: Rank,
    rules: &Rules,
    table: &StrategyTable,
) {
    for player in players {
        if player.hand_done[0] {
            continue;
        }
        let valid = valid_actions_property(player, rules);
        let action = table.decide(&player.hands[0], dealer_up, &valid);
        if action == Action::Surrender {
            player.surrender(0);
        }
    }
}

/// Mirrors `OfferInsuranceState.handle_dealer_blackjack`.
fn handle_dealer_blackjack(players: &mut [PlayerRound], rules: &Rules) {
    for player in players.iter_mut() {
        if player.insurance > 0.0 {
            let total = player.insurance * (1.0 + rules.insurance_payout);
            player.payout_insurance(total);
        }
    }
    for player in players.iter_mut() {
        if player.hand_done[0] {
            continue; // already resolved (e.g. early surrender)
        }
        if player.hands[0].is_blackjack() {
            let bet = player.bets[0];
            player.payout(0, bet); // push
            player.winners = vec![Winner::Draw];
        } else {
            player.winners = vec![Winner::Dealer];
        }
        player.hand_done[0] = true;
    }
}

/// Mirrors `PlayersTurnState.get_valid_actions` under the classic action
/// validator.
fn valid_actions_state(player: &PlayerRound, hand_index: usize, rules: &Rules) -> ValidActions {
    let hand = &player.hands[hand_index];
    let has_doubled = player.action_history[hand_index].contains(&Action::Double);

    let is_split_ace = hand.is_split() && hand.contains_ace() && hand.len() >= 2;
    if is_split_ace && !rules.hit_split_aces {
        return ValidActions::stand_only();
    }

    let mut valid = ValidActions::hit_stand();
    if !has_doubled && hand.len() == 2 {
        if rules.can_double_down(hand) && player.can_afford(player.bets[hand_index]) {
            valid.double = true;
        }
        if rules.can_split(hand)
            && rules.can_split_more(player.hands.len())
            && player.can_afford(player.bets[hand_index])
        {
            valid.split = true;
        }
        let is_first_action = player.action_history[hand_index].is_empty();
        if rules.can_surrender(hand, is_first_action) && !hand.is_split() {
            valid.surrender = true;
        }
    }
    valid
}

/// Mirrors the `Player.valid_actions` property, which the early-surrender
/// phase consults (it differs from the state-machine variant: no
/// affordability checks, a table-limit check on doubles, no split-ace
/// stand-only branch).
fn valid_actions_property(player: &PlayerRound, rules: &Rules) -> ValidActions {
    if player.hand_done[0] {
        return ValidActions::default();
    }
    let hand = &player.hands[0];
    match hand.len() {
        0 => return ValidActions::default(),
        1 => return ValidActions::hit_stand(),
        _ => {}
    }

    let mut valid = ValidActions::hit_stand();
    if hand.len() == 2 {
        if rules.can_double_down(hand) {
            let doubled_bet = player.bets[0] * 2.0;
            if doubled_bet <= rules.max_bet {
                valid.double = true;
            }
        }
        if hand.is_rank_pair()
            && rules.can_split(hand)
            && player.hands.len() < rules.max_splits as usize + 1
        {
            valid.split = true;
        }
        if !hand.is_split() {
            let is_first_action = player.action_history[0].is_empty();
            if rules.can_surrender(hand, is_first_action) {
                valid.surrender = true;
            }
        }
    }
    valid
}

/// Mirrors `PlayersTurnState.handle`: each hand is played to completion in
/// seat order; hands appended by splits are picked up by the growing index.
fn players_turn<S: DealSource>(
    players: &mut [PlayerRound],
    dealer_up: Rank,
    shoe: &mut S,
    rules: &Rules,
    table: &StrategyTable,
) -> Result<(), OutOfCards> {
    for player in players {
        let mut hand_index = 0;
        while hand_index < player.hands.len() {
            if player.hand_done[hand_index] {
                hand_index += 1;
                continue;
            }
            while !player.hand_done[hand_index] {
                let valid = valid_actions_state(player, hand_index, rules);
                let action = table.decide(&player.hands[hand_index], dealer_up, &valid);
                if valid.contains(action) {
                    player_action(player, hand_index, action, shoe, rules)?;
                } else {
                    // The reference engine forces a stand on an invalid
                    // action; unreachable with a well-formed table, kept
                    // for fidelity.
                    player.hand_done[hand_index] = true;
                }
                let busted = player.hands[hand_index].value() > 21;
                if busted || player.is_done() {
                    break;
                }
            }
            hand_index += 1;
        }
    }
    Ok(())
}

/// Mirrors `PlayersTurnState.player_action`.
fn player_action<S: DealSource>(
    player: &mut PlayerRound,
    hand_index: usize,
    action: Action,
    shoe: &mut S,
    rules: &Rules,
) -> Result<(), OutOfCards> {
    player.action_history[hand_index].push(action);

    match action {
        Action::Hit => {
            // Quirk preserved from the reference engine: any split hand
            // that CONTAINS an ace refuses the hit (not just split-ace
            // pairs) -- e.g. a split 7,7 hand that drew an ace is forced
            // to stand even though the chart may say hit.
            let hand = &player.hands[hand_index];
            if hand.is_split() && hand.contains_ace() && hand.len() > 1 {
                player.hand_done[hand_index] = true;
                return Ok(());
            }

            let card = shoe.deal()?;
            player.hit(hand_index, card);

            let hand = &player.hands[hand_index];
            if rules.is_five_card_charlie(hand) {
                player.hand_done[hand_index] = true;
            } else if hand.is_split() && hand.contains_ace() && hand.len() == 2 {
                // Split ace stands automatically after one card (dead code
                // in practice -- split hands always start at two cards --
                // but mirrored from the reference).
                player.hand_done[hand_index] = true;
            } else if hand.value() > 21 {
                player.hand_done[hand_index] = true;
            }
        }

        Action::Split => {
            let is_splitting_aces = player.hands[hand_index].ranks()[0] == Rank::Ace;
            player.split(hand_index);

            // One card to the original hand, then one to the new hand.
            let new_hand_index = player.hands.len() - 1;
            for i in [hand_index, new_hand_index] {
                let card = shoe.deal()?;
                player.hands[i].add(card);
                if is_splitting_aces {
                    player.hand_done[i] = true;
                }
            }
        }

        Action::Double => {
            // Cannot double on split aces; the action was still recorded
            // in the history (as in the reference).
            let hand = &player.hands[hand_index];
            if hand.is_split() && hand.contains_ace() {
                return Ok(());
            }
            player.double_down(hand_index);
            let card = shoe.deal()?;
            player.hit(hand_index, card);
            player.hand_done[hand_index] = true;
        }

        Action::Stand => {
            player.hand_done[hand_index] = true;
        }

        Action::Surrender => {
            player.surrender(hand_index);
            player.hand_done[hand_index] = true;
        }
    }
    Ok(())
}

/// Mirrors `DealersTurnState`: the dealer completes the hand only while at
/// least one player hand's outcome still depends on the dealer's total.
fn dealers_turn<S: DealSource>(
    players: &[PlayerRound],
    dealer: &mut Hand,
    shoe: &mut S,
    rules: &Rules,
) -> Result<(), OutOfCards> {
    if any_live_hand(players) {
        while rules.should_dealer_hit(dealer) {
            dealer.add(shoe.deal()?);
        }
    }
    Ok(())
}

fn any_live_hand(players: &[PlayerRound]) -> bool {
    for player in players {
        for (i, hand) in player.hands.iter().enumerate() {
            if i < player.bets.len() && player.bets[i] <= 0.0 {
                continue; // surrendered, or already settled (e.g. paid BJ)
            }
            if hand.is_empty() {
                continue;
            }
            if hand.value() > 21 {
                continue; // busted: loses regardless of dealer total
            }
            if hand.is_blackjack() {
                continue; // outcome fixed by the dealt dealer cards
            }
            return true;
        }
    }
    false
}

/// Mirrors `EndRoundState.calculate_winner` with `ClassicWinResolver`.
/// The branch chain transliterates the resolver clause-for-clause, so
/// same-bodied arms are intentional.
#[allow(clippy::if_same_then_else)]
fn calculate_winner(players: &mut [PlayerRound], dealer: &Hand) {
    let dealer_value = dealer.value();
    let dealer_blackjack = dealer.is_blackjack();

    for player in players {
        player.winners.clear();
        for hand in &player.hands {
            let player_value = hand.value();
            let player_blackjack = hand.is_blackjack();
            let winner = if player_blackjack && dealer_blackjack {
                Winner::Draw
            } else if player_blackjack {
                Winner::Player
            } else if dealer_blackjack {
                Winner::Dealer
            } else if player_value > 21 {
                Winner::Dealer
            } else if dealer_value > 21 {
                Winner::Player
            } else if player_value > dealer_value {
                Winner::Player
            } else if dealer_value > player_value {
                Winner::Dealer
            } else {
                Winner::Draw
            };
            player.winners.push(winner);
        }
    }
}

/// Mirrors `EndRoundState.resolve_no_peek_insurance`.
fn resolve_no_peek_insurance(players: &mut [PlayerRound], dealer: &Hand, rules: &Rules) {
    if rules.dealer_peek {
        return;
    }
    let dealer_blackjack = dealer.is_blackjack();
    for player in players {
        if player.insurance <= 0.0 {
            continue;
        }
        if dealer_blackjack {
            let payout = player.insurance * (1.0 + rules.insurance_payout);
            player.payout_insurance(payout);
        }
        player.insurance = 0.0;
    }
}

/// Mirrors `EndRoundState.handle_payouts` on the classic-variant path
/// (payout calculator present, so the bonus-combination branch is dead).
fn handle_payouts(players: &mut [PlayerRound], dealer: &Hand, rules: &Rules) {
    let dealer_blackjack = dealer.is_blackjack();
    let is_no_peek = !rules.dealer_peek;

    for player in players {
        // Void late surrenders against a revealed dealer blackjack in
        // no-peek mode (early surrender, decided before the dealer checks,
        // holds).
        if is_no_peek && dealer_blackjack && !rules.allow_early_surrender {
            for i in 0..player.hands.len() {
                if player.bets[i] == 0.0
                    && i < player.original_bets.len()
                    && player.original_bets[i] > 0.0
                {
                    let original = player.original_bets[i];
                    let half = original / 2.0;
                    player.money -= half;
                    player.total_winnings -= half;
                    player.bets[i] = original;
                    player.winners[i] = Winner::Dealer;
                }
            }
        }

        for i in 0..player.hands.len() {
            let bet = player.bets[i];
            if bet == 0.0 {
                continue;
            }
            let is_blackjack = player.blackjack && !player.hands[i].is_split();
            match player.winners[i] {
                Winner::Player => {
                    let amount = if is_blackjack {
                        bet * (1.0 + rules.blackjack_payout)
                    } else {
                        bet * 2.0
                    };
                    player.payout(i, amount);
                }
                Winner::Draw => {
                    player.payout(i, bet);
                }
                Winner::Dealer => {}
            }
        }

        // OBO (Original Bets Only): with a no-peek dealer blackjack the
        // player's exposure is capped at the initial wager.
        if is_no_peek && dealer_blackjack && rules.allow_obo {
            let losing_total: f64 = (0..player.hands.len())
                .filter(|i| player.winners[*i] == Winner::Dealer)
                .map(|i| player.bets[i])
                .sum();
            if losing_total > player.initial_bets {
                let refund = losing_total - player.initial_bets;
                player.money += refund;
            }
        }
    }
}
