//! GPU engine: a wgpu compute backend for `simulate_batch` that is
//! bit-identical to the CPU fast core for every configuration it accepts.
//!
//! Architecture -- "CPU shuffles, GPU plays, host settles":
//!
//! - The shard layout and per-shard seeds are exactly `sim::shard_layout`.
//! - The host generates each shard's shuffle-ordering sequence with
//!   `shoe::OrderingGen`, which shares the shoe's shuffle code and RNG, so
//!   the GPU consumes the very card streams the CPU engine would deal.
//! - The kernel (kernel.wgsl) plays rounds in pure integer arithmetic and
//!   emits one packed outcome word per (round, seat).
//! - The host replays all money arithmetic and Welford statistics in f64
//!   (gpu/replay.rs), per round in shard order, and merges shards in order
//!   -- reproducing `simulate_batch`'s report bit-for-bit.
//!
//! Parallelism: without counting, shoes are independent, so each GPU
//! thread plays one shoe (massive fan-out). With counting, the running
//! count carries across shoe boundaries (the first round of a fresh shoe
//! bets and plays on the previous shoe's stale count until finish_round
//! resets it -- a preserved reference quirk), so each thread plays one
//! shard, sliced across waves with an explicit carry.
//!
//! True-count thresholds compare exactly in integers: tc >= thr is
//! count*4*den >= thr4*num for decks = num/den. For quarter-representable
//! thresholds this is equivalent to the CPU's f64 comparison: whenever the
//! rational tc does not equal thr exactly, |tc - thr| >= 1/(4*cards) --
//! astronomically larger than the f64 double-rounding error -- and exact
//! equality forces 13 | 4*thr*... which cannot happen for |thr| <= 26, so
//! the f64 value can never land on the wrong side. Configurations outside
//! the gates below simply refuse (the Python facade falls back to the CPU
//! core); a shard whose play the kernel cannot reproduce exactly
//! (mid-round shoe exhaustion consumes RNG mid-round) is replayed on the
//! CPU shard runner, which is exact because shards are independent.

mod replay;
#[cfg(test)]
mod tests;

use crate::counting::CountingConfig;
use crate::rules::Rules;
use crate::shoe::{OrderingGen, ShoeOptions, ShuffleStyle};
use crate::sim::{BatchCfg, run_shard, shard_layout};
use crate::stats::SimStats;
use crate::strategy::{Action, StrategyTable};
#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyDict;
use rand::SeedableRng;
use rand_xoshiro::Xoshiro256PlusPlus;
use rayon::prelude::*;
use replay::RoundReplayer;
use std::sync::OnceLock;

// ---------------------------------------------------------------------
// GPU ABI (must match kernel.wgsl)
// ---------------------------------------------------------------------

#[repr(C)]
#[derive(Clone, Copy, Default, bytemuck::Pod, bytemuck::Zeroable)]
struct GpuParams {
    total_cards: u32,
    reshuffle_point: u32,
    burn: u32,
    n_players: u32,
    max_hands: u32,
    stride_words: u32,
    mode_shard: u32,
    counting_on: u32,
    always_insure: u32,
    rules_bits: u32,
    double_on: u32,
    n_deviations: u32,
    min_bet_e8: i32,
    max_bet_e8: i32,
    bankroll_e8: i32,
    init_decks_num: u32,
    init_decks_den: u32,
    max_rounds_per_seg: u32,
    n_segments: u32,
    pad_: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Default, bytemuck::Pod, bytemuck::Zeroable)]
struct GpuSegment {
    cards_base: u32, // in card units; always word-aligned
    n_orderings: u32,
    round_budget: u32,
    rec_base: u32, // in round-record units
    carry_count: i32,
    decks_num: u32,
    decks_den: u32,
    next_pos: u32,
    ordering_idx: u32,
    pad0: u32,
    pad1: u32,
    pad2: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Default, bytemuck::Pod, bytemuck::Zeroable)]
struct GpuStatus {
    rounds_played: u32,
    flags: u32,
    out_count: i32,
    out_decks_num: u32,
    out_decks_den: u32,
    out_next: u32,
    out_ordering: u32,
    pad0: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Default, bytemuck::Pod, bytemuck::Zeroable)]
struct GpuDeviation {
    hand_value: u32,
    is_soft: u32,
    dealer_value: u32,
    thr4: i32,
    above: i32,
    below: i32,
}

const F_EXHAUSTED: u32 = 1;
const F_ORDER_OUT: u32 = 2;
const F_GUARD: u32 = 16;

