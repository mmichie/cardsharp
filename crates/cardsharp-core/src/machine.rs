//! The resumable round state machine (beads-i2s.1, natively).
//!
//! [`RoundMachine`] is the interactive counterpart of the batch runner:
//! `step(answer)` runs the engine forward to its next question and hands
//! it back. It is plain Rust -- `Send`, no PyO3, no threads -- so a Rust
//! caller drives a table directly, and [`crate::session::Session`] is a
//! thin PyO3 wrapper over it.
//!
//! ```no_run
//! use cardsharp_core::machine::{Answer, RoundMachine, Source, Step};
//! use cardsharp_core::rules::Rules;
//! use cardsharp_core::strategy::Action;
//!
//! let mut table = RoundMachine::new(Rules::default(), Source::shoe(&Rules::default(), "perfect", None, 7).unwrap(), vec![1000.0]);
//! let mut step = table.step(Answer::Bets(vec![10.0])).unwrap();
//! while let Step::Ask(ask) = &step {
//!     let answer = if ask.valid.stand { Answer::Action(Action::Stand) } else { Answer::Insurance(false) };
//!     step = table.step(answer).unwrap();
//! }
//! ```
//!
//! # How control is inverted, and why not with a thread
//!
//! There is exactly ONE round implementation -- [`play_round`] -- and it
//! drives the conversation: it calls the [`Decider`] whenever it needs an
//! answer. Turning that inside out, so the CALLER drives, needs some way
//! to suspend a Rust call stack, and Rust has none on stable.
//!
//! The predecessor of this module borrowed a thread for it: `play_round`
//! ran on a worker whose decider blocked on a channel, and the Python side
//! released the GIL and waited. That works, but it costs a thread and two
//! channels per open session and only ever existed to cross the GIL.
//!
//! This machine replays instead. It keeps the shoe as it stood at the
//! START of the round plus the answers given so far, and every `step`
//! plays the round again from that point: answers 0..n come from the log,
//! and the FIRST question past the log is recorded and handed back. The
//! engine is then answered "stand" (or "decline") so it unwinds, and
//! everything from that point on -- including the shoe clone and any
//! error -- is thrown away. The shoe is committed only when a replay
//! reaches the end of the round without asking anything new, which is
//! exactly when every answer used was a real one.
//!
//! So the round is played O(k) times for k decisions instead of once.
//! That is the price, and it is the right one here: k is a handful (a
//! busy round is a dozen), each replay is microseconds, and the
//! alternative -- a second, incremental implementation of the round flow
//! -- is the one thing this crate has consistently refused to have, since
//! two implementations drift and the parity corpus can only pin one.
//!
//! Speculation cannot leak. The scratch shoe is a clone, the seats are
//! rebuilt from the persistent bankrolls each time, and the decider is
//! fresh, so a discarded replay leaves nothing behind.

use crate::card::Rank;
use crate::round::{Decider, DecisionPhase, PlayerRound, RoundConfig, play_round};
use crate::rules::Rules;
use crate::shoe::{CardStream, DealSource, OutOfCards, Shoe, ShoeOptions, ShuffleStyle};
use crate::sim::{RoundRecord, make_record};
use crate::strategy::{Action, ValidActions};
use rand::SeedableRng;
use rand_xoshiro::Xoshiro256PlusPlus;
use std::fmt;

/// One seat's view of the table mid-round, snapshotted at every decision
/// point. Carries everything the event-translation layer needs to render
/// or emit per-card events by diffing consecutive snapshots.
#[cfg_attr(feature = "python", pyo3::pyclass(get_all))]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
#[derive(Debug, Clone)]
pub struct SeatSnapshot {
    /// Hands as rank codes (Ace=1 .. King=13), in play order.
    pub hands: Vec<Vec<u32>>,
    /// Actions resolved so far, per hand.
    pub actions: Vec<Vec<String>>,
    /// Per-hand bets as they currently stand.
    pub bets: Vec<f64>,
    pub hand_done: Vec<bool>,
    pub insurance: f64,
    pub money: f64,
}

