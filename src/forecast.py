from __future__ import annotations
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX


def prepare_series(df: pd.DataFrame, freq: str | None = "D") -> pd.Series:
    """
    df ya filtrado por BANCO/MONEDA/DiaNombre.
    Convierte Valor (egreso negativo) a MONTO positivo y agrega por FECHA.
    Si freq != None, reindexa a esa frecuencia y completa faltantes con 0.
    """
    dff = df.copy()

    # MONTO positivo para modelar magnitud de egresos
    dff["MONTO"] = (-dff["Valor"]).astype(float)

    s = dff.groupby("FECHA")["MONTO"].sum().sort_index()
    s.index = pd.to_datetime(s.index)

    if freq is not None:
        idx = pd.date_range(start=s.index.min(), end=s.index.max(), freq=freq)
        s = s.reindex(idx, fill_value=0.0)

    return s


def forecast_holt_winters(series: pd.Series, steps: int = 30, seasonal_periods: int | None = 7):
    """
    Holt-Winters:
    - Diseñado para serie diaria si seasonal_periods=7
    - Si no hay datos suficientes para estacionalidad, cae a modelo sin estacionalidad
    """
    y = series.copy()

    n = len(y)
    if seasonal_periods is not None and n >= 2 * seasonal_periods:
        model = ExponentialSmoothing(
            y,
            trend="add",
            seasonal="add",
            seasonal_periods=seasonal_periods
        ).fit(optimized=True)
        return y, model.forecast(steps)

    # fallback sin estacionalidad
    model = ExponentialSmoothing(
        y,
        trend="add",
        seasonal=None
    ).fit(optimized=True)
    return y, model.forecast(steps)


def forecast_sarima(series: pd.Series, steps: int = 30, s: int = 7):
    """
    SARIMA para serie diaria:
    - s=7 captura patrón semanal
    """
    y = series.copy()

    model = SARIMAX(
        y,
        order=(1, 1, 1),
        seasonal_order=(1, 1, 1, s),
        enforce_stationarity=False,
        enforce_invertibility=False
    ).fit(disp=False)

    fcst = model.get_forecast(steps=steps).predicted_mean
    return y, fcst
