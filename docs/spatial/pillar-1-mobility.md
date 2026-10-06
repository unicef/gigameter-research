## Pillar 1: Entity Geofencing & Mobility Trajectory Detection

!!! note "v0.3 draft"
    This page describes the v0.3 design. Code still implements v0.2. Settings are on the [Parameters](../blueprint/parameters.md) page.

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

    2. `COMMUTER`: Two or more supported clusters visited in alternation across days.

    3. `RELOCATED`: Two or more supported clusters in sequence.

    4. `HIGH_MOBILITY`: No supported cluster, or too much noise.

### 3\. Key Analytical Mechanics

*   **Fix Events:** Rows are collapsed into fix events. Carried fixes (coordinates repeated under a different network) are excluded. See [Blueprint Section 2](../blueprint/technical_blueprint.md#2-evidence-unit-fix-events).

*   **DBSCAN Clustering:** Haversine DBSCAN on fix events with `device_eps_m` and `device_min_samples`.

*   **Supported Clusters:** A cluster counts only when it spans at least `min_cluster_device_days` days. Single-day excursions become noise.

*   **Dominant Cluster:** The cluster with the most support. Cluster labels such as `0` carry no meaning.

*   **Geofence Audit:** After the facility anchor is chosen (Pillar 2), each device's displacement from the anchor is reported as an audit. It no longer feeds classification.
