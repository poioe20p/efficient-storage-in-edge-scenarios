Revised §1.1 Structure — 9 Paragraphs

Understood. You want a properly developed introduction, not a compressed one. Here's a 9-paragraph structure that follows your funnel logic, with each paragraph doing exactly one job and citing the right papers. Each ¶ is roughly the size of your existing traffic paragraph (5–7 lines).

> **Framing note (2026-07-31; refreshed 2026-08-01):** ¶9 (Central Claim)
> follows the current three-interface thesis framing
> (`tese/Notes/thesis_overview.md`): **telemetry delivery semantics** (RQ1),
> **bottleneck-aware capacity-action selection** (RQ2), and **readiness
> propagation / traffic admission** (RQ3). The earlier "trigger quality /
> telemetry freshness / backend selection" labels are superseded. ¶8
> (coordination gap) is retained **as background motivation only**: the
> evidence ledger `tese/literature_review/global_literature_review.md` now
> carries a banner flagging its own coordination-gap framing as superseded —
> keep any such claim corpus-bounded ("within the reviewed corpus") and do not
> let it become the thesis's central claim. Tiered data placement is a
> held-constant platform capability, not a claimed contribution.
>
> **Citation status (2026-08-01):** `tese/references.bib` is populated *as
> citations are used*, not pre-populated. All references below are now either in
> the literature corpus (PDF) or already in the `.bib` — see the reference map.
> Not yet in the `.bib` (add at first use): `Qu2018AutoScalingWebApplicationsClouds`,
> `Llorens2021SDNBasedHorizontalAutoScalingLoadBalancing`,
> `Okwuibe2020SDNEnhancedResourceOrchestrationContainerized`,
> `Nicolaescu2021StoreEdgeNetworkedDataSEND`, `Breitbach2019ContextAwareDataTaskPlacement`,
> `Pelle2022CostLatencyEdgePlatform`, `Yaseen2025CountersTelemetrySurveyProgrammableNetwork`.
> Already in the `.bib`: `ITU2025InternetTraffic`,
> `Gurung2026CloudRevolutionTracingOriginsRise`,
> `Cao2020OverviewEdgeComputingResearch`, `Satyanarayanan2017EmergenceEdgeComputing`.
> (2026-08-01) Unverifiable/absent references (e.g. `Tao2019`, `Qadir2020`) were
> replaced with in-corpus alternatives that fit the same context — see the
> “Replaced references” table below.
> (2026-08-02) ¶5–¶6 reframed: edge computing is presented as inherently
> geo-distributed (dispersion is its defining mechanism; “edge” and
> “geo-distributed deployment” are the same thing, not distinct concepts).
> ¶6 now leads with per-site scarcity and the operational cost of dispersal
> and cites `Satyanarayanan2017EmergenceEdgeComputing` for the stated
> disadvantages (dispersion-driven management complexity, weaker perimeter
> security); `Cao2020OverviewEdgeComputingResearch` is dropped from ¶6 but
> remains in ¶4/¶5. The capacity claim is anchored to
> `Okwuibe2020SDNEnhancedResourceOrchestrationContainerized` and
> `Breitbach2019ContextAwareDataTaskPlacement`. Those three keys are now in
> use but still pending addition to `tese/references.bib`.

## Reference key → paper → location

> Folder paths are relative to `tese/literature_review/`. (2026-08-01) All keys
> used below are now in the corpus (PDF) or already in `tese/references.bib`;
> the “Replaced references” table records the swaps.

