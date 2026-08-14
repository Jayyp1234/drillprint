# v1.3 Errata — discovered during M1 implementation (2026-08-10)

Measured facts from running the actual model/generators; fold into v1.3.1.
Each is already implemented (and commented) in the code.

## E1 — A4 period gate: floor 0.9, RPM-aware ceiling

A4 specified period ∈ [1.0, 2.0] × T_model. Measured across the full
135-corner sweep:

- **Floor:** low-dwell corners run at 0.92–0.97 × T_model — the slip-phase
  oscillation is slightly *faster* than the free natural period. Floor → **0.9**.
- **Ceiling:** at 60 RPM the stick dwell dominates: dwell ≈ 1.3–1.45 ×
  (T_s − T_c)/(k·Ω) (verified against 4 corners), pushing genuine limit cycles
  to 2.01–2.58 × T_model. Per A4's own rationale ("dwell grows as commanded
  RPM falls") the ceiling is now RPM-aware: **2.0 at ≥ 90 RPM, 2.7 at 60 RPM**.

Result: 125/135 corners pass, 10 relabel NORMAL (steady sliding), 0 failures.
Passing ratios span 1.00–2.58.

## E2 — A11 PI gains: 500/50 → 20 000/2 000

With K_p = 500 N·m·s/rad the surface RPM swings ~75 % during stick-slip,
violating §2's own requirement ("near-constant RPM, oscillating torque").
K_p = 20 000, K_i = 2 000 gives a 20 rad/s closed-loop top pole (a realistic
stiff top drive); surface RPM swing drops below 15 %.

## E3 — A11 pump comb: SPM 110's "5.5 Hz fundamental" is unemittable

5.5 Hz exceeds both Nyquist (5 Hz) and the A7 cap (4.5 Hz) on the 10 Hz
TORQUE_SURF/WOB channels. Implemented physically instead: a stroke-rate comb
at n × SPM/60 Hz capped at 4.5 Hz with the 3×-piston harmonic emphasized —
SPM 60 → lines at 1, 2, 3, 4 Hz (strongest 3.0); SPM 110 → 1.83, 3.67 Hz.

## E4 — Cross-realization matching of steady-state signatures needs a second statistic (discovered in M2)

**The finding.** The offset-histogram ("diagonal alignment") statistic is
structurally blind to the system's own primary use case. §14/A19 mandate that
queries are *different realizations* than library episodes (disjoint seeds and
parameter draws) — which is also what live rig data always is. But a
steady-state dysfunction signature (a whirl or bounce comb, developed
stick-slip at sub-hop period) produces hash types that recur at EVERY library
frame; matches therefore spread uniformly over all offsets, the histogram is
flat, and λ (estimated from that same histogram) equals the max bin — the
offset statistic can never reach significance, at any severity. Measured:
cross-seed whirl matching scored 2 with the offset statistic under conditions
where the signatures were spectrally identical. Wang's spike works for music
because a query is a *recording of the same instance*; DrillPrint's queries
never are.

**The fix (implemented).** Two statistics, two jobs:
- **Offset statistic** (unchanged): evolving/transient content and
  same-instance replay; still the episode-instance identifier (δ*) and the
  §11 period-comb readout.
- **Geometry statistic** (new): m = distinct matched hash TYPES vs the
  Poisson collision null λ_geom = |Q_types| · |L_types| / S_eff, with S_eff
  the in-band hash space (hashing.effective_hash_space — ~62k for the whirl
  ORDER band, not 2^24), corrected across episodes, alert at m ≥ d_min = 12
  AND p_geom_corr < 1e-4. This is the correct test of the §9 claim: spectral
  GEOMETRY surviving RPM change. Verified: cross-seed whirl matches at m ≈
  40+ vs λ_geom ≈ 1; random queries never fire; ramp-vs-time-domain still
  fails (the negative arm holds).
- Displayed confidence = 1 − min(p_corr, p_geom_corr).

**Supporting fixes (all implemented, all required for the geometry statistic
to have anything to match):**
- **E4a — Band-restricted peak picking:** the class's hashing band restricts
  peak CANDIDATES before the density cap (out-of-band content must not crowd
  the 5-peak budget), while the local-max test and median threshold still run
  full-spectrum (a narrow band dense with lines would otherwise put the
  median on the lines themselves).