fn snapshot_players(players: &[PlayerRound]) -> Vec<SeatSnapshot> {
    players
        .iter()
        .map(|p| SeatSnapshot {
            hands: p
                .hands
                .iter()
                .map(|h| h.ranks().iter().map(|r| r.code() as u32).collect())
                .collect(),
            actions: p
                .action_history
                .iter()
                .map(|hist| hist.iter().map(|a| a.as_str().to_string()).collect())
                .collect(),
            bets: p.bets.clone(),
            hand_done: p.hand_done.clone(),
            insurance: p.insurance,
            money: p.money,
        })
        .collect()
}

/// What the engine is waiting for.
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AskKind {
    /// Insurance against a dealer ace. Answer with [`Answer::Insurance`].
    Insurance,
    /// The pre-peek early-surrender offer. Answer with an
    /// [`Answer::Action`]; the engine acts only on `Surrender` and treats
    /// anything else as declining.
    EarlySurrender,
    /// The main per-hand play loop. Answer with an [`Answer::Action`] the
    /// ask's `valid` set contains.
    Play,
}

/// A question the engine stopped on.
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
#[derive(Debug, Clone)]
pub struct Ask {
    pub kind: AskKind,
    /// Seat being asked.
    pub seat: usize,
    /// Hand being asked about (always 0 for insurance and early
    /// surrender, which precede any split).
    pub hand_index: usize,
    /// Legal actions. Empty for [`AskKind::Insurance`], which takes a
    /// yes/no rather than an action.
    pub valid: ValidActions,
    /// Every seat's state at this moment.
    pub players: Vec<SeatSnapshot>,
    /// The dealer's upcard. The hole card is never visible here.
    pub dealer_up: Rank,
}

/// A completed round.
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
#[derive(Debug, Clone)]
pub struct Finished {
    pub record: RoundRecord,
    /// Per-seat bankrolls after settlement.
    pub money: Vec<f64>,
}

/// Where the round stands after a [`RoundMachine::step`].
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
#[derive(Debug, Clone)]
pub enum Step {
    /// The engine needs an answer before it can go on.
    Ask(Ask),
    /// The round is over; the machine is ready for the next
    /// [`Answer::Bets`].
    RoundOver(Box<Finished>),
}

/// What the caller answers with.
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
#[derive(Debug, Clone, PartialEq)]
pub enum Answer {
    /// One bet per seat: deal a new round. Only legal between rounds.
    Bets(Vec<f64>),
    /// Take or decline insurance.
    Insurance(bool),
    /// Play the pending hand.
    Action(Action),
}

/// A `step` was refused. Nothing is consumed when one of these is
/// returned except `CardsExhausted`, which ends the round.
#[derive(Debug, Clone, PartialEq)]
pub enum StepError {
    /// An answer arrived with nothing pending.
    NothingPending,
    /// [`Answer::Bets`] arrived while a round was still in progress.
    RoundInProgress,
    /// The answer was of the wrong kind for the pending ask.
    WrongAnswer { pending: AskKind },
    /// The action is not in the pending ask's valid set.
    IllegalAction(Action),
    /// Wrong number of bets for the table.
    BetCount { expected: usize, got: usize },
    /// A bet fell outside the table limits.
    BetOutsideLimits {
        seat: usize,
        bet: f64,
        min: f64,
        max: f64,
    },
    /// A bet exceeded that seat's bankroll.
    BetExceedsBankroll { seat: usize, bet: f64, money: f64 },
    /// The card source ran dry mid-round. Only an injected stream can do
    /// this; a shoe recycles.
    CardsExhausted,
}

