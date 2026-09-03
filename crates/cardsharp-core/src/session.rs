//! The Python face of an interactive session (beads-i2s.1).
//!
//! Everything here is translation. The round logic lives in
//! [`crate::machine::RoundMachine`], which is native, `Send`, and drives
//! the SAME `play_round` the batch entry points use -- there is exactly
//! one implementation of the round rules. This module turns its
//! [`Answer`]/[`Step`] vocabulary into the strings and pyclasses the
//! Python facade has always spoken:
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
//! burn cards, CSM behavior, and mid-round exhaustion recycling follow the
//! exact cut-card semantics the batch engine (and the retired reference
//! engine) implement. Per-seat bankrolls persist too; bets are validated
//! against them.
//!
//! There is no worker thread and no channel any more, and so no GIL
//! choreography: a step is a plain call that returns. The session is a
//! sendable `#[pyclass]`, and `close()` is a flag rather than a join.

use crate::machine::{Answer, Ask, AskKind, RoundMachine, SeatSnapshot, Source, Step, StepError};
use crate::rules::Rules;
use crate::sim::RoundRecord;
use crate::strategy::{Action, ValidActions};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;

/// `StepError` to the exception the facade has always raised. The split
/// is the Python one: a protocol/state problem is a `RuntimeError`, a bad
/// argument is a `ValueError`.
fn step_error(error: &StepError) -> PyErr {
    match error {
        StepError::NothingPending
        | StepError::RoundInProgress
        | StepError::WrongAnswer { .. }
        | StepError::CardsExhausted => PyRuntimeError::new_err(error.to_string()),
        StepError::IllegalAction(_)
        | StepError::BetCount { .. }
        | StepError::BetOutsideLimits { .. }
        | StepError::BetExceedsBankroll { .. } => PyValueError::new_err(error.to_string()),
    }
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

fn ask_step(ask: Ask) -> SessionStep {
    let (phase, valid_actions) = match ask.kind {
        AskKind::Insurance => (
            "insurance",
            vec!["insure".to_string(), "decline".to_string()],
        ),
        AskKind::EarlySurrender => ("early_surrender", valid_action_names(&ask.valid)),
        AskKind::Play => ("decision", valid_action_names(&ask.valid)),
    };
    SessionStep {
        phase: phase.to_string(),
        seat: Some(ask.seat),
        hand_index: Some(ask.hand_index),
        valid_actions,
        players: ask.players,
        dealer_cards: vec![ask.dealer_up.code() as u32],
        result: None,
    }
}

fn round_over_step(record: RoundRecord) -> SessionStep {
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
    SessionStep {
        phase: "round_over".to_string(),
        seat: None,
        hand_index: None,
        valid_actions: Vec::new(),
        players,
        dealer_cards: record.dealer_cards.clone(),
        result: Some(record),
    }
}

fn to_session_step(step: Step) -> SessionStep {
    match step {
        Step::Ask(ask) => ask_step(ask),
        Step::RoundOver(finished) => round_over_step(finished.record),
    }
}

/// A resumable interactive blackjack session on the fast core.
///
/// `begin_round(bets)` starts a round on the persistent shoe and runs the
/// engine to its first question; `apply(action)` answers and runs to the
/// next. Each call returns a `SessionStep` whose `phase` is one of
/// `"insurance"` (answers: insure / decline), `"early_surrender"` (the
/// engine acts on surrender, anything else declines), `"decision"`
/// (answers: the step's valid_actions), or `"round_over"` (carrying the
/// full `RoundRecord`). Per-seat bankrolls persist across rounds and gate
/// bets.
#[pyclass]
pub struct Session {
    machine: RoundMachine<Source>,
    closed: bool,
}

impl Session {
    fn open(&self) -> PyResult<()> {
        if self.closed {
            return Err(PyRuntimeError::new_err("session is closed"));
        }
        Ok(())
    }

    fn advance(&mut self, answer: Answer) -> PyResult<SessionStep> {
        self.machine
            .step(answer)
            .map(to_session_step)
            .map_err(|e| step_error(&e))
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
        let source = match cards {
            Some(codes) => {
                let stream = codes
                    .iter()
                    .map(|c| {
                        crate::card::Rank::from_code(*c)
                            .map_err(|e| PyValueError::new_err(e.to_string()))
                    })
                    .collect::<PyResult<Vec<_>>>()?;
                Source::stream(stream)
            }
            None => Source::shoe(&rules, shuffle_type, shuffle_count, seed)
                .map_err(PyValueError::new_err)?,
        };
        Ok(Session {
            machine: RoundMachine::new(rules, source, vec![bankroll; n_players]),
            closed: false,
        })
    }

    /// Start a round with one bet per seat; runs the engine to its first
    /// question (or straight to round_over, e.g. on dealt blackjacks).
    fn begin_round(&mut self, bets: Vec<f64>) -> PyResult<SessionStep> {
        self.open()?;
        self.advance(Answer::Bets(bets))
    }

    /// Answer the pending step: an action name for decision /
    /// early_surrender phases, or "insure" / "decline" for insurance.
    fn apply(&mut self, action: &str) -> PyResult<SessionStep> {
        self.open()?;
        let pending = self
            .machine
            .pending()
            .ok_or_else(|| PyRuntimeError::new_err("no decision pending"))?;

        let answer = match pending.kind {
            AskKind::Insurance => match action {
                "insure" => Answer::Insurance(true),
                "decline" => Answer::Insurance(false),
                other => {
                    return Err(PyValueError::new_err(format!(
                        "insurance phase takes 'insure' or 'decline', got '{other}'"
                    )));
                }
            },
            AskKind::EarlySurrender | AskKind::Play => Answer::Action(
                Action::parse(action)
                    .ok_or_else(|| PyValueError::new_err(format!("unknown action '{action}'")))?,
            ),
        };
        self.advance(answer)
    }

    /// Per-seat bankrolls as of the last completed round.
    #[getter]
    fn money(&self) -> Vec<f64> {
        self.machine.money().to_vec()
    }

    #[getter]
    fn n_players(&self) -> usize {
        self.machine.n_players()
    }

    /// True between begin_round and the round_over step.
    #[getter]
    fn round_active(&self) -> bool {
        self.machine.round_active()
    }

    /// Shut the session down. Further `begin_round` / `apply` calls
    /// raise; the read-only attributes keep answering.
    fn close(&mut self) {
        self.closed = true;
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
