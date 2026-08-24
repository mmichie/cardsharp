//! GPU-vs-CPU exactness tests: for every accepted configuration the GPU
//! engine must reproduce `run_batch_cpu`'s SimStats BIT-FOR-BIT (same
//! seed, same shard layout, same card streams, same f64 accumulation).
//! Skipped (with a note) when no usable GPU adapter is present.

use super::run_gpu_batch;
use crate::counting::{CountingConfig, Deviation};
use crate::round::RoundConfig;
use crate::rules::{DoubleOn, Rules};
use crate::shoe::{ShoeOptions, ShuffleStyle};
use crate::sim::{BatchCfg, run_batch_cpu};
use crate::stats::SimStats;
use crate::strategy::{Action, StrategyTable, TABLE_BYTES};

fn gpu_available() -> bool {
    match super::ctx() {
        Ok(_) => true,
        Err(e) => {
            eprintln!("skipping GPU exactness test: {e}");
            false
        }
    }
}

/// A strategy table exercising every action kind and fallback: hits and
/// stands, doubles on 9-11, DS on soft 17-18, splits for 2s/3s/6s/7s/8s/
/// 9s/aces, surrender on hard 15-16 vs strong upcards.
fn test_table() -> Vec<u8> {
    let mut t = vec![0u8; TABLE_BYTES];
    // Hard rows: totals 4..=21 (18 rows x 10 columns).
    for v in 4..=21u32 {
        for col in 0..10usize {
            let idx = (v as usize - 4) * 10 + col;
            t[idx] = match v {
                4..=8 => 0,               // hit
                9..=11 => 2,              // double
                12..=16 if col <= 4 => 1, // stand vs 2-6
                15..=16 if col >= 8 => 5, // surrender vs ten/ace
                12..=16 => 0,             // hit vs 7-9
                _ => 1,                   // stand 17+
            };
        }
    }
    // Soft rows: 13..=21 (9 rows), from 180.
    for v in 13..=21u32 {
        for col in 0..10usize {
            let idx = 180 + (v as usize - 13) * 10 + col;
            t[idx] = match v {
                13..=16 => 0,             // hit
                17 | 18 if col <= 4 => 3, // DS vs 2-6
                17 => 0,
                18 if col >= 7 => 0, // hit vs 9/ten/ace
                _ => 1,              // stand
            };
        }
    }
    // Pair rows: 2..=9, ten, ace (10 rows), from 270.
    for row in 0..10usize {
        for col in 0..10usize {
            let idx = 270 + row * 10 + col;
            t[idx] = match row {
                0 | 1 | 4 | 5 => {
                    if col <= 5 {
                        4 // split 2s/3s/6s/7s vs 2-7
                    } else {
                        0
                    }
                }
                6 => 4, // always split 8s
                7 => {
                    if col == 5 || col >= 8 {
                        1 // 9s stand vs 7/ten/ace
                    } else {
                        4
                    }
                }
                9 => 4, // always split aces
                8 => 1, // tens stand
                _ => {
                    if col <= 4 {
                        2 // 5s double vs 2-6 (row 3)
                    } else {
                        0
                    }
                }
            };
        }
    }
    t
}

fn base_rules() -> Rules {
    Rules {
        blackjack_payout: 1.5,
        dealer_hit_soft_17: true,
        allow_split: true,
        allow_double_down: true,
        allow_insurance: true,
        allow_surrender: true,
        allow_early_surrender: false,
        allow_double_after_split: false,
        allow_resplitting: false,
        dealer_peek: false,
        num_decks: 6,
        min_bet: 10.0,
        max_bet: 1000.0,
        max_splits: 3,
        insurance_payout: 2.0,
        five_card_charlie: false,
        penetration: 0.75,
        burn_cards: 0,
        resplit_aces: false,
        hit_split_aces: false,
        allow_obo: true,
        use_csm: false,
        double_on: DoubleOn::Any,
    }
}

