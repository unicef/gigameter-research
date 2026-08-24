## Pillar 4: Outage Classification, Connectivity Modeling & 4-State Telemetry

### 1\. Why This Pillar Exists

Determining whether an entity is "online" or "offline" is a non-trivial challenge. A missing telemetry record or failed ping does not automatically indicate an Internet Service Provider (ISP) network blackout.

Real-world deployment environments introduce significant non-network variables:

1. **Facility Operational Schedules:** Schools and public facilities close at night and on weekends; hardware is powered off.

2. **Power Grid Instability:** Local power grids experience blackouts, shutting down both client hardware and local routers simultaneously.

3. **Offline Sync & Caching Engine:** The GigaMeter application utilizes local browser storage (IndexedDB) to cache telemetry offline during outages:
    *   **Ping Telemetry:** Written to IndexedDB immediately upon generation and synced to the server via a background job every **2 hours**.
    *   **Active Speedtests:** Measurement payloads are cached locally and synced automatically once connectivity is re-established (retaining up to **7 days** of history).
    *   **Data Retention Rules:** Local synced telemetry rows are pruned after **3 days**, while un-synced historical data is purged after **30 days**.

**Pillar 4 exists to establish a rigorous, deterministic baseline for entity connectivity during active operational hours (08:00–19:59 local device time) and serve as the foundation for predictive modeling and automated disconnection alarms**.

### 2\. Deterministic Starting Baseline: The 4-State Taxonomy

Time-series ping telemetry (generated every 15 minutes during operational hours) is deterministically categorized into four analytical states:

| State | Status Name | Logical Database Conditions | Analytical Interpretation & Real-World Context | Metric Impact |
| ---| ---| ---| ---| --- |
| State A | Internet ON | `is_connected = TRUE`<br>AND `latency` is numerical | Client device active, app container functional, end-to-end network reachability validated. | Uptime Numerator & Denominator |
| State B | Internet OFF | `is_connected = FALSE` | Client active, WAN reachability explicitly failed. (Cached in IndexedDB locally; may sync up to 2 hours late). | Downtime Denominator |
| State D | Degraded / Discrepancy | `is_connected = TRUE`<br>AND `latency IS NULL` | Widespread global pattern (~6.50% of dataset): Connection check succeeds, but latency returns null (severe packet loss or async promise boundary timeout). Awaiting final engineering clarification; isolated in sensitivity models. | Isolate / Examine Separately |
| State C | Gap / No Observation | Missing row inside active operational interval | No telemetry received. Indicates hardware powered off, deep sleep, app crash, power cut, or pending sync. | Exclude from Uptime Baseline |

#### Formal Baseline Uptime Formula:

$$\text{Uptime } (\%) = \frac{\text{Count(State A)}}{\text{Count(State A)} + \text{Count(State B)}} \times 100$$

_(Bounded strictly between 08:00 and 19:59 local device time; excludes State C gaps; isolates State D for sensitivity analysis)_.

### 3\. Future Research & Modeling Roadmap

While the 4-State taxonomy provides the immediate deterministic starting point, Pillar 4 encompasses two upcoming research tracks:

1. **Measurement-Ping Validation Pipeline:**
    *   Construct an automated cross-validation engine that checks whether active speedtest measurement payloads exist during timeframes where ping telemetry reports downtime (State B) or gaps (State C).
    *   Cross-reference startup speedtest runs (`trigger_type = 'startup'`) upon system reboot to verify whether time-series gaps were caused by power restarts vs. ISP outages.

2. **Predictive Time-Series Disconnection Modeling:**
    *   Build time-series machine learning models to forecast future school offline events and predict imminent disconnections based on historical ping latency jitter, error trends, and regional outage patterns.