| Key | Paper (title — authors, year) | Location |
|---|---|---|
| `ITU2025InternetTraffic` | *Facts and Figures 2025: Internet Traffic* — ITU report, 2025 | `tese/references.bib` (no PDF) |
| `Gurung2026CloudRevolutionTracingOriginsRise` | “Cloud Revolution: Tracing the Origins and Rise of Cloud Computing” — Gurung et al., IEEE CCWC 2026 | `tese/references.bib` (no PDF) |
| `Cao2020OverviewEdgeComputingResearch` | “An Overview on Edge Computing Research” — Cao et al., IEEE Access 8, 2020 | `04_context_edge/An_Overview_on_Edge_Computing_Research.pdf` (+ in `.bib`) |
| `Satyanarayanan2017EmergenceEdgeComputing` | “The Emergence of Edge Computing” — Satyanarayanan, IEEE Computer 50(1), 2017 | `04_context_edge/The_Emergence_of_Edge_Computing.pdf` (+ in `.bib`) |
| `Okwuibe2020SDNEnhancedResourceOrchestrationContainerized` | “SDN Enhanced Resource Orchestration of Containerized Edge Applications for Industrial IoT” — Okwuibe et al., IEEE Access 8, 2020 | `05_context_orchestration/SDN_Enhanced_Resource_Orchestration_of_Containerized_Edge_Applications_for_Industrial_IoT.pdf` |
| `Breitbach2019ContextAwareDataTaskPlacement` | “Context-Aware Data and Task Placement in Edge Computing Environments” — Breitbach et al., IEEE PerCom 2019 | `02_action_selection_rq2/Context-Aware_Data_and_Task_Placement_in_Edge_Computing_Environments.pdf` |
| `Nicolaescu2021StoreEdgeNetworkedDataSEND` | “Store Edge Networked Data (SEND): A Data and Performance Driven Edge Storage Framework” — Nicolaescu et al., IEEE INFOCOM 2021 | `02_action_selection_rq2/Store_Edge_Networked_Data_SEND_A_Data_and_Performance_Driven_Edge_Storage_Framework.pdf` |
| `Qu2018AutoScalingWebApplicationsClouds` | “Auto-Scaling Web Applications in Clouds: A Taxonomy and Survey” — Qu, Calheiros & Buyya, ACM Comput. Surv. 51(4), 2018 | `02_action_selection_rq2/Auto-Scaling Web Applications in Clouds - A Taxonomy and Survey.pdf` |
| `Llorens2021SDNBasedHorizontalAutoScalingLoadBalancing` | “An SDN-Based Solution for Horizontal Auto-Scaling and Load Balancing of Transparent VNF Clusters” — Llorens-Carrodeguas et al., Sensors 21(24), 2021 | `03_readiness_admission_rq3/An_SDN-Based_Solution_for_Horizontal_Auto-Scaling_and_Load_Balancing_of_Transparent_VNF_Clusters.pdf` |
| `Pelle2022CostLatencyEdgePlatform` | “Cost and Latency Optimized Edge Computing Platform” — Pelle et al., Electronics 11(4):561, 2022 | `04_context_edge/Cost and Latency Optimized Edge Computing Platform.pdf` |
| `Yaseen2025CountersTelemetrySurveyProgrammableNetwork` | “From Counters to Telemetry: A Survey of Programmable Network-Wide Monitoring” — Yaseen, Network 5:38, 2025 | `01_telemetry_rq1/From Counters to Telemetry - A Survey of Programmable Network-Wide Monitoring.pdf` |

### Replaced references (not in corpus / unverifiable — record only)

| Old key | Replaced by (¶) |
|---|---|
| `Armbrust2010ViewCloudComputing` | `Gurung2026CloudRevolutionTracingOriginsRise` (¶3) |
| `Shi2016EdgeComputingVisionChallenges` | `Cao2020OverviewEdgeComputingResearch` (¶4) |
| `Tao2019` (unverifiable) | `Cao2020OverviewEdgeComputingResearch`, `Okwuibe2020...` (¶6) |
| `Hong2019` | `Okwuibe2020SDNEnhancedResourceOrchestrationContainerized` (¶6) |
| `Qadir2020` (unverifiable) | `Breitbach2019ContextAwareDataTaskPlacement` (¶6) |
| `Sonkoly2021` | `Nicolaescu2021StoreEdgeNetworkedDataSEND` (¶6) |
| `PodolskiyIaaS` | `Qu2018AutoScalingWebApplicationsClouds` (¶8) |
| `Wang2026AutoScalingLoadAwareSDNFV` | `Llorens2021SDNBasedHorizontalAutoScalingLoadBalancing` (¶8) |
| `Pierro2026EvaluatingKubernetesAutoscalingStrategiesIoT` | `Okwuibe2020SDNEnhancedResourceOrchestrationContainerized` (¶8) |

