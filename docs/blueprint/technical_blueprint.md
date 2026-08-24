# Geofencing: Technical Blueprint & Research Methodology

**Version:** <span style="background-color: #677eff; color: white; padding: 3px 12px; border-radius: 8px; font-size: 0.9em; font-weight: 500; display: inline-block;">v0.2</span>

**Status:** <span style="background-color: #e91e63; color: white; padding: 3px 12px; border-radius: 8px; font-size: 0.9em; font-weight: 500; display: inline-block;">Hardening (exploring edge cases)</span>

**Maturity:** <span style="background-color: #2e8555; color: white; padding: 3px 12px; border-radius: 8px; font-size: 0.9em; font-weight: 500; display: inline-block;">Active Baseline</span>

## 1\. Objective
The primary objective of this framework is to replace static, self-reported administrative registries with spatially verified, crowdsourced field telemetry. By capturing background Wi-Fi BSSID environmental scans and high-frequency active speedtests via the GigaMeter application, the system dynamically calculates location truth, evaluates device mobility trajectories, and cross-validates official government administrative records.

### 1.1 The 3 Research Pillars Fall Under This Topis

| Pillar Name | Primary Input Data | Core Methodologies | Primary Output / Operational Value |
| ---| ---| ---| --- |
| Pillar 1: Entity Geofencing & Mobility | Time-series coordinates, `device_id`, timestamps | DBSCAN clustering (eps=150m), operational window (08:00–19:59) | Mobility classification (`STATIONARY`, `COMMUTER`, `RELOCATED`, `HIGH_MOBILITY`). |
| Pillar 2: Geolocation Quality & Confidence | Google API resolved lat/lon, accuracy, BSSIDs, SSIDs | Inverse-variance weighted centroids, 5-factor scoring model, BSSID Coherence Penalty | Unpenalized location score (S\_raw​), mobile hotspot tags, hardware health score. |
| Pillar 3: Government Data Validation | Empirical facility centroids, official government registry pins | Haversine displacement (D\_govt​), Two-Track Engine Architecture | Decoupled location verification flags (`VERIFIED_ACCURATE`, `GOVT_PIN_MISMATCH`, etc.). |

### 1.2 The Two-Track Engine Paradigm Shift
Earlier iterations of spatial validation utilized a single-flag cascade where severe hardware volatility (e.g., a laptop transported 200km between a school and a regional office) or high mobile hotspot usage forced the system into outputting a single flag such as `BSSID_SPATIAL_SPLIT`. This created an analytical paradox: even if the primary spatial cluster matched the official government registry pin perfectly (<= 30m), the single-flag system masked the verified physical building location under a hardware anomaly tag.

To eliminate this paradox, `v0.2` introduces the Two-Track Engine Architecture, cleanly decoupling two independent research dimensions:

1. **Track 1: Location Truth Engine (Pillar 3 Focus):** Evaluates the physical location of the brick-and-mortar facility against official government administrative records using the unpenalized spatial confidence score (S\_raw, 0–100) of the primary empirical cluster.
2. **Track 2: Hardware Integrity Engine (Pillars 1 & 2 Focus):** Evaluates device deployment permanence, mobile hotspot dependency, and spatial split anomalies (> 2km), applying a multiplicative BSSID Coherence Penalty (P\_coherence) to yield a dedicated `hardware_health_score` and decoupled `hardware_anomaly_tags`.

## 2\. 4-Layer Facility Location & Consolidation Architecture
### 2.1 Overview & Pillar Integration Mechanics
Raw crowdsourced telemetry contains significant spatial noise introduced by personal mobile tethering (teacher smartphones), staff commuter devices, and hardware relocations. To transform raw Wi-Fi BSSID environmental scans into an empirical location truth engine, processing is organised into a 4-Layer Consolidation Framework.

This 4-layer model directly operationalises our core research pillars:
*   Layer 1 executes Pillar 1 (`MobilityAnalyzer`) to isolate device-level mobility trajectories and extract primary operational clusters.
*   Layer 2 executes Pillar 2 (`SpatialProfiler`) to calculate accuracy-weighted empirical centroids across persistent fixed infrastructure.
*   Layer 3 executes the composite scoring engine inside `FacilityValidator` to measure hardware stability, multi-device spatial consensus, and BSSID coherence.
*   Layer 4 completes Pillars 1, 2 & 3 (`FacilityValidator`) by cross-validating empirical centroids against official government administrative coordinates to output decoupled primary location flags and secondary hardware anomaly tags.

