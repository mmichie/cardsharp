//! What a Rust consumer of the rlib can reach.
//!
//! This binary compiles against the crate's EXPORTED surface only, with
//! default features -- which is the configuration a downstream project
//! gets, and the one with no PyO3 in the graph. Anything the round engine
//! needs that is not `pub` fails here rather than in the downstream's
//! build.

use cardsharp_core::card::Rank;
use cardsharp_core::machine::{Answer, AskKind, RoundMachine, Source, Step};
use cardsharp_core::round::{
    Decider, DecisionPhase, PlayerRound, RoundConfig, TableDecider, play_round,
};
use cardsharp_core::rules::{DoubleOn, Rules};
use cardsharp_core::shoe::{DealSource, Shoe, ShoeOptions};
use cardsharp_core::strategy::{Action, StrategyTable, TABLE_BYTES, ValidActions};

fn six_deck() -> Rules {
    Rules {
        num_decks: 6,
        dealer_peek: true,
        min_bet: 10.0,
        max_bet: 500.0,
        double_on: DoubleOn::Any,
        ..Default::default()
    }
}

/// A table can be opened, bet on, and played to settlement without ever
/// naming a Python type.
#[test]
fn a_shoe_backed_table_plays_a_round() {
    let rules = six_deck();
    let source = Source::shoe(&rules, "perfect", None, 20260901).expect("shuffle style");
    let mut table = RoundMachine::new(rules, source, vec![1_000.0]);

    let mut step = table.step(Answer::Bets(vec![10.0])).expect("bets accepted");
    let mut asked = 0;
    loop {
        match step {
            Step::Ask(ask) => {
                asked += 1;
                assert!(asked < 32, "a round should not ask this many questions");
                assert!(ask.seat == 0 && !ask.players[0].hands.is_empty());
                step = table
                    .step(match ask.kind {
                        AskKind::Insurance => Answer::Insurance(false),
                        _ => Answer::Action(Action::Stand),
                    })
                    .expect("answer accepted");
            }
            Step::RoundOver(finished) => {
                assert_eq!(finished.money.len(), 1);
                assert_eq!(finished.record.players.len(), 1);
                assert!(finished.record.cards_consumed >= 4);
                assert_eq!(table.money(), &finished.money[..]);
                assert!(!table.round_active());
                break;
            }
        }
    }
}

/// The `Decider` seam is the batch inversion point, and a downstream can
/// implement it: this one always stands, which pins the round's shape
/// against a fixed deal without any strategy table.
struct AlwaysStand;

impl Decider for AlwaysStand {
    fn bet(&mut self, _seat: usize, rules: &Rules, _money: f64) -> f64 {
        rules.min_bet
    }
    fn wants_insurance(&mut self, _seat: usize, _players: &[PlayerRound], _up: Rank) -> bool {
        false
    }
    fn decide(
        &mut self,
        _seat: usize,
        _hand_index: usize,
        _phase: DecisionPhase,
        _players: &[PlayerRound],
        _up: Rank,
        _valid: &ValidActions,
    ) -> Action {
        Action::Stand
    }
}

#[test]
fn play_round_takes_a_downstream_decider() {
    let rules = six_deck();
    let mut shoe = Shoe::new(
        ShoeOptions::classic(rules.num_decks, rules.penetration, rules.burn_cards),
        rand::SeedableRng::seed_from_u64(7),
    );
    let before = shoe.cards_remaining();
    let cfg = RoundConfig {
        initial_bankroll: 1_000.0,
        conditional_settlement: false,
    };
    let result = play_round(
        &mut shoe,
        &rules,
        &cfg,
        &mut AlwaysStand,
        vec![PlayerRound::new(1_000.0)],
    )
    .expect("a fresh six-deck shoe cannot run dry");

    assert_eq!(result.players.len(), 1);
    assert_eq!(result.players[0].hands[0].len(), 2);
    assert!(result.dealer.len() >= 2);
    assert!(shoe.cards_remaining() < before);
}

/// The batch runner and the strategy table are reachable too, so a
/// downstream can price a rule set rather than only play one hand.
#[test]
fn the_batch_runner_and_the_strategy_table_are_reachable() {
    // Stand on everything: a legal table, and the cheapest one to spell.
    let table = StrategyTable::from_bytes(&[1u8; TABLE_BYTES]).expect("a valid table");
    let rules = six_deck();
    let batch = cardsharp_core::sim::BatchCfg {
        round: RoundConfig {
            initial_bankroll: 1_000.0,
            conditional_settlement: false,
        },
        n_players: 1,
        always_insure: false,
    };
    let options = ShoeOptions::classic(rules.num_decks, rules.penetration, rules.burn_cards);
    let (stats, per_deal) = cardsharp_core::sim::run_batch_cpu(
        &rules, &table, &batch, None, &options, 500, 99, 1, false,
    )
    .expect("the shoe recycles");
    assert_eq!(stats.games_played, 500);
    assert_eq!(stats.n_rounds, 500);
    assert!(per_deal.is_none());

    // ...and the seam the batch path uses is public as well.
    let _ = TableDecider::new(&table, None, false);
}

/// `digest` is meant to be written down by a downstream, so it is checked
/// from outside the crate as well as in.
#[test]
fn the_rule_digest_is_reachable_and_discriminating() {
    let six = six_deck();
    assert_eq!(six.digest(), six.clone().digest());
    assert_ne!(six.digest(), Rules::default().digest());
    assert_ne!(
        six.digest(),
        Rules {
            double_on: DoubleOn::TenToEleven,
            ..six.clone()
        }
        .digest()
    );
    assert!(six.validate().is_ok());
}