---

¶1 — Internet Traffic Growth (The Hook)
Job: Establish the scale. Global internet traffic surpassed 7 EB in 2025, more than double since 2020. This is your opening data point — concrete, cited, visual (Figure 1.1). Keep it factual, not interpretative.

Citation: ITU2025InternetTraffic (already in .bib)

Risk: As I said before, this is a generic hook. To mitigate that, add one sentence at the end of this paragraph that plants a seed: "A substantial fraction of this traffic is generated and consumed at the network edge, by applications with stringent latency expectations." This bridges immediately to ¶2 instead of leaving the reader wondering why traffic volume matters.

¶2 — What Drives This Growth
Job: Name the technological drivers — streaming, social media, IoT, connected devices, real-time interactive applications. This paragraph justifies why the growth is happening and hints that these applications are increasingly latency-sensitive and data-intensive. Crucially, this paragraph transitions from "traffic exists" to "traffic has properties that matter."

Citation: You can cite the ITU report again, or add a supplementary source on internet application trends. No new paper strictly needed — this is interpretive context.

Flag: The writing guide says "DO NOT mention IoT." I think mentioning IoT in a list of traffic drivers (alongside streaming and social media) is factually defensible — the ITU report itself includes IoT in traffic growth statistics. The prohibition is against framing the thesis around IoT, not against acknowledging IoT exists. But be aware of the tension. If you want to be safe, replace "IoT" with "connected devices and real-time applications."

¶3 — Cloud as the Default Deployment Model
Job: These applications are overwhelmingly deployed on cloud infrastructure. Cloud provides abundant compute and storage resources, economies of scale, global reach, and operational maturity. This is the status quo — the unexamined default for application deployment. You're establishing the baseline that edge computing will be contrasted against.

Citation: Gurung et al. (2026) — "Cloud Revolution: Tracing the Origins and Rise of Cloud Computing," IEEE CCWC 2026. Already in references.bib as `Gurung2026CloudRevolutionTracingOriginsRise`.

Alternative (in corpus): Cao et al. (2020) — "An Overview on Edge Computing Research," IEEE Access 8 — `04_context_edge/`. (Armbrust et al. (2010) "A View of Cloud Computing" remains the canonical cloud paper but has no PDF in the corpus.)

¶4 — The Latency Problem: Why Cloud Isn't Enough
Job: Despite cloud's resource abundance, some applications have latency constraints that a centralized cloud model cannot satisfy — the physical distance between cloud data centers and end users imposes a fundamental lower bound on response time. Interactive web services, real-time content personalization, and data-intensive applications are particularly affected. This tension — abundant resources but high latency — is what motivated the emergence of fog and edge computing paradigms.

Citation: Satyanarayanan (2017) — "The Emergence of Edge Computing," IEEE Computer. DOI: 10.1109/MC.2017.9. The authoritative voice on why edge exists. In references.bib as `Satyanarayanan2017EmergenceEdgeComputing`.

Also: Cao et al. (2020) — "An Overview on Edge Computing Research," IEEE Access 8. DOI: 10.1109/ACCESS.2020.2991734. In corpus at `04_context_edge/An_Overview_on_Edge_Computing_Research.pdf` and in the `.bib`.