const RB_DEALER_PEEK: u32 = 1;
const RB_ALLOW_INSURANCE: u32 = 2;
const RB_ALLOW_EARLY_SURRENDER: u32 = 4;
const RB_ALLOW_SURRENDER: u32 = 8;
const RB_ALLOW_SPLIT: u32 = 16;
const RB_ALLOW_DOUBLE: u32 = 32;
const RB_ALLOW_DAS: u32 = 64;
const RB_ALLOW_RESPLIT: u32 = 128;
const RB_RESPLIT_ACES: u32 = 256;
const RB_HIT_SPLIT_ACES: u32 = 512;
const RB_FIVE_CARD_CHARLIE: u32 = 1024;
const RB_DEALER_H17: u32 = 2048;

// Wave sizing. Buffers stay far under wgpu's default 128MB binding limit.
const WAVE_RECORD_WORD_CAP: usize = 24 << 20;
const WAVE_CARD_WORD_CAP: usize = 24 << 20;
const WAVE_SEGMENT_CAP: usize = 1 << 20;
const PER_SHARD_SHOE_CAP: usize = 8192;
const SHARD_SLICE_ROUNDS: u64 = 32768;

// ---------------------------------------------------------------------
// Device context (cached for the process lifetime)
// ---------------------------------------------------------------------

struct GpuCtx {
    device: wgpu::Device,
    queue: wgpu::Queue,
    pipeline: wgpu::ComputePipeline,
    adapter_info: wgpu::AdapterInfo,
}

static CTX: OnceLock<Result<GpuCtx, String>> = OnceLock::new();

fn ctx() -> Result<&'static GpuCtx, String> {
    CTX.get_or_init(init_ctx).as_ref().map_err(|e| e.clone())
}

fn init_ctx() -> Result<GpuCtx, String> {
    let instance =
        wgpu::Instance::new(wgpu::InstanceDescriptor::new_without_display_handle_from_env());
    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
        power_preference: wgpu::PowerPreference::HighPerformance,
        ..Default::default()
    }))
    .map_err(|e| format!("no usable GPU adapter: {e}"))?;
    let adapter_info = adapter.get_info();
    let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor {
        label: Some("cardsharp-gpu"),
        ..Default::default()
    }))
    .map_err(|e| format!("GPU device unavailable: {e}"))?;
    let shader = device.create_shader_module(wgpu::include_wgsl!("kernel.wgsl"));
    let pipeline = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
        label: Some("cardsharp-round-kernel"),
        layout: None,
        module: &shader,
        entry_point: Some("main"),
        compilation_options: Default::default(),
        cache: None,
    });
    Ok(GpuCtx {
        device,
        queue,
        pipeline,
        adapter_info,
    })
}

// ---------------------------------------------------------------------
// Gates: exactness prerequisites. Everything rejected here falls back to
// the CPU core in the Python facade.
// ---------------------------------------------------------------------

/// A money parameter in eighth-units, exact when the value is
/// quarter-representable (all mid-round money then stays on the
/// eighth-unit lattice, where f64 comparisons equal integer comparisons).
fn money_e8(x: f64, name: &str) -> Result<i32, String> {
    if !x.is_finite() || !(0.0..=1.0e8).contains(&x) {
        return Err(format!(
            "{name} {x} outside the GPU engine's [0, 1e8] range"
        ));
    }
    if (x * 4.0).fract() != 0.0 {
        return Err(format!(
            "{name} {x} is not a multiple of 0.25 (required for exact GPU money arithmetic)"
        ));
    }
    Ok((x * 8.0) as i32)
}

struct GpuConfig {
    params: GpuParams, // n_segments/mode filled per wave
    deviations: Vec<GpuDeviation>,
    table_words: Vec<u32>,
    counting_on: bool,
    max_rps: u32, // upper bound on rounds per shoe
}

fn action_code(a: Action) -> i32 {
    match a {
        Action::Hit => 0,
        Action::Stand => 1,
        Action::Double => 2,
        Action::Split => 3,
        Action::Surrender => 4,
    }
}

