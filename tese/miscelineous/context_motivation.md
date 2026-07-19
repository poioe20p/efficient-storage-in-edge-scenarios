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

¶5 — Edge Advantages
Job: Present the three core advantages of edge computing. (1) Low latency: services deployed closer to users, shorter RTT. (2) High bandwidth availability / reduced backbone traffic: data processed locally instead of traversing the core network, alleviating congestion on inter-domain links. (3) Context awareness / location awareness: edge nodes can leverage local environmental information that a distant cloud cannot access. For your thesis, advantages (1) and (2) are the most relevant — latency drives your p95/p99 metrics, and reduced backbone traffic connects to your data locality story (cross-region reads, Tier 1/2 data placement).

Citation: Shi et al. (2016) and/or Mao et al. (2017) — "A Survey on Mobile Edge Computing," IEEE Communications Surveys & Tutorials. DOI: 10.1109/COMST.2017.2937873. Not in your .bib. Mao is more comprehensive on the advantages taxonomy.

¶6 — Edge Constraints: The Resource Scarcity Problem
Job: The flip side. Unlike the cloud, edge environments are resource-constrained — limited CPU, memory, storage, and power per node. Edge infrastructure is heterogeneous (different hardware across sites), variable (demand fluctuates), and distributed (many small sites rather than few large data centers). These constraints mean that resource efficiency is not optional — edge platforms must allocate resources judiciously, scaling only when justified by demand. This sets up the entire motivation for your thesis: how do you orchestrate resources efficiently at the edge?

Citation: Khan et al. (2019) — "Edge computing: A survey," Future Generation Computer Systems. DOI: 10.1016/j.future.2019.02.050. Good on resource constraints. Not in your .bib. Alternatively, Shi et al. (2016) already covers constraints — you could cite the same paper as ¶5 for consistency.

¶7 — Stateful Services: The Harder Problem
Job: This is the bridge paragraph — the most important one you're missing. Many edge services are not stateless microservices that can be freely replicated. They are stateful — they depend on data co-located with compute. A content discovery platform, for instance, serves personalized feeds built from content items stored across regions; the data has gravity — it pulls computation toward where it resides. This makes resource management fundamentally different from the stateless cloud pattern: you cannot simply spin up a new instance anywhere; you must consider where the data lives, how fresh it is, and how much data to replicate locally. Introduce the Multi-Region Content Discovery Platform here as the representative workload: content items ingested regionally, discovered globally through tag-based personalized feeds, with heterogeneous document types and two stress regimes (data-locality and compute-analytics).

Citation: None strictly needed — this is conceptual framing. But you could cite Breitbach et al. (2019) — "Context-Aware Data and Task Placement in Edge Computing Environments" — which is already in your .bib and studies n-replication data placement (mirroring Tier 0→1→2).

¶8 — The Orchestration Problem: The Coordination Gap
Job: Now introduce the coordination gap. In every major edge/cloud platform — Kubernetes, NFV MANO (OSM, ONAP), MEC platforms — three critical functions are handled by separate components: monitoring (Prometheus/InfluxDB), traffic routing (kube-proxy/SDN switches), and auto-scaling (HPA/OSM LCM). Each component operates on its own control loop with its own reconciliation interval and no shared state. The accumulation of these independent delays creates a coordination gap: the time between overload onset and traffic reaching newly provisioned capacity can reach 30–120 seconds, even though the container itself boots in ~10 seconds (Podolskiy et al.). This separation is the unexamined default — no paper across the literature argues for or against it. It has been documented (Wang et al., SDNFV architecture), observed as a side effect (Pierro & Ullah, K8s HPA evaluation), and called for (Yaseen, 2025) — but never isolated, measured, or varied as an independent experimental variable.

Citations: Wang2026AutoScalingLoadAwareSDNFV ✅ in .bib | Pierro2026EvaluatingKubernetesAutoscalingStrategiesIoT ✅ in .bib | Yaseen2025CountersTelemetrySurveyProgrammableNetwork ✅ in .bib | Podolskiy et al. ❌ missing from .bib — I need to find the DOI for this one. It's the IaaS provider latency measurement paper cited in the global lit review.

¶9 — Central Claim, Honest Scope, and What This Thesis Does
Job: Close the section with a clear thesis statement. "This thesis experimentally examines three links in the detection→delivery→action chain — trigger quality, telemetry freshness, and backend selection — characterizing how each independently affects service quality during demand shifts in stateful edge services." The SDN controller is the experimental apparatus, not the hypothesis. Then add the honest scope: does not claim SDN superiority over Kubernetes; does not claim scalability to large deployments; does not claim generalizability beyond MongoDB replica sets. This preempts the "you didn't compare against X" critique.

Citation: None — this is your claim.