These two together are the canonical pair. Satyanarayanan gives you the conceptual argument (distance = latency); Cao gives you the structured survey. (Shi et al. (2016) "Edge Computing: Vision and Challenges" is the common alternative but has no PDF in the corpus.)

¶5 — Edge Computing Is Inherently Geo-Distributed

Edge computing is, by construction, a geo-distributed deployment
model. Its defining move is to disperse computing and storage across
many sites in close physical proximity to users, rather than
concentrating them in a small number of large data centers
\parencite{Satyanarayanan2017EmergenceEdgeComputing}. The cloud, by
contrast, consolidates capacity into relatively few, very large sites
spread across the globe. The distinction between the two is therefore
not “edge computing” versus “geo-distributed deployment” — both are
geographically distributed — but the degree and purpose of that
distribution: few large, distant sites versus many small, proximate
ones. It is this dispersal that produces the paradigm's advantages.
First, services placed closer to users experience lower round-trip
time, directly benefiting latency-sensitive applications. Second,
processing data locally instead of traversing the core network reduces
backbone traffic and alleviates congestion on inter-domain links
\parencite{Cao2020OverviewEdgeComputingResearch,Satyanarayanan2017EmergenceEdgeComputing}.
For this thesis, both advantages are
directly relevant: latency drives the p95 and p99 metrics used to
evaluate service quality, and reduced backbone traffic connects to the
data locality trade-offs explored in the experimental workload
(cross-region reads, tiered data placement).

¶6 — The Costs of Dispersal: Resource Scarcity, Management Complexity,
and Data Gravity

The dispersal that produces these advantages is also the source of
edge computing's constraints, and those constraints are intrinsic to
the paradigm rather than incidental properties of particular
deployments. The first is per-site scarcity: an edge site operates
under finite per-site capacity, with limited compute, storage, and
bandwidth, and — unlike a cloud data center — cannot mask a demand
surge through over-provisioning
\parencite{Okwuibe2020SDNEnhancedResourceOrchestrationContainerized,Breitbach2019ContextAwareDataTaskPlacement}.
The second is the operational cost of the dispersal itself:
Satyanarayanan notes that “the dispersion inherent in edge computing
raises the complexity of management considerably,” and that edge sites
have weaker perimeter security than cloud data centers
\parencite{Satyanarayanan2017EmergenceEdgeComputing}. Yet even when
spare capacity exists elsewhere in the system, the binding constraint
is not raw compute or memory exhaustion but network locality: scaling
a service across sites to absorb a demand surge forces requests and
data to traverse the wide-area link. This is a qualitatively different
bottleneck from CPU or memory exhaustion. When data has a home — when a
content item ingested at one site is requested by users of another —
the orchestration system must decide whether to serve the request
remotely, paying WAN latency on every access; to replicate the hot data
subset locally, paying synchronisation overhead; or to provision a full
replica, paying storage and replication cost
\parencite{Breitbach2019ContextAwareDataTaskPlacement,Nicolaescu2021StoreEdgeNetworkedDataSEND}.
These are not stateless scale-out decisions; they are
data-gravity-aware resource allocation decisions, and they must be
made under the time pressure of an ongoing demand shift.

¶7 — Stateful Services in Geo-Distributed Edge Deployments

The resource management problem is compounded when the services themselves
are stateful. Stateless microservices can be replicated freely — a new
instance absorbs traffic immediately. But many applications in a
geo-distributed edge deployment depend on data co-located with compute. A
content discovery platform, for instance, ingests content items regionally
and serves personalized feeds globally.
The data has gravity: it resides in the database of the region that
ingested it, and a server in the opposite region that needs that data
must either fetch it remotely or wait for local replication
\parencite{Breitbach2019ContextAwareDataTaskPlacement,Pelle2022CostLatencyEdgePlatform}. This means adding a new server in
response to load does not, by itself, solve the problem. The data must
be brought closer, and the orchestration system must detect when this is
necessary, deliver that information to the decision point, provision the
right kind of capacity, and redirect traffic to it. In resource-constrained
deployments, where over-provisioning across sites is not an option, each of these
steps introduces delay that directly degrades the quality of service users
experience. This thesis uses a Multi-Region Content Discovery Platform —
a geo-distributed edge deployment — as its experimental workload: content
items are ingested regionally and discovered globally through tag-based
personalized feeds, with heterogeneous document types and two stress
regimes — one driven by data locality, the other by compute-analytics
throughput.

