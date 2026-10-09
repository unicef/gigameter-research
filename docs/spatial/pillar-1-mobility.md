## Pillar 1: Entity Geofencing & Mobility Trajectory Detection

!!! note "v0.3"
    This page describes the v0.3 methodology, which the `MobilityAnalyzer` code implements. Settings are on the [Parameters](../blueprint/parameters.md) page.

### 1\. Why This Pillar Exists

In crowdsourced field telemetry, client monitoring software (the GigaMeter application) runs on hardware devices - such as laptops, tablets, desktop PCs, or smartphones - that are inherently susceptible to physical movement.

In real-world deployment scenarios:

*   Teachers or school staff frequently take laptops home during off-hours or weekends.

*   Hardware equipment is occasionally transferred between facilities or regional offices.

*   Users run speedtests while connected to mobile hotspots or in transit.

If telemetry from a roaming laptop is blindly assigned to a static school facility, speedtest results recorded at a teacher's home 50 kilometers away will pollute the connectivity baseline of the school building. Pillar 1 evaluates hardware movement at the individual device level, separating fixed facility anchors from mobile or commuting hardware.

### 2\. Core Research Objectives

*   **Isolate Device Trajectories:** Track individual hardware instances (`device_id` / `browser_id`) across time and space using DBSCAN on fix events.

*   **Classify Without a Facility Prior:** A device is classified from its own clusters and dates. It does not depend on the facility centroid, so a wrong centroid cannot make every device look mobile.

*   **Separate Class From Evidence:** Every device reports a mobility class and, separately, `evidence_device_days`.

*   **Classify Hardware Mobility Taxonomy:**

    1. `STATIONARY`: One supported cluster with a low noise share.

    2. `COMMUTER`: Two or more supported clusters, with the device switching between them at least `commuter_min_alternations` times.

    3. `RELOCATED`: Two or more supported clusters with fewer switches, meaning the device moved and stayed.

    4. `HIGH_MOBILITY`: Enough evidence, but no supported cluster, or too much noise.

    5. `INSUFFICIENT_EVIDENCE`: Too few fix events, or fix events on a single day, so no cluster could be supported. Checked first, so a device seen once is not called mobile.

### 3\. Key Analytical Mechanics

*   **Fix Events:** Rows are collapsed into fix events. Carried fixes (coordinates repeated under a different network) are excluded. See [Blueprint Section 2](../blueprint/technical_blueprint.md#2-evidence-unit-fix-events).

*   **DBSCAN Clustering:** Haversine DBSCAN on fix events with `device_eps_m` and `device_min_samples`.

*   **Supported Clusters:** A cluster counts only when it spans at least `min_cluster_device_days` days. Single-day excursions become noise.

*   **Dominant Cluster:** The cluster with the most support. Cluster labels such as `0` carry no meaning.

*   **Geofence Audit:** Each device's displacement from a reference point is reported as an audit and never feeds classification. The reference is the facility anchor (Pillar 2) when known, otherwise the device's dominant cluster; `reference_source` says which. See [Blueprint Section 4.3](../blueprint/technical_blueprint.md#43-geofence-audit).