- **E4b — Per-profile peak neighborhood:** §7's (Δm=3, Δk=3) suits transient
  content; for stationary combs the ±3-frame local-max test thins each line
  to ~1 peak per 7 frames and the ±3-bin window lets a strong line's skirt
  suppress its own ±1-order sidebands (measured: 42 peaks in 117 frames,
  sidebands absent). ORDER profile now picks with (0, 1) —
  frequency-axis-only. Profile gains a peak_neighborhood field.
- **E4c — Whirl comb enrichment (physics, not tuning):** the contact-force
  direction rotates at the whirl rate, so the body-frame (N_b+1) line carries
  order-1 modulation → sidebands at (N_b+1)±1; the lobe-contact nonlinearity
  adds 2(N_b+1) with its own ±1 sidebands. Stable class comb:
  {m−1, m, m+1, 2m−1, 2m, 2m+1}.

**Product implication (v1.3.1 decision needed).** The Alignment View's
single-spike hero moment appears for transient/evolving content and
same-instance replay — NOT for steady-state cross-realization detections,
where the histogram is flat (or a period-comb for quasi-periodic content,
which §11 already frames as the measured-period readout). The drill-down for
steady-state detections should lead with the matched-type overlap (which
peaks of the class comb were found — arguably the more explainable visual)
plus the δ-comb where present. §19/§34 demo copy needs a wording pass.

## E5 — The A12 schema and query path must materialize E4's split, or the ≤10 ms gate fails 65× (discovered in M3)

**The finding.** With the A12 schema as amended, one whirl evaluation against
the full 176-episode / 456k-hash library took **654 ms** (gate: ≤ 10 ms).
Cause: E4's stationarity, at the storage layer. A stationary comb stores each
hash type at ~every anchor of ~every same-class episode, so a query hash pulls
~1,200 posting rows and a window pulls ~71k — almost all feeding an offset
histogram that E4 already proved is flat for exactly this content.

**The fix (implemented, measured):** the store materializes the two-statistic
split:
1. **`fingerprint_types` table** — DISTINCT (hash, episode, channel, profile,
   domain) with an `n_anchors` count. The geometry screen is one SQL
   aggregate over this table (0.9 ms).
2. **Two-stage query** (`store/query.py` ClassMatcher): geometry screen →
   top-K candidates → anchor postings fetched ONLY for *evolving* types
   (n_anchors ≤ 8). Stationary types' anchors never leave the database —
   their offset contribution is uniform by construction, so omitting them is
   correct, not approximate. The matcher takes the screen's counts via a
   `geometry_counts` override, and stationary-only matches still surface
   (empty offset stats, live geometry stats).
3. **`episode_profiles` table** (n_frames / n_hashes / n_distinct per episode
   × profile) — feeds δ-bin sizing and the E4 collision null; plus
   `class_bindings` gains profile/band columns; plus an (episode_id, hash)
   composite index with the join order pinned via CROSS JOIN (SQLite's
   planner otherwise drives from the anchor table and scans whole episodes —
   measured: 59 ms to return 7 rows).

**Measured after fix, full library:** whirl cross-realization 2.4 ms ·
stick-slip 2.1 ms · bounce 8.2 ms · pump-comb negative probe 1.8 ms — all
under the 10 ms gate, detections correct, zero pump-comb false alerts.

**E6 (2026-08-11 benchmark forensics):** two harness classes of defect plus one
engine inconsistency, found when the first full A19 run returned implausible
numbers (baseline P=R=1.0 at 0 dB; stick-slip 0% everywhere):

- *Harness (bench/run.py, H1–H6):* the baseline was scored only inside a 20 s
  post-onset slice with `fp=0` hardcoded (unfalsifiable — now a sliding-window
  scan over the whole run, scored through the same `score_run` contract as
  DrillPrint); §12.5 treatments were applied to the dysfunction segment only
  (the baseline was detecting the noise burst — now uniform across the run,
  noise floor referenced to event-span power); gain/SNR treatments were
  corrupting RPM_SURF, rescaling the order axis itself (RPM_SURF is the
  drive-side order-tracking reference and is never treated; A16 sensor noise
  lives in the generators); P/R were macro-averaged across runs and latencies
  dropped (now pooled micro-averages + median latency + FA per normal-hour);
  one event per run gave ~3 events/class/SNR (now all three classes per run,
  seed-shuffled, normal separators ≥ 2×W_LOW).