fn shoe_options(rules: &Rules, style: ShuffleStyle) -> ShoeOptions {
    ShoeOptions {
        num_decks: rules.num_decks,
        penetration: rules.penetration,
        burn_cards: rules.burn_cards,
        use_csm: false,
        shuffle_style: style,
        shuffle_count: None,
    }
}

fn assert_stats_eq(cpu: &SimStats, gpu: &SimStats, label: &str) {
    assert_eq!(cpu.games_played, gpu.games_played, "{label}: games_played");
    assert_eq!(cpu.player_wins, gpu.player_wins, "{label}: player_wins");
    assert_eq!(cpu.dealer_wins, gpu.dealer_wins, "{label}: dealer_wins");
    assert_eq!(cpu.draws, gpu.draws, "{label}: draws");
    assert_eq!(cpu.n_rounds, gpu.n_rounds, "{label}: n_rounds");
    for (name, a, b) in [
        ("net_mean", cpu.net_mean, gpu.net_mean),
        ("net_m2", cpu.net_m2, gpu.net_m2),
        ("bet_mean", cpu.bet_mean, gpu.bet_mean),
        ("bet_m2", cpu.bet_m2, gpu.bet_m2),
        ("net_bet_c", cpu.net_bet_c, gpu.net_bet_c),
        ("net_sum", cpu.net_sum, gpu.net_sum),
        ("bet_sum", cpu.bet_sum, gpu.bet_sum),
        ("total_bet_sum", cpu.total_bet_sum, gpu.total_bet_sum),
    ] {
        assert_eq!(
            a.to_bits(),
            b.to_bits(),
            "{label}: {name} differs: cpu={a:?} gpu={b:?}"
        );
    }
}

#[allow(clippy::too_many_arguments)]
fn check_equality(
    label: &str,
    rules: &Rules,
    table_bytes: &[u8],
    counting: Option<&CountingConfig>,
    style: ShuffleStyle,
    n_rounds: u64,
    seed: u64,
    n_players: usize,
    initial_bankroll: f64,
    always_insure: bool,
) {
    let table = StrategyTable::from_bytes(table_bytes).expect("valid table");
    let options = shoe_options(rules, style);
    let batch = BatchCfg {
        round: RoundConfig {
            initial_bankroll,
            conditional_settlement: false,
        },
        n_players,
        always_insure,
    };
    let (cpu, _) = run_batch_cpu(
        rules, &table, &batch, counting, &options, n_rounds, seed, 0, false,
    )
    .expect("cpu batch");
    let gpu = run_gpu_batch(
        rules,
        table_bytes,
        &table,
        counting,
        &options,
        n_rounds,
        seed,
        n_players,
        initial_bankroll,
        always_insure,
    )
    .unwrap_or_else(|e| panic!("{label}: gpu batch failed: {e}"));
    assert_stats_eq(&cpu, &gpu, label);
}

fn i18_deviations() -> Vec<Deviation> {
    let dev = |hand_value: u32,
               is_soft: bool,
               dealer_value: u32,
               threshold: f64,
               above: Option<Action>,
               below: Option<Action>| Deviation {
        hand_value,
        is_soft,
        dealer_value,
        threshold,
        above,
        below,
    };
    vec![
        dev(16, false, 10, 0.0, Some(Action::Stand), Some(Action::Hit)),
        dev(15, false, 10, 4.0, Some(Action::Stand), None),
        dev(13, false, 2, -1.0, None, Some(Action::Hit)),
        dev(12, false, 3, 2.0, Some(Action::Stand), Some(Action::Hit)),
        dev(12, false, 4, 0.0, Some(Action::Stand), Some(Action::Hit)),
        dev(11, false, 11, 1.0, Some(Action::Double), None),
        dev(10, false, 10, 4.0, Some(Action::Double), None),
        dev(9, false, 2, 1.0, Some(Action::Double), None),
        dev(9, false, 7, 3.0, Some(Action::Double), None),
    ]
}

