import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import re
import unicodedata
redeploy-test-1
# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="Reinvestment Promotion Builder",
    layout="wide"
)

st.title("🎰 Casino Reinvestment Promotion Builder")
st.write("Set percentages, minimums, and generate promotion layout.")

# ---------------------------------------------------------
# Helper functions: header detection, normalization, dedupe
# ---------------------------------------------------------
def clean_column_name(col):
    """Normalize column names: remove accents, spaces -> _, remove punctuation."""
    if not isinstance(col, str):
        col = str(col)

    col = col.strip()

    # Remove accents
    col = "".join(
        c for c in unicodedata.normalize('NFKD', col)
        if not unicodedata.combining(c)
    )

    # Replace spaces with underscore
    col = col.replace(" ", "_")

    # Remove chars other than alnum and underscore
    col = re.sub(r"[^0-9a-zA-Z_]", "", col)

    # Collapse multiple underscores
    col = re.sub(r"_+", "_", col)

    return col.strip("_")


def fix_excel_headers(df, min_nonnull_for_header: int = 3):
    """Detect first valid header row and normalize column names."""
    header_row = None
    for i, row in df.iterrows():
        if row.notnull().sum() >= min_nonnull_for_header:
            header_row = i
            break

    if header_row is None:
        header_row = 0

    raw_headers = df.iloc[header_row].astype(str).tolist()
    cleaned_headers = [clean_column_name(h) for h in raw_headers]

    df_fixed = df.iloc[header_row + 1:].reset_index(drop=True)
    df_fixed.columns = cleaned_headers

    return df_fixed


def fix_duplicate_columns(df):
    """Make column names unique by appending _2, _3, ..."""
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

# ---------------------------------------------------------
# Calculation function (uses Gestion as segment)
# ---------------------------------------------------------
def apply_reinvestment(df, pct_dict, min_wallet, cap):
    df = df.copy()

    # Required columns (normalized)
    required_cols = [
        "Gestion",
        "NG",
        "Visitas",
        "TeoricoNeto",
        "WinTotalNeto",
        "WxV",
        "Visitas_Est",
        "Trip_Esperado",
        "Pais"
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"Missing columns required for calculations: {missing}")
        return None

    # ---------------------------------------------------------
    # Calculate Potencial = max(TeoricoNeto, WinTotalNeto)
    # ---------------------------------------------------------
    df["TeoricoNeto"] = pd.to_numeric(df["TeoricoNeto"], errors="coerce").fillna(0)
    df["WinTotalNeto"] = pd.to_numeric(df["WinTotalNeto"], errors="coerce").fillna(0)

    df["Potencial"] = df[["TeoricoNeto", "WinTotalNeto"]].max(axis=1)

    # Ensure numeric columns
    numeric_cols = ["Potencial", "Visitas", "TeoricoNeto", "WinTotalNeto", 
                    "WxV", "Visitas_Est", "Trip_Esperado"]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # Eligibility step 1: NG filter
    df["eligible"] = (pd.to_numeric(df["NG"], errors="coerce").fillna(0) == 0)

    # Base reinvestment initialization
    df["reinvestment"] = 0.0

    # Map % per segment
    df["pct"] = df["Gestion"].map(pct_dict).fillna(0.0)

    # Base reinvestment for eligible players
    eligible_mask = df["eligible"] == True
    df.loc[eligible_mask, "reinvestment"] = df.loc[eligible_mask, "Potencial"] * df.loc[eligible_mask, "pct"]

    # Minimum per wallet
    df.loc[eligible_mask & (df["reinvestment"] < min_wallet), "reinvestment"] = min_wallet

    # Apply global cap
    df.loc[eligible_mask, "reinvestment"] = df.loc[eligible_mask, "reinvestment"].clip(upper=cap)

    # ---------------------------------------------------------
    # Eligibility step 2: >100% of WxV → ineligible
    # ---------------------------------------------------------
    df["WxV"] = pd.to_numeric(df["WxV"], errors="coerce").fillna(0)
    over_100_mask = df["reinvestment"] > df["WxV"]

    df.loc[over_100_mask, "eligible"] = False
    df.loc[over_100_mask, "reinvestment"] = 0
    df.loc[over_100_mask, "Rango_Reinv"] = "NO APLICA"

    # ---------------------------------------------------------
    # Expected Trips (3-day window)
    # ---------------------------------------------------------
    df["Trips_Calc"] = np.where(
        df["Visitas"] > 0,
        df["Visitas"] / 3.0,
        df["Visitas_Est"] / 3.0
    )

    # ---------------------------------------------------------
    # Rango Reinversion
    # ---------------------------------------------------------
    conditions = [
        df["reinvestment"] == 0,
        (df["WxV"] > 0) & (df["reinvestment"] <= df["WxV"] * 0.5),
        (df["WxV"] > 0) & (df["reinvestment"] <= df["WxV"]),
    ]
    choices = ["NO APLICA", "<50%", "50-100%"]

    df["Rango_Reinv"] = np.select(conditions, choices, default="NO APLICA")

    # Round visualization
    df["reinvestment"] = df["reinvestment"].round(2)

    return df