impl fmt::Display for StepError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            StepError::NothingPending => write!(f, "no decision pending"),
            StepError::RoundInProgress => {
                write!(f, "a round is already in progress; answer the pending step")
            }
            StepError::WrongAnswer { pending } => {
                write!(f, "the pending step is a {pending:?} question")
            }
            StepError::IllegalAction(action) => {
                write!(f, "action '{}' is not legal here", action.as_str())
            }
            StepError::BetCount { expected, got } => {
                write!(f, "expected {expected} bets, got {got}")
            }
            StepError::BetOutsideLimits {
                seat,
                bet,
                min,
                max,
            } => {
                write!(
                    f,
                    "seat {seat}: bet {bet} outside table limits [{min}, {max}]"
                )
            }
            StepError::BetExceedsBankroll { seat, bet, money } => {
                write!(f, "seat {seat}: bet {bet} exceeds bankroll {money}")
            }
            StepError::CardsExhausted => write!(f, "card stream exhausted mid-round"),
        }
    }
}

impl std::error::Error for StepError {}

/// The pending question, reduced to what validating the next answer
/// needs. Cheap to copy, so a wrapper can read it without cloning an ask.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Pending {
    pub kind: AskKind,
    pub valid: ValidActions,
}

/// One answer in the replay log. Bets are not logged -- they live on the
/// round and are handed to the decider directly.
#[derive(Debug, Clone, Copy, PartialEq)]
enum Reply {
    Insure(bool),
    Act(Action),
}

/// A round in flight: the bets it was dealt on, every answer given so
/// far, and what it is waiting for.
struct LiveRound {
    bets: Vec<f64>,
    log: Vec<Reply>,
    pending: Option<Pending>,
}

/// The replay decider. Answers questions 0..log.len() from the log, then
/// records the next one and stands the round out so it unwinds.
struct ReplayDecider<'a> {
    bets: &'a [f64],
    log: &'a [Reply],
    next: usize,
    ask: Option<Ask>,
}

impl<'a> ReplayDecider<'a> {
    fn new(bets: &'a [f64], log: &'a [Reply]) -> Self {
        ReplayDecider {
            bets,
            log,
            next: 0,
            ask: None,
        }
    }

    /// The logged reply for this question, or `None` if we have reached
    /// the frontier -- in which case `build` is recorded as the ask the
    /// caller must now answer.
    fn replay_or_record(&mut self, build: impl FnOnce() -> Ask) -> Option<Reply> {
        let index = self.next;
        self.next += 1;
        if let Some(reply) = self.log.get(index) {
            return Some(*reply);
        }
        if self.ask.is_none() {
            self.ask = Some(build());
        }
        None
    }
}

impl Decider for ReplayDecider<'_> {
    fn bet(&mut self, seat: usize, _rules: &Rules, _money: f64) -> f64 {
        // Bets arrive with the round (validated by the machine); they are
        // not part of the question log.
        self.bets[seat]
    }

    fn wants_insurance(&mut self, seat: usize, players: &[PlayerRound], dealer_up: Rank) -> bool {
        let reply = self.replay_or_record(|| Ask {
            kind: AskKind::Insurance,
            seat,
            hand_index: 0,
            valid: ValidActions::default(),
            players: snapshot_players(players),
            dealer_up,
        });
        match reply {
            Some(Reply::Insure(yes)) => yes,
            // Past the frontier (or, unreachably, a log entry of the
            // wrong kind): decline, so the round unwinds. Discarded.
            Some(Reply::Act(_)) | None => false,
        }
    }

    fn decide(
        &mut self,
        seat: usize,
        hand_index: usize,
        phase: DecisionPhase,
        players: &[PlayerRound],
        dealer_up: Rank,
        valid: &ValidActions,
    ) -> Action {
        let kind = match phase {
            DecisionPhase::EarlySurrender => AskKind::EarlySurrender,
            DecisionPhase::Play => AskKind::Play,
        };
        let reply = self.replay_or_record(|| Ask {
            kind,
            seat,
            hand_index,
            valid: *valid,
            players: snapshot_players(players),
            dealer_up,
        });
        match reply {
            Some(Reply::Act(action)) => action,
            // Past the frontier: stand, so the round ends and the replay
            // can be thrown away.
            Some(Reply::Insure(_)) | None => Action::Stand,
        }
    }
}