#[test]
fn gpu_matches_cpu_flat_basic() {
    if !gpu_available() {
        return;
    }
    let table = test_table();
    let rules = base_rules();
    check_equality(
        "flat-basic-6d",
        &rules,
        &table,
        None,
        ShuffleStyle::Perfect,
        60_000,
        12345,
        1,
        1000.0,
        false,
    );
}

#[test]
fn gpu_matches_cpu_across_rule_variants() {
    if !gpu_available() {
        return;
    }
    let table = test_table();

    let mut peek = base_rules();
    peek.dealer_peek = true;
    peek.dealer_hit_soft_17 = false;
    peek.allow_double_after_split = true;

    let mut no_peek_obo = base_rules();
    no_peek_obo.allow_obo = true;
    no_peek_obo.burn_cards = 2;

    let mut no_peek_no_obo = base_rules();
    no_peek_no_obo.allow_obo = false;
    no_peek_no_obo.allow_surrender = false;

    let mut early_surrender = base_rules();
    early_surrender.allow_early_surrender = true;
    early_surrender.dealer_peek = true;

    let mut charlie_65 = base_rules();
    charlie_65.five_card_charlie = true;
    charlie_65.blackjack_payout = 1.2; // 6:5, exercises inexact payouts
    charlie_65.num_decks = 2;
    charlie_65.penetration = 0.6;

    let mut single_deck = base_rules();
    single_deck.num_decks = 1;
    single_deck.penetration = 0.9;
    single_deck.allow_resplitting = true;
    single_deck.resplit_aces = true;
    single_deck.hit_split_aces = true;

    let mut tight_double = base_rules();
    tight_double.double_on = DoubleOn::NineToEleven;
    tight_double.dealer_peek = true;
    tight_double.max_splits = 1;

    for (label, rules) in [
        ("peek-s17-das", &peek),
        ("no-peek-obo-burn", &no_peek_obo),
        ("no-peek-no-obo", &no_peek_no_obo),
        ("early-surrender", &early_surrender),
        ("charlie-6to5-2d", &charlie_65),
        ("single-deck-rsa", &single_deck),
        ("double-9-11-max1", &tight_double),
    ] {
        check_equality(
            label,
            rules,
            &table,
            None,
            ShuffleStyle::Perfect,
            40_000,
            987 + rules.num_decks as u64,
            1,
            1000.0,
            false,
        );
    }
}

#[test]
fn gpu_matches_cpu_multi_player_and_insurance() {
    if !gpu_available() {
        return;
    }
    let table = test_table();
    let rules = base_rules();
    check_equality(
        "three-players",
        &rules,
        &table,
        None,
        ShuffleStyle::Perfect,
        30_000,
        555,
        3,
        1000.0,
        false,
    );
    check_equality(
        "always-insure",
        &rules,
        &table,
        None,
        ShuffleStyle::Perfect,
        30_000,
        556,
        2,
        1000.0,
        true,
    );
}

#[test]
fn gpu_matches_cpu_realistic_shuffles() {
    if !gpu_available() {
        return;
    }
    let table = test_table();
    let rules = base_rules();
    for style in [ShuffleStyle::Riffle, ShuffleStyle::Strip] {
        check_equality(
            &format!("shuffle-{style:?}"),
            &rules,
            &table,
            None,
            style,
            30_000,
            777,
            1,
            1000.0,
            false,
        );
    }
}

#[test]
fn gpu_matches_cpu_counting() {
    if !gpu_available() {
        return;
    }
    let table = test_table();
    let rules = base_rules();
    let counting = CountingConfig {
        deviations: i18_deviations(),
        initial_decks: 6.0,
    };
    // 80k rounds in one shard spans three 32768-round slices, so the
    // count/decks carry across waves is exercised here.
    check_equality(
        "counting-hilo",
        &rules,
        &table,
        Some(&counting),
        ShuffleStyle::Perfect,
        80_000,
        4242,
        1,
        1000.0,
        false,
    );

    let mut peek = base_rules();
    peek.dealer_peek = true;
    check_equality(
        "counting-peek-2p",
        &peek,
        &table,
        Some(&counting),
        ShuffleStyle::Perfect,
        40_000,
        4243,
        2,
        1000.0,
        false,
    );
}