### 2.2 Architectural Blueprint & Layer Progression

```mermaid
graph TD
    L1["<div style='width: 550px; text-align: left;'><b>LAYER 1: Device Trajectory Disambiguation (Pillar 1 Output)</b><br/>• Filter strictly for operational hours (08:00-19:59 local time)<br/>• Extract Cluster 0 (Primary) for Stationary & Commuter devices<br/>• Discard secondary residential clusters & relocated device points</div>"]
    
    L2["<div style='width: 550px; text-align: left;'><b>LAYER 2: Empirical Facility Centroid Engine (Pillar 2 Output)</b><br/>• Calculate Accuracy-Weighted Spatial Centroid across valid devices<br/>• Execute Strategy: TELEMETRY_DOMINANCE | GOVT_PROXIMITY | STATIONARY<br/>• Extract persistent 'Anchor BSSIDs' observed across multiple devices</div>"]
    
    L3["<div style='width: 550px; text-align: left;'><b>LAYER 3: Two-Track Engine Evaluation (Pillars 1, 2 & 3 Output)</b><br/>• Track 1: Location Confidence Score = S_raw (0 - 100 Unpenalized)<br/>• Track 2: Hardware Health Score = S_raw * P_coherence<br/>• Apply Multiplicative Coherence Penalty (P_coherence) for Splits >2km</div>"]
    
    L4["<div style='width: 550px; text-align: left;'><b>LAYER 4: Decoupled Taxonomy Output Engine</b><br/>• Track 1 Flag: VERIFIED_ACCURATE, GOVT_PIN_MISMATCH, etc.<br/>• Track 2 Tags: ['BSSID_SPATIAL_SPLIT'], ['HOTSPOT_TETHERED']</div>"]

    L1 --> L2
    L2 --> L3
    L3 --> L4
```

1. **SpatialProfiler answers:** _"Where is the physical building located?"_

2. **MobilityAnalyzer answers:** _"How are the individual devices moving relative to that building?"_

3. **FacilityValidator answers:** _"Can we verify the building location on government maps (Track 1), and how reliable is the installed monitoring hardware (Track 2)?"_

## 2.3 Processing Sequence & Module Dependency Chain
To ensure data integrity and prevent circular import issues in code execution, the pipeline components run in a strict, unidirectional dependency chain:

```mermaid
graph TD
    S1["<div style='min-width: 550px; text-align: left;'><b>[ Step 1: Pre-Processing & Timezone Enrichment ]</b><br/>• Maps UTC timestamps to local device time (08:00 - 19:59 window)</div>"]

    S2["<div style='min-width: 550px; text-align: left;'><b>[ Step 2: SpatialProfiler Execution (Pillar 2 Base) ]</b><br/>• Identifies & tags mobile tethering hotspots (SSID regex & drift > 1km)<br/>• Computes physical Empirical Facility Centroid via Strategy Mode</div>"]

    S3["<div style='min-width: 550px; text-align: left;'><b>[ Step 3: MobilityAnalyzer Execution (Pillar 1 Trajectory) ]</b><br/>• Computes instantaneous displacement (displacement_m) per ping<br/>• Runs DBSCAN clustering to categorize device mobility behavior</div>"]

    S4["<div style='min-width: 550px; text-align: left;'><b>[ Step 4: FacilityValidator Execution (Pillars 1, 2 & 3 Truth Engine) ]</b><br/>• Evaluates 5-Factor Raw Score & BSSID Coherence Penalty (P_coherence)<br/>• <b>Track 1:</b> Evaluates unpenalized centroid vs Govt Pin ➔ location_verification_flag<br/>• <b>Track 2:</b> Evaluates hardware health score & outputs hardware_anomaly_tags</div>"]

    S1 --> S2
    S2 -->|Passes Facility Centroid Anchor| S3
    S3 -->|Passes Device Mobility Classes & Clusters| S4
```

