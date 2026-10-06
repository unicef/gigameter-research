"""
Module: src/spatial_intelligence/geo.py
Purpose: Shared spatial helpers: accuracy-weighted centroids, haversine
         DBSCAN, and pairwise distances.
"""

from typing import Optional, Sequence, Tuple

import numpy as np
from gigaspatial.processing import calculate_distance
from sklearn.cluster import DBSCAN

EARTH_RADIUS_M = 6371e3
NOISE_LABEL = -1


def haversine_m(lat1, lon1, lat2, lon2):
    """Haversine distance in meters. Accepts scalars or broadcastable arrays."""
    lat1, lon1, lat2, lon2 = np.broadcast_arrays(
        *(np.asarray(v, dtype=float) for v in (lat1, lon1, lat2, lon2))
    )
    return calculate_distance(lat1, lon1, lat2, lon2, R=EARTH_RADIUS_M)


def weighted_centroid(
    lats: Sequence[float],
    lons: Sequence[float],
    accuracies_m: Optional[Sequence[float]] = None,
    accuracy_floor_m: float = 1.0,
) -> Tuple[float, float]:
    """
    Inverse-variance weighted centroid, `w = 1 / max(A, floor)^2`.

    Missing accuracies take the median of the known ones, or equal weights
    when none are known. Only call this on points from one spatial cluster;
    averaging across clusters produces a location no device visited.

    Raises:
        ValueError: If no points are given.
    """
    lat_arr = np.asarray(lats, dtype=float)
    lon_arr = np.asarray(lons, dtype=float)
    if lat_arr.size == 0:
        raise ValueError("weighted_centroid needs at least one point")

    if accuracies_m is None:
        weights = np.ones_like(lat_arr)
    else:
        acc = np.asarray(accuracies_m, dtype=float)
        known = acc[np.isfinite(acc)]
        fill = float(np.median(known)) if known.size else 1.0
        acc = np.where(np.isfinite(acc), acc, fill)
        weights = 1.0 / np.square(np.maximum(acc, accuracy_floor_m))

    total = weights.sum()
    return (
        float(np.sum(lat_arr * weights) / total),
        float(np.sum(lon_arr * weights) / total),
    )


def dbscan_labels(
    lats: Sequence[float],
    lons: Sequence[float],
    eps_m: float,
    min_samples: int,
) -> np.ndarray:
    """
    Haversine DBSCAN labels. `-1` is noise; other labels carry no order or rank.
    """
    lat_arr = np.asarray(lats, dtype=float)
    lon_arr = np.asarray(lons, dtype=float)
    if lat_arr.size == 0:
        return np.array([], dtype=int)
    coords = np.radians(np.column_stack([lat_arr, lon_arr]))
    model = DBSCAN(
        eps=eps_m / EARTH_RADIUS_M, min_samples=min_samples, metric="haversine"
    )
    return model.fit(coords).labels_


def max_pairwise_distance_m(
    lats: Sequence[float], lons: Sequence[float]
) -> float:
    """Largest haversine distance between any two points; 0.0 for fewer than two."""
    lat_arr = np.asarray(lats, dtype=float)
    lon_arr = np.asarray(lons, dtype=float)
    if lat_arr.size < 2:
        return 0.0
    dist = haversine_m(
        lat_arr[:, None], lon_arr[:, None], lat_arr[None, :], lon_arr[None, :]
    )
    return float(np.nanmax(dist))
