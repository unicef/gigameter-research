## Pillar 2: Geolocation Quality, BSSID Fingerprinting & Confidence Scoring

!!! note "v0.3 draft"
    This page describes the v0.3 design. `SpatialProfiler` implements the anchor selection; the scores below are still computed by the v0.2 `FacilityValidator`. Settings are on the [Parameters](../blueprint/parameters.md) page.

### 1\. Why This Pillar Exists

Crowdsourced Wi-Fi location resolution depends on environmental scans submitted to Google's Geolocation API. Field environments present significant spatial noise:

*   Facilities in rural areas may scan only 1 or 2 nearby Wi-Fi routers, yielding lower precision radii.

*   Staff frequently use consumer mobile hotspots (e.g., `"iPhone"`, `"Galaxy A15"`), which move across days.

*   Devices are carried between the facility and other places, so one facility's telemetry can describe several locations.

*   Consecutive rows often repeat the same coordinates, sometimes under a different network than the one that produced them.

GigaMeter operates under a Strict No-IP Policy. If Wi-Fi geolocation fails, coordinates stay `NULL`. Pillar 2 selects the observed location that represents the facility, quantifies confidence in it (0–100), and detects mobile tethering.

### 2\. Core Research Objectives

*   **Fix Events as Evidence:** Count support in fix events and device-days, never raw rows.

*   **BSSID Mobility Detection:** Flag a network as mobile when its own accurate, non-carried fixes form two or more supported clusters.

*   **Facility Observation Clusters:** Cluster all anchor-window fix events, including events without a BSSID, and select exactly one cluster as the facility anchor.

*   **No Averaging Across Clusters:** A facility coordinate is always computed inside one cluster.

*   **Strategy Agreement:** Run govt proximity and telemetry dominance, report whether they agree, and resolve disagreement only by a registry name match.

*   **BSSID Coherence Penalty (P\_coherence):** Scale down hardware health when supported clusters are far apart.

### 3\. Key Analytical Mechanics

*   **Accuracy-Weighted Centroid** (one weight per fix event, inside the anchor cluster):

$$w_i = \frac{1}{\max(A_i, A_{\text{floor}})^2}$$

$$\bar{\phi} = \frac{\sum (w_i \cdot \phi_i)}{\sum w_i}, \quad \bar{\lambda} = \frac{\sum (w_i \cdot \lambda_i)}{\sum w_i}$$

*   **5-Factor Composite Score (S\_raw, 0–100),** computed on the anchor cluster:

$$S_{\text{raw}} = \underbrace{S_{\text{stability}}}_{\text{30 pt}} + \underbrace{S_{\text{consensus}}}_{\text{25 pt}} + \underbrace{S_{\text{bssid}}}_{\text{20 pt}} + \underbrace{S_{\text{depth}}}_{\text{15 pt}} + \underbrace{S_{\text{precision}}}_{\text{10 pt}}$$

*   **Coherence Multiplier (P\_coherence),** where $D_{\text{split}}$ is the maximum distance between supported facility clusters:

$$P_{\text{coherence}} = 
\begin{cases} 
1.0, & \text{if } D_{\text{split}} \le 1000\text{m} \\[1ex]
1.0 - 0.5 \times \left( \frac{D_{\text{split}} - 1000}{1000} \right), & \text{if } 1000\text{m} < D_{\text{split}} \le 2000\text{m} \\[1ex]
0.1, & \text{if } D_{\text{split}} > 2000\text{m}
\end{cases}$$

Full rules are in [Blueprint Section 5](../blueprint/technical_blueprint.md#5-pillar-2-spatialprofiler-logic).