## 3\. Pillar 1: MobilityAnalyzer Blueprint & Logic
### 3.1 Overview & Trajectory Disambiguation
The `MobilityAnalyzer` module evaluates hardware movement trajectories at the individual `device_id` level. It utilizes DBSCAN (Density-Based Spatial Clustering of Applications with Noise) with a native Haversine metric to group geographic locations into spatial clusters without requiring a pre-defined cluster count.
#### Processing Passes:
*   **Pass 1: Mobile Hotspot & Drift Filtering**: Identifies personal mobile hotspots and tags high-volatility BSSIDs to prevent consumer phones from skewing hardware trajectory analysis.
*   **Pass 2: Density-Based Spatial Clustering (DBSCAN)**: Groups valid coordinate pairs per device using a spatial radius threshold (eps = 150 meters) and a minimum density threshold (min\_samples = 3).
*   **Pass 3: Temporal & Operational Disambiguation**: Evaluates scan distributions across clusters during active operational hours (08:00–19:59) vs. off-hours/weekends.
*   **Pass 4**: Behavioral Classification & Geofence Auditing: Classifies hardware behavior into four operational states: `STATIONARY`, `COMMUTER`, `RELOCATED`, or `HIGH_MOBILITY`.
### 3.2 Multi-Pass Device Mobility Engine Flowchart

```mermaid
graph TD
    IN["<div style='min-width: 550px; text-align: left;'><b>[ Input: Valid Device Telemetry Scans ]</b></div>"]

    P1["<div style='min-width: 550px; text-align: left;'><b>[ Pass 1: Mobile Hotspot & Drift Detection ]</b><br/>• Isolate fixed infrastructure scans from mobile tethering</div>"]

    P2["<div style='min-width: 550px; text-align: left;'><b>[ Pass 2: DBSCAN Spatial Clustering ]</b><br/>• Convert coordinates to Radians: (lat, lon) * (&pi; / 180)<br/>• Parameter: eps = 150m / 6371008.8m (Earth Radius)<br/>• Parameter: min_samples = 3<br/>• Output: Assign Cluster ID (0, 1, 2... or -1 for Noise)</div>"]

    P3["<div style='min-width: 550px; text-align: left;'><b>[ Pass 3: Temporal & Operational Disambiguation ]</b><br/>• Calculate Cluster 0 centroid (Primary Operational Cluster)<br/>• Measure geofence displacement (D_centroid) per ping<br/>• Evaluate timestamp sequence across secondary clusters</div>"]

    P4["<div style='min-width: 550px; text-align: left;'><b>[ Pass 4: Behavioral Classification Engine ]</b></div>"]

    %% Outcomes %%
    O1["<b>STATIONARY</b><br/>(Compliant Anchor)"]
    O2["<b>COMMUTER</b><br/>(Staff Personal)"]
    O3["<b>RELOCATED</b><br/>(Hardware Moved)"]
    O4["<b>HIGH_MOBILITY</b><br/>(Mobile Hotspot)"]

    %% Flow %%
    IN --> P1
    P1 --> P2
    P2 --> P3
    P3 --> P4

    %% Branching Logic %%
    P4 -->|1 Cluster &<br/>Compliant > 90%| O1
    P4 -->|2+ Clusters &<br/>Off-Hour Shift| O2
    P4 -->|2+ Clusters &<br/>Sequential Shift| O3
    P4 -->|Compliance < 50% /<br/>No Form| O4
```

## 3.3 Summary Comparison Table of Mobility Classes

| Mobility Class | Cluster Count (K) | Spatial Pattern | Temporal Behavior | Real-World Operational Context |
| ---| ---| ---| ---| --- |
| `STATIONARY` | 1 Primary Cluster | Tight spatial anchor (<=150m - 200m) | High compliance (>= 90%) across all days and hours | Dedicated, fixed desktop or router monitoring hardware anchored to the school building. |
| `COMMUTER` | 2+ Clusters | Alternates between Cluster 0 (School) and Cluster 1+ (Home/Off-site) | Cluster 0 during active hours (08:00–19:59); Cluster 1 off-hours and weekends | Mobile laptop or tablet owned by a teacher/staff member who brings it to work and takes it home. |
| `RELOCATED` | 2+ Clusters | Permanent geographic shift from Cluster A to Cluster B | Strictly Cluster A before Date T; strictly Cluster B after Date T | Equipment permanently transferred to another facility, stolen, or school physically relocated. |
| `HIGH_MOBILITY` | Many / Noise | Low geofence compliance (< 50%) or scattered spatial points | Volatile across days and operational hours | Roaming mobile hotspot, staff personal smartphone, or field audit kit. |

