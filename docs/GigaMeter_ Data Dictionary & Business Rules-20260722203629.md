# GigaMeter: Data Dictionary & Business Rules

**Document Version:** v2.2 (Empirical Telemetry Update)
**Status:** Operational / Active Baseline (Pending specific asset lifecycle verification)
## 1\. Project Overview
GigaMeter (formerly known as "Daily Check App" or "PCDC") is an open-source telemetry platform used to monitor internet service.
*   **Scope Expansion (2026):** The system has evolved from a "one-facility-type" app to a generic **"Entity"** platform. It now supports monitoring for schools, health facilities, and refugee camps.
*   **Offline Resilience & Sync Architecture:** The application uses local browser storage (IndexedDB) to ensure continuous data collection during internet outages:
    *   **Ping Telemetry:** Every ping result is written to IndexedDB immediately upon generation, regardless of connectivity status. An automated background job attempts to sync queued pings to the server every **2 hours**.
    *   **Active Speedtest Measurements:** Full measurement payloads are cached locally and synced automatically once connectivity is re-established (caching up to **7 days** of measurement history).
    *   **Data Pruning & Retention Rules:** Local synced telemetry rows are pruned after **~3 days**, while un-synced or stale historical data is purged after **30 days**.
The primary objectives of analyzing this data are:
1. **Connectivity Monitoring:** Determining if an entity's internet is online or offline and calculating formal Uptime.
2. **Geofencing & Validation:** Validating the physical location of the device running the test against government-provided coordinates.
## 2\. Ping Data (Time-Series Telemetry)
*   **Definition:** Lightweight telemetry data sent from the installed GigaMeter app to indicate device uptime and network reachability.
*   **Expected Frequency:** Every 15 minutes (4 pings per hour per entity/device) during active operational hours.
### 2.1. Ping Data Dictionary & Key Fields
*   `id`: Unique identifier for the ping record.
*   `timestamp`: The exact date and time the ping was recorded.
*   `is_connected` (Boolean): Indicates whether the app successfully reached the network (`true` or `false`).
*   `latency` (Float): The response time in milliseconds. Only present if the internet connection is fully established.
*   `giga_id_school` / `entity_id`: Unique identifier for the monitored entity.
*   CRITICAL TRANSITION RULE: While `entity_id` is the modern standard for the overarching Entity platform, the underlying PostgreSQL database still heavily utilizes `giga_id_school` as the primary key for school facilities. For all school-centric research, treat these two fields as functionally identical.
*   Join Strategy: Always default to using `giga_id_school` when performing SQL joins between telemetry tables (e.g., measurements) and the school master metadata table.
*   `app_local_uuid` / `browser_id`: Identifiers for the specific app installation and device environment.
*   `is_school_hours` (Boolean): A derived SQL field tagging records between 08:00 to 20:00 local time.
### 2.2. Ping Business Rules & Status Logic
To accurately evaluate the true state of an entity's internet connectivity, data models must process time-series telemetry using four distinct analytical states:

| State | Status Name | Logical Database Conditions | Interpretation & Technical Reality | Metric Impact |
| ---| ---| ---| ---| --- |
| State A | Internet is ON | `is_connected = true`<br><br>AND `latency` is numerical | The client device is active, the app container is functional, and the end-to-end network handshake is valid. | Uptime<br> |
| State B | Internet is OFF | `is_connected = false`<br> | The device and app are running, but WAN connectivity has explicitly failed. (Note: Written to IndexedDB locally and may sync up to 2 hours late). | Downtime<br> |
| State D | Degraded State / Telemetry Discrepancy | `is_connected = true`<br><br>AND `latency IS NULL`<br> | Widespread Pattern (6.50% of global dataset): The app successfully executes an interface/environmental connection check, but the latency payload returns null. Indicates severe packet loss, network degradation/timeouts, or an unresolved async promise boundary. | Isolate/Examine Separately<br><br>(Do not auto-bucket as pure uptime or downtime) |
| State C | Missing Data / No Observation | Null database footprint inside valid timeframes | No telemetry records exist for an expected interval window. | Exclude from Baseline<br> |

#### Crucial Analytical Note on State C (Missing Data) Gaps
A timeline gap (State C) within active operational hours (08:00–19:59 local time) does _not_ indicate a simple internet blackout. Because pings are safely written to IndexedDB offline, a genuine gap strictly signifies one of the following scenarios:
*   The system hardware is fully powered down, in deep sleep, or closed (e.g., weekends, holidays, or a total grid power cut affecting both the computer and router).
*   The application container has crashed or was closed out by the user.
*   Data is currently pending inside the active 2-hour local upload window, or was permanently purged by the 30-day retention rule before syncing.
### 2.3. Uptime Calculation Logic & Telemetry Cadence
Uptime is a critical KPI calculated strictly during active operational hours (08:00 to 19:59 local device time) so entities are not penalized for nighttime or weekend closures.
#### A. Formal Uptime Formula

