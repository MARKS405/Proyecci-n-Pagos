from __future__ import annotations

import re
from pathlib import Path
import pandas as pd

# Orden esperado de columnas en el "TOTAL A PAGAR" (Column2..Column11)
BANK_COLS_ORDER = [
    "BCP_PEN", "BCP_USD",
    "SCOTIABANK_PEN", "SCOTIABANK_USD",
    "SANTANDER_PEN", "SANTANDER_USD",
    "INTERBANK_PEN", "INTERBANK_USD",
    "TOTAL_PEN", "TOTAL_USD",
]


# -------------------------------------------------
# Utilidades
# -------------------------------------------------
def _extract_date_from_path(path: Path) -> pd.Timestamp | None:
    """
    Busca un patrón dd.mm.yyyy en el path (carpetas o nombre del archivo).
    """
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", str(path))
    if not m:
        return None
    dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
    return pd.to_datetime(f"{dd}/{mm}/{yyyy}", dayfirst=True, errors="coerce")


def _read_total_a_pagar_row(xlsx_path: Path, sheet_name: str = "RESUMEN") -> pd.Series | None:
    """
    Lee la hoja RESUMEN (sin header) y devuelve la fila 'TOTAL A PAGAR'.
    """
    try:
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None, engine="openpyxl")
    except Exception:
        return None

    mask = df.apply(
        lambda r: r.astype(str).str.strip().str.upper().eq("TOTAL A PAGAR").any(),
        axis=1
    )
    if not mask.any():
        return None

    return df.loc[mask].iloc[0]


def _coerce_money(x) -> float:
    """
    Convierte '-', '', NaN a 0.0 y limpia separadores.
    """
    if pd.isna(x):
        return 0.0

    s = str(x).strip()
    if s in {"-", ""}:
        return 0.0

    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


# -------------------------------------------------
# ETL por carpeta individual (ej. 2024 o 2025)
# -------------------------------------------------
def load_payments_folder(base_folder: str | Path) -> pd.DataFrame:
    """
    Devuelve tabla larga:
    FECHA | BANCO | MONEDA | Valor | DiaNombre
    """
    base = Path(base_folder)
    files = [p for p in base.rglob("*.xlsx") if not p.name.startswith("~$")]

    rows = []
    for f in files:
        fecha = _extract_date_from_path(f)
        if fecha is None or pd.isna(fecha):
            continue

        total_row = _read_total_a_pagar_row(f)
        if total_row is None:
            continue

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

    long_df = wide_df.melt(
        id_vars=["FECHA"],
        var_name="Atributo",
        value_name="Valor"
    )

    long_df[["BANCO", "MONEDA"]] = long_df["Atributo"].str.split("_", n=1, expand=True)
    long_df = long_df.drop(columns=["Atributo"])

    long_df["DiaNombre"] = long_df["FECHA"].dt.day_name()

    return long_df


# -------------------------------------------------
# ETL multi-año (2024 + 2025)
# -------------------------------------------------
def load_payments_folders(base_folders: list[str | Path]) -> pd.DataFrame:
    """
    Carga y concatena varias carpetas (ej. ['2024', '2025']).
    """
    dfs = []
    for folder in base_folders:
        df = load_payments_folder(folder)
        if not df.empty:
            dfs.append(df)

    if not dfs:
        return pd.DataFrame(columns=["FECHA", "BANCO", "MONEDA", "Valor", "DiaNombre"])

    out = pd.concat(dfs, ignore_index=True)
    out = out.sort_values("FECHA")
    return out
