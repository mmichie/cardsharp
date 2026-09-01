//! Strategy table lookup and action resolution.
//!
//! The table is compiled on the Python side from the CSV charts (or solver
//! output) by `cardsharp.fastsim.encoding.encode_strategy_table` and crosses
//! the boundary as 370 bytes: 18 hard rows (totals 4-21), 9 soft rows
//! (13-21), 10 pair rows (2-9, ten-value, ace), each 10 dealer-upcard
//! columns (2-9, ten, ace). `decide` transliterates
//! `BasicStrategy.decide_action` + `_get_valid_action`, including every
//! fallback (DS, Rh/Rs, refused splits re-read as hard totals).

use crate::card::Rank;
use crate::hand::Hand;
use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
#[cfg_attr(feature = "serde", serde(rename_all = "lowercase"))]
pub enum Action {
    Hit,
    Stand,
    Double,
    Split,
    Surrender,
}

impl Action {
    /// String form matching `cardsharp.blackjack.action.Action.value`.
    /// This is also the serde spelling.
    pub fn as_str(self) -> &'static str {
        match self {
            Action::Hit => "hit",
            Action::Stand => "stand",
            Action::Double => "double",
            Action::Split => "split",
            Action::Surrender => "surrender",
        }
    }

    /// Parse the string form. The inverse of `as_str`, and what the
    /// session boundary uses to turn a caller's answer into an action.
    pub fn parse(name: &str) -> Option<Self> {
        Some(match name {
            "hit" => Action::Hit,
            "stand" => Action::Stand,
            "double" => Action::Double,
            "split" => Action::Split,
            "surrender" => Action::Surrender,
            _ => return None,
        })
    }
}

/// A cell in the strategy chart. `DoubleStand` is the chart's "DS"
/// (double if allowed, otherwise stand); it is never a playable action.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TableAction {
    Hit,
    Stand,
    Double,
    DoubleStand,
    Split,
    Surrender,
}

impl TableAction {
    fn from_byte(byte: u8) -> Result<Self, InvalidTable> {
        Ok(match byte {
            0 => TableAction::Hit,
            1 => TableAction::Stand,
            2 => TableAction::Double,
            3 => TableAction::DoubleStand,
            4 => TableAction::Split,
            5 => TableAction::Surrender,
            _ => return Err(InvalidTable::BadCell(byte)),
        })
    }

    /// The playable action a chart cell names directly, if any. Mirrors
    /// `hard_action in valid_actions` in the Python split fallback, where
    /// the "DS" string sentinel can never match a list of Action enums.
    fn as_action(self) -> Option<Action> {
        match self {
            TableAction::Hit => Some(Action::Hit),
            TableAction::Stand => Some(Action::Stand),
            TableAction::Double => Some(Action::Double),
            TableAction::Split => Some(Action::Split),
            TableAction::Surrender => Some(Action::Surrender),
            TableAction::DoubleStand => None,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub enum InvalidTable {
    BadLength(usize),
    BadCell(u8),
}

impl fmt::Display for InvalidTable {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            InvalidTable::BadLength(n) => {
                write!(f, "strategy table must be {TABLE_BYTES} bytes, got {n}")
            }
            InvalidTable::BadCell(b) => write!(f, "invalid strategy cell byte {b}"),
        }
    }
}

impl std::error::Error for InvalidTable {}

pub const TABLE_BYTES: usize = 18 * 10 + 9 * 10 + 10 * 10;

pub struct StrategyTable {
    hard: [[TableAction; 10]; 18],
    soft: [[TableAction; 10]; 9],
    pairs: [[TableAction; 10]; 10],
}

impl StrategyTable {
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, InvalidTable> {
        if bytes.len() != TABLE_BYTES {
            return Err(InvalidTable::BadLength(bytes.len()));
        }
        let mut table = StrategyTable {
            hard: [[TableAction::Hit; 10]; 18],
            soft: [[TableAction::Hit; 10]; 9],
            pairs: [[TableAction::Hit; 10]; 10],
        };
        let mut idx = 0;
        for row in table.hard.iter_mut() {
            for cell in row.iter_mut() {
                *cell = TableAction::from_byte(bytes[idx])?;
                idx += 1;
            }
        }
        for row in table.soft.iter_mut() {
            for cell in row.iter_mut() {
                *cell = TableAction::from_byte(bytes[idx])?;
                idx += 1;
            }
        }
        for row in table.pairs.iter_mut() {
            for cell in row.iter_mut() {
                *cell = TableAction::from_byte(bytes[idx])?;
                idx += 1;
            }
        }
        Ok(table)
    }

