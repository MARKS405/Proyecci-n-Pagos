from __future__ import annotations

import re
from pathlib import Path
import pandas as pd

# Orden esperado de columnas en el "TOTAL A PAGAR" (equivalente a Column2..Column11)
BANK_COLS_ORDER = [
    "BCP_PEN", "BCP_USD",
    "SCOTIABANK_PEN", "SCOTIABANK_USD",
    "SANTANDER_PEN", "SANTANDER_USD",
    "INTERBANK_PEN", "INTERBANK_USD",
    "TOTAL_PEN", "TOTAL_USD",
]


def _extract_date_from_path(path: Path) -> pd.Timestamp | None:
    """
    Busca un patrón dd.mm.yyyy en el path (carpetas o nombre del archivo).
    Ej: ...\\DICIEMBRE\\12.12.2025\\PAGOS FINANZAS 12.12.2025 Vf.xlsx
    """
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", str(path))
    if not m:
        return None
    dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
    return pd.to_datetime(f"{dd}/{mm}/{yyyy}", dayfirst=True, errors="coerce")


def _read_total_a_pagar_row(xlsx_path: Path, sheet_name: str = "RESUMEN") -> pd.Series | None:
    """
    Lee la hoja RESUMEN sin header (header=None) y devuelve la fila donde aparece 'TOTAL A PAGAR'.
    """
    try:
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None, engine="openpyxl")
    except Exception:
        return None

    # Detecta fila donde ANY celda == "TOTAL A PAGAR" (limpiando espacios y mayúsculas)
    mask = df.apply(
        lambda r: r.astype(str).str.strip().str.upper().eq("TOTAL A PAGAR").any(),
        axis=1
    )
    if not mask.any():
        return None

    return df.loc[mask].iloc[0]


def _coerce_money(x) -> float:
    """
    Convierte valores tipo '-', '', NaN a 0.0.
    Limpia separadores típicos y convierte a float.
    """
    if pd.isna(x):
        return 0.0

    s = str(x).strip()
    if s in {"-", ""}:
        return 0.0

    # Si el Excel viene con comas de miles, las removemos
    s = s.replace(",", "")

    try:
        return float(s)
    except ValueError:
        return 0.0


def load_payments_folder(base_folder: str | Path) -> pd.DataFrame:
    """
    Devuelve tabla en formato largo:
    FECHA | BANCO | MONEDA | Valor | DiaNombre
    """
    base = Path(base_folder)
    files = [p for p in base.rglob("*.xlsx") if not p.name.startswith("~$")]

    rows = []
    for f in files:
        fecha = _extract_date_from_path(f)
        if fecha is None or pd.isna(fecha):
            continue

        total_row = _read_total_a_pagar_row(f, sheet_name="RESUMEN")
        if total_row is None:
            continue

        # Equivalente a quedarte con Column2..Column11 (10 columnas)
        # En python (0-based): iloc[1:11] => posiciones 1..10
        vals = total_row.iloc[1:11].tolist()
        if len(vals) != 10:
            continue

        wide = {"FECHA": fecha}
        for col_name, v in zip(BANK_COLS_ORDER, vals):
            wide[col_name] = _coerce_money(v)

        rows.append(wide)

    if not rows:
        return pd.DataFrame(columns=["FECHA", "BANCO", "MONEDA", "Valor", "DiaNombre"])

    wide_df = pd.DataFrame(rows).sort_values("FECHA")

    # Unpivot (melt) -> Atributo = "BCP_PEN", etc.
    long_df = wide_df.melt(id_vars=["FECHA"], var_name="Atributo", value_name="Valor")

    # Split por "_" -> BANCO, MONEDA
    long_df[["BANCO", "MONEDA"]] = long_df["Atributo"].str.split("_", n=1, expand=True)
    long_df = long_df.drop(columns=["Atributo"])

    # Día de la semana (en inglés por defecto: Tuesday, Friday)
    long_df["DiaNombre"] = long_df["FECHA"].dt.day_name()

    return long_df