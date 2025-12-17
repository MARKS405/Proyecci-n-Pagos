import streamlit as st
import plotly.express as px

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
    # ahora el horizonte en días (porque estás en freq='D')
    steps = st.number_input("Horizonte (días)", min_value=7, max_value=365, value=30, step=1)

@st.cache_data(show_spinner=True)
def cached_load_from_zip(zip_bytes: bytes) -> tuple[Path, list[Path]]:
    """
    Descomprime el ZIP en un tmpdir y devuelve:
    - tmp_path
    - lista de carpetas encontradas para años (2024/2025)
    """
    tmpdir = tempfile.TemporaryDirectory()
    tmp_path = Path(tmpdir.name)

    with zipfile.ZipFile(zip_bytes, "r") as z:
        z.extractall(tmp_path)

    # Guardamos tmpdir para que no se destruya
    st.session_state["_tmpdir"] = tmpdir

    # Detectar carpetas 2024 y 2025 (en cualquier nivel)
    folders = []
    for year in ["2024", "2025"]:
        found = list(tmp_path.rglob(year))
        # nos quedamos con directorios llamados exactamente 2024/2025
        found_dirs = [p for p in found if p.is_dir() and p.name == year]
        if found_dirs:
            folders.append(found_dirs[0])

    return tmp_path, folders

if zip_file is None:
    st.info("Sube un ZIP para comenzar.")
    st.stop()

tmp_path, year_folders = cached_load_from_zip(zip_file.getvalue())

if not year_folders:
    st.error("No encontré carpetas '2024' o '2025' dentro del ZIP. Revisa la estructura del ZIP.")
    st.stop()

df = load_payments_folders(year_folders)

if df.empty:
    st.warning("No se encontraron datos. Revisa que los Excel tengan la hoja 'RESUMEN' y la fila 'TOTAL A PAGAR'.")
    st.stop()

# -----------------------------
# Traducción de días a español
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
# Filtros: solo Banco y Día
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
# Función para pintar un panel por moneda
# -----------------------------
def render_panel(moneda: str):
    st.subheader(f"💱 {moneda}")

    dff = dff_base[dff_base["MONEDA"] == moneda].copy()

    c1, c2 = st.columns([2, 1])

    # Histórico positivo
    with c1:
        ts = dff.groupby("FECHA")["Valor"].sum().reset_index().sort_values("FECHA")
        ts["Monto"] = -ts["Valor"]  # egresos positivos
        fig = px.line(ts, x="FECHA", y="Monto", title=f"Histórico ({moneda}) — egresos en positivo")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.metric("Registros (filtrados)", len(dff))
        st.metric("Suma total (filtrada)", f"{(-dff['Valor'].sum()):,.2f}")
        st.write("Muestra (formato largo):")
        st.dataframe(dff.sort_values("FECHA").tail(15), use_container_width=True)

    st.write("")

    # Forecast
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


# -----------------------------
# Render: PEN y USD
# -----------------------------
render_panel("PEN")
st.divider()
render_panel("USD")
