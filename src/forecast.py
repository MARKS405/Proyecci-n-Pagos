from __future__ import annotations
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX


def prepare_series(df: pd.DataFrame, freq = "D") -> pd.Series:
     """
    Espera df ya filtrado por BANCO/MONEDA/DiaNombre.
    Devuelve una serie indexada por FECHA (suma por fecha).
    """
    df["MONTO"] = -df["Valor"]
    dff = df[["FECHA", "MONTO"]].copy()
    s = dff.groupby("FECHA")["MONTO"].sum().sort_index()
    s.index = pd.to_datetime(s.index)
    if freq is not None:
        idx = pd.date_range(start=s.index.min(), end=s.index.max(), freq=freq)
        s = s.reindex(idx, fill_value=0.0)

    return s


def infer_weekly_freq(series: pd.Series) -> str:
    """
    Heurística: si la moda del dayofweek es:
    - 1 => martes => W-TUE
    - 4 => viernes => W-FRI
    - otro => W
    """
    dow = series.index.dayofweek  # Mon=0 ... Sun=6
    mode = int(pd.Series(dow).mode().iloc[0])
    if mode == 1:
        return "W-TUE"
    if mode == 4:
        return "W-FRI"
    return "W"


def to_regular_weekly(series: pd.Series) -> pd.Series:
    """
    Fuerza la serie a frecuencia semanal. Si faltan semanas:
    - fillna(0.0): interpreta como "no hubo pago registrado esa semana".
    (Si en tu negocio eso no aplica, se ajusta a interpolación u otro criterio.)
    """
    freq = infer_weekly_freq(series)
    y = series.asfreq(freq)
    y = y.fillna(0.0)
    return y


def forecast_holt_winters(series: pd.Series, steps: int = 30, seasonal_periods: int = 7):
    """
    Holt-Winters aditivo con tendencia y estacionalidad semanal.
    """
    y = to_regular_weekly(series)
    model = ExponentialSmoothing(
        y,
        trend="add",
        seasonal="add",
        seasonal_periods=seasonal_periods
    ).fit(optimized=True)
    fcst = model.forecast(steps)
    return y, fcst


def forecast_sarima(series: pd.Series, steps: int = 30, s: int = 7):
    """
    SARIMA básico como punto de partida.
    Luego lo calibramos con grid search o auto_arima si deseas.
    """
    y = to_regular_weekly(series)
    model = SARIMAX(
        y,
        order=(1, 1, 1),
        seasonal_order=(1, 1, 1, s),
        enforce_stationarity=False,
        enforce_invertibility=False
    ).fit(disp=False)
    fcst = model.get_forecast(steps=steps).predicted_mean

    return y, fcst

