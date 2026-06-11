//! Interactive resumable sessions on the fast core (beads-i2s.1).
//!
//! A `Session` plays rounds through the SAME `play_round` the batch entry
//! points use -- there is exactly one implementation of the round rules.
//! Inversion of control comes from running the round on a dedicated
//! worker thread whose `ChannelDecider` blocks on a channel whenever the
//! engine needs an answer; the Python side resumes it:
//!
//! ```text
//! session = Session(rules, n_players=1, bankroll=1000, seed=7)
//! step = session.begin_round([10.0])      # deal, run to first question
//! while step.phase != "round_over":
//!     step = session.apply("hit")          # answer, run to the next one
//! step.result                              # the round's RoundRecord
//! ```
//!
//! The shoe persists across rounds inside one session, so penetration,
//! burn cards, CSM behavior, and mid-round exhaustion recycling follow
//! the exact cut-card semantics the batch engine (and the retired
//! reference engine) implement. Per-seat bankrolls persist too; bets are
//! validated against them. GIL note: the session releases the GIL while
//! waiting on the worker, and the worker never touches Python, so there
//! is no deadlock surface; channel round-trips per decision are
//! microseconds, irrelevant at interactive or Python-strategy speeds.

use crate::card::Rank;
use crate::round::{Decider, DecisionPhase, PlayerRound, RoundConfig, play_round};
use crate::rules::Rules;
use crate::shoe::{CardStream, DealSource, OutOfCards, Shoe, ShoeOptions, ShuffleStyle};
use crate::sim::{RoundRecord, make_record};
use crate::strategy::{Action, ValidActions};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use rand::SeedableRng;
use rand_xoshiro::Xoshiro256PlusPlus;
use std::sync::Mutex;
use std::sync::mpsc::{Receiver, Sender, channel};
use std::thread::JoinHandle;

/// One seat's view of the table mid-round, snapshotted at every decision
/// point. Carries everything the event-translation layer needs to render
/// or emit per-card events by diffing consecutive snapshots.
#[pyclass(get_all)]
#[derive(Clone)]
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

/// What the session is waiting on Python for.
#[derive(Clone, Copy, PartialEq, Eq)]
enum PendingKind {
    Insurance,
    EarlySurrender,
    Play,
}

/// Worker -> session messages.
enum Request {
    Decision {
        kind: PendingKind,
        seat: usize,
        hand_index: usize,
        valid: ValidActions,
        snapshot: Vec<SeatSnapshot>,
        dealer_up: u8,
    },
    RoundDone {
        record: RoundRecord,
        money: Vec<f64>,
    },
    Fatal(String),
}

/// Session -> worker messages.
enum Reply {
    Start { bets: Vec<f64> },
    Act(Action),
    Insure(bool),
}

/// The interactive decider: every engine question crosses the channel to
/// Python and blocks until `apply()` answers. If the session side goes
/// away mid-round, the decider turns inert (stand / no insurance) so the
/// worker can unwind the round and exit instead of blocking forever.
struct ChannelDecider<'a> {
    bets: Vec<f64>,
    req_tx: &'a Sender<Request>,
    reply_rx: &'a Receiver<Reply>,
    dead: bool,
}

impl ChannelDecider<'_> {
    fn ask(&mut self, request: Request) -> Option<Reply> {
        if self.dead || self.req_tx.send(request).is_err() {
            self.dead = true;
            return None;
        }
        match self.reply_rx.recv() {
            Ok(reply) => Some(reply),
            Err(_) => {
                self.dead = true;
                None
            }
        }
    }
}

impl Decider for ChannelDecider<'_> {
    fn bet(&mut self, seat: usize, _rules: &Rules, _money: f64) -> f64 {
        // Bets arrive with begin_round (validated session-side); no
        // channel round-trip needed.
        self.bets[seat]
    }

    fn wants_insurance(&mut self, seat: usize, players: &[PlayerRound], dealer_up: Rank) -> bool {
        match self.ask(Request::Decision {
            kind: PendingKind::Insurance,
            seat,
            hand_index: 0,
            valid: ValidActions::default(),
            snapshot: snapshot_players(players),
            dealer_up: dealer_up.code(),
        }) {
            Some(Reply::Insure(yes)) => yes,
            Some(_) | None => {
                self.dead = true;
                false
            }
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
            DecisionPhase::EarlySurrender => PendingKind::EarlySurrender,
            DecisionPhase::Play => PendingKind::Play,
        };
        match self.ask(Request::Decision {
            kind,
            seat,
            hand_index,
            valid: *valid,
            snapshot: snapshot_players(players),
            dealer_up: dealer_up.code(),
        }) {
            Some(Reply::Act(action)) => action,
            Some(_) | None => {
                // Session gone or protocol breach: stand the hand out so
                // the round (and then the worker) can end.
                self.dead = true;
                Action::Stand
            }
        }
    }
}