#[test]
fn gpu_matches_cpu_edge_bankrolls_and_bets() {
    if !gpu_available() {
        return;
    }
    let table = test_table();
    let rules = base_rules();
    // Bankroll tight enough that can_afford denies doubles/splits after
    // earlier posts: exercises the integer money lattice.
    check_equality(
        "tight-bankroll",
        &rules,
        &table,
        None,
        ShuffleStyle::Perfect,
        30_000,
        808,
        1,
        25.0,
        false,
    );
    let mut quarter = base_rules();
    quarter.min_bet = 2.5;
    quarter.max_bet = 12.5;
    check_equality(
        "quarter-bets",
        &quarter,
        &table,
        None,
        ShuffleStyle::Perfect,
        30_000,
        809,
        1,
        100.25,
        false,
    );
}

#[test]
fn gpu_matches_cpu_counting_single_deck() {
    if !gpu_available() {
        return;
    }
    // Short single-deck shoes: frequent reshuffles (stale-count first
    // rounds), volatile true counts, and enough shoes per slice that the
    // ordering provisioning has to top up across waves.
    let table = test_table();
    let mut rules = base_rules();
    rules.num_decks = 1;
    rules.penetration = 0.9;
    let counting = CountingConfig {
        deviations: i18_deviations(),
        initial_decks: 1.0,
    };
    check_equality(
        "counting-1d-pen09",
        &rules,
        &table,
        Some(&counting),
        ShuffleStyle::Perfect,
        80_000,
        6161,
        1,
        1000.0,
        false,
    );
}

#[test]
fn gpu_matches_cpu_multiple_shards() {
    if !gpu_available() {
        return;
    }
    let table = test_table();
    let rules = base_rules();
    // 600k rounds = 3 shards: exercises the shard layout, ordered merge,
    // and wave batching across shards.
    check_equality(
        "flat-3-shards",
        &rules,
        &table,
        None,
        ShuffleStyle::Perfect,
        600_000,
        31337,
        1,
        1000.0,
        false,
    );
}

#[test]
fn gpu_matches_cpu_full_penetration_fallback() {
    if !gpu_available() {
        return;
    }
    let table = test_table();
    let mut rules = base_rules();
    rules.num_decks = 1;
    rules.penetration = 1.0; // forces mid-round exhaustion reshuffles
    // The kernel must flag these shards and the host must CPU-replay them
    // -- results still bit-identical.
    check_equality(
        "pen-1.0-cpu-fallback",
        &rules,
        &table,
        None,
        ShuffleStyle::Perfect,
        20_000,
        999,
        1,
        1000.0,
        false,
    );
}

#[test]
fn gpu_rejects_unsupported_configs() {
    // Gate checks run before device init, so this test needs no GPU.
    let table = test_table();
    let table_parsed = StrategyTable::from_bytes(&table).unwrap();
    let rules = base_rules();
    let options = shoe_options(&rules, ShuffleStyle::Perfect);

    let run = |rules: &Rules, options: &ShoeOptions, bankroll: f64, players: usize| {
        run_gpu_batch(
            rules,
            &table,
            &table_parsed,
            None,
            options,
            100,
            1,
            players,
            bankroll,
            false,
        )
    };

    let mut csm = options.clone();
    csm.use_csm = true;
    assert!(
        run(&rules, &csm, 1000.0, 1).is_err(),
        "CSM must be rejected"
    );
    assert!(
        run(&rules, &options, 1000.30, 1).is_err(),
        "non-quarter bankroll must be rejected"
    );
    assert!(
        run(&rules, &options, 1000.0, 8).is_err(),
        "8 players must be rejected"
    );
    let mut splits = rules.clone();
    splits.max_splits = 4;
    assert!(
        run(&splits, &options, 1000.0, 1).is_err(),
        "max_splits > 3 must be rejected"
    );
}
