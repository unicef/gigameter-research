## Pillar 2: Geolocation Quality, BSSID Fingerprinting & Confidence Scoring

### 1\. Why This Pillar Exists

Crowdsourced Wi-Fi location resolution depends on ambient environmental scans submitted to Google's Geolocation API. However, field environments present significant spatial noise:

*   Facilities in rural areas may scan only 1 or 2 nearby Wi-Fi routers, yielding lower precision radii.

*   Staff frequently use consumer mobile hotspots (e.g., `"iPhone"`, `"Galaxy A15"`), which move continuously across days.

*   Devices occasionally report severe BSSID spatial splits (> 2km), where a single device pings from two distant locations.
Furthermore, GigaMeter operates under a Strict No-IP Fallback Policy. If Wi-Fi triangulation fails, coordinates return as `NULL` rather than defaulting to inaccurate ISP data centers hundreds of kilometers away. Pillar 2 exists to quantify spatial precision (0–100 score), detect mobile tethering anomalies, and apply mathematical coherence penalties to unstable hardware setups.

### 2\. Core Research Objectives

*   **Inverse-Variance Spatial Weighting:** Compute empirical facility centroids where high-precision scans (<= 10m) carry exponentially greater mathematical weight than low-precision scans (100m).

*   **Mobile Hotspot & Drift Detection:** Automatically flag personal mobile tethering via case-insensitive SSID regex matching and multi-day BSSID spatial drift checks (> 1km).

*   **BSSID Coherence Penalty (P\_coherence):** Scale down hardware health scores when a facility's associated BSSIDs exhibit a severe spatial split (> 2km).

### 6\. Key Analytical Mechanics

*   **Accuracy-Weighted Centroid Formula:**

$$w_i = \frac{1}{\max(A_i, 1.0)^2}$$

$$\bar{\phi} = \frac{\sum (w_i \cdot \phi_i)}{\sum w_i}, \quad \bar{\lambda} = \frac{\sum (w_i \cdot \lambda_i)}{\sum w_i}$$

*   **5-Factor Composite Scoring Model (S\_raw, 0–100):**

$$S_{\text{raw}} = \underbrace{S_{\text{stability}}}_{\text{30 pt}} + \underbrace{S_{\text{consensus}}}_{\text{25 pt}} + \underbrace{S_{\text{bssid}}}_{\text{20 pt}} + \underbrace{S_{\text{depth}}}_{\text{15 pt}} + \underbrace{S_{\text{precision}}}_{\text{10 pt}}$$

*   **BSSID Coherence Multiplier (P\_coherence):**

$$P_{\text{coherence}} = 
\begin{cases} 
1.0, & \text{if } D_{\text{bssid_max}} \le 1000\text{m } \text{(Tight Alignment)} \\[1ex]
1.0 - 0.5 \times \left( \frac{D_{\text{bssid_max}} - 1000}{1000} \right), & \text{if } 1000\text{m} < D_{\text{bssid_max}} \le 2000\text{m} \\[1ex]
0.1, & \text{if } D_{\text{bssid_max}} > 2000\text{m } \text{(Severe BSSID Split)}
\end{cases}$$