/// Counts dealt cards so RoundDone can report cards_consumed, which the
/// plain Shoe does not track per round.
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

/// A session's card source: a seeded shoe for real play, or an injected
/// stream for tests and replays.
enum Source {
    Shoe(Box<Shoe>),
    Stream(CardStream),
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

fn worker_loop<S: DealSource>(
    rules: Rules,
    mut source: Tally<S>,
    mut money: Vec<f64>,
    req_tx: Sender<Request>,
    reply_rx: Receiver<Reply>,
) {
    let cfg = RoundConfig {
        // Only read by conditional settlement, which sessions never
        // enable; per-seat bankrolls live in `money`.
        initial_bankroll: 0.0,
        conditional_settlement: false,
    };
    loop {
        let bets = match reply_rx.recv() {
            Ok(Reply::Start { bets }) => bets,
            Ok(_) => {
                let _ = req_tx.send(Request::Fatal(
                    "protocol error: expected begin_round".to_string(),
                ));
                return;
            }
            Err(_) => return, // session dropped between rounds
        };

        let players: Vec<PlayerRound> = money.iter().map(|m| PlayerRound::new(*m)).collect();
        let mut decider = ChannelDecider {
            bets,
            req_tx: &req_tx,
            reply_rx: &reply_rx,
            dead: false,
        };
        let dealt_before = source.dealt;
        match play_round(&mut source, &rules, &cfg, &mut decider, players) {
            Ok(result) => {
                if decider.dead {
                    return; // session dropped mid-round; result is moot
                }
                for (seat, player) in result.players.iter().enumerate() {
                    money[seat] = player.money;
                }
                let consumed = (source.dealt - dealt_before) as u32;
                let record = make_record(result, consumed);
                if req_tx
                    .send(Request::RoundDone {
                        record,
                        money: money.clone(),
                    })
                    .is_err()
                {
                    return;
                }
            }
            Err(_) => {
                // Only the injected-stream source can run dry; the shoe
                // recycles. Surface it and end the session.
                let _ = req_tx.send(Request::Fatal(
                    "card stream exhausted mid-round".to_string(),
                ));
                return;
            }
        }
    }
}

/// One pending decision, session-side: what the worker awaits and which
/// answers are legal.
struct PendingDecision {
    kind: PendingKind,
    valid: ValidActions,
}

/// A resumable interactive blackjack session on the fast core.
///
/// `begin_round(bets)` starts a round on the persistent shoe and runs the
/// engine to its first question; `apply(action)` answers and runs to the
/// next. Each call returns a `SessionStep` whose `phase` is one of
/// `"insurance"` (answers: insure / decline), `"early_surrender"` (the
/// engine acts on surrender, anything else declines), `"decision"`
/// (answers: the step's valid_actions), or `"round_over"` (carrying the
/// full `RoundRecord`). Per-seat bankrolls persist across rounds and
/// gate bets.
#[pyclass(unsendable)]
pub struct Session {
    /// Mutex only so the receiver can be polled with the GIL released
    /// (`py.detach` needs Sync); the session itself is unsendable and
    /// never contended.
    req_rx: Mutex<Receiver<Request>>,
    reply_tx: Option<Sender<Reply>>,
    worker: Option<JoinHandle<()>>,
    n_players: usize,
    min_bet: f64,
    max_bet: f64,
    money: Vec<f64>,
    pending: Option<PendingDecision>,
    round_active: bool,
}

fn parse_action(name: &str) -> Option<Action> {
    Some(match name {
        "hit" => Action::Hit,
        "stand" => Action::Stand,
        "double" => Action::Double,
        "split" => Action::Split,
        "surrender" => Action::Surrender,
        _ => return None,
    })
}

fn valid_action_names(valid: &ValidActions) -> Vec<String> {
    let mut names = Vec::new();
    for (flag, name) in [
        (valid.hit, "hit"),
        (valid.stand, "stand"),
        (valid.double, "double"),
        (valid.split, "split"),
        (valid.surrender, "surrender"),
    ] {
        if flag {
            names.push(name.to_string());
        }
    }
    names
}

impl Session {
    fn pump(&mut self, py: Python<'_>) -> PyResult<SessionStep> {
        let received = py.detach(|| {
            self.req_rx
                .lock()
                .expect("session receiver lock poisoned")
                .recv()
        });
        match received {
            Ok(Request::Decision {
                kind,
                seat,
                hand_index,
                valid,
                snapshot,
                dealer_up,
            }) => {
                let (phase, valid_names) = match kind {
                    PendingKind::Insurance => (
                        "insurance",
                        vec!["insure".to_string(), "decline".to_string()],
                    ),
                    PendingKind::EarlySurrender => ("early_surrender", valid_action_names(&valid)),
                    PendingKind::Play => ("decision", valid_action_names(&valid)),
                };
                self.pending = Some(PendingDecision { kind, valid });
                Ok(SessionStep {
                    phase: phase.to_string(),
                    seat: Some(seat),
                    hand_index: Some(hand_index),
                    valid_actions: valid_names,
                    players: snapshot,
                    dealer_cards: vec![dealer_up as u32],
                    result: None,
                })
            }
            Ok(Request::RoundDone { record, money }) => {
                self.round_active = false;
                self.pending = None;
                self.money = money;
                let players = record
                    .players
                    .iter()
                    .map(|p| SeatSnapshot {
                        hands: p.hands.clone(),
                        actions: p.actions.clone(),
                        bets: p.bets.clone(),
                        hand_done: p.hands.iter().map(|_| true).collect(),
                        insurance: 0.0,
                        money: p.money,
                    })
                    .collect();
                Ok(SessionStep {
                    phase: "round_over".to_string(),
                    seat: None,
                    hand_index: None,
                    valid_actions: Vec::new(),
                    players,
                    dealer_cards: record.dealer_cards.clone(),
                    result: Some(record),
                })
            }
            Ok(Request::Fatal(msg)) => {
                self.round_active = false;
                self.pending = None;
                Err(PyRuntimeError::new_err(msg))
            }
            Err(_) => {
                self.round_active = false;
                self.pending = None;
                Err(PyRuntimeError::new_err("session worker terminated"))
            }
        }
    }