    /// Dealer upcard to chart column. Mirrors `BasicStrategy._dealer_index`.
    pub fn dealer_index(up: Rank) -> usize {
        let bj = up.bj_value();
        if bj == 11 {
            9
        } else if bj >= 10 {
            8
        } else {
            (bj - 2) as usize
        }
    }

    /// Raw chart lookup. Mirrors `BasicStrategy._lookup`: a rank pair reads
    /// the pair chart regardless of split legality; otherwise soft 13-21,
    /// then hard 4-21, defaulting to hit.
    fn lookup(&self, hand: &Hand, dealer_idx: usize) -> TableAction {
        if hand.is_rank_pair() {
            let bj = hand.ranks()[0].bj_value();
            let row = if bj == 11 {
                9
            } else if bj == 10 {
                8
            } else {
                (bj - 2) as usize
            };
            return self.pairs[row][dealer_idx];
        }
        let v = hand.value();
        if hand.is_soft() && (13..=21).contains(&v) {
            return self.soft[(v - 13) as usize][dealer_idx];
        }
        if (4..=21).contains(&v) {
            return self.hard[(v - 4) as usize][dealer_idx];
        }
        TableAction::Hit
    }

    /// Chart lookup plus validity resolution. Mirrors
    /// `BasicStrategy.decide_action` -> `_get_valid_action` exactly,
    /// including the Rh/Rs surrender fallback and the refused-split
    /// re-read of the hard chart.
    pub fn decide(&self, hand: &Hand, dealer_up: Rank, valid: &ValidActions) -> Action {
        let dealer_idx = Self::dealer_index(dealer_up);
        let chosen = self.lookup(hand, dealer_idx);

        match chosen {
            TableAction::DoubleStand => {
                // DS = double if allowed, otherwise stand.
                if valid.double {
                    Action::Double
                } else if valid.stand {
                    Action::Stand
                } else {
                    Action::Hit
                }
            }
            TableAction::Double => {
                if valid.double {
                    Action::Double
                } else if valid.hit {
                    Action::Hit
                } else {
                    Action::Stand
                }
            }
            TableAction::Surrender => {
                if valid.surrender {
                    return Action::Surrender;
                }
                // For pairs (e.g. 8,8 vs A) split is the correct fallback
                // before defaulting to hit.
                if valid.split {
                    return Action::Split;
                }
                // Published charts distinguish Rh (surrender else hit) from
                // Rs (surrender else stand): standing is right exactly for
                // hard 17+.
                if hand.value() >= 17 && !hand.is_soft() {
                    if valid.stand {
                        Action::Stand
                    } else {
                        Action::Hit
                    }
                } else if valid.hit {
                    Action::Hit
                } else {
                    Action::Stand
                }
            }
            TableAction::Split => {
                if valid.split {
                    return Action::Split;
                }
                // Cannot split: re-evaluate as the hard total (9,9 = hard
                // 18 -> stand, not hit).
                let v = hand.value();
                if (4..=21).contains(&v) {
                    let hard_action = self.hard[(v - 4) as usize][dealer_idx];
                    if let Some(action) = hard_action.as_action()
                        && valid.contains(action)
                    {
                        return action;
                    }
                }
                if valid.hit {
                    Action::Hit
                } else {
                    Action::Stand
                }
            }
            TableAction::Hit | TableAction::Stand => {
                let action = match chosen {
                    TableAction::Hit => Action::Hit,
                    _ => Action::Stand,
                };
                if valid.contains(action) {
                    return action;
                }
                // Last-resort fallback.
                if valid.hit {
                    Action::Hit
                } else if valid.stand {
                    Action::Stand
                } else {
                    valid.first()
                }
            }
        }
    }
}

/// The set of currently legal actions, in the Python engine's list order
/// (hit, stand, double, split, surrender).
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct ValidActions {
    pub hit: bool,
    pub stand: bool,
    pub double: bool,
    pub split: bool,
    pub surrender: bool,
}

impl ValidActions {
    pub fn hit_stand() -> Self {
        ValidActions {
            hit: true,
            stand: true,
            ..Default::default()
        }
    }

