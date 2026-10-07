"""
Module: src/spatial_intelligence/plot_utils.py
Purpose: Small Plotly helpers shared by the spatial plots.
"""

import math

import plotly.graph_objects as go


def add_log_x_vline(fig: go.Figure, x: float, text: str) -> None:
    """
    Dashed vertical line with a label on a log-scale x axis.

    Plotly reads annotation positions on log axes as log10 values, so the
    label is placed at `log10(x)` while the line keeps the data value.
    """
    fig.add_vline(x=x, line_dash="dash", line_color="gray")
    fig.add_annotation(
        x=math.log10(x),
        y=1.0,
        yref="paper",
        text=text,
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        font=dict(size=10),
    )