fn build_config(
    rules: &Rules,
    table_bytes: &[u8],
    counting: Option<&CountingConfig>,
    shoe_options: &ShoeOptions,
    n_players: usize,
    initial_bankroll: f64,
    always_insure: bool,
) -> Result<GpuConfig, String> {
    if shoe_options.use_csm {
        return Err("CSM shoes are not supported by the GPU engine".into());
    }
    if !(1..=7).contains(&n_players) {
        return Err(format!(
            "GPU engine supports 1..=7 players, got {n_players}"
        ));
    }
    if rules.max_splits > 3 {
        return Err(format!(
            "GPU engine supports max_splits <= 3, got {}",
            rules.max_splits
        ));
    }
    if rules.num_decks > 32 {
        return Err(format!(
            "GPU engine supports up to 32 decks, got {}",
            rules.num_decks
        ));
    }
    let total_cards = 52u32 * rules.num_decks;
    // Exactly Shoe::new's reshuffle point.
    let reshuffle_point = (total_cards as f64 * shoe_options.penetration) as u32;
    let burn = shoe_options.burn_cards;
    if reshuffle_point <= burn {
        return Err(format!(
            "GPU engine requires the reshuffle point ({reshuffle_point}) to exceed \
             burn_cards ({burn})"
        ));
    }

    let min_bet_e8 = money_e8(rules.min_bet, "min_bet")?;
    let max_bet_e8 = money_e8(rules.max_bet, "max_bet")?;
    let bankroll_e8 = money_e8(initial_bankroll, "initial_bankroll")?;

    let mut rules_bits = 0u32;
    let mut set = |on: bool, bit: u32| {
        if on {
            rules_bits |= bit;
        }
    };
    set(rules.dealer_peek, RB_DEALER_PEEK);
    set(rules.allow_insurance, RB_ALLOW_INSURANCE);
    set(rules.allow_early_surrender, RB_ALLOW_EARLY_SURRENDER);
    set(rules.allow_surrender, RB_ALLOW_SURRENDER);
    set(rules.allow_split, RB_ALLOW_SPLIT);
    set(rules.allow_double_down, RB_ALLOW_DOUBLE);
    set(rules.allow_double_after_split, RB_ALLOW_DAS);
    set(rules.allow_resplitting, RB_ALLOW_RESPLIT);
    set(rules.resplit_aces, RB_RESPLIT_ACES);
    set(rules.hit_split_aces, RB_HIT_SPLIT_ACES);
    set(rules.five_card_charlie, RB_FIVE_CARD_CHARLIE);
    set(rules.dealer_hit_soft_17, RB_DEALER_H17);

    let double_on = match rules.double_on {
        crate::rules::DoubleOn::Any => 0u32,
        crate::rules::DoubleOn::NineToEleven => 1,
        crate::rules::DoubleOn::TenToEleven => 2,
    };

    let mut deviations = Vec::new();
    let mut init_decks_num = 2u32;
    let mut init_decks_den = 2u32;
    if let Some(c) = counting {
        let d2 = c.initial_decks * 2.0;
        if !(1.0..=4000.0).contains(&d2) || d2.fract() != 0.0 {
            return Err(format!(
                "GPU engine requires initial_decks in half-deck steps within \
                 [0.5, 2000], got {}",
                c.initial_decks
            ));
        }
        init_decks_num = d2 as u32;
        init_decks_den = 2;
        if c.deviations.len() > 64 {
            return Err(format!(
                "GPU engine supports at most 64 deviations, got {}",
                c.deviations.len()
            ));
        }
        for d in &c.deviations {
            let t4 = d.threshold * 4.0;
            if !t4.is_finite() || t4.fract() != 0.0 || t4.abs() > 104.0 {
                return Err(format!(
                    "GPU engine requires deviation thresholds in quarter steps \
                     within [-26, 26], got {}",
                    d.threshold
                ));
            }
            deviations.push(GpuDeviation {
                hand_value: d.hand_value,
                is_soft: d.is_soft as u32,
                dealer_value: d.dealer_value,
                thr4: t4 as i32,
                above: d.above.map_or(-1, action_code),
                below: d.below.map_or(-1, action_code),
            });
        }
    }

    // Upper bound on rounds per shoe: a round begins while next < the
    // reshuffle point and consumes at least 2*(n_players + 1) cards.
    let min_cards_per_round = 2 * (n_players as u32 + 1);
    let max_rps = (reshuffle_point - burn - 1) / min_cards_per_round + 1;

    let stride_words = total_cards.div_ceil(4);
    let mut table_words = vec![0u32; 93];
    for (i, b) in table_bytes.iter().enumerate() {
        table_words[i / 4] |= (*b as u32) << ((i % 4) * 8);
    }

    Ok(GpuConfig {
        params: GpuParams {
            total_cards,
            reshuffle_point,
            burn,
            n_players: n_players as u32,
            max_hands: rules.max_splits + 1,
            stride_words,
            mode_shard: 0,
            counting_on: counting.is_some() as u32,
            always_insure: always_insure as u32,
            rules_bits,
            double_on,
            n_deviations: deviations.len() as u32,
            min_bet_e8,
            max_bet_e8,
            bankroll_e8,
            init_decks_num,
            init_decks_den,
            max_rounds_per_seg: max_rps,
            n_segments: 0,
            pad_: 0,
        },
        deviations,
        table_words,
        counting_on: counting.is_some(),
        max_rps,
    })
}

// ---------------------------------------------------------------------
// Wave dispatch
// ---------------------------------------------------------------------

