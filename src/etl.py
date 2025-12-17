from __future__ import annotations

import re
from pathlib import Path
import pandas as pd

BANKS_ALLOWED = {"BCP", "SCOTIABANK", "SANTANDER", "INTERBANK", "TOTAL"}
CCY_ALLOWED = {"PEN", "USD"}

FINAL_COLS = [
    "BCP_PEN", "BCP_USD",
    "SCOTIABANK_PEN", "SCOTIABANK_USD",
    "SANTANDER_PEN", "SANTANDER_USD",
    "INTERBANK_PEN", "INTERBANK_USD",
    "TOTAL_PEN", "TOTAL_USD",
]


def _extract_date_from_path(path: Path) -> pd.Timestamp | None:
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", str(path))
    if not m:
        return None
    dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
    return pd.to_datetime(f"{dd}/{mm}/{yyyy}", dayfirst=True, errors="coerce")


def _coerce_money(x) -> float:
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


def _read_total_a_pagar_wide(xlsx_path: Path, sheet_name: str = "RESUMEN") -> dict | None:
    """
    Lee 'RESUMEN' y devuelve dict wide (BCP_PEN, ..., TOTAL_USD),
    robusto a celdas combinadas (merge) usando forward-fill en headers.
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

    row_idx = df.index[mask][0]
    if row_idx < 2:
        return None

    hdr_bank = df.loc[row_idx - 2].copy()
    hdr_ccy = df.loc[row_idx - 1].copy()
    values = df.loc[row_idx]

    # ✅ Forward-fill para headers con celdas combinadas
    hdr_bank = hdr_bank.ffill()
    hdr_ccy = hdr_ccy.ffill()

    wide = {}
    for col in df.columns:
        bank_raw = hdr_bank[col]
        ccy_raw = hdr_ccy[col]

        bank = str(bank_raw).strip().upper()
        ccy = str(ccy_raw).strip().upper()

        # Normalizaciones típicas
        bank = bank.replace("\n", " ")
        ccy = ccy.replace("\n", " ")

        # Aceptar bancos aunque vengan con extra texto (ej: "SCOTIABANK S.A.")
        if "BCP" in bank:
            bank = "BCP"
        elif "SCOTIABANK" in bank:
            bank = "SCOTIABANK"
        elif "SANTANDER" in bank:
            bank = "SANTANDER"
        elif "INTERBANK" in bank:
            bank = "INTERBANK"
        elif "TOTAL" in bank:
            bank = "TOTAL"

        if bank in BANKS_ALLOWED and ccy in CCY_ALLOWED:
            wide[f"{bank}_{ccy}"] = _coerce_money(values[col])

    # Si no detectó nada, devolvemos None para que NO rellene con ceros silenciosamente
    if not wide:
        return None

    for k in FINAL_COLS:
        wide.setdefault(k, 0.0)

    return wide



def load_payments_folder(base_folder: str | Path) -> pd.DataFrame:
    base = Path(base_folder)
    files = [p for p in base.rglob("*.xlsx") if not p.name.startswith("~$")]

    rows = []
    for f in files:
        fecha = _extract_date_from_path(f)
        if fecha is None or pd.isna(fecha):
            continue

        wide_vals = _read_total_a_pagar_wide(f, sheet_name="RESUMEN")
        if wide_vals is None:
            continue

        wide_vals["FECHA"] = fecha
        rows.append(wide_vals)

    if not rows:
        return pd.DataFrame(columns=["FECHA", "BANCO", "MONEDA", "Valor", "DiaNombre"])

    wide_df = pd.DataFrame(rows).sort_values("FECHA")

    long_df = wide_df.melt(id_vars=["FECHA"], var_name="Atributo", value_name="Valor")

    long_df[["BANCO", "MONEDA"]] = long_df["Atributo"].str.split("_", n=1, expand=True)
    long_df = long_df.drop(columns=["Atributo"])

    long_df["DiaNombre"] = long_df["FECHA"].dt.day_name()

    return long_df


def load_payments_folders(base_folders: list[str | Path]) -> pd.DataFrame:
    dfs = []
    for folder in base_folders:
        df = load_payments_folder(folder)
        if not df.empty:
            dfs.append(df)

    if not dfs:
        return pd.DataFrame(columns=["FECHA", "BANCO", "MONEDA", "Valor", "DiaNombre"])

    out = pd.concat(dfs, ignore_index=True).sort_values("FECHA")
    return out