    fn sender(&self) -> PyResult<&Sender<Reply>> {
        self.reply_tx
            .as_ref()
            .ok_or_else(|| PyRuntimeError::new_err("session is closed"))
    }

    fn shutdown(&mut self) {
        self.reply_tx = None; // closes the channel; a waiting worker unwinds
        if let Some(handle) = self.worker.take() {
            let _ = handle.join();
        }
    }
}

#[pymethods]
impl Session {
    /// Open a session. With `cards`, rounds replay the injected sequence
    /// (no shuffling, for tests and replays); otherwise a real shoe is
    /// built from the rules (num_decks, penetration, burn_cards, CSM)
    /// and the shuffle options, seeded deterministically.
    #[new]
    #[pyo3(signature = (rules, n_players = 1, bankroll = 1000.0, seed = 0, cards = None, shuffle_type = "perfect", shuffle_count = None))]
    fn new(
        rules: PyRef<'_, Rules>,
        n_players: usize,
        bankroll: f64,
        seed: u64,
        cards: Option<Vec<u8>>,
        shuffle_type: &str,
        shuffle_count: Option<u32>,
    ) -> PyResult<Self> {
        if n_players < 1 {
            return Err(PyValueError::new_err("n_players must be at least 1"));
        }
        let rules: Rules = rules.clone();
        let (min_bet, max_bet) = (rules.min_bet, rules.max_bet);
        let money = vec![bankroll; n_players];
        let (reply_tx, reply_rx) = channel::<Reply>();
        let (req_tx, req_rx) = channel::<Request>();

        let inner = match cards {
            Some(codes) => {
                let stream: Vec<Rank> = codes
                    .iter()
                    .map(|c| Rank::from_code(*c).map_err(|e| PyValueError::new_err(e.to_string())))
                    .collect::<PyResult<_>>()?;
                Source::Stream(CardStream::new(stream))
            }
            None => {
                let options = ShoeOptions {
                    num_decks: rules.num_decks,
                    penetration: rules.penetration,
                    burn_cards: rules.burn_cards,
                    use_csm: rules.use_csm,
                    shuffle_style: ShuffleStyle::from_name(shuffle_type)
                        .map_err(PyValueError::new_err)?,
                    shuffle_count,
                };
                let rng = Xoshiro256PlusPlus::seed_from_u64(seed);
                Source::Shoe(Box::new(Shoe::new(options, rng)))
            }
        };
        let source = Tally { inner, dealt: 0 };
        let worker_money = money.clone();
        let worker =
            std::thread::spawn(move || worker_loop(rules, source, worker_money, req_tx, reply_rx));

        Ok(Session {
            req_rx: Mutex::new(req_rx),
            reply_tx: Some(reply_tx),
            worker: Some(worker),
            n_players,
            min_bet,
            max_bet,
            money,
            pending: None,
            round_active: false,
        })
    }

