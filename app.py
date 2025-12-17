import streamlit as st
import plotly.express as px

import io
import tempfile
import zipfile
from pathlib import Path

from src.etl import load_payments_folders
from src.forecast import prepare_series, forecast_holt_winters, forecast_sarima

st.set_page_config(page_title="Pagos - Forecast", layout="wide")
st.title("📈 Programación de Pagos — Dashboard & Forecast (2024–2025)")

# -----------------------------
# Sidebar: solo ZIP
# -----------------------------
with st.sidebar:
    st.header("Fuente de datos")
    st.caption("Sube un ZIP que contenga las carpetas 2024 y 2025 (cada una con subcarpetas mes/día y archivos Excel).")
    zip_file = st.file_uploader("ZIP (2024 + 2025)", type=["zip"])

    st.divider()
    st.header("Forecasting")
    model_name = st.selectbox("Modelo", ["Holt-Winters", "SARIMA"])
    steps = st.number_input("Horizonte (días)", min_value=7, max_value=365, value=30, step=1)

if zip_file is None:
    st.info("Sube un ZIP para comenzar.")
    st.stop()

# -----------------------------
# Descomprimir ZIP correctamente
# -----------------------------
# Guardamos el ZIP en memoria para que no se pierda en reruns
zip_bytes = zip_file.getvalue()

# Creamos el tmpdir una sola vez por sesión/ZIP (si cambia el ZIP, recreamos)
zip_signature = (zip_file.name, len(zip_bytes))

if st.session_state.get("zip_signature") != zip_signature:
    # Limpia tmpdir anterior
    old_tmp = st.session_state.get("_tmpdir")
    if old_tmp is not None:
        try:
            old_tmp.cleanup()
        except Exception:
            pass

    tmpdir = tempfile.TemporaryDirectory()
    tmp_path = Path(tmpdir.name)

    # 👇 IMPORTANTE: BytesIO
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
        z.extractall(tmp_path)

    st.session_state["_tmpdir"] = tmpdir
    st.session_state["tmp_path"] = str(tmp_path)
    st.session_state["zip_signature"] = zip_signature

tmp_path = Path(st.session_state["tmp_path"])

# Detectar carpetas 2024 y 2025 (en cualquier nivel)
year_folders = []
for year in ["2024", "2025"]:
    found = [p for p in tmp_path.rglob(year) if p.is_dir() and p.name == year]
    if found:
        year_folders.append(found[0])

if not year_folders:
    st.error("No encontré carpetas '2024' o '2025' dentro del ZIP. Revisa la estructura (deben ser carpetas con ese nombre).")
    st.stop()

# -----------------------------
# Cargar datos (multi-año)
# -----------------------------
df = load_payments_folders(year_folders)

if df.empty:
    st.warning("No se encontraron datos. Revisa que los Excel tengan la hoja 'RESUMEN' y la fila 'TOTAL A PAGAR'.")
    st.stop()

# -----------------------------
# Días en español
# -----------------------------
MAP_DIAS = {
    "Monday": "Lunes",
    "Tuesday": "Martes",
    "Wednesday": "Miércoles",
    "Thursday": "Jueves",
    "Friday": "Viernes",
    "Saturday": "Sábado",
    "Sunday": "Domingo",
}
df["DiaNombre_ES"] = df["DiaNombre"].map(MAP_DIAS)

# -----------------------------
# Filtros (sin moneda)
# -----------------------------
bancos = sorted(df["BANCO"].dropna().unique().tolist())
dias = sorted(df["DiaNombre_ES"].dropna().unique().tolist())

default_banco = ["SCOTIABANK"] if "SCOTIABANK" in bancos else bancos
default_dia = ["Viernes"] if "Viernes" in dias else dias

with st.sidebar:
    st.header("Filtros")
    banco_sel = st.multiselect("Banco", bancos, default=default_banco)
    dia_sel = st.multiselect("Día de la semana", dias, default=default_dia)

dff_base = df[
    df["BANCO"].isin(banco_sel)
    & df["DiaNombre_ES"].isin(dia_sel)
].copy()

# -----------------------------
# Panel por moneda
# -----------------------------
def render_panel(moneda: str):
    st.subheader(f"💱 {moneda}")

    dff = dff_base[dff_base["MONEDA"] == moneda].copy()

    c1, c2 = st.columns([2, 1])

    with c1:
        ts = dff.groupby("FECHA")["Valor"].sum().reset_index().sort_values("FECHA")
        ts["Monto"] = -ts["Valor"]
        fig = px.line(ts, x="FECHA", y="Monto", title=f"Histórico ({moneda}) — egresos en positivo")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.metric("Registros (filtrados)", len(dff))
        st.metric("Suma total (filtrada)", f"{(-dff['Valor'].sum()):,.2f}")
        st.write("Muestra (formato largo):")
        st.dataframe(dff.sort_values("FECHA").tail(15), use_container_width=True)

    st.markdown("### 🔮 Forecast")

    series = prepare_series(dff, freq="D")
    if len(series) < 8:
        st.info("Muy pocos puntos para forecast estable con estos filtros.")
        return

    if model_name == "Holt-Winters":
        y, fcst = forecast_holt_winters(series, steps=int(steps))
    else:
        y, fcst = forecast_sarima(series, steps=int(steps))

    hist = y.reset_index()
    hist.columns = ["FECHA", "Monto"]
    hist["Tipo"] = "Histórico"

    pred = fcst.reset_index()
    pred.columns = ["FECHA", "Monto"]
    pred["Tipo"] = "Forecast"

    plot_df = hist._append(pred, ignore_index=True)
    fig2 = px.line(plot_df, x="FECHA", y="Monto", color="Tipo", title=f"Forecast ({moneda}) — {model_name}")
    st.plotly_chart(fig2, use_container_width=True)

# Render
render_panel("PEN")
st.divider()
render_panel("USD")