¶8 — The Orchestration Problem: The Coordination Gap

In the major cloud and edge orchestration platforms considered here —
Kubernetes, NFV MANO frameworks such as OSM and ONAP, and MEC platforms —
the functions that would need to coordinate during a demand shift are
implemented as separate components with independent control loops. A monitoring system such as Prometheus or
InfluxDB scrapes metrics on a fixed interval. An auto-scaler such as the
Kubernetes HPA or the OSM Policy Manager evaluates thresholds and
provisions new instances. A load balancer — kube-proxy, HAProxy, or SDN
flow tables — eventually discovers the new backends and steers traffic to
them. Each handoff between these components adds latency: the monitoring
scrape interval, the alarm evaluation window, the provisioning time, and
the health-check discovery gap accumulate before newly provisioned
capacity can serve traffic
\parencite{Qu2018AutoScalingWebApplicationsClouds,Llorens2021SDNBasedHorizontalAutoScalingLoadBalancing}. The coordination gap
is not unique to edge deployments — reactive scaling is the default
across cloud and edge platforms
\parencite{Qu2018AutoScalingWebApplicationsClouds} — but its consequences are
amplified where resources are finite: cloud data centers mask the gap with
over-provisioning; edge sites cannot. This coordination gap
— the accumulated delay between overload onset and traffic reaching newly
provisioned capacity — has been documented in passing in the OSM MANO architecture
\parencite{Llorens2021SDNBasedHorizontalAutoScalingLoadBalancing}, is
reflected in the component split of a real containerized edge stack
\parencite{Okwuibe2020SDNEnhancedResourceOrchestrationContainerized}, and
has been called for at the survey level by Yaseen
\parencite{Yaseen2025CountersTelemetrySurveyProgrammableNetwork} — but
never isolated, measured, or varied as an independent experimental
variable. Within the reviewed corpus, no paper argues for this separation
or against co-location: the separation appears as the unexamined default.
Within this gap, this
thesis isolates three specific links in the demand-to-capacity chain — how
demand evidence is delivered to the controller, which capacity action is
chosen in response, and when ready capacity is admitted to traffic.

¶9 — Central Claim and Honest Scope

This thesis experimentally examines three links in the demand-to-capacity
chain — telemetry delivery semantics (how demand evidence reaches the
controller, and whether intermediate evidence is preserved), capacity-action
selection (whether the controller scales compute or storage in response to
the observed bottleneck), and readiness propagation (how quickly a ready
backend is admitted to traffic and becomes usable capacity) —
characterising how each independently affects service quality during demand
shifts in a stateful service deployed across two geo-distributed sites. An
SDN controller serves as the experimental apparatus: by co-locating
monitoring, routing, and scaling in a single process with shared data
structures, it makes each of the three interfaces independently controllable,
so each link can be varied while the others are held constant. The thesis
does not claim that SDN is superior to Kubernetes or any specific
orchestration platform; does not claim that these interfaces matter equally
for all workloads or at all deployment scales; and does not claim that the
platform mechanisms — the Double-VIP traffic model, tiered data placement
and Tier 1 selective synchronisation — generalise beyond the tested
infrastructure (they are held constant as platform capabilities, not part of
the claimed contribution). It claims only that the three interfaces are
measurable, previously uncharacterised links in the demand-to-capacity path,
and that varying each independently within a unified control point reveals
which dimensions matter and under what conditions.