    /// Start a round with one bet per seat; runs the engine to its first
    /// question (or straight to round_over, e.g. on dealt blackjacks).
    fn begin_round(&mut self, py: Python<'_>, bets: Vec<f64>) -> PyResult<SessionStep> {
        if self.round_active {
            return Err(PyRuntimeError::new_err(
                "a round is already in progress; answer the pending step",
            ));
        }
        if bets.len() != self.n_players {
            return Err(PyValueError::new_err(format!(
                "expected {} bets, got {}",
                self.n_players,
                bets.len()
            )));
        }
        for (seat, bet) in bets.iter().enumerate() {
            if *bet < self.min_bet || *bet > self.max_bet {
                return Err(PyValueError::new_err(format!(
                    "seat {seat}: bet {bet} outside table limits [{}, {}]",
                    self.min_bet, self.max_bet
                )));
            }
            if *bet > self.money[seat] {
                return Err(PyValueError::new_err(format!(
                    "seat {seat}: bet {bet} exceeds bankroll {}",
                    self.money[seat]
                )));
            }
        }
        self.sender()?
            .send(Reply::Start { bets })
            .map_err(|_| PyRuntimeError::new_err("session worker terminated"))?;
        self.round_active = true;
        self.pump(py)
    }

    /// Answer the pending step: an action name for decision /
    /// early_surrender phases, or "insure" / "decline" for insurance.
    fn apply(&mut self, py: Python<'_>, action: &str) -> PyResult<SessionStep> {
        let pending = self
            .pending
            .as_ref()
            .ok_or_else(|| PyRuntimeError::new_err("no decision pending"))?;

        let reply = match pending.kind {
            PendingKind::Insurance => match action {
                "insure" => Reply::Insure(true),
                "decline" => Reply::Insure(false),
                other => {
                    return Err(PyValueError::new_err(format!(
                        "insurance phase takes 'insure' or 'decline', got '{other}'"
                    )));
                }
            },
            PendingKind::EarlySurrender | PendingKind::Play => {
                let parsed = parse_action(action)
                    .ok_or_else(|| PyValueError::new_err(format!("unknown action '{action}'")))?;
                if !pending.valid.contains(parsed) {
                    return Err(PyValueError::new_err(format!(
                        "action '{action}' is not legal here"
                    )));
                }
                Reply::Act(parsed)
            }
        };

        self.sender()?
            .send(reply)
            .map_err(|_| PyRuntimeError::new_err("session worker terminated"))?;
        self.pending = None;
        self.pump(py)
    }

    /// Per-seat bankrolls as of the last completed round.
    #[getter]
    fn money(&self) -> Vec<f64> {
        self.money.clone()
    }

    #[getter]
    fn n_players(&self) -> usize {
        self.n_players
    }

    /// True between begin_round and the round_over step.
    #[getter]
    fn round_active(&self) -> bool {
        self.round_active
    }

    /// Shut the session down; the worker thread exits. Further calls
    /// raise. Dropping the object does the same implicitly.
    fn close(&mut self) {
        self.shutdown();
    }
}

impl Drop for Session {
    fn drop(&mut self) {
        self.shutdown();
    }
}

/// One resumption point of an interactive round.
#[pyclass(get_all)]
#[derive(Clone)]
pub struct SessionStep {
    /// "insurance" | "early_surrender" | "decision" | "round_over".
    pub phase: String,
    /// Seat being asked (None at round_over).
    pub seat: Option<usize>,
    /// Hand index being asked about (None at round_over).
    pub hand_index: Option<usize>,
    /// Legal answers for `apply` at this step.
    pub valid_actions: Vec<String>,
    /// Every seat's current state.
    pub players: Vec<SeatSnapshot>,
    /// Dealer cards VISIBLE to the table: the upcard while the round is
    /// live, the full hand at round_over. The hole card never leaks
    /// early.
    pub dealer_cards: Vec<u32>,
    /// The completed round's record, at round_over only.
    pub result: Option<RoundRecord>,
}