fn readback(device: &wgpu::Device, buffer: &wgpu::Buffer) -> Result<Vec<u32>, String> {
    let slice = buffer.slice(..);
    let (tx, rx) = std::sync::mpsc::channel();
    slice.map_async(wgpu::MapMode::Read, move |r| {
        let _ = tx.send(r);
    });
    device
        .poll(wgpu::PollType::wait_indefinitely())
        .map_err(|e| format!("GPU poll failed: {e:?}"))?;
    rx.recv()
        .map_err(|_| "GPU readback channel closed".to_string())?
        .map_err(|e| format!("GPU buffer map failed: {e:?}"))?;
    let data = slice
        .get_mapped_range()
        .map_err(|e| format!("GPU mapped range failed: {e:?}"))?;
    let out: Vec<u32> = bytemuck::cast_slice(&data).to_vec();
    drop(data);
    buffer.unmap();
    Ok(out)
}

fn run_wave(
    gpu: &GpuCtx,
    params: &GpuParams,
    cards: &[u32],
    segments: &[GpuSegment],
    table_words: &[u32],
    deviations: &[GpuDeviation],
    record_rounds: u32,
) -> Result<(Vec<u32>, Vec<GpuStatus>), String> {
    use wgpu::util::DeviceExt;
    let device = &gpu.device;

    let params_buf = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("params"),
        contents: bytemuck::bytes_of(params),
        usage: wgpu::BufferUsages::UNIFORM,
    });
    let cards_buf = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("cards"),
        contents: bytemuck::cast_slice(cards),
        usage: wgpu::BufferUsages::STORAGE,
    });
    let seg_buf = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("segments"),
        contents: bytemuck::cast_slice(segments),
        usage: wgpu::BufferUsages::STORAGE,
    });
    let table_buf = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("table"),
        contents: bytemuck::cast_slice(table_words),
        usage: wgpu::BufferUsages::STORAGE,
    });
    let dummy = [GpuDeviation::default()];
    let dev_slice: &[GpuDeviation] = if deviations.is_empty() {
        &dummy
    } else {
        deviations
    };
    let dev_buf = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("deviations"),
        contents: bytemuck::cast_slice(dev_slice),
        usage: wgpu::BufferUsages::STORAGE,
    });
    let record_words = record_rounds as u64 * params.n_players as u64;
    let records_buf = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("records"),
        size: (record_words.max(1)) * 4,
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC,
        mapped_at_creation: false,
    });
    let status_bytes = (segments.len() * std::mem::size_of::<GpuStatus>()) as u64;
    let status_buf = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("status"),
        size: status_bytes,
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC,
        mapped_at_creation: false,
    });
    let staging_records = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("staging-records"),
        size: (record_words.max(1)) * 4,
        usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
        mapped_at_creation: false,
    });
    let staging_status = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("staging-status"),
        size: status_bytes,
        usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
        mapped_at_creation: false,
    });

    let layout = gpu.pipeline.get_bind_group_layout(0);
    let entries: Vec<wgpu::BindGroupEntry> = [
        &params_buf,
        &cards_buf,
        &seg_buf,
        &table_buf,
        &dev_buf,
        &records_buf,
        &status_buf,
    ]
    .iter()
    .enumerate()
    .map(|(i, b)| wgpu::BindGroupEntry {
        binding: i as u32,
        resource: b.as_entire_binding(),
    })
    .collect();
    let bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("cardsharp-wave"),
        layout: &layout,
        entries: &entries,
    });

    let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
        label: Some("cardsharp-wave"),
    });
    {
        let mut pass = encoder.begin_compute_pass(&wgpu::ComputePassDescriptor {
            label: Some("cardsharp-wave"),
            timestamp_writes: None,
        });
        pass.set_pipeline(&gpu.pipeline);
        pass.set_bind_group(0, &bind_group, &[]);
        pass.dispatch_workgroups((segments.len() as u32).div_ceil(64), 1, 1);
    }
    encoder.copy_buffer_to_buffer(
        &records_buf,
        0,
        &staging_records,
        0,
        record_words.max(1) * 4,
    );
    encoder.copy_buffer_to_buffer(&status_buf, 0, &staging_status, 0, status_bytes);
    gpu.queue.submit([encoder.finish()]);

    let records = readback(device, &staging_records)?;
    let status_words = readback(device, &staging_status)?;
    let statuses: Vec<GpuStatus> = bytemuck::cast_slice(&status_words).to_vec();
    Ok((records, statuses))
}

// ---------------------------------------------------------------------
// Orchestration
// ---------------------------------------------------------------------

fn pack_ordering(cards: &[crate::card::Rank], stride_words: usize) -> Vec<u32> {
    let mut words = vec![0u32; stride_words];
    for (i, r) in cards.iter().enumerate() {
        words[i / 4] |= (r.code() as u32) << ((i % 4) * 8);
    }
    words
}

