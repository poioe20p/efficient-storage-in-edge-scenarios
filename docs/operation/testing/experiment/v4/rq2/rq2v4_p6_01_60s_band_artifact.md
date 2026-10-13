# RQ2 v4 — P6.1 platform finding: the 60 s VIP re-arm band

> **Status:** registered 2026-10-13 (Edge Experiment Analyzer). Trigger identified from run
> artifacts + controller code; effective knob values confirmed against the run's
> `controller_env_snapshot.env` (sudo -n read). Affects **all** v4/rq2 regimes (cb complete;
> mx in flight; db pending).
> **Scope:** analysis-time finding. **No run is invalidated**; no MC gate is affected. The
> finding constrains the interpretation of the window-share relief gates (G1, and the hash
> legs of G3) — it is an arm-independent, anti-relief bias.

## 1. What it is

Once every ~60 s — **phase-locked to run start**, not wall clock — an ~8–10 s band in which
~25–35 % of client requests gain **+0.3–1.4 s** latency; window-p95 crosses 1 s in
essentially every lane of every run, both aligned arms. The remaining ~50 s of each minute
is clean (steady-state window-p95 0.5–0.9 s). This band fails 6–7 of every 42–51 post-settle
windows even in fully relieved lanes — alone it caps any lane's relief share at ≈84–87 %.

## 2. Mechanism (identified)

1. Client→VIP DNAT/SNAT flows are installed with **`hard_timeout=60 s`**
   (`VIP_HARD_TIMEOUT=60` in the canonical `current_state_integrated.env`; confirmed in the
   run snapshot; logged as `dnat/snat installed … (idle=30s hard=60s)`).
2. At phase start all clients' flows install in one burst (first install lines at episode
   t0 in `both_cb_48`: 14:58:09.795 lan1 / 14:58:10.683 lan2).
3. 60 s later OVS silently hard-expires them all (flow expiry itself is not logged); the
   VIP punt rule (priority 100 < DNAT 200) resumes and punts each client's next packet to
   the os_ken controller (`install_vip_punt_rules` docstring: "When the DNAT rule expires
   (idle_timeout or hard_timeout) the punt rule resumes and triggers fresh backend
   selection").
4. The controller serially re-selects and re-installs the batch: ~40–55
   `dnat/snat installed` per cycle per lane, concentrated in seconds **:10–:18** of each
   minute, with ~400 `select_server` log lines in the same band vs **0** in quiet windows
   (15:02 measurement: band[:11–19]=400, quiet[:21–29]=0). Draining the batch takes ~8–10 s
   on the Python controller; ~25–35 % of requests in that window wait for the
   punt→select→install round trip.
5. Each re-install rebases a fresh 60 s timer; the next expiry batch lands in the same
   phase, slightly spread — the cycle is self-sustaining.

**Arm-independence and isolation evidence**

| Check | Result |
|---|---|
| `none_cb_48` install cycle | present (400 installs; same per-minute cadence) |
| Non-episode phases (`demand_drop`, rate 1.0, frac 0.1) | same per-minute max ≈1.4–2 s — independent of load/capacity |
| Edge `T_proc` in the bad window | flat ≈85–100 ms — not edge processing |
| Host sampler (1 Hz) around band seconds | no correlation — not host interference |
| First `[scale-up] compute fired` | 14:58:37.736 (lan1) / 14:58:40.993 (lan2) — the band precedes any scaling |

## 3. Impact on the pre-registered gates (cb, as computed)

- Caps any lane's post-settle relief share at ≈84–87 %; the G1 80 % floor then tolerates
  only 2–4 extra misses per run.
- `both`@cb: **5/7** — misses s43-lan1 78.6 %, s46-lan2 71.1 %.
- `comp`@cb: **4/7** — misses s42/44/46, all lan2, 76.2–78.6 %.
- Every miss is 1–4 windows beyond the band. **Artifact-excluded sensitivity: 93–98 %
  everywhere → all 14 replicates pass.** (Sensitivity is diagnostic — not a gate
  redefinition.)
- Direction and comparator untouched: `comp`/`both` p50 0.20–0.21 s, ~100 % completion,
  0–2 timeouts vs `none`/`stor` p50 2.36–2.39 s, 92–99.6 % completion, up to 150 timeouts.

## 4. Open engineering question (bears on any fix)

Whether client flows are re-pinned to newly added nodes **only** on expiry (the
punt-on-expiry path suggests so). If the periodic expiry is what redistributes load to new
capacity, the 60 s hard timer is partly load-bearing for the relief mechanism itself and a
blind increase would be unsafe. Candidate future fix: proactive re-pin / flow-mod push on
topology change — post-campaign work, not attempted now.

## 5. Handling (registered policy)

- **No mid-campaign config change.** All campaign runs share the canonical override;
  changing it would break comparability across cells of the campaign.
- Every affected regime's write-up records: measured gate values **as-is** + this artifact
  + the artifact-excluded sensitivity.
- **Author sign-off item** (to decide at P6 write-up):
  (a) report as-is with sensitivity *(analyzer recommendation)*;
  (b) author-sanctioned analysis note pre-declaring band windows non-evaluable for the
  share metric;
  (c) platform fix + whole-cell reruns (cost: cb aligned cells ≈ 14 runs ≈ 10 h; only
  meaningful once §4 is resolved).
- mx (in flight) and db inherit the same handling; nothing is rerun mid-campaign.

## 6. Reproduction pointers (on `cloud-vm-rq2`)

- G1 JSONs (14 aligned cb runs) + window math: `~/rq2v4_battery/g1lock.py`, `g1_rq2v4_*.json`
- Install cadence: `grep "dnat/snat installed" <run>/controller_lan{1,2}.log` (by-second
  histogram shows the :10–:18 bursts)
- Select storm: `grep -c select_server` in :11–:19 vs :21–:29 (400 vs 0 at 15:02)
- Effective knobs: `sudo -n grep ^VIP_ <run>/controller_env_snapshot.env` →
  `VIP_HARD_TIMEOUT=60`, `VIP_IDLE_TIMEOUT=30`, `VIP_DATA_PER_CONNECTION_FLOWS=1`
- Per-run screener `~/rq2v4_battery/p5check.py`; checkpoint records
  `~/rq2v4_battery/evidence/`

## 7. Related observation: lane-2 sequencing (measured, partially resolved)

The controller fires lan1 decisions **~3.3 s before lan2 every cycle**, with a common ~70 s
decision cadence: both_cb_48 fires lan1 14:58:37.736 / 14:59:47.811 / 15:00:57.884 /
15:02:07.964 vs lan2 +3.26 s ≈ each; both_cb_42 the same pattern (+4.4 s on the first
cycle). First installs likewise lan1-first (14:58:09.795 vs 14:58:10.683).

Measured source of the offset: **the two lanes run independent single-lane controllers
(main_n1/main_n2) with their own fixed decision clocks**, started ~1–3 s apart; every
lan1 action therefore precedes the corresponding lan2 action. The lanes' telemetry window
clocks are independent too (aggregator `window_end` phases differ by ~33 s between lanes —
reporting cadence only, not decision-relevant). Clients also start ~1 s apart (per-lane
first episode request 14:58:09.788 vs 14:58:10.678).

Consequences: lan2's capacity adds land ~3.3 s later each cycle by construction. Its
**remaining marginality** (post-settle median p95 ~0.75–0.9 s vs lan1 0.5–0.7 s; relief
onset ~100–114 s vs lan1 48–108 s) is *not* explained by the offset alone and stays open —
next probes: per-lane effective node counts actually serving during the steady window and
per-node load balance per lane.
