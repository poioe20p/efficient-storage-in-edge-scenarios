# Edge Platform Comparison — Thesis vs. Literature

> Citation counts from Semantic Scholar unless noted. New candidates (MiCADO-Edge, StarlingX, ECaaS) not yet in literature review.

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

- **Single-Process**: Monitoring, auto-scaling, and LB co-located in one process with shared state.
- **Stateful**: Persistent data tier with data locality affecting routing decisions.
- Thesis is unique in co-locating all three functions for stateful HTTP API services.

## New Candidates (not in LR)

| Candidate | DOI |
|---|---|
| MiCADO-Edge — Ullah et al. (2021) | `10.1007/s10723-021-09589-5` |
| ECaaS — Simić et al. (2021) | `10.1109/ACCESS.2021.3102954` |
| StarlingX — Abuibaid et al. (2022) | `10.1109/ACCESS.2022.3204286` |