struct ShardRun {
    seed: u64,
    target: u64,
    rounds_done: u64,
    stats: SimStats,
    needs_cpu: bool,
    finished: bool,
    // Shoe mode: the lazily built generator.
    ordering_gen: Option<OrderingGen>,
    // Shard mode: pending packed orderings; [0] is the current one.
    pending: Vec<Vec<u32>>,
    carry_count: i32,
    decks_num: u32,
    decks_den: u32,
    next_pos: u32,
}

impl ShardRun {
    fn new(target: u64, seed: u64, params: &GpuParams) -> Self {
        ShardRun {
            seed,
            target,
            rounds_done: 0,
            stats: SimStats::new(),
            needs_cpu: false,
            finished: target == 0,
            ordering_gen: None,
            pending: Vec::new(),
            carry_count: 0,
            decks_num: params.init_decks_num,
            decks_den: params.init_decks_den,
            next_pos: params.burn,
        }
    }
}

/// Running estimate of rounds per shoe, for provisioning orderings.
struct RoundsPerShoe {
    rounds: u64,
    shoes: u64,
    initial: u64,
}

impl RoundsPerShoe {
    fn new(cfg: &GpuConfig, n_players: usize) -> Self {
        // A typical round consumes ~5.4 cards for one player and ~2.7 per
        // extra seat; only provisioning depends on this, never results.
        let usable = (cfg.params.reshuffle_point - cfg.params.burn) as u64;
        let est = (usable * 10 / (27 * n_players as u64 + 27)).max(1);
        RoundsPerShoe {
            rounds: 0,
            shoes: 0,
            initial: est,
        }
    }

    fn record(&mut self, rounds: u64, shoes: u64) {
        self.rounds += rounds;
        self.shoes += shoes;
    }

