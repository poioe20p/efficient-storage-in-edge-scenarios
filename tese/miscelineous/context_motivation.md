Revised §1.1 Structure — 9 Paragraphs

Understood. You want a properly developed introduction, not a compressed one. Here's a 9-paragraph structure that follows your funnel logic, with each paragraph doing exactly one job and citing the right papers. Each ¶ is roughly the size of your existing traffic paragraph (5–7 lines).

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

Citation needed: Armbrust et al. (2010) — "A View of Cloud Computing," Communications of the ACM. Canonical reference. Not in your .bib. DOI: 10.1145/1721654.1721672

Alternative: Buyya et al. (2009), "Cloud computing and emerging IT platforms," Future Generation Computer Systems. DOI: 10.1016/j.future.2008.12.001. Older but still well-cited. Armbrust is the better choice.

¶4 — The Latency Problem: Why Cloud Isn't Enough
Job: Despite cloud's resource abundance, some applications have latency constraints that a centralized cloud model cannot satisfy — the physical distance between cloud data centers and end users imposes a fundamental lower bound on response time. Interactive web services, real-time content personalization, and data-intensive applications are particularly affected. This tension — abundant resources but high latency — is what motivated the emergence of fog and edge computing paradigms.

Citation needed: Satyanarayanan (2017) — "The Emergence of Edge Computing," IEEE Computer. DOI: 10.1109/MC.2017.9. The authoritative voice on why edge exists. Not in your .bib.

Also: Shi et al. (2016) — "Edge Computing: Vision and Challenges," IEEE Internet of Things Journal. DOI: 10.1109/JIOT.2016.2579198. Not in your .bib.

These two together are the canonical pair. Satyanarayanan gives you the conceptual argument (distance = latency); Shi gives you the structured survey.

¶5 — Geo-Distributed Deployment Advantages

Deploying services across geo-distributed sites offers several advantages over centralized cloud
deployments. First, services deployed closer to users experience lower
round-trip time, directly benefiting latency-sensitive applications.
Second, processing data locally instead of traversing the core network
reduces backbone traffic and alleviates congestion on inter-domain links
\parencite{Cao2020OverviewEdgeComputingResearch,Satyanarayanan2017EmergenceEdgeComputing}.
For this thesis, both advantages are
directly relevant: latency drives the p95 and p99 metrics used to evaluate
service quality, and reduced backbone traffic connects to the data
locality trade-offs explored in the experimental workload (cross-region
reads, tiered data placement).

¶6 — Geo-Distributed Constraints: Resource Scarcity and Data Gravity

Geo-distributed deployments, however, face a different scarcity than hyperscale
clouds. Unlike cloud data centers where resources are conceptually
infinite, geo-distributed sites operate under finite per-site capacity
\parencite{Tao2019,Hong2019}. The binding constraint is not CPU or
memory exhaustion but network locality: scaling a service across sites
to absorb a demand surge forces requests and data to traverse the
wide-area link. This is a qualitatively different bottleneck
from CPU or memory exhaustion. When data has a home — when a content item
ingested at one site is requested by users of another — the orchestration
system must decide whether to serve the request remotely, paying WAN
latency on every access; to replicate the hot data subset locally, paying
synchronisation overhead; or to provision a full replica, paying storage
and replication cost \parencite{Qadir2020,Sonkoly2021}. These are not
stateless scale-out decisions; they are data-gravity-aware resource
allocation decisions, and they must be made under the time pressure of an
ongoing demand shift.

¶7 — Stateful Services in Geo-Distributed Deployments

The resource management problem is compounded when the services themselves
are stateful. Stateless microservices can be replicated freely — a new
instance absorbs traffic immediately. But many geo-distributed applications depend on
data co-located with compute. A content discovery platform, for instance,
ingests content items regionally and serves personalized feeds globally.
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
experience. This thesis uses a Multi-Region Content Discovery Platform
as its experimental workload: content items are ingested regionally and
discovered globally through tag-based personalized feeds, with
heterogeneous document types and two stress regimes — one driven by data
locality, the other by compute-analytics throughput.

¶8 — The Orchestration Problem: The Coordination Gap

In every major cloud and edge platform — Kubernetes, NFV MANO frameworks
such as OSM and ONAP, and MEC platforms — the functions that would need
to coordinate during a demand shift are implemented as separate components
with independent control loops. A monitoring system such as Prometheus or
InfluxDB scrapes metrics on a fixed interval. An auto-scaler such as the
Kubernetes HPA or the OSM Policy Manager evaluates thresholds and
provisions new instances. A load balancer — kube-proxy, HAProxy, or SDN
flow tables — eventually discovers the new backends and steers traffic to
them. Each handoff between these components adds latency: the monitoring
scrape interval, the alarm evaluation window, the provisioning time, and
the health-check discovery gap accumulate to 30–120 seconds of
coordination latency, even though the container itself boots in
approximately 10 seconds \parencite{PodolskiyIaaS}. The coordination gap
is not unique to geo-distributed deployments — Podolskiy et al.\ documented
it across AWS, Azure, and GCP — but its consequences are amplified where
resources are finite: cloud data centers mask the gap with
over-provisioning; resource-constrained sites cannot. This coordination gap
— the accumulated delay between overload onset and traffic reaching newly
provisioned capacity — has been documented in passing by Wang et al.\ in
their SDNFV 5G architecture \parencite{Wang2026AutoScalingLoadAwareSDNFV},
observed as a side effect by Pierro and Ullah in a Kubernetes HPA
evaluation \parencite{Pierro2026EvaluatingKubernetesAutoscalingStrategiesIoT},
and called for at the survey level by Yaseen
\parencite{Yaseen2025CountersTelemetrySurveyProgrammableNetwork} — but
never isolated, measured, or varied as an independent experimental
variable. No paper across the literature argues for this separation or
against co-location: it is the unexamined default.

¶9 — Central Claim and Honest Scope

This thesis experimentally examines three links in the detection→delivery→
action chain — trigger quality (what signals are monitored), telemetry
freshness (how fast those signals arrive), and backend selection (how
quickly new capacity receives traffic) — characterising how each
independently affects service quality during demand shifts in a stateful
service deployed across two geo-distributed sites. An SDN controller serves
as the experimental apparatus: by co-locating monitoring, routing, and
scaling in a single process with shared data structures, it eliminates
the propagation delays that confound separated architectures and enables
each link to be varied while the others are held constant. The thesis does
not claim that SDN is superior to Kubernetes or any specific orchestration
platform; does not claim that the coordination gap matters equally for all
workloads or at all deployment scales; and does not claim that the
mechanisms demonstrated — the Double-VIP traffic model, the MongoDB
replica-set tiering — generalise beyond the tested infrastructure. It
claims only that the coordination gap is a measurable, previously
uncharacterised phenomenon, and that varying each link independently
within a unified control point reveals which dimensions matter and under
what conditions.