/// Counts dealt cards so a finished round can report `cards_consumed`,
/// which the plain shoe does not track per round.
struct Tally<S: DealSource> {
    inner: S,
    dealt: u64,
}

impl<S: DealSource> DealSource for Tally<S> {
    fn begin_round(&mut self) {
        self.inner.begin_round()
    }
    fn end_round(&mut self) {
        self.inner.end_round()
    }
    fn deal(&mut self) -> Result<Rank, OutOfCards> {
        let card = self.inner.deal()?;
        self.dealt += 1;
        Ok(card)
    }
    fn cards_remaining(&self) -> usize {
        self.inner.cards_remaining()
    }
    fn remaining_rank_counts(&self) -> [u32; 13] {
        self.inner.remaining_rank_counts()
    }
}

/// A table's card source: a seeded shoe for real play, or an injected
/// stream for tests and replays.
#[derive(Clone)]
pub enum Source {
    Shoe(Box<Shoe>),
    Stream(CardStream),
}

impl Source {
    /// A real shoe built from the rules (num_decks, penetration,
    /// burn_cards, CSM) and the shuffle options, seeded deterministically.
    pub fn shoe(
        rules: &Rules,
        shuffle_type: &str,
        shuffle_count: Option<u32>,
        seed: u64,
    ) -> Result<Self, String> {
        let options = ShoeOptions {
            num_decks: rules.num_decks,
            penetration: rules.penetration,
            burn_cards: rules.burn_cards,
            use_csm: rules.use_csm,
            shuffle_style: ShuffleStyle::from_name(shuffle_type)?,
            shuffle_count,
        };
        let rng = Xoshiro256PlusPlus::seed_from_u64(seed);
        Ok(Source::Shoe(Box::new(Shoe::new(options, rng))))
    }

    /// A fixed card sequence, dealt in order and never shuffled.
    pub fn stream(cards: Vec<Rank>) -> Self {
        Source::Stream(CardStream::new(cards))
    }
}

impl DealSource for Source {
    fn begin_round(&mut self) {
        match self {
            Source::Shoe(s) => s.begin_round(),
            Source::Stream(s) => s.begin_round(),
        }
    }
    fn end_round(&mut self) {
        match self {
            Source::Shoe(s) => s.end_round(),
            Source::Stream(s) => s.end_round(),
        }
    }
    fn deal(&mut self) -> Result<Rank, OutOfCards> {
        match self {
            Source::Shoe(s) => s.deal(),
            Source::Stream(s) => s.deal(),
        }
    }
    fn cards_remaining(&self) -> usize {
        match self {
            Source::Shoe(s) => s.cards_remaining(),
            Source::Stream(s) => s.cards_remaining(),
        }
    }
    fn remaining_rank_counts(&self) -> [u32; 13] {
        match self {
            Source::Shoe(s) => s.remaining_rank_counts(),
            Source::Stream(s) => s.remaining_rank_counts(),
        }
    }
}

/// A resumable interactive blackjack table over one persistent card
/// source. See the module docs for how control is inverted.
///
/// The shoe persists across rounds, so penetration, burn cards, CSM
/// behavior and mid-round exhaustion recycling follow the exact cut-card
/// semantics the batch engine implements. Per-seat bankrolls persist too,
/// and bets are validated against them.
pub struct RoundMachine<S: DealSource + Clone> {
    rules: Rules,
    cfg: RoundConfig,
    /// The card source as of the last COMPLETED round; every replay
    /// starts from a clone of this.
    source: S,
    money: Vec<f64>,
    round: Option<LiveRound>,
}

impl<S: DealSource + Clone> RoundMachine<S> {
    /// Open a table with one bankroll per seat.
    pub fn new(rules: Rules, source: S, bankrolls: Vec<f64>) -> Self {
        RoundMachine {
            rules,
            cfg: RoundConfig {
                // Only read by conditional settlement, which interactive
                // play never enables; per-seat bankrolls live in `money`.
                initial_bankroll: 0.0,
                conditional_settlement: false,
            },
            source,
            money: bankrolls,
            round: None,
        }
    }

