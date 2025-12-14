import streamlit as st
import plotly.express as px

from src.etl import load_payments_folder
from src.forecast import prepare_series, forecast_holt_winters, forecast_sarima


st.set_page_config(page_title="Pagos - Forecast", layout="wide")
st.title("📈 Programación de Pagos 2025 — Dashboard & Forecast")


with st.sidebar:
    st.header("Fuente de datos")
    base_folder = st.text_input(
        "Carpeta base (equivalente a Folder.Files de Power BI)",
        value=r"C:\Users\MARKS\OneDrive - La Viga S.A\Finanzas - PAGOS CUARENTENA\PROGRAMACIÓN DE PAGOS\2025"
    )

    st.divider()
    st.header("Forecasting")
    model_name = st.selectbox("Modelo", ["Holt-Winters", "SARIMA"])
    steps = st.number_input("Horizonte (semanas)", min_value=4, max_value=52, value=10, step=1)


@st.cache_data(show_spinner=True)
def cached_load(folder: str):
    return load_payments_folder(folder)


df = cached_load(base_folder)

if df.empty:
    st.warning("No se encontraron datos. Revisa: ruta, archivos .xlsx y hoja 'RESUMEN'.")
    st.stop()


# Opciones para filtros
bancos = sorted(df["BANCO"].dropna().unique().tolist())
moedas = sorted(df["MONEDA"].dropna().unique().tolist())
dias = sorted(df["DiaNombre"].dropna().unique().tolist())

with st.sidebar:
    st.header("Filtros")
    banco_sel = st.multiselect("Banco", bancos, default=bancos)
    moneda_sel = st.multiselect("Moneda", moedas, default=moedas)
    dia_sel = st.multiselect("Día de semana", dias, default=dias)


dff = df[
    df["BANCO"].isin(banco_sel)
    & df["MONEDA"].isin(moneda_sel)
    & df["DiaNombre"].isin(dia_sel)
].copy()


col1, col2 = st.columns([2, 1])

with col1:
    ts = dff.groupby("FECHA")["Valor"].sum().reset_index().sort_values("FECHA")
    fig = px.line(ts, x="FECHA", y="Valor", title="Serie histórica (suma según filtros)")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.metric("Registros (filtrados)", len(dff))
    st.metric("Suma total (filtrada)", f"{dff['Valor'].sum():,.2f}")
    st.write("Muestra (formato largo):")
    st.dataframe(dff.sort_values("FECHA").tail(20), use_container_width=True)


st.subheader("🔮 Forecast")

series = prepare_series(dff)

if len(series) < 8:
    st.info("Muy pocos puntos para un forecast estable. Prueba filtrar por un solo día (Tuesday o Friday) y por banco/moneda.")
else:
    if model_name == "Holt-Winters":
        y, fcst = forecast_holt_winters(series, steps=int(steps))
    else:
        y, fcst = forecast_sarima(series, steps=int(steps))

    # Dataset para gráfico combinado
    hist = y.reset_index()
    hist.columns = ["FECHA", "Valor"]
    hist["Tipo"] = "Histórico"

    pred = fcst.reset_index()
    pred.columns = ["FECHA", "Valor"]
    pred["Tipo"] = "Forecast"

    plot_df = hist._append(pred, ignore_index=True)
    fig2 = px.line(plot_df, x="FECHA", y="Valor", color="Tipo", title=f"Forecast — {model_name}")
    st.plotly_chart(fig2, use_container_width=True)