## 4\. Pillar 2: SpatialProfiler Blueprint & Logic
### 4.1 Overview & Data Ingestion Rules
The `SpatialProfiler` module serves as the **foundational spatial processing engine**. It ingests raw telemetry measurements, standardizes facility identifiers (`school_id_giga`), enriches records with local device timestamps, and tags consumer mobile hotspots, and resolves empirical facility centroids using configurable strategy modes.
#### Processing Rules:
1. **Strict No-IP Fallback Policy:** The profiler strictly discards records where `detected_latitude` or `detected_longitude` is `null`. IP-based geolocation fallback is never applied.
2. **Operational Window Isolation:** Time-series telemetry is filtered strictly between 08:00:00 and 19:59:59 local device time (`is_operational_hours = True`) to prevent nighttime or off-hour device transport from skewing facility locations.
3. **Consumer Hotspot & Drift Engine:**
    1. **SSID Regex Pattern Matching:** Passive and active SSIDs are evaluated against a consumer hotspot pattern:
        1. Pattern = (?i)(iphone\\android\\galaxy\\hotspot\\teacher\\pixel\\redmi\\tether\\samsung\\huawei\\oppo\\vivo\\xiaomi\\realme\\mobicom\\unitel\\mifi)
    2. **Multi-Day Spatial Drift Check:** BSSIDs displaying multi-day spatial drift exceeding 1000m across different dates are tagged as `is_hotspot_drift = True`.
4. **Candidate BSSID Spatial Clustering & Spatial Splits:**
    *   Pairwise distances (D\_bssid) between BSSID centroids are calculated.
    *   D\_bssid <= 200m → Merged & averaged (same physical campus/building).
    *   200m < D\_bssid \\<= 2000m → Retained as minor campus dispersion.
    *   D\_bssid > 2000m → Triggers `BSSID_SPATIAL_SPLIT` anomaly tag.

### 4.2 Configurable Primary Cluster Resolution Strategies

To address BSSID splits (> 2km) without introducing analytical bias, `SpatialProfiler` supports three configurable resolution modes:

*   **Mode 1:** `GOVT_PROXIMITY_ANCHOR` **(Prior-Informed Default):** If a BSSID split occurs, the engine checks if any candidate cluster centroid is <= 2000m from official government coordinates (phi\_govt, lambda\_govt). If candidate clusters exist near the government pin, it selects the cluster with the highest operational scan density among them.

*   **Mode 2:** `TELEMETRY_DOMINANCE` **(Unbiased Field Benchmark):** Evaluates spatial data strictly based on scan volume during active operational hours (08:00–19:59), ignoring government coordinates entirely. Ideal for Pillar 3 auditing without circular reasoning.

*   **Mode 3:** `STATIONARY_FIRST` **(Hardware-First Mode):** Filters candidate clusters for scans originating strictly from devices classified as `STATIONARY` before computing the facility centroid.

### 4.3 Spatial Profiling & Aggregation Engine Flowchart