    pub fn rules(&self) -> &Rules {
        &self.rules
    }

    /// Per-seat bankrolls as of the last completed round.
    pub fn money(&self) -> &[f64] {
        &self.money
    }

    pub fn n_players(&self) -> usize {
        self.money.len()
    }

    /// True between the [`Answer::Bets`] that dealt a round and its
    /// [`Step::RoundOver`].
    pub fn round_active(&self) -> bool {
        self.round.is_some()
    }

    /// What the engine is waiting for, if anything.
    pub fn pending(&self) -> Option<Pending> {
        self.round.as_ref().and_then(|r| r.pending)
    }

    /// Answer the machine and run the engine to its next question.
    ///
    /// [`Answer::Bets`] deals a fresh round (and may run straight to
    /// [`Step::RoundOver`], e.g. on dealt blackjacks);
    /// [`Answer::Insurance`] and [`Answer::Action`] answer the pending
    /// ask. A rejected answer changes nothing, so the pending ask
    /// survives it.
    pub fn step(&mut self, answer: Answer) -> Result<Step, StepError> {
        match answer {
            Answer::Bets(bets) => {
                if self.round.is_some() {
                    return Err(StepError::RoundInProgress);
                }
                self.validate_bets(&bets)?;
                self.round = Some(LiveRound {
                    bets,
                    log: Vec::new(),
                    pending: None,
                });
                self.replay()
            }
            Answer::Insurance(yes) => {
                self.push(Reply::Insure(yes), |pending| match pending.kind {
                    AskKind::Insurance => Ok(()),
                    kind => Err(StepError::WrongAnswer { pending: kind }),
                })?;
                self.replay()
            }
            Answer::Action(action) => {
                self.push(Reply::Act(action), |pending| match pending.kind {
                    AskKind::EarlySurrender | AskKind::Play => {
                        if pending.valid.contains(action) {
                            Ok(())
                        } else {
                            Err(StepError::IllegalAction(action))
                        }
                    }
                    kind => Err(StepError::WrongAnswer { pending: kind }),
                })?;
                self.replay()
            }
        }
    }

    fn validate_bets(&self, bets: &[f64]) -> Result<(), StepError> {
        if bets.len() != self.money.len() {
            return Err(StepError::BetCount {
                expected: self.money.len(),
                got: bets.len(),
            });
        }
        for (seat, bet) in bets.iter().enumerate() {
            if *bet < self.rules.min_bet || *bet > self.rules.max_bet {
                return Err(StepError::BetOutsideLimits {
                    seat,
                    bet: *bet,
                    min: self.rules.min_bet,
                    max: self.rules.max_bet,
                });
            }
            if *bet > self.money[seat] {
                return Err(StepError::BetExceedsBankroll {
                    seat,
                    bet: *bet,
                    money: self.money[seat],
                });
            }
        }
        Ok(())
    }

    /// Validate an answer against the pending ask and append it to the
    /// log. Nothing is appended if `check` refuses.
    fn push(
        &mut self,
        reply: Reply,
        check: impl FnOnce(Pending) -> Result<(), StepError>,
    ) -> Result<(), StepError> {
        let round = self.round.as_mut().ok_or(StepError::NothingPending)?;
        let pending = round.pending.ok_or(StepError::NothingPending)?;
        check(pending)?;
        round.log.push(reply);
        round.pending = None;
        Ok(())
    }