# ---------------------------------------------------------
# SIDEBAR INPUTS (UI)
# ---------------------------------------------------------
st.sidebar.header("🔧 Input Parameters")

st.sidebar.subheader("Reinvestment Percentages (%) - mapped to 'Gestion' values")
pct_arg = st.sidebar.number_input("ARG %", min_value=0.0, max_value=100.0, value=10.0)
pct_bra = st.sidebar.number_input("BRA %", min_value=0.0, max_value=100.0, value=15.0)
pct_ury_local = st.sidebar.number_input("URY Local %", min_value=0.0, max_value=100.0, value=8.0)
pct_ury_resto = st.sidebar.number_input("URY Resto %", min_value=0.0, max_value=100.0, value=5.0)

pct_dict = {
    "ARG": pct_arg / 100.0,
    "BRA": pct_bra / 100.0,
    "URY_Local": pct_ury_local / 100.0,
    "URY_Resto": pct_ury_resto / 100.0,
}

st.sidebar.subheader("Reinvestment Rules")
min_per_wallet = st.sidebar.number_input("Minimum Reinvestment Per Wallet", min_value=0.0, value=100.0)
cap_value = st.sidebar.number_input("Accumulated Cap (max per wallet)", min_value=0.0, value=20000.0)

# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------
st.subheader("📥 Load Base Data")
uploaded_file = st.file_uploader("Upload Source Excel (.xlsx)", type=["xlsx"])

df_source = None

if uploaded_file is not None:
    try:
        raw_df = pd.read_excel(uploaded_file, header=None)
    except Exception as exc:
        st.error(f"Error reading Excel file: {exc}")
        raw_df = None

    if raw_df is not None:

        # 1. Fix header row
        df_fixed = fix_excel_headers(raw_df, min_nonnull_for_header=3)

        # 2. Dedupe column names
        df_fixed = fix_duplicate_columns(df_fixed)

        # 3. Make object columns Arrow-safe
        for col in df_fixed.columns:
            if df_fixed[col].dtype == "object":
                df_fixed[col] = df_fixed[col].astype(str)

        df_source = df_fixed.copy()

        st.success("✅ Excel loaded, headers fixed, normalized, duplicates removed")

        with st.expander("Preview cleaned columns"):
            st.write(list(df_source.columns))

        st.dataframe(df_source.head(200), width='stretch')

# ---------------------------------------------------------
# RUN CALCULATION / EXPORT
# ---------------------------------------------------------
st.subheader("Generate Promotion")

if df_source is None:
    st.info("Upload an Excel file to begin. The app expects 'Gestion', 'NG', 'Visitas', and win columns.")
else:
    if st.button("Generate Promotion Layout"):
        df_result = apply_reinvestment(df_source, pct_dict, min_per_wallet, cap_value)

        if df_result is not None:

            st.success("✅ Promotion Layout Generated")
            st.dataframe(df_result, width='stretch')

            # ---------------------------------------------------------
            # SUMMARY KPIs (EXPANDED)
            # ---------------------------------------------------------
            with st.expander("📊 Summary KPIs"):

                total_reinv = df_result["reinvestment"].sum()
                total_eligible = int(df_result["eligible"].sum())

                st.metric("Total Reinvestment (sum)", f"{total_reinv:,.2f}")
                st.metric("Eligible Players", f"{total_eligible:,}")

                # Reinvestment per País
                st.subheader("Reinvestment by País")
                kpi_pais = df_result.groupby("Pais")["reinvestment"].sum().reset_index()
                st.dataframe(kpi_pais, width='stretch')

                # Reinvestment per Gestion
                st.subheader("Reinvestment by Gestión")
                kpi_gestion = df_result.groupby("Gestion")["reinvestment"].sum().reset_index()
                st.dataframe(kpi_gestion, width='stretch')

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
                    "Avg Reinvestment % over Teórico": df_result["Reinv_pct_Teorico"].mean(),
                    "Avg Reinvestment % over Actual": df_result["Reinv_pct_Actual"].mean(),
                    "Avg Reinvestment per Visit": (df_result["reinvestment"] / df_result["Visitas"].replace(0, np.nan)).mean(),
                    "Eligibility Rate (%)": df_result["eligible"].mean() * 100,
                    "Excluded Players (NG or >100%)": len(df_result) - df_result["eligible"].sum(),
                    "Average WxV": df_result["WxV"].mean(),
                    "Average Potencial": df_result["Potencial"].mean(),
                    "Average Trip Win": df_result["Trip_Esperado"].mean(),
                }

                st.json(extra_kpis)

            # ---------------------------------------------------------
            # DOWNLOAD OUTPUT
            # ---------------------------------------------------------
            def to_excel_bytes(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Promotion")
                return output.getvalue()

            excel_data = to_excel_bytes(df_result)

            st.download_button(
                "⬇️ Download Excel Layout",
                data=excel_data,
                file_name="promotion_layout.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