```mermaid
graph TD
    %% Linear Filters
    IN["<div style='min-width: 500px; text-align: left;'><b>[ Raw Telemetry Ingestion ]</b><br/>• Raw measurements & pings</div>"]
    F1["<div style='min-width: 500px; text-align: left;'><b>[ Filter: App Version & Source ]</b><br/>• App Version &ge; 2.0.2 & source = 'DailyCheckApp'</div>"]
    F2["<div style='min-width: 500px; text-align: left;'><b>[ Temporal Standardization ]</b><br/>• UTC &rarr; Local Device Timestamp</div>"]
    F3["<div style='min-width: 500px; text-align: left;'><b>[ Operational Window Filter ]</b><br/>• 08:00 to 19:59 Local Time</div>"]
    F4["<div style='min-width: 500px; text-align: left;'><b>[ Strict No-IP Filter ]</b><br/>• Drop if detected_latitude IS NULL</div>"]

    %% Hotspot Detection
    HS["<div style='min-width: 500px; text-align: left;'><b>[ Mobile Hotspot & Drift Engine ]</b><br/>• Regex Match: SSID matches consumer hotspot patterns?<br/>• Spatial Drift: BSSID moves > 1000m across days?</div>"]
    
    HS_YES["Tag: is_mobile_hotspot = True"]
    HS_NO["Tag: is_mobile_hotspot = False"]

    %% Clustering
    CL["<div style='min-width: 500px; text-align: left;'><b>[ Candidate BSSID Spatial Clustering ]</b><br/>• Group scans by BSSID & calculate inverse-variance weighted centroids<br/>• Measure pairwise distance between BSSID centroids (max_bssid_dist_m)</div>"]

    %% Distance Branches
    C1["Merge & Average<br/><i>(Same Campus)</i>"]
    C2["Tag: CAMPUS_DISPERSION"]
    C3["Trigger: BSSID_SPATIAL_SPLIT"]

    %% Strategy Engine
    ST["<div style='min-width: 500px; text-align: left;'><b>[ Configurable Strategy Resolution Engine ]</b><br/>• <b>GOVT_PROXIMITY_ANCHOR:</b> Select cluster &le; 2km from Govt Pin<br/>• <b>TELEMETRY_DOMINANCE:</b> Select cluster with max operational scans<br/>• <b>STATIONARY_FIRST:</b> Select cluster from stationary devices</div>"]

    %% Output
    EXP["<div style='min-width: 500px; text-align: left;'><b>[ Export ]</b><br/>• Empirical Facility Centroid & BSSID Infrastructure Profiles</div>"]

    %% Connections
    IN --> F1 --> F2 --> F3 --> F4 --> HS
    
    HS -->|Yes| HS_YES
    HS -->|No| HS_NO
    
    HS_YES --> CL
    HS_NO --> CL

    CL -->|dist &le; 200m| C1
    CL -->|200m < dist &le; 2km| C2
    CL -->|dist > 2km| C3

    C1 --> ST
    C2 --> ST
    C3 --> ST

    ST --> EXP
```

##   

## 5\. Pillar 3 & 4: FacilityValidator & Two-Track Engine Mechanics
### 5.1 Overview & Two-Track Engine Logic
The `FacilityValidator` module consolidates multi-device spatial clusters into a Two-Track Validation Engine. It bridges empirical field telemetry with administrative metadata to evaluate two independent tracks: Location Truth (Pillar 3) and Hardware Health (Pillars 1 & 2).
### 5.2 Comprehensive 5-Factor Score Component Breakdown
The raw spatial confidence score (S\_raw, 0–100) evaluates five distinct spatial and operational dimensions of the primary empirical cluster:

$$S_{\text{raw}} = S_{\text{stability}} + S_{\text{consensus}} + S_{\text{bssid}} + S_{\text{depth}} + S_{\text{precision}}$$

| Component Name | Max Points | Tracked Inputs & Metrics | Mathematical Logic & Evaluation Rules | Operational Impact & Thresholds |
| ---| ---| ---| ---| --- |
| 1\. Device Stability Profile (S\_stability) | 30 pts | Categorical mobility class of all devices registered to facility (`STATIONARY`, `COMMUTER`, `RELOCATED`, `HIGH_MOBILITY`). | `if STATIONARY in devices: score = 30.0`<br><br>`elif COMMUTER in devices: score = 20.0`<br><br>`else: score = 10.0`<br> | Evaluates hardware permanence. Awarded 30 points if at least one stationary device anchors the building. |
| 2\. Multi-Device Spatial Consensus (S\_consensus) | 25 pts | Maximum pairwise Haversine distance (d\_max in meters) between primary cluster centroids across multiple devices. | `if d_max <= 30: score = 25.0`<br><br>`elif 30 < d_max <= 200:`<br><br>`score = 25.0 * (1.0 - (d_max - 30) / 170.0)`<br><br>`else: score = 0.0`<br><br>(Single-device default = 12.5 pts)<br> | Evaluates whether distinct hardware devices agree on facility location. d\_max > 200m indicates conflicting hardware setups. |
| 3\. BSSID Infrastructure Persistence (S\_bssid) | 20 pts | Presence of fixed, non-null BSSIDs and active operational days recorded with valid BSSIDs. | `if bssid_exists and days_active >= 3:`<br><br>`score = 20.0`<br><br>`else: score = 10.0`<br> | Rewards persistent Wi-Fi router infrastructure. Ambient background scans without associated BSSIDs receive 10 points. |
| 4\. Data Temporal Depth (S\_depth) | 15 pts | Count of unique operational days recorded in the observation window. | `score = min(15.0, 15.0 * (days_active / 10.0))`<br> | Scales linearly up to 10 active days. Reaching 10+ operational days awards the full 15 points. |
| 5\. API Precision Radius (S\_precision) | 10 pts | Mean reported Google Geolocation API accuracy radius (mean\_acc in meters). | `score = max(0.0, 10.0 * (1.0 - (mean_acc - 10) / 90.0))`<br> | Evaluates precision returned by Google API. mean\_acc <= 10m receives 10 points; mean\_acc >= 100m receives 0 points. |

