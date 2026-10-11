# RQ2 v4 — P2.5: Relief diagnosis (why comp cannot relieve)

> **Status:** 2026-10-11 · read-only autopsy #3 complete (nothing modified).
> **Scope:** explains the P2.3 relief failure
> ([`rq2v4_p2_02_knee_calibration.md`](rq2v4_p2_02_knee_calibration.md)) and
> proposes the P2.6 repair for author approval.
> **Evidence:** run `20261011_211706_rq2v4_p2_comp_h023` (+ cross-check
> `20261011_164429_rq2v4_p1_comp_cb25`); controller logs, env snapshots,
> per-client CSV histograms, per-node stats.

## 1. The mechanism (code-anchored)

Three designed behaviours compose into a **60-second one-hot funnel**:

1. **Per-client DNAT binding (enabler).** `VIP_SERVER_PER_CONNECTION_FLOWS`
   is unset (defaults 0) → DNAT/SNAT match only `eth_src/ipv4_src`, no
   `tcp_src` (`flows.py:386,434`; `ingress.py:168–176`). Every connection of
   a client reuses its flow — **no per-request re-selection**.
2. **Synchronized hard timeout (the epoch clock).** Flows install with
   `hard_timeout=VIP_HARD_TIMEOUT=60 s` (`flows.py:403–404,445–446`; env 60).
   All 48 clients started together → their flows **hard-expire in ~2 s bursts
   every exactly 60.0 s** (measured: bursts 21:20:41, 21:21:41, 21:22:44, …
   period 60.0 s, all selections per burst → one MAC).
3. **Deterministic single winner per burst.** At each burst every client
   selects within ~2 s and the pool state is identical: `tied=1`,
   byte-identical WSM costs → **all clients get the same backend**. When a
   spawn's 45 s warm lease covers the burst, the claim monopolizes it
   (`selection.py:139–144`, `_claim_warm_backend:72–113` — a claimed lease is
   **not consumed**; 257/633 lan1 selections = 41 % of epochs warm-monopolized).

Net: **one unit per lane serves ALL lane traffic for each ~60 s epoch**
(168 requests/30 s to a single backend), rotating to the "coldest idle unit"
each epoch. Added units time-share the hot seat; concurrency census never
exceeded 2 units ≥30 % CPU (mostly 1). Cross-lane picks possible (pure
argmin; one epoch selected the peer-LAN unit).

## 2. Why the added capacity did nothing (math)

Press 5.6 rps/lane; single-unit ceiling ≈ 5–8 rps/lane (P2.2) ⇒ one unit
sits AT the knee (p50 ≈ 1.8 s steady state, 100 % eventually served).
Spread over 3 units ⇒ 1.9 rps/unit ≈ 39 % of the onset rate → nominal
latency; over 6 ⇒ 0.93 rps/unit. **Observed concurrency = 1 unit ⇒ added
capacity = 0.** The elastic action is honest; the *admission path* destroys
concurrency.

Provenance: v3-era compute "relief" was measured at loads below one-unit
capacity — concurrency-based relief has never been demonstrated on this
platform. This diagnosis also explains the P1.4 battery note ("assignments
rotate per window").

## 3. Candidate fixes (ranked)

1. **ε-band tie-spread in `select_server`** — treat costs within ε as tied
   and spread the epoch burst across the band (round-robin/stateless hash).
   Directly restores concurrency. Knob `BACKEND_SELECTION_SPREAD_EPS`
   (≈0.03; ≪ hop term 0.28, < peer gap 0.14).
2. **Warm-lease band inclusion** — in the warm branch, the claimed backend
   joins the ε-band instead of monopolizing it. Keeps warm-up purpose (new
   node is always eligible) while ending the 45 s monopoly (41 % of epochs).
3. *(Config-only, insufficient alone)* `VIP_SERVER_PER_CONNECTION_FLOWS=1` —
   shrinks epochs to telemetry-window time-sharing but does not create
   concurrency; imports flow churn and flips the documented per-client
   design. **Not recommended as the fix.**
4. *(Enabler)* jitter the hard timeout to de-synchronize epochs — cheap, but
   no concurrency gain without 1–2.

## 4. P2.6 — repair (APPROVED + IMPLEMENTED 2026-10-11)

**Edits (controller only; deployed by checkout sync — no image rebuild):**
implemented as designed — knob `_BACKEND_SELECTION_SPREAD_EPS` (default
0.03), ε-band + stateless client-hash spread in `select_server`, warm claim
joins the band; selftest
`source/scripts/testing/rq2v4_p2_06_selection_spread_selftest.py` green;
P2.7 re-seat running.

| # | File | Change |
| --- | --- | --- |
| 1 | `source/sdn_controller/scaling_config.py` | `_BACKEND_SELECTION_SPREAD_EPS` (env `BACKEND_SELECTION_SPREAD_EPS`, default **0.03**; 0 = legacy behaviour) |
| 2 | `source/sdn_controller/_vip_routing/selection.py` | `select_server`: after the argmin, collect candidates with `cost ≤ min + ε`, spread via a stateless deterministic hash of the client identity (band sorted by (cost, mac)); warm branch: claimed backend **joins** the band instead of monopolising it |
| 3 | `source/scripts/testing/rq2v4_p2_06_selection_spread_selftest.py` | new: band membership, spread uniformity across clients, legacy behaviour at ε=0, warm inclusion, no peer-band drift |
| 4 | docs | `docs/operation/telemetry/…`/`testing_overview` load-balancing note + design-side record (thesis Ch3 text stays the author's, flagged in P7) |

**Semantics:** the cost function and pool rules are untouched; the change
only spreads selections among **near-equal-cost** candidates (≤ ε apart) —
i.e. it removes the arbitrary tie collapse. Warm-up still gives the new
backend eligibility; it no longer gives it exclusivity.

**Risks:** slight mean-cost rise (bounded by ε); ε must stay below the
peer/hop gap (0.14) — selftest asserts; reproductions of pre-P2.6 runs
mean the pre-P2.6 commit (same discipline as the P1 repair).

**Verification (P2.7, VM):** re-run the seat block at 0.23 — `comp` must
relieve (post-add p95 < 1 s in ≥ 80 % of windows both lanes, completion
≥ 95 %, recovery persists) and `stor` must still not relieve; `none` at
0.20 unchanged by construction (single static per lane ⇒ band size 1 —
no re-run needed unless cheap). The full 3-run block is ~1.5 h.

## 5. Provenance

- Read-only autopsy: VM session 2026-10-11 22:20–22:30 Z; no files created
  or modified on the VM; local analysis via stdin one-offs.
- Anchors verified: `flows.py:386,403–404,434,445–446`;
  `ingress.py:153,168–176,404–424`; `scaling_config.py:274,285–286,307–309`;
  `selection.py:72–113,139–144,206–215,328–338`; `control_events.py:44–70`;
  `main_n1.py:597`.
