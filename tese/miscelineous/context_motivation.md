Revised §1.1 Structure — 9 Paragraphs

Understood. You want a properly developed introduction, not a compressed one. Here's a 9-paragraph structure that follows your funnel logic, with each paragraph doing exactly one job and citing the right papers. Each ¶ is roughly the size of your existing traffic paragraph (5–7 lines).

> **Framing note (2026-07-31; refreshed 2026-08-01):** ¶9 (Central Claim)
> follows the current three-interface thesis framing
> (`tese/Notes/thesis_overview.md`): **telemetry delivery semantics** (RQ1),
> **bottleneck-aware capacity-action selection** (RQ2), and **readiness
> admission** (RQ3). The earlier "trigger quality /
> telemetry freshness / backend selection" labels are superseded. ¶8's
> coordination gap IS now the central (corpus-bounded) claim of the filled
> §1.1: the work 'narrows that goal to the coordination gap between
> independently operating control loops, a specific and previously
> unexamined slice'. Keep any such claim corpus-bounded ('within the
> reviewed corpus'). Tiered data placement is a
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
> (2026-08-03) ¶6 expanded beyond per-site scarcity to the full complexity
> taxonomy (heterogeneity, demand volatility, placement/scheduling
> decoupling, multi-owner resources), adding `Luo2021ResourceSchedulingEdgeComputingSurvey`
> and `Liu2019SurveyEdgeComputingSystemsTools`; the production
> over-provisioning/imbalance evidence `Xu2021FirstLookPublicEdgePlatforms`
> (NEP) is now cited in ¶6 (previously absent despite being the
> production-motivation). ¶8 gains a SOTA-positioning sentence (the thesis
> follows the integration direction surveys call for, using standard
> mechanisms). All three new keys are added to `tese/references.bib`.
> (2026-08-12) ¶6's data-gravity tail (network locality / serve-remotely /
> replicate-hot-subset / full-replica options) moved to ¶7, where the
> stateful-services discussion already carried the compressed version;
> ¶6 now ends on multi-owner complexity and its title drops "Data Gravity".
> Pelle kept cited in the merged ¶7 block.
> (2026-08-13) ¶7 trimmed to roughly half its length: the "data has
> gravity" example sentence, the "spare capacity / network locality"
> sentence, and the "adding a server does not solve it / over-provisioning
> not an option" clauses were removed as redundant; the three
> serve-remotely / replicate-hot-subset / full-replica options, the
> detect-to-redirect chain, and the workload intro remain.
> (2026-08-13b) ¶7 gains a closing bridge to ¶8: the detect-provision-
> redirect chain is mapped onto separate monitoring, auto-scaler, and load
> balancer components, each with its own control loop, so the jump into
> ¶8 is no longer abrupt. ¶8's opening reworded to "This separation is the
> norm..." so it picks up the bridge directly.
> (2026-08-13c) ¶8's opening re-anchored per-source after verification: the
> component facts are pinned to Llorens (OSM MON/POL/LCM, Prometheus TSDB,
> OFS flow tables) and Qu (monitoring interval + LB tier as taxonomy
> dimensions); unsupported tool names (InfluxDB, kube-proxy, HAProxy, HPA)
> dropped. AdapPF (Huang & Pierre 2023) added as the single corpus paper
> that varies a monitoring interval experimentally; the "never varied"
> claim qualified to "along the full demand-to-capacity chain". BibTeX key
> added: Huang2023AdapPFSelfAdaptiveScrapeInterval.
> (2026-08-21) This guide has been applied to the filled §1.1 in main.tex,
> with deviations: ¶6 anchors to Breitbach/Nicolaescu/Pelle (Okwuibe not
> cited in ¶6); Xu2021 (NEP) and Liu2019 are in references.bib but not cited
> in the filled §1.1; the 'Multi-Region Content Discovery Platform' workload
> description below is stale — the filled §1.1 describes a stateful edge
> service across two geo-distributed sites with a MongoDB replica-set
> storage tier.

## Reference key → paper → location

> Folder paths are relative to `tese/literature_review/`. (2026-08-01) All keys
> used below are now in the corpus (PDF) or already in `tese/references.bib`;
> the “Replaced references” table records the swaps.