### 5.3 BSSID Coherence Penalty Factor (P\_coherence)
The BSSID Coherence Penalty measures spatial agreement across all BSSIDs associated with a facility (D\_bssid\_max in meters). It is applied strictly to Track 2 (Hardware Health) to penalize roaming hardware without degrading Track 1 (Location Truth):

$$P_{\text{coherence}} = 
\begin{cases} 
1.0, & \text{if } D_{\text{bssid_max}} \le 1000\text{m } \text{(Tight Alignment)} \\[1ex]
1.0 - 0.5 \times \left( \frac{D_{\text{bssid_max}} - 1000}{1000} \right), & \text{if } 1000\text{m} < D_{\text{bssid_max}} \le 2000\text{m} \\[1ex]
0.1, & \text{if } D_{\text{bssid_max}} > 2000\text{m } \text{(Severe BSSID Split)}
\end{cases}$$

$$\text{Track 1 (Location Confidence Score)} = S_{\text{raw}}$$

$$\text{Track 2 (Hardware Health Score)} = S_{\text{raw}} \times P_{\text{coherence}}$$

## 6\. Two-Track Decoupled Taxonomy Engine Flowchart
The parallel evaluation flowchart demonstrates how Track 1 (Location Truth) and Track 2 (Hardware Integrity) execute independently:

```mermaid
graph TD
    IN["<div style='min-width: 300px; text-align: center;'><b>[ Facility Telemetry Input ]</b></div>"]

    IN --> T1
    IN --> T2

    subgraph Track1 ["TRACK 1: LOCATION TRUTH ENGINE"]
        T1["<b>TRACK 1: LOCATION TRUTH ENGINE</b><br/><i>(Evaluates Dominant Empirical Cluster)</i>"]
        S_RAW["Calculate Raw Score (S_raw)"]
        PIN_CHECK{"Govt Registry Pin<br/>Available?"}
        
        %% Decisions
        C1{"Score &ge; 70 &<br/>D_govt &le; 200m?"}
        C2{"Score &ge; 70 &<br/>D_govt > 500m?"}
        C3{"Score &ge; 60 &<br/>200m < D_govt &le; 500m?"}
        C4{"Score < 50?"}

        %% Output Flags
        F_NO_PIN["<b>NO_GOVT_PIN_AVAILABLE</b>"]
        F_ACC["<b>VERIFIED_ACCURATE</b>"]
        F_MIS["<b>GOVT_PIN_MISMATCH</b>"]
        F_DIS["<b>CAMPUS_DISPERSION</b>"]
        F_UNS["<b>UNSTABLE_MOBILE_ONLY</b>"]
        F_MIN["<b>MINOR_DISCREPANCY</b>"]

        T1 --> S_RAW --> PIN_CHECK
        PIN_CHECK -->|NO| F_NO_PIN
        PIN_CHECK -->|YES| C1
        
        C1 -->|YES| F_ACC
        C1 -->|NO| C2
        
        C2 -->|YES| F_MIS
        C2 -->|NO| C3
        
        C3 -->|YES| F_DIS
        C3 -->|NO| C4
        
        C4 -->|YES| F_UNS
        C4 -->|NO| F_MIN
    end

    subgraph Track2 ["TRACK 2: HARDWARE INTEGRITY ENGINE"]
        T2["<b>TRACK 2: HARDWARE INTEGRITY ENGINE</b><br/><i>(Evaluates Device & BSSID Reliability)</i>"]
        P_COH["Calculate BSSID Coherence Penalty<br/>(P_coherence)"]
        H_SCORE["Hardware Health Score = S_raw * P_coherence"]
        
        ANOM["<b>Evaluates Hardware Anomalies:</b><br/>• D_bssid_max > 2km? &rarr; Tag: <code>BSSID_SPATIAL_SPLIT</code><br/>• Hotspot Scans &ge; 50%? &rarr; Tag: <code>HOTSPOT_TETHERED_FACILITY</code>"]
        
        OUT_TAGS["<b>Output List:</b><br/><code>hardware_anomaly_tags</code>"]

        T2 --> P_COH --> H_SCORE --> ANOM --> OUT_TAGS
    end
```

