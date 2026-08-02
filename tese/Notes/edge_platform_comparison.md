# Edge Platform Comparison — Thesis vs. Literature

> **Status (2026-08-01):** this table supports the *apparatus* rationale for Ch.1/Ch.3
> (co-location makes the three control-loop interfaces independently tunable — see
> `thesis_overview.md` §5 and purpose map P6). It is **not** a superiority claim and
> **not** thesis evidence for the RQ gaps. Citation counts from Semantic Scholar unless
> noted. Keep any “unique” reading corpus-bounded (“within the reviewed corpus”).
> MiCADO-Edge, StarlingX, and ECaaS are **candidates not yet added** to
> `tese/literature_review/` — add them (PDF + README row) only when they are used.

| Platform | Cites | HTTP API? | Monitoring | Auto-Scaling | LB/Routing | Stateful? | Single-Process? |
|---|---|---|---|---|---|---|---|
| **Thesis** | — | ✅ Flask+MongoDB | ✅ Thread 2 | ✅ Thread 3 | ✅ Thread 1 (VIP) | ✅ Tiered MongoDB | ✅ **Yes** |
| MiCADO-Edge (2021) | ~95 | ✅ Microservices | ✅ App metrics | ✅ HPA-like | ✅ K8s SD | ❌ | ❌ |
| ECaaS (2021) | ~44 | ✅ User services | ✅ Node health | ✅ DC formation | ⚠️ Membership | ❌ | ❌ |
| LAVEA (2017) | 293 | Partial | ✅ Implicit | ✅ Implicit | ✅ Implicit | ❌ | ❌ |
| Pelle et al. (2022) | 17 | ❌ | ⚠️ CloudWatch | ❌ | ⚠️ Greengrass | ✅ AnnaBellaDB | ❌ |
| Okwuibe et al. (2020) | — | ❌ | ✅ InfluxDB | ✅ K8s | ❌ | ❌ | ❌ |
| Toka et al. (2021) | — | Partial | ✅ K8s metrics | ✅ ML HPA | ❌ | ❌ | ❌ |
| StarlingX (2022) | ~14 | ✅ HTTP GET | ✅ CPU/mem/net | ⚠️ Failover | ⚠️ Failover | ❌ | ❌ |
| Hung et al. (2022) | 4 | ❌ | ✅ Telemetry | ❌ | ✅ Routing | ❌ | ⚠️ 2 layers |

## Key

- **Single-Process / Co-resident**: Monitoring, auto-scaling, and LB share one process
  (three co-resident execution contexts with message-driven internal paths — see
  `docs/operation/system_mechanisms.md`).
- **Stateful**: Persistent data tier; data placement is a HELD-CONSTANT platform
  capability, not a claimed contribution (`thesis_overview.md` §2, §9).
- **Apparatus reading (corpus-bounded):** within the reviewed corpus, the thesis is the
  only system that co-locates the three functions for stateful HTTP API services with
  each interface independently tunable. This is an *apparatus* statement, not a
  superiority claim.

## New Candidates (not yet in the corpus — add only when used)

| Candidate | DOI | Status |
|---|---|---|
| MiCADO-Edge — Ullah et al. (2021) | `10.1007/s10723-021-09589-5` | candidate |
| ECaaS — Simić et al. (2021) | `10.1109/ACCESS.2021.3102954` | candidate |
| StarlingX — Abuibaid et al. (2022) | `10.1109/ACCESS.2022.3204286` | candidate |

Add each to `tese/literature_review/04_context_edge/` (PDF + README row) when it is
actually cited; `tese/references.bib` entries are added at first use.