    fn estimate(&self) -> u64 {
        if self.shoes >= 8 {
            (self.rounds / self.shoes).max(1)
        } else {
            self.initial
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn run_gpu_batch(
    rules: &Rules,
    table_bytes: &[u8],
    table: &StrategyTable,
    counting: Option<&CountingConfig>,
    shoe_options: &ShoeOptions,
    n_rounds: u64,
    seed: u64,
    n_players: usize,
    initial_bankroll: f64,
    always_insure: bool,
) -> Result<SimStats, String> {
    let cfg = build_config(
        rules,
        table_bytes,
        counting,
        shoe_options,
        n_players,
        initial_bankroll,
        always_insure,
    )?;
    let gpu = ctx()?;

    let shards_layout = shard_layout(n_rounds, seed);
    let mut shards: Vec<ShardRun> = shards_layout
        .iter()
        .map(|(rounds, shard_seed)| ShardRun::new(*rounds, *shard_seed, &cfg.params))
        .collect();

    let replayer = RoundReplayer {
        rules,
        n_players,
        initial_bankroll,
        counting: cfg.counting_on,
    };

    if n_rounds > 0 {
        if cfg.counting_on {
            run_shard_mode(gpu, &cfg, &mut shards, shoe_options, &replayer)?;
        } else {
            run_shoe_mode(gpu, &cfg, &mut shards, shoe_options, &replayer)?;
        }
    }

    // Shards the kernel could not reproduce exactly replay wholesale on
    // the CPU shard runner -- exact, because shards are independent.
    let batch = BatchCfg {
        round: crate::round::RoundConfig {
            initial_bankroll,
            conditional_settlement: false,
        },
        n_players,
        always_insure,
    };
    let cpu_stats: Vec<(usize, SimStats)> = shards
        .par_iter()
        .enumerate()
        .filter(|(_, s)| s.needs_cpu)
        .map(|(i, s)| {
            run_shard(
                rules,
                table,
                &batch,
                counting,
                shoe_options,
                s.target,
                s.seed,
                false,
            )
            .map(|(stats, _)| (i, stats))
        })
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| e.to_string())?;
    for (i, stats) in cpu_stats {
        shards[i].stats = stats;
    }

    let mut total = SimStats::new();
    for s in &shards {
        total.merge(&s.stats);
    }
    Ok(total)
}

/// Phase timings for one engine run, printed when CARDSHARP_GPU_TIMING is
/// set (diagnostics only; never affects results).
#[derive(Default)]
struct Timing {
    generate: std::time::Duration,
    gpu: std::time::Duration,
    replay: std::time::Duration,
    waves: u32,
}

impl Timing {
    fn report(&self, mode: &str) {
        if std::env::var_os("CARDSHARP_GPU_TIMING").is_some() {
            eprintln!(
                "cardsharp gpu timing [{mode}]: waves={} generate={:?} gpu={:?} replay={:?}",
                self.waves, self.generate, self.gpu, self.replay
            );
        }
    }
}

/// Generate and pack `want` consecutive orderings per planned shard, in
/// parallel across shards (each shard's generator advances independently).
fn generate_blocks(
    shards: &mut [ShardRun],
    plan: &[(usize, usize)],
    shoe_options: &ShoeOptions,
    stride_words: usize,
) -> Vec<Vec<u32>> {
    let mut work: Vec<(usize, u64, Option<OrderingGen>)> = plan
        .iter()
        .map(|&(si, want)| (want, shards[si].seed, shards[si].ordering_gen.take()))
        .collect();
    let blocks: Vec<Vec<u32>> = work
        .par_iter_mut()
        .map(|(want, seed, slot)| {
            let generator = slot.get_or_insert_with(|| {
                OrderingGen::new(shoe_options, Xoshiro256PlusPlus::seed_from_u64(*seed))
            });
            let mut block = Vec::with_capacity(*want * stride_words);
            for _ in 0..*want {
                block.extend(pack_ordering(generator.current(), stride_words));
                generator.advance();
            }
            block
        })
        .collect();
    for (&(si, _), (_, _, slot)) in plan.iter().zip(work) {
        shards[si].ordering_gen = slot;
    }
    blocks
}

/// Flat-bet mode: one GPU thread per shoe; shoes of one shard replay in
/// order, shards merge in order.
fn run_shoe_mode(
    gpu: &GpuCtx,
    cfg: &GpuConfig,
    shards: &mut [ShardRun],
    shoe_options: &ShoeOptions,
    replayer: &RoundReplayer,
) -> Result<(), String> {
    let n_players = cfg.params.n_players as usize;
    let stride_words = cfg.params.stride_words as usize;
    let mut est = RoundsPerShoe::new(cfg, n_players);
    let record_round_cap = WAVE_RECORD_WORD_CAP / n_players;
    let mut timing = Timing::default();

    loop {
        // ---- plan the wave: how many shoes per shard, under the caps ----
        let t0 = std::time::Instant::now();
        let mut plan: Vec<(usize, usize)> = Vec::new();
        let mut total_segments = 0usize;
        let mut card_words = 0usize;
        let mut rec_rounds = 0usize;
        for (si, s) in shards.iter().enumerate() {
            if s.finished {
                continue;
            }
            let remaining = s.target - s.rounds_done;
            let want = ((remaining / est.estimate()) as usize + 2)
                .min(PER_SHARD_SHOE_CAP)
                .min(WAVE_SEGMENT_CAP - total_segments)
                .min((WAVE_CARD_WORD_CAP - card_words) / stride_words)
                .min((record_round_cap - rec_rounds) / cfg.max_rps as usize);
            if want == 0 {
                break;
            }
            plan.push((si, want));
            total_segments += want;
            card_words += want * stride_words;
            rec_rounds += want * cfg.max_rps as usize;
        }
        if plan.is_empty() {
            timing.report("shoe");
            return Ok(());
        }

        // ---- generate orderings in parallel, then assemble the wave ----
        let blocks = generate_blocks(shards, &plan, shoe_options, stride_words);
        let mut cards: Vec<u32> = Vec::with_capacity(card_words);
        let mut segments: Vec<GpuSegment> = Vec::with_capacity(total_segments);
        let mut seg_shard: Vec<usize> = Vec::with_capacity(total_segments);
        let mut rec_cursor = 0u32;
        for (&(si, want), block) in plan.iter().zip(&blocks) {
            let mut base_word = cards.len();
            cards.extend_from_slice(block);
            for _ in 0..want {
                segments.push(GpuSegment {
                    cards_base: (base_word * 4) as u32,
                    n_orderings: 1,
                    round_budget: cfg.max_rps,
                    rec_base: rec_cursor,
                    carry_count: 0,
                    decks_num: cfg.params.init_decks_num,
                    decks_den: cfg.params.init_decks_den,
                    next_pos: cfg.params.burn,
                    ordering_idx: 0,
                    ..Default::default()
                });
                seg_shard.push(si);
                rec_cursor += cfg.max_rps;
                base_word += stride_words;
            }
        }
        timing.generate += t0.elapsed();

        let t1 = std::time::Instant::now();
        let mut params = cfg.params;
        params.mode_shard = 0;
        params.n_segments = segments.len() as u32;
        let (records, statuses) = run_wave(
            gpu,
            &params,
            &cards,
            &segments,
            &cfg.table_words,
            &cfg.deviations,
            rec_cursor,
        )?;
        timing.gpu += t1.elapsed();
        timing.waves += 1;
        let t2 = std::time::Instant::now();

        // ---- serial accounting: how many rounds each segment contributes
        let mut per_shard: Vec<Vec<(u32, u64)>> = vec![Vec::new(); shards.len()];
        for (k, st) in statuses.iter().enumerate() {
            let si = seg_shard[k];
            let s = &mut shards[si];
            if s.finished {
                continue;
            }
            let cut_reached = st.out_next >= cfg.params.reshuffle_point;
            if st.flags & (F_EXHAUSTED | F_GUARD) != 0 || !cut_reached {
                s.needs_cpu = true;
                s.finished = true;
                per_shard[si].clear();
                continue;
            }
            est.record(st.rounds_played as u64, 1);
            let take = (st.rounds_played as u64).min(s.target - s.rounds_done);
            if take > 0 {
                per_shard[si].push((segments[k].rec_base, take));
            }
            s.rounds_done += take;
            if s.rounds_done == s.target {
                s.finished = true;
            }
        }

        // ---- parallel replay, one task per shard. Rounds feed each
        // shard's single SimStats sequentially in round order (a shard's
        // wave segments are contiguous and ordered), preserving the CPU
        // engine's per-round Welford order exactly.
        replay_wave(shards, &per_shard, &records, n_players, replayer);
        timing.replay += t2.elapsed();
    }
}

/// Replay each shard's assigned record ranges, in order, into that
/// shard's accumulator; shards run in parallel, rounds within a shard
/// sequentially.
fn replay_wave(
    shards: &mut [ShardRun],
    per_shard: &[Vec<(u32, u64)>],
    records: &[u32],
    n_players: usize,
    replayer: &RoundReplayer,
) {
    shards
        .par_iter_mut()
        .zip(per_shard.par_iter())
        .for_each(|(s, list)| {
            if s.needs_cpu {
                return;
            }
            for (rec_base, take) in list {
                for r in 0..*take {
                    let base = (*rec_base as usize + r as usize) * n_players;
                    replayer.replay_round(&mut s.stats, &records[base..base + n_players]);
                }
            }
        });
}

/// Counting mode: one GPU thread per shard slice, with the count/decks
/// carry threaded through waves.
fn run_shard_mode(
    gpu: &GpuCtx,
    cfg: &GpuConfig,
    shards: &mut [ShardRun],
    shoe_options: &ShoeOptions,
    replayer: &RoundReplayer,
) -> Result<(), String> {
    let n_players = cfg.params.n_players as usize;
    let stride_words = cfg.params.stride_words as usize;
    let mut est = RoundsPerShoe::new(cfg, n_players);
    let record_round_cap = WAVE_RECORD_WORD_CAP / n_players;
    let mut timing = Timing::default();

    loop {
        // ---- plan the wave: slice budget and ordering need per shard ----
        let t0 = std::time::Instant::now();
        let mut plan: Vec<(usize, usize)> = Vec::new(); // (shard, missing orderings)
        let mut budgets: Vec<(usize, u32)> = Vec::new();
        let mut total_segments = 0usize;
        let mut card_words = 0usize;
        let mut rec_rounds = 0usize;
        for (si, s) in shards.iter().enumerate() {
            if s.finished {
                continue;
            }
            let budget = (s.target - s.rounds_done).min(SHARD_SLICE_ROUNDS) as u32;
            let need = ((budget as u64 / est.estimate()) as usize + 2).max(2);
            if total_segments >= WAVE_SEGMENT_CAP
                || card_words + need * stride_words > WAVE_CARD_WORD_CAP
                || rec_rounds + budget as usize > record_round_cap
            {
                break;
            }
            plan.push((si, need.saturating_sub(s.pending.len())));
            budgets.push((si, budget));
            total_segments += 1;
            card_words += need.max(s.pending.len()) * stride_words;
            rec_rounds += budget as usize;
        }
        if budgets.is_empty() {
            timing.report("shard");
            return Ok(());
        }

        // ---- top up pending orderings in parallel, then assemble ----
        let blocks = generate_blocks(shards, &plan, shoe_options, stride_words);
        for (&(si, _), block) in plan.iter().zip(blocks) {
            for chunk in block.chunks_exact(stride_words) {
                shards[si].pending.push(chunk.to_vec());
            }
        }
        let mut cards: Vec<u32> = Vec::with_capacity(card_words);
        let mut segments: Vec<GpuSegment> = Vec::with_capacity(budgets.len());
        let mut seg_shard: Vec<usize> = Vec::with_capacity(budgets.len());
        let mut rec_cursor = 0u32;
        for &(si, budget) in &budgets {
            let s = &shards[si];
            let base_word = cards.len();
            for ordering in &s.pending {
                cards.extend_from_slice(ordering);
            }
            segments.push(GpuSegment {
                cards_base: (base_word * 4) as u32,
                n_orderings: s.pending.len() as u32,
                round_budget: budget,
                rec_base: rec_cursor,
                carry_count: s.carry_count,
                decks_num: s.decks_num,
                decks_den: s.decks_den,
                next_pos: s.next_pos,
                ordering_idx: 0,
                ..Default::default()
            });
            seg_shard.push(si);
            rec_cursor += budget;
        }
        timing.generate += t0.elapsed();

        let t1 = std::time::Instant::now();
        let mut params = cfg.params;
        params.mode_shard = 1;
        // The kernel's record-overrun guard: in shard mode a segment's
        // record region is its slice budget, not the per-shoe bound.
        params.max_rounds_per_seg = SHARD_SLICE_ROUNDS as u32;
        params.n_segments = segments.len() as u32;
        let (records, statuses) = run_wave(
            gpu,
            &params,
            &cards,
            &segments,
            &cfg.table_words,
            &cfg.deviations,
            rec_cursor,
        )?;
        timing.gpu += t1.elapsed();
        timing.waves += 1;
        let t2 = std::time::Instant::now();

        let mut per_shard: Vec<Vec<(u32, u64)>> = vec![Vec::new(); shards.len()];
        for (k, st) in statuses.iter().enumerate() {
            let si = seg_shard[k];
            let s = &mut shards[si];
            let played = st.rounds_played as u64;
            // Provisioning always supplies >= 2 orderings, so a healthy
            // segment makes progress; anything else is an anomaly and the
            // shard falls back to the CPU runner.
            if st.flags & (F_EXHAUSTED | F_GUARD) != 0 || played == 0 {
                s.needs_cpu = true;
                s.finished = true;
                continue;
            }
            let _ = F_ORDER_OUT; // legitimate: the next wave continues
            est.record(played, st.out_ordering as u64 + 1);
            per_shard[si].push((segments[k].rec_base, played));
            s.rounds_done += played;
            s.carry_count = st.out_count;
            s.decks_num = st.out_decks_num;
            s.decks_den = st.out_decks_den;
            s.next_pos = st.out_next;
            s.pending.drain(0..st.out_ordering as usize);
            if s.rounds_done >= s.target {
                s.finished = true;
                s.pending.clear();
            }
        }

        replay_wave(shards, &per_shard, &records, n_players, replayer);
        timing.replay += t2.elapsed();
    }
}

// ---------------------------------------------------------------------
// Python surface
//
// The kernel, the host replay and the exactness gates above are native;
// only these two entry points need PyO3, so the whole section sits behind
// the `python` feature and a `gpu`-only Rust build compiles clean.
// ---------------------------------------------------------------------

/// Probe GPU availability: (available, adapter description or reason).
#[cfg(feature = "python")]
#[pyfunction]
pub fn gpu_probe() -> (bool, String) {
    match ctx() {
        Ok(c) => (
            true,
            format!("{} ({:?})", c.adapter_info.name, c.adapter_info.backend),
        ),
        Err(e) => (false, e.clone()),
    }
}

/// GPU twin of `simulate_batch`: same report dict, bit-identical for the
/// same seed and configuration. Configurations the GPU engine cannot
/// reproduce exactly raise ValueError with the reason (the Python facade
/// uses that to fall back or to error loudly under --engine gpu).
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (rules, table, n_rounds, seed, n_players = 1, initial_bankroll = 1000.0, always_insure = false, threads = 0, counting = None, shuffle_type = "perfect", shuffle_count = None))]
#[allow(clippy::too_many_arguments)]
pub fn simulate_batch_gpu<'py>(
    py: Python<'py>,
    rules: PyRef<'py, Rules>,
    table: &[u8],
    n_rounds: u64,
    seed: u64,
    n_players: usize,
    initial_bankroll: f64,
    always_insure: bool,
    threads: usize,
    counting: Option<PyRef<'py, CountingConfig>>,
    shuffle_type: &str,
    shuffle_count: Option<u32>,
) -> PyResult<Bound<'py, PyDict>> {
    if n_players < 1 {
        return Err(PyValueError::new_err("n_players must be at least 1"));
    }
    let table_parsed =
        StrategyTable::from_bytes(table).map_err(|e| PyValueError::new_err(e.to_string()))?;
    let rules: Rules = rules.clone();
    let counting: Option<CountingConfig> = counting.map(|c| c.clone());
    let shoe_options = ShoeOptions {
        num_decks: rules.num_decks,
        penetration: rules.penetration,
        burn_cards: rules.burn_cards,
        use_csm: rules.use_csm,
        shuffle_style: ShuffleStyle::from_name(shuffle_type).map_err(PyValueError::new_err)?,
        shuffle_count,
    };
    let table_bytes = table.to_vec();

    let run = || {
        run_gpu_batch(
            &rules,
            &table_bytes,
            &table_parsed,
            counting.as_ref(),
            &shoe_options,
            n_rounds,
            seed,
            n_players,
            initial_bankroll,
            always_insure,
        )
    };
    let stats = py
        .detach(|| {
            if threads == 0 {
                run()
            } else {
                rayon::ThreadPoolBuilder::new()
                    .num_threads(threads)
                    .build()
                    .expect("failed to build thread pool")
                    .install(run)
            }
        })
        .map_err(PyValueError::new_err)?;
    stats.to_dict(py)
}