## 7\. Decoupled Taxonomy Output Matrix
### 7.1 Track 1: Primary Location Verification Flags (Pillar 3)

| Location Flag | Trigger Conditions | Real-World Operational Interpretation | Recommended Action |
| ---| ---| ---| --- |
| `VERIFIED_ACCURATE` | S\_raw >= 70.0 AND D\_govt <= 200m | Field telemetry confirms official government registry coordinates. High-confidence baseline established. | None. Facility baseline verified. |
| `GOVT_PIN_MISMATCH` | S\_raw >= 70.0 AND D\_govt > 500m | Empirical telemetry is spatially stable, but government coordinates are significantly inaccurate (e.g., pinned to village center or district office). | Submit spatial coordinate correction to Ministry. |
| `CAMPUS_DISPERSION` | S\_raw >= 60.0 AND 200m < D\_govt <= 500m | Telemetry confirms presence near the government pin, but spatial spread reflects a large multi-building campus, sports field, or peripheral annex. | Retain location as valid; flag for minor boundary refinement. |
| `UNSTABLE_MOBILE_ONLY` | S\_raw < 50.0 | Telemetry is too sparse or spatially volatile to guarantee physical building coordinates. | Needs fixed monitoring hardware. |
| `NO_GOVT_PIN_AVAILABLE` | Official Govt Coordinates missing/null | Empirical centroid calculated successfully, but no government metadata exists for comparison. | Append empirical centroid to registry. |
| `INSUFFICIENT_DATA` | Total valid spatial scans < 5 in the observation window | Fewer than 5 valid spatial scans recorded in the observation window. | Await additional telemetry syncs. |

### 7.2 Track 2: Secondary Hardware Anomaly Tags (Pillars 1 & 2)

| Anomaly Tag | Trigger Conditions | Real-World Operational Interpretation | Recommended Action |
| ---| ---| ---| --- |
| `BSSID_SPATIAL_SPLIT` | Max pairwise BSSID distance D\_bssid\_max > 2000m (2km) | Hardware monitoring devices registered to this facility operate across two or more distinct geographic locations (e.g., laptop transported between school and regional office). | Flag monitoring setup as mobile. Dedicated fixed hardware missing at the school. |
| `HOTSPOT_TETHERED_FACILITY` | Active Wi-Fi scans matching consumer hotspot patterns or multi-day drift > 1km are >= 50% | Entity relies primarily on staff personal smartphones or mobile hotspots for connectivity rather than fixed ISP infrastructure. | Flag connectivity as temporary/mobile tethered. Exclude mobile SSIDs from building checks. |

## 8\. Summary of Research Data Dictionary Rules
*   **Measurement Source Filtering:** Raw measurement payloads use `source = 'DailyCheckApp'` in the database. Data is filtered on this field for app-specific speedtest analysis.
*   **Timezone Standardization:** Raw UTC timestamps (`created_timestamp`) always converted to local device time before executing operational hour (08:00–19:59) models.
*   **Strict No-IP Fallback Policy:** IP-based geolocation is never used by GigaMeter. Always filter out null coordinates (`WHERE detected_latitude IS NOT NULL`) before spatial calculations. IP fallback imputation NEVER been attempted.