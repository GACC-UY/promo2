# app.py
import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import re
import unicodedata
import altair as alt

# ---------------------------------------------------------
# Page config
# ---------------------------------------------------------
st.set_page_config(page_title="Reinvestment Promotion Builder", layout="wide")
st.title("🎰 Casino Reinvestment Promotion Builder")
st.write("Upload data, set percentages and rules, generate promotion layout.")

# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------
def clean_column_name(col):
    """Normalize column names: remove accents, spaces -> _, remove punctuation."""
    if not isinstance(col, str):
        col = str(col)
    col = col.strip()
    col = "".join(c for c in unicodedata.normalize("NFKD", col) if not unicodedata.combining(c))
    col = col.replace(" ", "_")
    col = re.sub(r"[^0-9a-zA-Z_]", "", col)
    col = re.sub(r"_+", "_", col)
    return col.strip("_")


def fix_excel_headers(df, min_nonnull_for_header: int = 3):
    """Find first row with at least `min_nonnull_for_header` values and use as header; normalize."""
    header_row = None
    for i, row in df.iterrows():
        if row.notnull().sum() >= min_nonnull_for_header:
            header_row = i
            break
    if header_row is None:
        header_row = 0
    raw_headers = df.iloc[header_row].astype(str).tolist()
    cleaned_headers = [clean_column_name(h) for h in raw_headers]
    df_fixed = df.iloc[header_row + 1 :].reset_index(drop=True)
    df_fixed.columns = cleaned_headers
    return df_fixed


def fix_duplicate_columns(df):
    """Append _2, _3 ... to duplicate column names."""
    cols = df.columns.tolist()
    counts = {}
    new_cols = []
    for col in cols:
        if col not in counts:
            counts[col] = 1
            new_cols.append(col)
        else:
            counts[col] += 1
            new_cols.append(f"{col}_{counts[col]}")
    df.columns = new_cols
    return df


def normalize_gestion_value(val):
    """Normalize a Gestion value into uppercase underscore form for mapping."""
    s = str(val).strip()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^0-9A-Za-z_]", "", s)
    return s.upper()

