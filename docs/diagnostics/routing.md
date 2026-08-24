## Pillar 5: ISP SLA Accountability, BBR & Bufferbloat Analytics (Early Stage)

### 1\. Why This Pillar Exists

Standard throughput tests (download and upload speed in Mbps) fail to capture the full quality of service (QoS) experienced by end users. A school may subscribe to a 50 Mbps connection yet suffer unviable performance during digital learning sessions due to high latency under load (**Bufferbloat**), severe packet loss, or poor backhaul routing.

**Pillar 5 exists as an exploratory research pillar to leverage kernel-level NDT7 diagnostic payloads (****`results`** **JSON) to establish objective ISP Service Level Agreement (SLA) accountability**.

### 2\. Exploratory Research Scope & NDT7 Metrics

While Pillar 5 is currently in an early analytical stage, the platform extracts and maps key TCP kernel diagnostic parameters from active NDT7 test runs:

| Research Metric | JSON Extraction Path (`results` Column) | Units | Diagnostic & SLA Utility |
| ---| ---| ---| --- |
| Download Throughput | `NDTResult.S2C.LastClientMeasurement.MeanClientMbps` | Mbps | Actual user throughput during download test. |
| Upload Throughput | `NDTResult.C2S.LastClientMeasurement.MeanClientMbps` | Mbps | Actual user throughput during upload test. |
| Working Latency (RTT) | `NDTResult.S2C.LastServerMeasurement.TCPInfo.RTT` / 1000.0 | msms | Real-time round-trip latency under active load. |
| Baseline Latency (MinRTT) | `NDTResult.S2C.LastServerMeasurement.BBRInfo.MinRTT` / 1000.0 | msms | Unloaded baseline network latency. |
| Bufferbloat (ΔRTT) | RTT−MinRTT | msms | Latency degradation under load; identifies ISP or router queue bloat. |
| TCP Packet Retransmissions | `NDTResult.S2C.LastServerMeasurement.TCPInfo.TotalRetrans` | Count | Total retransmitted TCP packets; primary indicator of physical link loss. |
| BBR Bottleneck Capacity | `NDTResult.S2C.LastServerMeasurement.BBRInfo.BW` | Bytes/sec | The maximum end-to-end bandwidth from the server to the client as measured by BBR. |

### 3\. Future Analytical Direction

As additional diagnostic dataset assets are integrated into GigaMeter, Pillar 5 research will focus on:

*   **Root-Cause Degradation Separation:** Isolating whether poor user performance stems from weak local school Wi-Fi signal (`wifi_signal_dbm`) versus ISP backhaul congestion or inefficient M-Lab server routing.

*   **Automated SLA Breach Reporting:** Generating automated compliance reports comparing contractual ISP bandwidth and latency guarantees against empirical NDT7 kernel metrics.