- *Engine:* LOW/LOW_DEEP peak neighborhood was (3, 3); the stick-slip comb is
  stationary in time exactly like ORDER lines, so the ±3-frame local-max test
  made each line compete with its own noise-jittered self and thinned it ~4×
  under in-band noise. Now (1, 1) — the E4b rationale applied consistently.
  Libraries built before this are stale; ≥ v4 required.
- *Measured after fixes (offline ladder, composite context):* stick-slip
  Tier-2 alerts at SNR 20/10/3/0 dB (p_geom 1e-49 → 4e-19), correct corner at
  ≥10 dB, correct class with neighbor-corner attribution at ≤3 dB. Smoke
  composite: whirl TP at 6.6 s, bounce TP at 5.3 s (inside A2 targets),
  baseline honest (SSSI ≈126 FA/normal-hour at SNR 10).

**E6a/E6c (2026-08-11, second forensics round — the first honest full run):**
the fixed harness exposed two engine defects producing FP+FN pairs on
stick-slip in every composite run. **E6a:** the K=2 debounce's confirm latch
was never re-armed after a streak reset — a class could emit at most ONE
tier-2 detection per engine lifetime, so any early spurious confirm
permanently silenced the genuine event. **E6c:** structured in-band noise
overlapping the comb type-region could pass the geometry statistic with a
FLAT offset histogram (measured: d=24 against a uniform-null λ of 0.82 —
p ≈ 1e-23 — during a *normal* segment). Time-domain libraries are
deterministic, so genuine matches always carry diagonal alignment; geometry
alerts on time-domain pipelines now require offset corroboration
(p_off < 0.1; measured margins: spurious ≈ 1.0, genuine ≤ 0.09 at 0 dB).
Validated: spurious blocked and genuine stick-slip alerting at SNR
20/10/3/0 dB, 121 tests green.

**E7 status update (full run 2, harness v2 + E6a/E6c, library v4):** recall is
now real — whirl/bounce R=1.0 at every SNR (median latency 5.3–6.9 s), and
stick-slip detects at R=0.5/58 s at 20 dB (inside the A2 target). But E6a's
re-arm unmasked the FP rate the old latch was accidentally suppressing:
stick-slip P ≈ 0.03–0.05 (9–35 FA/normal-hour), and at 0 dB even ORDER
classes leak (whirl 70 FA/nh). The E6c gate blocks the measured spurious
*window* but at 720+ windows/run a p_off < 0.1 gate structurally leaks.
Conclusion: **E7 is no longer optional — landmark-prominence selectivity is
required for gate 2 (zero false alerts) to be reachable.** Operational
verdict meanwhile: at SNR ≥ 3 dB, whirl P ≥ 0.91 / bounce P ≥ 0.59 with
R = 1.0; the order-domain core claim stands at realistic noise levels.

**E7 — RESOLVED (2026-08-12): landmark prominence at the source.** §7 gains a
local-prominence gate: a candidate peak must stand ≥ 10 dB above the running
**25th percentile** of its ±8-bin spectral neighborhood (25th percentile, not
median — on a dense comb the local median lands on the lines themselves and
rejects the comb wholesale; the between-line floor owns the low quantiles at
any line density). This whitens pink-noise tilt and keeps noise maxima
(~4–6 dB proud) out of constellations entirely: library thins 547k → 430k
hashes (v6), and the E6c corroboration gate — whose premise fails on clean
stationary combs (measured genuine match: p_geom 1e-64 with p_off 0.36) — is
removed from the query path, superseded at the source. Validated: 12/12
genuine stick-slip alerts across 3 seeds × SNR {20,10,3,0}, 0/48 spurious
windows, order-domain cross-seed ramp matches intact, 121 tests green.
Library ≥ v6 required.