| Key                                                          | Paper (title — authors, year)                                                                                                                           | Location                                                                                                                            |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `ITU2025InternetTraffic`                                   | *Facts and Figures 2025: Internet Traffic* — ITU report, 2025                                                                                         | `tese/references.bib` (no PDF)                                                                                                    |
| `Gurung2026CloudRevolutionTracingOriginsRise`              | “Cloud Revolution: Tracing the Origins and Rise of Cloud Computing” — Gurung et al., IEEE CCWC 2026                                                   | `tese/references.bib` (no PDF)                                                                                                    |
| `Cao2020OverviewEdgeComputingResearch`                     | “An Overview on Edge Computing Research” — Cao et al., IEEE Access 8, 2020                                                                            | `04_context_edge/An_Overview_on_Edge_Computing_Research.pdf` (+ in `.bib`)                                                      |
| `Satyanarayanan2017EmergenceEdgeComputing`                 | “The Emergence of Edge Computing” — Satyanarayanan, IEEE Computer 50(1), 2017                                                                         | `04_context_edge/The_Emergence_of_Edge_Computing.pdf` (+ in `.bib`)                                                             |
| `Okwuibe2020SDNEnhancedResourceOrchestrationContainerized` | “SDN Enhanced Resource Orchestration of Containerized Edge Applications for Industrial IoT” — Okwuibe et al., IEEE Access 8, 2020                     | `05_context_orchestration/SDN_Enhanced_Resource_Orchestration_of_Containerized_Edge_Applications_for_Industrial_IoT.pdf`          |
| `Breitbach2019ContextAwareDataTaskPlacement`               | “Context-Aware Data and Task Placement in Edge Computing Environments” — Breitbach et al., IEEE PerCom 2019                                           | `02_action_selection_rq2/Context-Aware_Data_and_Task_Placement_in_Edge_Computing_Environments.pdf`                                |
| `Nicolaescu2021StoreEdgeNetworkedDataSEND`                 | “Store Edge Networked Data (SEND): A Data and Performance Driven Edge Storage Framework” — Nicolaescu et al., IEEE INFOCOM 2021                       | `02_action_selection_rq2/Store_Edge_Networked_Data_SEND_A_Data_and_Performance_Driven_Edge_Storage_Framework.pdf`                 |
| `Qu2018AutoScalingWebApplicationsClouds`                   | “Auto-Scaling Web Applications in Clouds: A Taxonomy and Survey” — Qu, Calheiros & Buyya, ACM Comput. Surv. 51(4), 2018                               | `02_action_selection_rq2/Auto-Scaling Web Applications in Clouds - A Taxonomy and Survey.pdf`                                     |
| `Llorens2021SDNBasedHorizontalAutoScalingLoadBalancing`    | “An SDN-Based Solution for Horizontal Auto-Scaling and Load Balancing of Transparent VNF Clusters” — Llorens-Carrodeguas et al., Sensors 21(24), 2021 | `03_readiness_admission_rq3/An_SDN-Based_Solution_for_Horizontal_Auto-Scaling_and_Load_Balancing_of_Transparent_VNF_Clusters.pdf` |
| `Pelle2022CostLatencyEdgePlatform`                         | “Cost and Latency Optimized Edge Computing Platform” — Pelle et al., Electronics 11(4):561, 2022                                                      | `04_context_edge/Cost and Latency Optimized Edge Computing Platform.pdf`                                                          |
| `Yaseen2025CountersTelemetrySurveyProgrammableNetwork`     | “From Counters to Telemetry: A Survey of Programmable Network-Wide Monitoring” — Yaseen, Network 5:38, 2025                                           | `01_telemetry_rq1/From Counters to Telemetry - A Survey of Programmable Network-Wide Monitoring.pdf`                              |
| `Luo2021ResourceSchedulingEdgeComputingSurvey`             | “Resource Scheduling in Edge Computing: A Survey” — Luo et al., IEEE COMST 23(4), 2021                                                                | `04_context_edge/Resource_Scheduling_in_Edge_Computing_A_Survey.pdf`                                                              |
| `Liu2019SurveyEdgeComputingSystemsTools`                   | “A Survey on Edge Computing Systems and Tools” — Liu et al., Proc. IEEE 107(8), 2019                                                                  | `04_context_edge/A_Survey_on_Edge_Computing_Systems_and_Tools.pdf`                                                                |
| `Xu2021FirstLookPublicEdgePlatforms`                       | “From Cloud to Edge: A First Look at Public Edge Platforms” — Xu et al., ACM IMC 2021                                                                 | `04_context_edge/From Cloud to Edge - A First Look at Public Edge Platforms.pdf`                                                  |

### Replaced references (not in corpus / unverifiable — record only)

| Old key                                                    | Replaced by (¶)                                                   |
| ---------------------------------------------------------- | ------------------------------------------------------------------ |
| `Armbrust2010ViewCloudComputing`                         | `Gurung2026CloudRevolutionTracingOriginsRise` (¶3)              |
| `Shi2016EdgeComputingVisionChallenges`                   | `Cao2020OverviewEdgeComputingResearch` (¶4)                     |
| `Tao2019` (unverifiable)                                 | `Cao2020OverviewEdgeComputingResearch`, `Okwuibe2020...` (¶6) |
| `Qadir2020` (unverifiable)                               | `Breitbach2019ContextAwareDataTaskPlacement` (¶6)               |
| `Sonkoly2021`                                            | `Nicolaescu2021StoreEdgeNetworkedDataSEND` (¶6)                 |
| `PodolskiyIaaS`                                          | `Qu2018AutoScalingWebApplicationsClouds` (¶8)                   |

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

