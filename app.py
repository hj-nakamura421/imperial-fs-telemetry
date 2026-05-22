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

# --- Thresholds (typical for an Emrax-228-class drivetrain) -----------------
MOTOR_TEMP_LIMIT_C = 100
INVERTER_TEMP_LIMIT_C = 80
VOLTAGE_NOMINAL_V = 600
VOLTAGE_SAG_LIMIT_V = 540

SAMPLE_DATA = Path(__file__).parent / "data" / "sample_run.csv"

REQUIRED_COLS = [
    "time_s",
    "lap",
    "motor_rpm",
    "motor_torque_nm",
    "power_kw",
    "motor_temp_c",
    "inverter_temp_c",
    "battery_voltage_v",
    "battery_current_a",
]


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
    motor_limit = st.number_input("Motor temp limit (°C)", 60, 150, MOTOR_TEMP_LIMIT_C)
    inv_limit = st.number_input("Inverter temp limit (°C)", 40, 120, INVERTER_TEMP_LIMIT_C)
    v_sag_limit = st.number_input("Voltage sag limit (V)", 400, 600, VOLTAGE_SAG_LIMIT_V)

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

missing = [c for c in REQUIRED_COLS if c not in df.columns]
if missing:
    st.error(f"CSV is missing required columns: {missing}")
    st.stop()

st.session_state["df"] = df


# --- Headline metrics -------------------------------------------------------
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Peak power", f"{df['power_kw'].max():.1f} kW")
c2.metric("Avg power", f"{df['power_kw'].mean():.1f} kW")
c3.metric("Max motor temp", f"{df['motor_temp_c'].max():.1f} °C")
c4.metric("Min pack voltage", f"{df['battery_voltage_v'].min():.1f} V")
c5.metric("Laps logged", int(df["lap"].max()))


# --- Anomaly summary --------------------------------------------------------
def _laps_of(mask: pd.Series) -> list[int]:
    return sorted(df.loc[mask, "lap"].unique().tolist())


warnings = []
motor_hot = df["motor_temp_c"] > motor_limit
if motor_hot.any():
    warnings.append(
        f"Motor over {motor_limit} °C — {motor_hot.sum()} samples on lap(s) {_laps_of(motor_hot)}"
    )

inv_hot = df["inverter_temp_c"] > inv_limit
if inv_hot.any():
    warnings.append(
        f"Inverter over {inv_limit} °C — {inv_hot.sum()} samples on lap(s) {_laps_of(inv_hot)}"
    )

v_low = df["battery_voltage_v"] < v_sag_limit
if v_low.any():
    warnings.append(
        f"Pack voltage under {v_sag_limit} V — {v_low.sum()} samples on lap(s) {_laps_of(v_low)}"
    )

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
    lap_stats = (
        df.groupby("lap")
        .agg(
            duration_s=("time_s", lambda x: round(x.max() - x.min(), 2)),
            avg_power_kw=("power_kw", "mean"),
            peak_power_kw=("power_kw", "max"),
            max_motor_temp_c=("motor_temp_c", "max"),
            min_pack_voltage_v=("battery_voltage_v", "min"),
            energy_kj=("power_kw", lambda x: round(x.sum() * (1 / 10), 2)),  # 10 Hz
        )
        .round(2)
        .reset_index()
    )

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
