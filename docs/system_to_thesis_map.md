Here is exactly how your **Three-Tier Architecture**, **Joint Placement Algorithm**, and **Self-Hydrating Containers** map to the academic promises you made in the **Enquadramento** and **Objectivos**.

---

### 1. Mapping to "Enquadramento" (The Context & Problem)

**The Prompt:** *"Flexible data storage systems capable of handling... access frequency or spatio-temporal usage patterns, have become critical. However, coordinating the auto-scaling of services based on such meta-information remains a complex... challenge."*

**Your Solution:**
You are solving this "complex challenge" by treating **Access Frequency** and **Spatio-Temporal Patterns** as the primary inputs for your **Tiered Storage Logic**.

* **"Spatio-Temporal Patterns":**
  * *Theory:* You need to know *where* (Space) and *when* (Time) data is needed.
  * *Your System:* The SDN Controller maps the **Space** (Network Topology/User Location). The MongoDB TTL Index maps the **Time** (Data is deleted after $N$ seconds).
* **"Access Frequency":**
  * *Theory:* You need to scale based on popularity.
  * *Your System:* The **Hit-Count Logic** inside the Edge Container. If `hit_count > threshold`, the system "promotes" the data from Tier 1 (Cache) to Tier 2 (Replica).
* **"Unresolved Challenge":**
  * *Theory:* Auto-scaling is hard to coordinate.
  * *Your System:* You resolved this by **coupling** the Service (App) and Data (Mongo). You don't scale them separately; the **Joint Placement Algorithm** ensures they always move together.

---

### 2. Mapping to "Specific Goals" (The Objectives)

Here is how your technical decisions fulfill the numbered objectives in your PDF:

#### Objective 2: "To design a programmable system architecture that supports dynamic scaling... based on spatio-temporal data popularity."

* **How you fulfill it:** You designed the **Multi-Dimensional Vector Bin Packing (MDVBP)** algorithm.
  * *Programmable:* The logic isn't hard-coded in hardware; it's Python code in the Ryu Controller.
  * *Dynamic Scaling:* The system automatically moves from Tier 0 $\to$ Tier 1 $\to$ Tier 2.
  * *Spatio-Temporal:* The placement decision is based on **Network Distance (Spatio)** and **TTL/Freshness (Temporal)**.

#### Objective 3: "To implement a functional prototype that integrates containerized services with adaptive, metadata-informed resource management."

* **How you fulfill it:** This is the **Self-Hydrating Container** (`sync.py` + `mongod`).
  * *Containerized Services:* You are using Docker.
  * *Adaptive:* The container "hydrates" itself based on environment variables.
  * *Metadata-Informed:* The "Metadata" is the **Hit Count**. The container adapts its retention policy (TTL) based on how often the data is accessed.

#### Objective 5: "To evaluate... efficiency on resource usage."

* **How you fulfill it:** This is the **Tier 1 (Ephemeral) Strategy**.
  * *The Argument:* A standard solution would replicate the *entire* database to the edge (Tier 2). That wastes storage.
  * *Your Efficiency:* Your system uses **Tier 1** first. It only consumes storage for the exact documents users are asking for. This is mathematically more efficient than full replication.

---

### 3. Mapping to "Activities" (Phase 2 & 3)

#### Phase 2.1: "Design a system architecture that integrates programmable control... and container-based resource abstraction."

* **Correspondence:** Your use of **SDN (Programmable Control)** to route traffic to **Docker (Resource Abstraction)**.
* *Key Detail:* The `entrypoint.sh` script in your container *is* the abstraction. The controller doesn't need to know how Mongo works; it just spins up the abstraction.

#### Phase 2.2: "Specify... decision-making algorithms, especially for handling spatio-temporal metadata."

* **Correspondence:** This is the **Hit-Count + TTL Algorithm**.
  * *Decision:* "Should I keep this document?"
  * *Algorithm:* `New_TTL = Current_Time + (Base_Time * Hit_Count)`.
  * This simple formula *is* the decision-making algorithm that handles the temporal metadata.

#### Phase 3.3: "Use a document-oriented database to manage and query data... supporting realistic edge data use cases."

* **Correspondence:** Your choice of **MongoDB**.
* *Why:* You aren't just storing Key-Values (like Redis). You are storing **Documents** (JSON). This allows the edge service (Port 5002) to perform "Querying" (filtering/rendering) at the edge, which supports "Realistic Use Cases" (like User Profiles or IoT Dashboards) rather than just static image serving.

---

### 4. The "Killer Argument" for Your Thesis Defense

When the jury asks: *"How exactly does your system improve over existing edge caching?"*

**You say:**

> "Existing systems largely rely on static caching or full database replication.
>
> My thesis fulfills the requirement for **'Efficiency'** by introducing a **Programmable Tier 1 (Ephemeral) Layer**. Instead of blindly replicating terabytes of data (Tier 2), my system utilizes **metadata-driven containers** that 'self-hydrate' using Change Streams.
>
> It fulfills the requirement for **'Spatio-Temporal Awareness'** by placing these containers physically close to the user (Spatio) and programmatically adjusting their data retention based on real-time Hit Counts (Temporal).
>
> This creates a system that is **lightweight by default** (Tier 1) but **scalable by design** (Tier 2), directly addressing the 'unresolved challenge' of coordinating auto-scaling with data patterns."

### Conclusion

Your technical architecture (The 3-Tier Lifecycle + Self-Hydrating Containers) is a **perfect fit**. It doesn't just "do the job"; it provides a specific, novel mechanism (The Programmable Tier 1) that directly answers the efficiency and metadata challenges posed in your proposal.
