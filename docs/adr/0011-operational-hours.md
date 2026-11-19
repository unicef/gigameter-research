# Operational hours are applied from SpatialConfig

Local time is `created_timestamp` converted at the facility. That conversion does not decide which hours count. `SpatialConfig.operational_hours` is an inclusive pair of integer local hours, and the end hour covers HH:00–HH:59. `in_operational_hours` is the only comparison. A fix event keeps the flag from its first row, so a burst that starts inside the window and finishes outside it stays in the anchor window. Governance percentages, the hourly chart, and the BSSID split count every row and do not apply the workday filter. An overnight window is rejected.

Which timestamp is the real test time for a row synced after the device was offline is unresolved.