¶6 — The Costs of Dispersal: Resource Scarcity and Management Complexity

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
\parencite{Satyanarayanan2017EmergenceEdgeComputing}. Surveying the
resource-scheduling literature, Luo et al. add two further sources of
complexity: edge resources are heterogeneous — nodes of widely
different capacity that must be scheduled jointly — and the demand
they serve is volatile, so coarse or static scheduling degrades
precisely when it matters most
\parencite{Luo2021ResourceSchedulingEdgeComputingSurvey}. The
consequences of that volatility are visible in production: a
measurement of a major public edge platform found resource usage
unbalanced by up to 14$\times$ across servers and 731$\times$ across
sites in the same province, with utilization about six times lower
than a comparable cloud — evidence that edge customers over-provision
because demand is hard to forecast, and that the resulting imbalance
traces to a decoupling between where capacity is placed and where
requests are scheduled
\parencite{Xu2021FirstLookPublicEdgePlatforms}. A further, often
overlooked, source of complexity is that edge resources belong to
different owners — a site's servers, the network it attaches to, and
the gateways in its users' homes are administered by different
parties — so orchestrating a service across them requires reconciling
multiple administrative domains
\parencite{Liu2019SurveyEdgeComputingSystemsTools}.

¶7 — Stateful Services in Geo-Distributed Edge Deployments

The resource management problem is compounded when the services
themselves are stateful. Unlike stateless microservices, which can be
replicated freely and absorb traffic immediately, stateful services in a
geo-distributed edge deployment depend on data co-located with compute:
a content item ingested at one site is served from the database of that
site, so a request reaching a server elsewhere must either be served
remotely, paying WAN latency on every access; or wait for the hot data to
be replicated locally, paying synchronisation overhead; or require a full
replica, paying storage and replication cost
\parencite{Breitbach2019ContextAwareDataTaskPlacement,Nicolaescu2021StoreEdgeNetworkedDataSEND,Pelle2022CostLatencyEdgePlatform}.
Scale-out alone does not solve this: the orchestration system must detect
when data must be brought closer, deliver that information to the decision
point, provision the right kind of capacity, and redirect traffic to it —
and each of these steps introduces delay that directly degrades service
quality under the time pressure of an ongoing demand shift. In practice,
these steps are not executed by a single control entity: a monitoring
component detects demand, an auto-scaler provisions capacity, and a load
balancer redirects traffic, each running under its own control loop. The
filled §1.1 describes a stateful edge service deployed across two
geo-distributed sites, whose compute backends are Docker containers and
whose data tier is a MongoDB replica set, studied through three interfaces:
telemetry delivery, capacity action selection, and readiness admission.

¶8 — The Orchestration Problem: The Coordination Gap

In the reviewed orchestration platforms, monitoring, scaling, and routing
are separate components: in OSM-based NFV, the Policy Manager,
Monitoring, and Lifecycle Management modules operate alongside an
SDN-based VNF Redirector whose monitoring polls the VIM into a Prometheus
time-series database and whose load balancing steers traffic through
OpenFlow flow tables
\parencite{Llorens2021SDNBasedHorizontalAutoScalingLoadBalancing}. Surveys
of auto-scaling likewise treat the monitoring interval and the
load-balancing tier as separate design dimensions
\parencite{Qu2018AutoScalingWebApplicationsClouds}. The handoff between
these components is consequential rather than merely architectural:
AdapPF shows that a coarse monitoring scrape interval degrades the
accuracy of application scheduling in geo-distributed cluster
federations, and that adaptive scraping restores it
\parencite{Huang2023AdapPFSelfAdaptiveScrapeInterval}, yet stops at
scheduling accuracy without tracing the effect through a stateful
service's scaling and admission path. The coordination gap
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
variable along the full demand-to-capacity chain. Within the reviewed
corpus, no paper argues for this separation
or against co-location: the separation appears as the unexamined default.
The direction of remedy, however, is well established: a survey of edge
resource scheduling calls for the joint treatment of communication,
computation, and storage resources
\parencite{Luo2021ResourceSchedulingEdgeComputingSurvey}, and a survey of
programmable network-wide monitoring calls for monitoring to be tightly
integrated with network control and automation
\parencite{Yaseen2025CountersTelemetrySurveyProgrammableNetwork}. This
thesis follows that direction with standard mechanisms — an SDN
controller, threshold-based scaling, and push/poll telemetry — and makes
its contribution not in any single mechanism but in co-locating them so
that the three interfaces can be varied independently and their effects
measured, extending the tradition of experimental studies that vary a
telemetry parameter and observe the consequence. Within this gap, this
thesis isolates three specific links in the demand-to-capacity chain — how
demand evidence is delivered to the controller, which capacity action is
chosen in response, and when ready capacity is admitted to traffic.

¶9 — Central Claim and Honest Scope

This thesis experimentally examines three links in the demand-to-capacity
chain — telemetry delivery semantics (how demand evidence reaches the
controller, and whether intermediate evidence is preserved), capacity-action
selection (whether the controller scales compute or storage in response to
the observed bottleneck), and readiness admission (how quickly a ready
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