# ---------------------------------------------------------
# Calculation function (updated rules)
# ---------------------------------------------------------
def apply_reinvestment(df, pct_dict, min_wallet, cap):
    df = df.copy()

    # Required columns that must be present in the cleaned dataframe
    required_cols = [
        "Gestion", "NG", "Visitas", "TeoricoNeto", "WinTotalNeto",
        "WxV", "Visitas_Est", "Trip_Esperado", "Pais",
        # New ingestion columns:
        "Pot_Trip", "Pot_Visita", "Comps", "Promo2", "MaxCategHist"
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"Missing columns required for calculations: {missing}")
        return None

    # ---------- Normalize numeric columns ----------
    num_cols = ["TeoricoNeto", "WinTotalNeto", "WxV", "Visitas", "Visitas_Est",
                "Trip_Esperado", "Pot_Trip", "Pot_Visita", "Comps", "Promo2"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # ---------- Potencial (kept for KPIs) ----------
    df["Potencial"] = df[["TeoricoNeto", "WinTotalNeto"]].max(axis=1)

    # ---------- Normalize Gestion into a key for mapping ----------
    df["GESTION_KEY"] = df["Gestion"].apply(normalize_gestion_value)

    # ---------- Determine pot_used based on GESTION ----------
    # URY local/resto use Pot_Visita; ARG/BRA/OTROS use Pot_Trip
    # Expect normalized keys: 'URY_LOCAL', 'URY_RESTO', 'ARG', 'BRA', 'OTROS'
    def select_pot(row):
        key = row["GESTION_KEY"]
        if key in ("URY_LOCAL", "URY_RESTO"):
            return row["Pot_Visita"]
        else:
            # default to Pot_Trip for ARG, BRA, OTROS and any other
            return row["Pot_Trip"]

    df["pot_used"] = df.apply(select_pot, axis=1)

    # ---------- pct mapping: keys must be normalized similarly ----------
    # Convert pct_dict keys to normalized uppercase keys for robustness
    pct_norm = {}
    for k, v in pct_dict.items():
        nk = normalize_gestion_value(k)
        pct_norm[nk] = v

    df["pct"] = df["GESTION_KEY"].map(pct_norm).fillna(0.0)

    # ---------- Initial eligibility (NG == 0) ----------
    df["eligible"] = (pd.to_numeric(df["NG"], errors="coerce").fillna(0) == 0)

    # ---------- Compute raw reinvestment ----------
    df["reinvestment_raw"] = df["pot_used"] * df["pct"]

    # ---------- Apply minimum per wallet (but only for eligible) ----------
    df["reinvestment"] = 0.0
    eligible_mask = df["eligible"] == True
    df.loc[eligible_mask, "reinvestment"] = df.loc[eligible_mask, "reinvestment_raw"]

    # apply min per wallet where applicable
    df.loc[eligible_mask & (df["reinvestment"] < min_wallet), "reinvestment"] = min_wallet

    # ---------- Apply cap ----------
    df.loc[eligible_mask, "reinvestment"] = df.loc[eligible_mask, "reinvestment"].clip(upper=cap)

    # ---------- New ineligibility rules ----------
    # 1) Comps > 200 -> not eligible
    df.loc[df["Comps"] > 200, "eligible"] = False
    df.loc[df["Comps"] > 200, "reinvestment"] = 0
    df.loc[df["Comps"] > 200, "Rango_Reinv"] = "NO APLICA"

    # 2) Reinvestment must be > Promo2, otherwise not eligible
    mask_leq_promo2 = df["reinvestment"] <= df["Promo2"]
    df.loc[mask_leq_promo2, "eligible"] = False
    df.loc[mask_leq_promo2, "reinvestment"] = 0
    df.loc[mask_leq_promo2, "Rango_Reinv"] = "NO APLICA"

    # 3) Reinvestment > WxV -> not eligible (over 100% rule)
    df["WxV"] = pd.to_numeric(df["WxV"], errors="coerce").fillna(0)
    mask_over_wxv = df["reinvestment"] > df["WxV"]
    df.loc[mask_over_wxv, "eligible"] = False
    df.loc[mask_over_wxv, "reinvestment"] = 0
    df.loc[mask_over_wxv, "Rango_Reinv"] = "NO APLICA"

    # ---------- Trips calculation ----------
    df["Trips_Calc"] = np.where(df["Visitas"] > 0, df["Visitas"] / 3.0, df["Visitas_Est"] / 3.0)

    # ---------- Rango_Reinv classification (only for remaining reinvestments) ----------
    conditions = [
        df["reinvestment"] == 0,
        (df["WxV"] > 0) & (df["reinvestment"] <= df["WxV"] * 0.5),
        (df["WxV"] > 0) & (df["reinvestment"] <= df["WxV"]),
    ]
    choices = ["NO APLICA", "<50%", "50-100%"]
    df["Rango_Reinv"] = np.select(conditions, choices, default="NO APLICA")

    # ---------- Round money columns ----------
    df["reinvestment"] = df["reinvestment"].round(2)
    df["pot_used"] = df["pot_used"].round(2)
    df["reinvestment_raw"] = df["reinvestment_raw"].round(2)

    return df

# ---------------------------------------------------------
# UI: Sidebar inputs
# ---------------------------------------------------------
st.sidebar.header("Reinvestment Parameters")

st.sidebar.subheader("Percentages (enter values in %) - map to Gestion values")
# Default keys are human-readable; they will be normalized internally
pct_arg = st.sidebar.number_input("ARG %", min_value=0.0, max_value=100.0, value=10.0)
pct_bra = st.sidebar.number_input("BRA %", min_value=0.0, max_value=100.0, value=15.0)
pct_ury = st.sidebar.number_input("URY (local/resto) %", min_value=0.0, max_value=100.0, value=8.0)
pct_otros = st.sidebar.number_input("OTROS %", min_value=0.0, max_value=100.0, value=5.0)

# Build pct dict with the raw labels you use in Excel; we'll normalize keys internally
pct_dict = {
    "ARG": pct_arg / 100.0,
    "BRA": pct_bra / 100.0,
    "Ury Local": pct_ury / 100.0,
    "URY Resto": pct_ury / 100.0,
    "Otros": pct_otros / 100.0
}

st.sidebar.subheader("Reinvestment Rules")
min_per_wallet = st.sidebar.number_input("Minimum Reinvestment Per Wallet", min_value=0.0, value=100.0)
cap_value = st.sidebar.number_input("Accumulated Cap (max per wallet)", min_value=0.0, value=20000.0)

# ---------------------------------------------------------
# Load data (Excel or CSV)
# ---------------------------------------------------------
st.subheader("📥 Load Base Data (CSV or XLSX)")
uploaded_file = st.file_uploader("Upload Source (CSV or XLSX)", type=["csv", "xlsx"])

df_source = None

if uploaded_file is not None:
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            raw_df = pd.read_csv(uploaded_file, header=None)
        else:
            # read without header so we detect header row ourselves
            raw_df = pd.read_excel(uploaded_file, header=None)
    except Exception as exc:
        st.error(f"Error reading file: {exc}")
        raw_df = None

    if raw_df is not None:
        # Fix headers, dedupe, and make Arrow-safe
        df_fixed = fix_excel_headers(raw_df, min_nonnull_for_header=3)
        df_fixed = fix_duplicate_columns(df_fixed)

        # Convert all object columns to string to avoid Arrow mixed-type errors,
        # but keep numeric columns convertible later in apply_reinvestment.
        for col in df_fixed.columns:
            if df_fixed[col].dtype == "object":
                # keep actual numeric-looking strings — they'll be coerced later
                df_fixed[col] = df_fixed[col].astype(str)

        df_source = df_fixed.copy()
        st.success("✅ File loaded and columns normalized")
        with st.expander("Detected columns"):
            st.write(list(df_source.columns))
        st.dataframe(df_source.head(100), width="stretch")

# ---------------------------------------------------------
# Run calculation + KPIs + Charts + Export
# ---------------------------------------------------------
st.subheader("Generate Promotion")

if df_source is None:
    st.info("Upload a file to calculate promotions.")
else:
    if st.button("Generate Promotion Layout"):
        df_result = apply_reinvestment(df_source, pct_dict, min_per_wallet, cap_value)
        if df_result is None:
            st.error("Calculation aborted due to missing columns.")
        else:
            st.success("✅ Promotion layout calculated")
            st.dataframe(df_result, width="stretch")

            # ----------------- Summary KPIs -----------------
            with st.expander("📊 Summary KPIs"):
                total_reinv = df_result["reinvestment"].sum()
                total_eligible = int(df_result["eligible"].sum())

                st.metric("Total Reinvestment (sum)", f"{total_reinv:,.2f}")
                st.metric("Eligible Players", f"{total_eligible:,}")

                # Reinvestment by Pais
                st.subheader("Reinvestment by País")
                if "Pais" in df_result.columns:
                    kpi_pais = df_result.groupby("Pais")["reinvestment"].sum().reset_index()
                    st.dataframe(kpi_pais, width="stretch")

                    # Pie chart
                    chart_pais = (
                        alt.Chart(kpi_pais)
                        .mark_arc()
                        .encode(
                            theta="reinvestment:Q",
                            color="Pais:N",
                            tooltip=["Pais", "reinvestment"]
                        )
                        .properties(width=400, height=400)
                    )
                    st.altair_chart(chart_pais)
                else:
                    st.write("Column 'Pais' not found for country KPIs.")

                # Reinvestment by Gestion
                st.subheader("Reinvestment by Gestión")
                kpi_gestion = df_result.groupby("Gestion")["reinvestment"].sum().reset_index()
                st.dataframe(kpi_gestion, width="stretch")

                chart_gestion = (
                    alt.Chart(kpi_gestion)
                    .mark_arc()
                    .encode(
                        theta="reinvestment:Q",
                        color="Gestion:N",
                        tooltip=["Gestion", "reinvestment"]
                    )
                    .properties(width=400, height=400)
                )
                st.altair_chart(chart_gestion)

                # Additional KPIs
                st.subheader("Additional KPIs")
                df_result["Reinv_pct_Teorico"] = np.where(
                    df_result["TeoricoNeto"] > 0,
                    df_result["reinvestment"] / df_result["TeoricoNeto"],
                    0
                )
                df_result["Reinv_pct_Actual"] = np.where(
                    df_result["WinTotalNeto"] > 0,
                    df_result["reinvestment"] / df_result["WinTotalNeto"],
                    0
                )

                extra_kpis = {
                    "Avg Reinv % over Teórico": df_result["Reinv_pct_Teorico"].mean(),
                    "Avg Reinv % over Actual": df_result["Reinv_pct_Actual"].mean(),
                    "Avg Reinv per Visit": (df_result["reinvestment"] / df_result["Visitas"].replace(0, np.nan)).mean(),
                    "Eligibility Rate (%)": float(df_result["eligible"].mean() * 100),
                    "Excluded Players (NG or >100% or Comps>200 or Promo2)": int(len(df_result) - df_result["eligible"].sum()),
                    "Average WxV": df_result["WxV"].mean(),
                    "Average Potencial": df_result["Potencial"].mean(),
                    "Average Pot_Visita": df_result["Pot_Visita"].mean() if "Pot_Visita" in df_result.columns else None,
                    "Average Pot_Trip": df_result["Pot_Trip"].mean() if "Pot_Trip" in df_result.columns else None,
                    "Average Trip Win": df_result["Trip_Esperado"].mean()
                }

                st.json(extra_kpis)

            # ----------------- Export Excel -----------------
            def to_excel_bytes(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Promotion")
                return output.getvalue()

            excel_bytes = to_excel_bytes(df_result)
            st.download_button(
                "⬇️ Download Promotion Excel",
                data=excel_bytes,
                file_name="promotion_layout.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
