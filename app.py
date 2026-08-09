"""Streamlit dashboard for Imperial FS drivetrain telemetry.

Drop in a CSV from a dyno or track test (see README for expected columns),
or click "Use sample run" to explore the synthetic dataset.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from telemetry import (
    TelemetryValidationError,
    Thresholds,
    detect_anomalies,
    headline_metrics,
    lap_summary,
    validate_telemetry_frame,
)

# --- Thresholds (illustrative defaults; editable in the interface) ----------
DEFAULT_THRESHOLDS = Thresholds()

SAMPLE_DATA = Path(__file__).parent / "data" / "sample_run.csv"

# --- Page setup -------------------------------------------------------------
st.set_page_config(
    page_title="Imperial FS — Drivetrain Telemetry",
    layout="wide",
    page_icon="🏎️",
)

st.title("Imperial Formula Student — Drivetrain Telemetry Analyzer")
st.caption(
    "Load a CSV from a dyno or track test to inspect motor performance, "
    "thermal management, and accumulator behaviour lap-by-lap."
)


# --- Data load --------------------------------------------------------------
@st.cache_data
def load_csv(path_or_buffer) -> pd.DataFrame:
    return pd.read_csv(path_or_buffer)


with st.sidebar:
    st.header("Data source")
    uploaded = st.file_uploader("Upload telemetry CSV", type=["csv"])
    use_sample = st.button("Use sample run", use_container_width=True)
    st.divider()
    st.subheader("Thresholds")
    motor_limit = st.number_input(
        "Motor temp limit (°C)", 60, 150, int(DEFAULT_THRESHOLDS.motor_temp_c)
    )
    inv_limit = st.number_input(
        "Inverter temp limit (°C)", 40, 120, int(DEFAULT_THRESHOLDS.inverter_temp_c)
    )
    v_sag_limit = st.number_input(
        "Voltage sag limit (V)", 400, 600, int(DEFAULT_THRESHOLDS.pack_voltage_v)
    )

if uploaded is not None:
    df = load_csv(uploaded)
elif use_sample or "df" not in st.session_state:
    if not SAMPLE_DATA.exists():
        st.error(
            "Sample data not found. Run `python data_generator.py` first to "
            "create `data/sample_run.csv`."
        )
        st.stop()
    df = load_csv(SAMPLE_DATA)
else:
    df = st.session_state["df"]

try:
    df = validate_telemetry_frame(df)
except TelemetryValidationError as exc:
    st.error(str(exc))
    st.stop()

st.session_state["df"] = df


# --- Headline metrics -------------------------------------------------------
metrics = headline_metrics(df)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Peak power", f"{metrics.peak_power_kw:.1f} kW")
c2.metric("Avg power", f"{metrics.average_power_kw:.1f} kW")
c3.metric("Max motor temp", f"{metrics.maximum_motor_temp_c:.1f} °C")
c4.metric("Min pack voltage", f"{metrics.minimum_pack_voltage_v:.1f} V")
c5.metric("Laps logged", metrics.laps_logged)


# --- Anomaly summary --------------------------------------------------------
thresholds = Thresholds(
    motor_temp_c=float(motor_limit),
    inverter_temp_c=float(inv_limit),
    pack_voltage_v=float(v_sag_limit),
)
anomalies = detect_anomalies(df, thresholds)
warnings = [
    f"{anomaly.message} — {anomaly.sample_count} samples on lap(s) "
    f"{list(anomaly.laps)}"
    for anomaly in anomalies
]

if warnings:
    st.warning("⚠️ Anomalies detected:\n\n- " + "\n- ".join(warnings))
else:
    st.success("No threshold violations detected.")


# --- Tabbed plots -----------------------------------------------------------
tab_motor, tab_thermal, tab_elec, tab_laps = st.tabs(
    ["Motor performance", "Thermal", "Electrical", "Lap analysis"]
)

with tab_motor:
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        subplot_titles=("Motor RPM", "Motor torque (Nm)", "Power (kW)"),
        vertical_spacing=0.06,
    )
    fig.add_trace(
        go.Scatter(x=df["time_s"], y=df["motor_rpm"], line=dict(color="#1f77b4")),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=df["time_s"], y=df["motor_torque_nm"], line=dict(color="#2ca02c")),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(x=df["time_s"], y=df["power_kw"], line=dict(color="#d62728")),
        row=3, col=1,
    )
    fig.update_xaxes(title_text="Time (s)", row=3, col=1)
    fig.update_layout(height=620, showlegend=False, margin=dict(t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)

with tab_thermal:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["time_s"], y=df["motor_temp_c"],
            name="Motor", line=dict(color="#d62728"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["time_s"], y=df["inverter_temp_c"],
            name="Inverter", line=dict(color="#ff7f0e"),
        )
    )
    fig.add_hline(
        y=motor_limit, line_dash="dash", line_color="#d62728",
        annotation_text=f"Motor limit ({motor_limit} °C)",
    )
    fig.add_hline(
        y=inv_limit, line_dash="dash", line_color="#ff7f0e",
        annotation_text=f"Inverter limit ({inv_limit} °C)",
    )
    fig.update_layout(
        height=480,
        xaxis_title="Time (s)",
        yaxis_title="Temperature (°C)",
        margin=dict(t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)

with tab_elec:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        subplot_titles=("Pack voltage (V)", "Pack current (A)"),
        vertical_spacing=0.08,
    )
    fig.add_trace(
        go.Scatter(x=df["time_s"], y=df["battery_voltage_v"], line=dict(color="#9467bd")),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=df["time_s"], y=df["battery_current_a"], line=dict(color="#17becf")),
        row=2, col=1,
    )
    fig.add_hline(
        y=v_sag_limit, line_dash="dash", line_color="#d62728",
        annotation_text=f"Sag limit ({v_sag_limit} V)", row=1, col=1,
    )
    fig.update_xaxes(title_text="Time (s)", row=2, col=1)
    fig.update_layout(height=520, showlegend=False, margin=dict(t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)

with tab_laps:
    lap_stats = lap_summary(df)

    st.subheader("Per-lap summary")
    st.dataframe(lap_stats, use_container_width=True, hide_index=True)

    fig = go.Figure(
        data=[
            go.Bar(
                x=lap_stats["lap"],
                y=lap_stats["avg_power_kw"],
                marker_color="#1f77b4",
            )
        ]
    )
    fig.update_layout(
        title="Average power per lap",
        xaxis_title="Lap",
        yaxis_title="Avg power (kW)",
        height=380,
        margin=dict(t=50, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption(
    "Built by a Formula Student team member for the Formula Student team. "
    "Source: github.com/hj-nakamura421/imperial-fs-telemetry"
)
