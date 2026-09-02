"""Formula Student drivetrain telemetry debrief dashboard."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from telemetry import (
    TelemetryValidationError,
    Thresholds,
    detect_events,
    event_table,
    headline_metrics,
    lap_summary,
    validate_telemetry_frame,
)


DATA_PATH = Path(__file__).parent / "data" / "sample_run.csv"
DEFAULT_THRESHOLDS = Thresholds()

st.set_page_config(page_title="FS drivetrain debrief", page_icon="🏁", layout="wide")
st.title("Formula Student EV drivetrain debrief")
st.caption(
    "A post-run review workspace for finding thermal, electrical and energy-management questions quickly. "
    "The bundled session is a labelled synthetic demonstration, not an official team log."
)


def load_default_data() -> pd.DataFrame:
    """Load the small committed scenario on each rerun so local edits stay visible."""
    return pd.read_csv(DATA_PATH)


def line_chart(frame: pd.DataFrame, columns: list[str], title: str, labels: dict[str, str]) -> go.Figure:
    figure = px.line(frame, x="time_s", y=columns, title=title, labels={"time_s": "Time (s)", **labels})
    figure.update_layout(legend_title_text="")
    return figure


with st.sidebar:
    st.header("Session setup")
    upload = st.file_uploader("Upload a telemetry CSV", type="csv")
    if upload:
        source_label = f"Uploaded session: {upload.name}"
        raw_frame = pd.read_csv(upload)
    else:
        source_label = "Bundled synthetic review scenario"
        raw_frame = load_default_data()

    st.caption(source_label)
    st.divider()
    st.subheader("Review limits")
    motor_limit = st.number_input("Motor temperature limit (°C)", 60, 160, int(DEFAULT_THRESHOLDS.motor_temp_c))
    inverter_limit = st.number_input(
        "Inverter temperature limit (°C)", 40, 140, int(DEFAULT_THRESHOLDS.inverter_temp_c)
    )
    nominal_pack_voltage_v = st.number_input("Nominal pack voltage (V)", 400, 900, 600)
    default_sag_limit = min(int(DEFAULT_THRESHOLDS.pack_voltage_v), int(nominal_pack_voltage_v))
    sag_limit = st.number_input(
        "Pack voltage sag limit (V)", 300, int(nominal_pack_voltage_v), default_sag_limit
    )

thresholds = Thresholds(
    motor_temp_c=float(motor_limit),
    inverter_temp_c=float(inverter_limit),
    pack_voltage_v=float(sag_limit),
)

try:
    frame = validate_telemetry_frame(raw_frame)
except TelemetryValidationError as error:
    st.error(f"This log cannot be reviewed yet: {error}")
    st.stop()

metrics = headline_metrics(frame, nominal_pack_voltage_v=float(nominal_pack_voltage_v))
events = detect_events(frame, thresholds)
review_log = event_table(events)
lap_stats = lap_summary(frame)

top_metrics = st.columns(4)
top_metrics[0].metric("Peak power", f"{metrics.peak_power_kw:.1f} kW")
top_metrics[1].metric("Max motor temp", f"{metrics.maximum_motor_temp_c:.1f} °C")
top_metrics[2].metric("Min pack voltage", f"{metrics.minimum_pack_voltage_v:.1f} V")
top_metrics[3].metric("Review windows", len(events))

debrief_tab, motor_tab, thermal_tab, electrical_tab, laps_tab = st.tabs(
    ["Test debrief", "Motor performance", "Thermal", "Electrical", "Lap analysis"]
)

with debrief_tab:
    st.subheader("Priority review log")
    if review_log.empty:
        st.success("No threshold events were detected for the configured limits.")
    else:
        st.warning(
            f"{len(review_log)} review window(s) detected. Confirm the signal, correlate it with driver and track context, "
            "then assign the next investigation rather than treating a threshold breach as a root cause."
        )
        st.dataframe(review_log, width="stretch", hide_index=True)
        st.download_button(
            "Download review log as CSV",
            review_log.to_csv(index=False),
            "telemetry_review_log.csv",
            "text/csv",
        )
        for event in events:
            with st.expander(
                f"{event.severity}: {event.title} — {event.start_time_s:.1f}–{event.end_time_s:.1f}s"
            ):
                st.write(event.review_prompt)

    st.subheader("Energy sanity check")
    energy_a, energy_b, energy_c = st.columns(3)
    energy_a.metric("Mechanical energy", f"{metrics.mechanical_energy_kj:.1f} kJ")
    energy_b.metric("Electrical energy", f"{metrics.electrical_energy_kj:.1f} kJ")
    efficiency_label = "—" if metrics.estimated_drivetrain_efficiency_pct is None else f"{metrics.estimated_drivetrain_efficiency_pct:.1f}%"
    energy_c.metric("Estimated drivetrain efficiency", efficiency_label)
    st.caption(
        "Energy is integrated from timestamped samples. The efficiency value is a first-pass diagnostic, not a calibrated loss model."
    )

with motor_tab:
    st.plotly_chart(
        line_chart(
            frame,
            ["motor_rpm", "motor_torque_nm"],
            "Motor speed and torque",
            {"motor_rpm": "Motor speed (rpm)", "motor_torque_nm": "Motor torque (Nm)"},
        ),
        width="stretch",
    )
    st.plotly_chart(
        px.line(
            frame,
            x="time_s",
            y="power_kw",
            title="Mechanical motor power",
            labels={"time_s": "Time (s)", "power_kw": "Power (kW)"},
        ),
        width="stretch",
    )

with thermal_tab:
    thermal_figure = line_chart(
        frame,
        ["motor_temp_c", "inverter_temp_c"],
        "Drivetrain temperatures",
        {"motor_temp_c": "Temperature (°C)", "inverter_temp_c": "Temperature (°C)"},
    )
    thermal_figure.add_hline(y=thresholds.motor_temp_c, line_dash="dash", line_color="#ef553b", annotation_text="motor limit")
    thermal_figure.add_hline(y=thresholds.inverter_temp_c, line_dash="dot", line_color="#ffa15a", annotation_text="inverter limit")
    st.plotly_chart(thermal_figure, width="stretch")

with electrical_tab:
    voltage_figure = px.line(
        frame,
        x="time_s",
        y="battery_voltage_v",
        title="Accumulator pack voltage",
        labels={"time_s": "Time (s)", "battery_voltage_v": "Pack voltage (V)"},
    )
    voltage_figure.add_hline(y=thresholds.pack_voltage_v, line_dash="dash", line_color="#ef553b", annotation_text="sag limit")
    st.plotly_chart(voltage_figure, width="stretch")
    st.plotly_chart(
        px.line(
            frame,
            x="time_s",
            y="battery_current_a",
            title="Accumulator pack current",
            labels={"time_s": "Time (s)", "battery_current_a": "Pack current (A)"},
        ),
        width="stretch",
    )

with laps_tab:
    st.subheader("Per-lap comparison")
    st.dataframe(lap_stats, width="stretch", hide_index=True)
    energy_figure = go.Figure()
    energy_figure.add_bar(x=lap_stats["lap"], y=lap_stats["mechanical_energy_kj"], name="Mechanical energy")
    energy_figure.add_bar(x=lap_stats["lap"], y=lap_stats["electrical_energy_kj"], name="Electrical energy")
    energy_figure.update_layout(
        title="Energy by lap", barmode="group", xaxis_title="Lap", yaxis_title="Energy (kJ)", legend_title_text=""
    )
    st.plotly_chart(energy_figure, width="stretch")

st.divider()
st.caption(
    "Portfolio implementation: Python, Streamlit, pandas and Plotly. Uploads are validated before analysis; events are grouped into review windows so a debrief starts with decisions, not a wall of samples."
)