![](https://t25789471.p.clickup-attachments.com/t25789471/c22e243a-70e1-4dde-a9e3-b57866d2a69b/image.emf)

*   Numerator - Successful Pings (State A): Pings where `is_connected = true` AND `latency` contains a valid numerical value.
*   Denominator - Total Powered-On Tests (State A + State B): Total valid ping records gathered while the device and app were actively running.
    *   _Note on State D (__`is_connected = true`__,_ _`latency IS NULL`__):_ Pending final engineering confirmation on this 6.5% discrepancy, these records should be isolated and evaluated separately rather than automatically bucketed into the denominator as full downtime.
*   Excluded Baseline (State C): Missing time-series intervals during active hours indicate the device/router was powered off, in sleep mode, or crashed, and are excluded from the uptime calculation.
#### B. Ping Generation Cadence & Anchoring Rules
When filtering and aggregating time-series data, analysts must account for the following client-side timer rules:
*   **Active Operational Window (08:00–19:59):** Telemetry generation is strictly bounded to device-local time between 8:00 AM and 7:59 PM. No pings are ever generated or cached outside this window. Nighttime and early morning gaps are 100% expected.
*   **App-Boot Anchoring:** The 15-minute ping interval relies on a `setInterval` function initialized when the app boots, not aligned to wall-clock boundaries (do not expect clean `:00`, `:15`, `:30`, `:45` timestamps).
*   **Initial Ping Delay:** The first ping of a session is recorded at `app_launch + 15 minutes`.
*   **Phase Resets & Sleep Pauses:** The 15-minute timer phase completely resets on every app restart, and pauses whenever the underlying machine enters sleep or standby mode.

## 3\. Measurements Data (Active Speedtests) & Diagnostic Payloads
Measurements store comprehensive speed test results and TCP kernel-level telemetry collected via active NDT7 diagnostic runs.
### 3.1. Measurement Core Fields
*   `entity_id` / `giga_id_school`: Unique facility identifier.
*   `source`: Origin app (`'DailyCheckApp'` in DB, representing GigaMeter).
*   `trigger_type`: `'scheduled'` (1 of 4 daily window runs) or `'startup'` (triggered within 15 mins of boot).
*   `wifi_connections`: Active Wi-Fi connection SSID/BSSID (empty `[]` if wired/Ethernet).
*   `detected_latitude` / `detected_longitude`: Wi-Fi BSSID resolved coordinates via Google API (`NULL` if unresolved; NO IP fallback).
*   `results` _(JSON string/object)_: The NDT7 Diagnostic Payload containing raw TCP kernel parameters and throughput metrics.
### 3.2. Nested `results` Payload Schema & Extraction Paths
The `results` field is split into two directional sub-objects:
*   `NDTResult.S2C` (Server-to-Client = Download Test)
*   `NDTResult.C2S` (Client-to-Server = Upload Test)
Plaintext

```sql
results
 ├── NDTResult.S2C / NDTResult.C2S
 │    ├── LastClientMeasurement
 │    │    ├── MeanClientMbps          <-- User-Facing Speed (Mbps)
 │    │    ├── NumBytes                <-- Bytes Transferred
 │    │    └── ElapsedTime             <-- Duration (seconds)
 │    ├── LastServerMeasurement
 │    │    ├── BBRInfo
 │    │    │    ├── BW                 <-- Bottleneck Bandwidth Capacity
 │    │    │    ├── MinRTT             <-- Unloaded Baseline RTT (microseconds)
 │    │    │    ├── CwndGain           <-- BBR Congestion Multiplier
 │    │    │    └── PacingGain         <-- BBR Pacing Multiplier
 │    │    └── TCPInfo
 │    │         ├── RTT                <-- Working Latency under load (microseconds)
 │    │         ├── MinRTT             <-- Minimum RTT (microseconds)
 │    │         ├── Lost               <-- Lost TCP Packets
 │    │         ├── TotalRetrans       <-- Total Packet Retransmissions
 │    │         ├── BytesRetrans       <-- Retransmitted Bytes
 │    │         ├── SndCwnd            <-- Send Congestion Window
 │    │         ├── DeliveryRate       <-- Socket Delivery Throughput
 │    │         └── RWndLimited        <-- Window Bottleneck Time
 │    └── ConnectionInfo
 │         ├── Client                 <-- Client IP : Source Port
 │         ├── Server                 <-- Target Server IP : Destination Port
 │         └── UUID                   <-- Unique M-Lab Test Run ID
```

### 3.3. Key Metric Mappings for Advanced Research

| Research Variable | JSON Extraction Path | Units | Diagnostic Utility |
| ---| ---| ---| --- |
| Download Speed | `results['NDTResult.S2C']['LastClientMeasurement']['MeanClientMbps']` | Mbps | User throughput during download test. |
| Upload Speed | `results['NDTResult.C2S']['LastClientMeasurement']['MeanClientMbps']` | Mbps | User throughput during upload test. |
| Working Latency | `results['NDTResult.S2C']['LastServerMeasurement']['TCPInfo']['RTT']` | Microseconds ($\\mu s$) | Real-time round-trip latency under active load. Divide by $1000$ for $ms$. |
| Baseline Latency | `results['NDTResult.S2C']['LastServerMeasurement']['BBRInfo']['MinRTT']` | Microseconds ($\\mu s$) | Unloaded WAN latency. Divide by $1000$ for $ms$. |
| Bufferbloat / Latency Delta | RTT - MinRTT | Microseconds ($\\mu s$) | Latency degradation under load. Spikes indicate local router/ISP queue bloat. |
| BBR Capacity | `results['NDTResult.S2C']['LastServerMeasurement']['BBRInfo']['BW']` | Bits or Bytes / sec | Physical link bottleneck bandwidth estimated by Google BBR. |
| Packet Loss Rate | `results['NDTResult.S2C']['LastServerMeasurement']['TCPInfo']['TotalRetrans']` | Count | Total retransmitted TCP packets; primary SLA accountability indicator. |
| Server Routing Node | `results['NDTResult.S2C']['ConnectionInfo']['Server']` | IP Address | Target M-Lab server IP. Used to detect bad BGP routing or overseas hairpinning |

### 3.4. Geolocation Resolution & Failure Rules (v2.0.3+)
*   Wi-Fi Scanning Mechanics:
    *   `wifi_connections` Field: Records only the active Wi-Fi network (SSID/BSSID) that the client device is currently associated with.
    *   **Background Geolocation Scan:** The geolocation routine scans all nearby Wi-Fi BSSIDs (active and passive/unconnected) in the device's environment.
    *   **_Analytical Note:_** An empty `wifi_connections` payload (`[]`) does not mean Wi-Fi scanning failed. High-accuracy coordinates can still be resolved as long as passive nearby BSSIDs were captured and sent to Google's Geolocation API.
*   Google API Resolution & Strict No-IP Policy:
    *   Coordinates are resolved server-side using **Google's Geolocation API** based on all detected BSSIDs.
    *   **No IP-Based Fallback:** IP-based geolocation is never used in GigaMeter due to severe inaccuracies for entity location mapping (e.g., resolving to distant ISP data centers).
    *   **API Resolution Failures (****`null`** **coordinates):** If Google's Geolocation API fails to resolve a location; or if no Wi-Fi networks are detected; `detected_latitude` and `detected_longitude` will be populated as `null`.
## 4\. Research Objectives & Analytical Pillars
### 4.1. Master Mapping & Identifier Continuity
To ensure seamless integration across datasets, all spatial and telemetry models must anchor on `giga_id_school` (or `entity_id`). This maintains identifier continuity when cross-referencing high-frequency telemetry tables with official government metadata databases.
### 4.2. Core Research Pillars
#### Pillar 1: Entity Geofencing & Mobility Detection
*   Objective: Monitor device mobility and verify whether client hardware remains bound to its assigned facility.
*   Methodology: Construct spatial heatmaps and cluster models using valid coordinate pairs (`detected_latitude`, `detected_longitude`). Trigger an anomaly flag when a device hardware instance relocates significantly beyond the registered physical boundary of the target entity.
#### Pillar 2: Geolocation Quality & Confidence Scoring
*   Objective: Establish the reliability of captured spatial coordinates and account for resolution failures.
*   Methodology: Score location reliability based on the reported precision radius (`detected_location_accuracy`) across repeated Wi-Fi environment scans. Because GigaMeter strictly avoids IP-based geolocation fallback, missing coordinates (`null`) must be treated as unresolvable Google Geolocation API requests rather than spatial errors or incorrect locations.
#### Pillar 3: Government Data Validation
*   Objective: Cross-validate official government administrative facility records against empirical field coordinates.
*   Methodology: Calculate spatial displacement (using Haversine distance metrics) between high-confidence, Wi-Fi-resolved coordinates and official government coordinates. Discrepancies beyond a defined distance threshold are flagged for manual verification or field re-mapping.
#### Pillar 4: Outage Classification & Connectivity Modeling
*   Objective: Differentiate genuine internet infrastructure blackouts from expected closures, system crashes, or power loss.
*   Methodology: Apply four-state time-series models (States A, B, C, and D) bounded strictly by operational hours (08:00 to 19:59 local device time):
    *   Network Outages (State B): Identify instances where the device is active but WAN reachability fails, accounting for up to 2-hour upload delays from IndexedDB offline caching.
    *   Telemetry Anomalies (State D): Isolate records where `is_connected = true` but `latency IS NULL` to prevent distortion of baseline connectivity metrics.
    *   Facility Power/App Outages (State C): Classify time-series gaps by evaluating startup measurement tests upon reboot and cross-referencing multi-day offline sync queues.