    pub fn stand_only() -> Self {
        ValidActions {
            stand: true,
            ..Default::default()
        }
    }

    pub fn contains(&self, action: Action) -> bool {
        match action {
            Action::Hit => self.hit,
            Action::Stand => self.stand,
            Action::Double => self.double,
            Action::Split => self.split,
            Action::Surrender => self.surrender,
        }
    }

    /// First action in Python list order; mirrors `valid_actions[0]` in the
    /// last-resort fallback.
    pub fn first(&self) -> Action {
        if self.hit {
            Action::Hit
        } else if self.stand {
            Action::Stand
        } else if self.double {
            Action::Double
        } else if self.split {
            Action::Split
        } else {
            Action::Surrender
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pair(rank: Rank) -> Hand {
        let mut h = Hand::new();
        h.add(rank);
        h.add(rank);
        h
    }

    /// A table where every cell is Surrender, to exercise fallbacks.
    fn all_surrender() -> StrategyTable {
        StrategyTable::from_bytes(&[5u8; TABLE_BYTES]).unwrap()
    }

    #[test]
    fn surrender_falls_back_rh_rs() {
        let table = all_surrender();
        let mut sixteen = Hand::new();
        sixteen.add(Rank::Ten);
        sixteen.add(Rank::Six);
        // 16: Rh -> hit when surrender unavailable.
        let valid = ValidActions::hit_stand();
        assert_eq!(table.decide(&sixteen, Rank::Ten, &valid), Action::Hit);

        let mut seventeen = Hand::new();
        seventeen.add(Rank::Ten);
        seventeen.add(Rank::Seven);
        // Hard 17: Rs -> stand when surrender unavailable.
        assert_eq!(table.decide(&seventeen, Rank::Ace, &valid), Action::Stand);
    }

    #[test]
    fn refused_split_rereads_hard_chart() {
        // Pair chart says split; hard chart all-stand; split not valid.
        let mut bytes = [1u8; TABLE_BYTES]; // stand everywhere
        for cell in bytes[270..370].iter_mut() {
            *cell = 4; // pairs: split
        }
        let table = StrategyTable::from_bytes(&bytes).unwrap();
        let nines = pair(Rank::Nine);
        let valid = ValidActions::hit_stand();
        // 9,9 with split refused = hard 18 -> stand.
        assert_eq!(table.decide(&nines, Rank::Six, &valid), Action::Stand);
    }

    #[test]
    fn ds_doubles_when_allowed_else_stands() {
        let bytes = [3u8; TABLE_BYTES];
        let table = StrategyTable::from_bytes(&bytes).unwrap();
        let mut soft18 = Hand::new();
        soft18.add(Rank::Ace);
        soft18.add(Rank::Seven);
        let mut valid = ValidActions::hit_stand();
        valid.double = true;
        assert_eq!(table.decide(&soft18, Rank::Six, &valid), Action::Double);
        valid.double = false;
        assert_eq!(table.decide(&soft18, Rank::Six, &valid), Action::Stand);
    }
}