**E8 (2026-08-13): temporal persistence for the ORDER domain.** The residual
low-SNR order-domain false alerts traced to noise maxima that genuinely clear
the prominence gate in resampled spectra — but flicker: measured, spurious
landmarks smear over 32 bins with ≤6/56-frame recurrence, while genuine whirl
lines sit at 8 bins present in 57/57 frames. §7 gains a per-profile
persistence gate: in ORDER, a bin (±1) must recur in ≥ 25 % of the window's
frames to carry landmarks. LOW/LOW_DEEP keep persistence OFF — their in-band
noise mode is already fully rejected by E7 prominence (0/48 measured), and
low-SNR comb lines recur in only ~20-30 % of frames, so persistence there
costs detection without buying rejection. Each domain gets the gate its
noise mode requires. Library ≥ v8. Validated: full probe matrix (2 seeds ×
4 SNRs × 3 classes) — 0 spurious, all genuine firing including stick-slip
at 0 dB; 121 tests green.

**E8b (2026-08-13, from the v8 full run):** the final leak was the OFFSET
path firing without evidence: on stationary library content a single
repeated query type piles into one δ-bin and fakes diagonal alignment
(measured spurious fire: d=2, coverage 0.01 — while every genuine match
carries d ≥ 16). The previous run had hidden this class of leak behind the
noise-dense normal sponges; E8's persistence honestly thinned those, and the
leak surfaced. Fix: ANY Tier-2 alert — offset path included — now requires
the distinct-evidence floor d ≥ 12. Validated under true engine conditions:
0/110 spurious 8-second sliding windows over treated normal segments, all
genuine detections firing on 8-second windows at SNR {20,10,3,0}, 121 tests
green.

**E7b (2026-08-13, from the v6 full run):** E7's thinning inverted the §5
absorption ranking in the ORDER domain — per-episode p-values normalize λ by
each episode's type count, so THIN post-E7 dysfunction fingerprints ranked
above DENSE normal sponges on noise queries (measured: spurious window,
normals d=282 sweeping the raw-evidence top-5, yet corners outranked on p;
whirl FA 170/normal-hour). Fix: candidates are now ranked by RAW matched
evidence (distinct types) — Shazam-faithful; p-values remain the winner's
significance gates, never the ranking. Measured after: genuine short-window
queries put the correct corners (right blade count) on top in production;
spurious windows are swept by normals and absorbed. Also exposed: the test
fixture's whirl mini-sweep covered only N_b=4 (noise types had masked
cross-blade-count matching) — fixture now spans blade counts, as §31's BUILD
stage requires of real libraries. 121 tests green.

**E7 (original diagnosis, kept for the record):** the geometry statistic's uniform
collision null underestimates structured-noise collisions ~30× when query
and library types share a spectral region; an empirical normals-median null
was tried and reverted (it flattens p_geom and destabilizes §5 absorption
ranking — noise-dense NORMAL fingerprints act as universal sponges, and the
offset statistic itself goes degenerate between unrelated noise-dense
stationary signals in mini-library conditions). Root cause: landmark
selectivity — noise maxima admitted as peaks make generic, dense type sets.
Candidate fix: prominence-based peak admission at the source (library +
query), then revisit the empirical null. E6c carries the practical defense
meanwhile; production composites show 0 order-domain FPs in 40 runs.

**E5a (user-hit in the field):** A12 declared `slug TEXT UNIQUE` — globally.
Building a second library version into the same DB re-generates the same
sweep corners with the same canonical slugs and crashes on the constraint.
Episode identity is **(library_version, slug)**; `id = '<version>/<slug>'`;
`UNIQUE (library_version, slug)`. A `PRAGMA user_version` guard now rejects
pre-fix DB files with a rebuild instruction instead of a traceback.

## Implementation notes that belong in the spec (v1.3.1 candidates)

- **Sensor-chain anti-alias:** impact-ring onsets are genuinely broadband;
  generators band-limit final ACC channels below 0.45·f_s (zero-phase FFT
  brick wall) — the synthetic equivalent of a real ADC front-end. Without it
  the A7 generator gate fails at 6 % out-of-band power.
- **Stability screen needs a decay discriminator:** lightly damped corners
  ring down for >90 s; "still decaying" (last-third swing < 0.6 × first-third)
  must count as no-limit-cycle, else transients masquerade as weak stick-slip.
- **Peak-to-peak swing must be percentile-based** (p0.5/p99.5): zero-phase FIR
  decimation edge spikes otherwise inflate swing on steady corners (plus a 2 s
  trailing trim guard on emitted windows).
- **RPM_SURF sensor noise must itself be band-limited** (≤ 0.44·f_s) — white
  noise to Nyquist violates the A7 gate on the measured channel.
