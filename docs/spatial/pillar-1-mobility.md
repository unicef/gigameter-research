## Pillar 1: Entity Geofencing & Mobility Trajectory Detection
### 1\. Why This Pillar Exists

In crowdsourced field telemetry, client monitoring software (the GigaMeter application) runs on hardware devices - such as laptops, tablets, desktop PCs, or smartphones - that are inherently susceptible to physical movement.

In real-world deployment scenarios:

*   Teachers or school staff frequently take laptops home during off-hours or weekends.

*   Hardware equipment is occasionally transferred between facilities or regional offices.

*   Users run speedtests while connected to mobile hotspots or in transit.

If telemetry from a roaming laptop is blindly assigned to a static school facility, speedtest results recorded at a teacher's home 50 kilometers away will pollute the connectivity baseline of the school building. Pillar 1 exists to evaluate hardware movement at the individual device level, separating fixed facility anchors from mobile or commuting hardware.

### 2\. Core Research Objectives

*   **Isolate Device Trajectories:** Track individual hardware instances (`device_id` / `browser_id`) across time and space using Density-Based Spatial Clustering (DBSCAN).

*   **Disambiguate Operational Context:** Differentiate between active school hours (08:00–19:59 local device time) and off-hour/weekend usage.

*   **Classify Hardware Mobility Taxonomy:** Categorize every registered monitoring device into one of four distinct behavioral states:

    1. `STATIONARY`: Dedicated fixed hardware permanently anchored to the facility campus.

    2. `COMMUTER`: Mobile device used at the facility during operational hours and taken home off-hours.

    3. `RELOCATED`: Equipment permanently transferred to another location after a specific date.

    4. `HIGH_MOBILITY`: Unanchored, roaming devices (e.g., field audit kits or staff smartphones).

### 3\. Key Analytical Mechanics

*   **Temporal Filtering:** Isolates pings and measurements recorded strictly within local device active operational hours (08:00–19:59).

*   **DBSCAN Clustering:** Converts coordinate pairs `(detected_latitude, detected_longitude)` into radians and applies DBSCAN with an 150m spatial radius threshold and min\_samples = 3 density requirement.

*   **Geofence Displacement Auditing:** Measures instantaneous Haversine displacement (D\_centroid) between individual test pings and the facility's empirical spatial anchor.