    /// Play the round again from the committed shoe, answering from the
    /// log, and stop at the first question the log does not cover.
    fn replay(&mut self) -> Result<Step, StepError> {
        let RoundMachine {
            rules,
            cfg,
            source,
            money,
            round,
        } = self;
        let live = round.as_mut().expect("replay with no live round");

        let mut scratch = Tally {
            inner: source.clone(),
            dealt: 0,
        };
        let mut decider = ReplayDecider::new(&live.bets, &live.log);
        let seats: Vec<PlayerRound> = money.iter().map(|m| PlayerRound::new(*m)).collect();
        let outcome = play_round(&mut scratch, rules, cfg, &mut decider, seats);
        let ask = decider.ask.take();

        // A new question means everything after it was speculative --
        // including an OutOfCards the real continuation might never reach
        // -- so the whole replay past that point is discarded.
        if let Some(ask) = ask {
            live.pending = Some(Pending {
                kind: ask.kind,
                valid: ask.valid,
            });
            return Ok(Step::Ask(ask));
        }

        match outcome {
            Ok(result) => {
                for (seat, player) in result.players.iter().enumerate() {
                    money[seat] = player.money;
                }
                *source = scratch.inner;
                let record = make_record(result, scratch.dealt as u32);
                *round = None;
                Ok(Step::RoundOver(Box::new(Finished {
                    record,
                    money: money.clone(),
                })))
            }
            Err(OutOfCards) => {
                // Every answer used was real, so this exhaustion is real:
                // the round cannot be finished and the table is done.
                *round = None;
                Err(StepError::CardsExhausted)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(feature = "serde")]
    use crate::rules::DoubleOn;

    fn stream(codes: &[u8]) -> Source {
        Source::stream(codes.iter().map(|c| Rank::from_code(*c).unwrap()).collect())
    }

    fn table(codes: &[u8]) -> RoundMachine<Source> {
        RoundMachine::new(
            Rules {
                min_bet: 10.0,
                ..Default::default()
            },
            stream(codes),
            vec![1000.0],
        )
    }

    fn ask(step: &Step) -> &Ask {
        match step {
            Step::Ask(a) => a,
            Step::RoundOver(_) => panic!("expected an ask, got round_over"),
        }
    }

    fn finished(step: &Step) -> &Finished {
        match step {
            Step::Ask(a) => panic!("expected round_over, got {:?}", a.kind),
            Step::RoundOver(f) => f,
        }
    }

    #[test]
    fn a_round_runs_to_the_first_question_then_resumes() {
        // Player 10,6 vs dealer 9; hit a 5 to 21, then stand.
        let mut t = table(&[10, 9, 6, 8, 5]);
        let step = t.step(Answer::Bets(vec![10.0])).unwrap();
        let a = ask(&step);
        assert_eq!(a.kind, AskKind::Play);
        assert_eq!(a.dealer_up, Rank::Nine);
        assert_eq!(a.players[0].hands, vec![vec![10, 6]]);
        assert!(t.round_active());

        let step = t.step(Answer::Action(Action::Hit)).unwrap();
        assert_eq!(ask(&step).players[0].hands, vec![vec![10, 6, 5]]);

        let step = t.step(Answer::Action(Action::Stand)).unwrap();
        let f = finished(&step);
        assert_eq!(f.record.players[0].hands, vec![vec![10, 6, 5]]);
        assert_eq!(f.record.players[0].winners, vec!["player"]);
        assert!(!t.round_active());
        assert_eq!(t.money(), &[1010.0]);
    }

    #[test]
    fn the_shoe_advances_by_exactly_the_cards_the_round_consumed() {
        // Two rounds off one stream; the second must start where the
        // first stopped, which is only true if the speculative replays
        // left the source alone.
        let mut t = table(&[10, 9, 6, 8, /* round 2 */ 2, 5, 9, 10, 7]);
        let step = t.step(Answer::Bets(vec![10.0])).unwrap();
        assert_eq!(ask(&step).players[0].hands, vec![vec![10, 6]]);
        let step = t.step(Answer::Action(Action::Stand)).unwrap();
        assert_eq!(finished(&step).record.cards_consumed, 4);

        let step = t.step(Answer::Bets(vec![10.0])).unwrap();
        let a = ask(&step);
        assert_eq!(a.players[0].hands, vec![vec![2, 9]]);
        assert_eq!(a.dealer_up, Rank::Five);
    }

    #[test]
    fn a_rejected_answer_leaves_the_pending_question_intact() {
        let mut t = table(&[10, 9, 6, 8, 5]);
        let step = t.step(Answer::Bets(vec![10.0])).unwrap();
        let valid_before = ask(&step).valid;

        assert_eq!(
            t.step(Answer::Action(Action::Split)).unwrap_err(),
            StepError::IllegalAction(Action::Split)
        );
        assert_eq!(
            t.step(Answer::Insurance(true)).unwrap_err(),
            StepError::WrongAnswer {
                pending: AskKind::Play
            }
        );
        assert_eq!(
            t.step(Answer::Bets(vec![10.0])).unwrap_err(),
            StepError::RoundInProgress
        );
        assert_eq!(t.pending().unwrap().valid, valid_before);

        // ...and the round still finishes normally.
        assert!(matches!(
            t.step(Answer::Action(Action::Stand)).unwrap(),
            Step::RoundOver(_)
        ));
    }

    #[test]
    fn bets_are_validated_against_the_table_and_the_bankroll() {
        let mut t = table(&[10, 9, 6, 8]);
        assert_eq!(
            t.step(Answer::Bets(vec![10.0, 10.0])).unwrap_err(),
            StepError::BetCount {
                expected: 1,
                got: 2
            }
        );
        assert_eq!(
            t.step(Answer::Bets(vec![5.0])).unwrap_err(),
            StepError::BetOutsideLimits {
                seat: 0,
                bet: 5.0,
                min: 10.0,
                max: 100.0
            }
        );
        assert_eq!(
            t.step(Answer::Action(Action::Hit)).unwrap_err(),
            StepError::NothingPending
        );

        let mut broke = RoundMachine::new(
            Rules {
                min_bet: 10.0,
                ..Default::default()
            },
            stream(&[10, 9, 6, 8]),
            vec![5.0],
        );
        assert_eq!(
            broke.step(Answer::Bets(vec![10.0])).unwrap_err(),
            StepError::BetExceedsBankroll {
                seat: 0,
                bet: 10.0,
                money: 5.0
            }
        );
    }

    #[test]
    fn a_stream_too_short_to_deal_reports_exhaustion() {
        let mut t = table(&[10, 9, 6]);
        assert_eq!(
            t.step(Answer::Bets(vec![10.0])).unwrap_err(),
            StepError::CardsExhausted
        );
        assert!(!t.round_active());
    }

    /// The speculative tail stands hands out, which makes the dealer
    /// draw where a real hit-to-bust would not. A stream with exactly
    /// enough cards for the real line therefore has to survive the
    /// question that precedes it: the replay's own exhaustion is
    /// discarded along with the rest of the speculation.
    #[test]
    fn speculative_exhaustion_never_surfaces_as_an_error() {
        // Player 10,6 vs dealer 6; hitting the 10 busts, after which no
        // hand is live and the dealer draws nothing -- so four cards is
        // the whole round. Standing instead would send the dealer to the
        // (absent) fifth card.
        let mut t = table(&[10, 6, 6, 8, 10]);
        let step = t.step(Answer::Bets(vec![10.0])).unwrap();
        assert_eq!(ask(&step).kind, AskKind::Play);
        let step = t.step(Answer::Action(Action::Hit)).unwrap();
        let f = finished(&step);
        assert_eq!(f.record.players[0].hands, vec![vec![10, 6, 10]]);
        assert_eq!(f.record.players[0].winners, vec!["dealer"]);
    }

    /// Insurance is a real fork, not a formality: the two answers to the
    /// same deal settle differently, which is what proves the answer
    /// reached the engine rather than being defaulted by the replay.
    #[test]
    fn insurance_is_asked_first_and_both_answers_reach_the_engine() {
        // Dealer shows an ace over a ten, so insurance pays; the player
        // holds 10,6 and loses the main bet either way.
        let deal = [10, 1, 6, 10];
        let insured = |take: bool| {
            let mut t = RoundMachine::new(
                Rules {
                    min_bet: 10.0,
                    ..Default::default()
                },
                stream(&deal),
                vec![1000.0],
            );
            let step = t.step(Answer::Bets(vec![10.0])).unwrap();
            assert_eq!(ask(&step).kind, AskKind::Insurance);
            // An insurance ask carries no actions; it takes a yes/no.
            assert_eq!(ask(&step).valid, ValidActions::default());

            let step = t.step(Answer::Insurance(take)).unwrap();
            // No peek, so the round runs on to the play decision.
            assert_eq!(ask(&step).kind, AskKind::Play);
            let step = t.step(Answer::Action(Action::Stand)).unwrap();
            finished(&step).record.players[0].net
        };
        // 5 staked, 15 back, 10 bet lost: the hedge is exactly even.
        assert_eq!(insured(true), 0.0);
        assert_eq!(insured(false), -10.0);
    }

    #[test]
    fn splitting_asks_about_each_hand_in_turn() {
        let mut t = table(&[
            8, 9, 8, 7, /* split draws */ 3, 2, /* hits */ 10, 10,
        ]);
        let step = t.step(Answer::Bets(vec![10.0])).unwrap();
        assert!(ask(&step).valid.split);
        let step = t.step(Answer::Action(Action::Split)).unwrap();
        let a = ask(&step);
        assert_eq!(a.hand_index, 0);
        assert_eq!(a.players[0].hands, vec![vec![8, 3], vec![8, 2]]);

        let step = t.step(Answer::Action(Action::Stand)).unwrap();
        assert_eq!(ask(&step).hand_index, 1);
        let step = t.step(Answer::Action(Action::Stand)).unwrap();
        assert_eq!(finished(&step).record.players[0].hands.len(), 2);
    }

    /// The machine is `Send` -- that is what lets `Session` drop
    /// `unsendable`, and what lets a Rust caller move a table onto
    /// another thread.
    #[test]
    fn the_machine_is_send() {
        fn assert_send<T: Send>() {}
        assert_send::<RoundMachine<Source>>();
        assert_send::<Step>();
        assert_send::<Answer>();
    }

    /// The `serde` feature is what makes a step storable, so the derives
    /// are exercised rather than merely compiled.
    #[cfg(feature = "serde")]
    #[test]
    fn steps_answers_and_rules_round_trip_through_serde() {
        let mut t = table(&[10, 9, 6, 8, 5]);
        let step = t.step(Answer::Bets(vec![10.0])).unwrap();
        let json = serde_json::to_string(&step).unwrap();
        let back: Step = serde_json::from_str(&json).unwrap();
        assert_eq!(ask(&back).players[0].hands, ask(&step).players[0].hands);
        assert_eq!(ask(&back).dealer_up, Rank::Nine);
        assert_eq!(ask(&back).valid, ask(&step).valid);

        let step = t.step(Answer::Action(Action::Stand)).unwrap();
        let back: Step = serde_json::from_str(&serde_json::to_string(&step).unwrap()).unwrap();
        // Stood on 16 against the dealer's 17.
        assert_eq!(finished(&back).record.players[0].net, -10.0);
        assert_eq!(finished(&back).money, finished(&step).money);

        for answer in [
            Answer::Bets(vec![10.0]),
            Answer::Insurance(true),
            Answer::Action(Action::Double),
        ] {
            let json = serde_json::to_string(&answer).unwrap();
            assert_eq!(serde_json::from_str::<Answer>(&json).unwrap(), answer);
        }

        // Rules serialize with `double_on` as its canonical string, and
        // a round trip preserves the digest -- which is the whole point
        // of storing them.
        let rules = Rules {
            num_decks: 6,
            double_on: DoubleOn::NineToEleven,
            ..Default::default()
        };
        let json = serde_json::to_string(&rules).unwrap();
        assert!(json.contains("\"double_on\":\"9-11\""));
        let back: Rules = serde_json::from_str(&json).unwrap();
        assert_eq!(back, rules);
        assert_eq!(back.digest(), rules.digest());
    }
}
