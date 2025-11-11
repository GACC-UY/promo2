import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import altair as alt
import unicodedata
import re

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="Reinvestment Promotion Builder", layout="wide")
st.title("🎰 Casino Reinvestment Promotion Builder")
st.write("Upload data, apply rules, and generate reinvestment layout.")

# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------
def clean_column_name(col):
    """Normalize column names to safe underscore format."""
    if not isinstance(col, str):
        col = str(col)
    col = col.strip()
    col = "".join(c for c in unicodedata.normalize("NFKD", col) if not unicodedata.combining(c))
    col = col.replace(" ", "_")
    col = re.sub(r"[^0-9A-Za-z_]", "", col)
    col = re.sub(r"_+", "_", col)
    return col.strip("_")


def normalize_gestion(val):
    """Normalize Gestion name to uppercase underscore."""
    if not isinstance(val, str):
        val = str(val)
    val = "".join(c for c in unicodedata.normalize("NFKD", val) if not unicodedata.combining(c))
    val = val.strip().replace(" ", "_").upper()
    return re.sub(r"[^0-9A-Za-z_]", "", val)


# ---------------------------------------------------------
# MAIN REINVESTMENT CALCULATION
# ---------------------------------------------------------
def apply_reinvestment(df, pct_dict, min_wallet, cap):
    df = df.copy()

    # -----------------------------------------------------
    # RENAME REAL INGESTION COLUMNS → INTERNAL NAMES
    # -----------------------------------------------------
    rename_map = {
        "Pot_xVisita": "WxV",
        "Prom_TeoNeto_Trip": "TeoricoNeto",
        "Prom_WinNeto_Trip": "WinTotalNeto",
        "Prom_Visita_Trip": "Visitas",
        "Pot_Trip": "Trip_Esperado",
        "Pot_Trip": "Pot_Trip",
        "Pot_xVisita": "Pot_Visita",
    }

    df = df.rename(columns=rename_map)

    # Ensure required columns exist
    required = [
        "Gestion", "NG", "Pais",
        "TeoricoNeto", "WinTotalNeto", "Visitas",
        "Pot_Trip", "Pot_Visita",
        "Comps", "Promo2"
    ]


    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"Missing required columns after renaming: {missing}")
        return None

    # Convert numeric fields
    numeric_cols = [
        "WxV", "TeoricoNeto", "WinTotalNeto", "Visitas",
        "Trip_Esperado", "Pot_Trip", "Pot_Visita",
        "Comps", "Promo2"
    ]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # Normalized Gestion (used for mapping)
    df["GESTION_KEY"] = df["Gestion"].apply(normalize_gestion)

    # -----------------------------------------------------
    # Reinvestment POT selection
    # -----------------------------------------------------
    def select_pot(row):
        if row["GESTION_KEY"] in ("URY_LOCAL", "URY_RESTO"):
            return row["Pot_Visita"]
        else:
            return row["Pot_Trip"]

    df["pot_used"] = df.apply(select_pot, axis=1)

    # -----------------------------------------------------
    # Percent mapping
    # -----------------------------------------------------
    pct_norm = {normalize_gestion(k): v for k, v in pct_dict.items()}
    df["pct"] = df["GESTION_KEY"].map(pct_norm).fillna(0.0)

    # -----------------------------------------------------
    # Eligibility stage 1 (NG)
    # -----------------------------------------------------
    df["eligible"] = (pd.to_numeric(df["NG"], errors="coerce").fillna(1) == 0)

    # -----------------------------------------------------
    # Raw reinvestment
    # -----------------------------------------------------
    df["reinvestment_raw"] = df["pot_used"] * df["pct"]

    # -----------------------------------------------------
    # Apply min wallet + cap
    # -----------------------------------------------------
    df["reinvestment"] = 0.0
    mask_elig = df["eligible"]

    df.loc[mask_elig, "reinvestment"] = df.loc[mask_elig, "reinvestment_raw"]
    df.loc[mask_elig & (df["reinvestment"] < min_wallet), "reinvestment"] = min_wallet
    df.loc[mask_elig, "reinvestment"] = df.loc[mask_elig, "reinvestment"].clip(upper=cap)

    # -----------------------------------------------------
    # New ineligibility rules
    # -----------------------------------------------------
    # 1. Comps > 200
    df.loc[df["Comps"] > 200, ["eligible", "reinvestment"]] = [False, 0]

    # 2. reinvestment <= Promo2
    df.loc[df["reinvestment"] <= df["Promo2"], ["eligible", "reinvestment"]] = [False, 0]

    # 3. reinvestment > WxV (over 100%)
    df.loc[df["reinvestment"] > df["WxV"], ["eligible", "reinvestment"]] = [False, 0]

    # -----------------------------------------------------
    # Rango Reinversion
    # -----------------------------------------------------
    conditions = [
        df["reinvestment"] == 0,
        (df["WxV"] > 0) & (df["reinvestment"] <= df["WxV"] * 0.5),
        (df["WxV"] > 0) & (df["reinvestment"] <= df["WxV"]),
    ]
    choices = ["NO APLICA", "<50%", "50-100%"]
    df["Rango_Reinv"] = np.select(conditions, choices, default="NO APLICA")

    df["reinvestment"] = df["reinvestment"].round(2)

    return df


# ---------------------------------------------------------
# SIDEBAR UI
# ---------------------------------------------------------
st.sidebar.header("Reinvestment Percentages (%)")

pct_dict = {
    "ARG": st.sidebar.number_input("ARG %", 0.0, 100.0, 10.0) / 100,
    "BRA": st.sidebar.number_input("BRA %", 0.0, 100.0, 15.0) / 100,
    "Ury Local": st.sidebar.number_input("URY Local %", 0.0, 100.0, 8.0) / 100,
    "URY Resto": st.sidebar.number_input("URY Resto %", 0.0, 100.0, 8.0) / 100,
    "Otros": st.sidebar.number_input("Otros %", 0.0, 100.0, 5.0) / 100,
}

st.sidebar.subheader("Reinvestment Rules")
min_wallet = st.sidebar.number_input("Minimum per Wallet", 0.0, value=100.0)
cap_value = st.sidebar.number_input("Cap per Wallet", 0.0, value=20000.0)


# ---------------------------------------------------------
# LOAD FILE
# ---------------------------------------------------------
st.subheader("📥 Load Data (CSV or XLSX)")
uploaded = st.file_uploader("Upload File", type=["csv", "xlsx"])

df_source = None

if uploaded:
    try:
        if uploaded.name.endswith(".csv"):
            df_raw = pd.read_csv(uploaded)
        else:
            df_raw = pd.read_excel(uploaded)
    except Exception as e:
        st.error(e)
        df_raw = None

    if df_raw is not None:
        df_source = df_raw.copy()
        df_source.columns = [clean_column_name(c) for c in df_source.columns]

        st.success("✅ File loaded successfully")
        st.dataframe(df_source.head(), width="stretch")


# ---------------------------------------------------------
# RUN CALCULATION
# ---------------------------------------------------------
if df_source is not None and st.button("Generate Promotion Layout"):

    df_result = apply_reinvestment(df_source, pct_dict, min_wallet, cap_value)

    if df_result is None:
        st.stop()

    st.success("✅ Promotion Layout Generated")
    st.dataframe(df_result, width="stretch")

    # ------------------- KPIs -------------------
    with st.expander("📊 KPIs"):

        st.subheader("Reinvestment by País")
        kpi_pais = df_result.groupby("Pais")["reinvestment"].sum().reset_index()
        st.dataframe(kpi_pais)

        chart_pais = alt.Chart(kpi_pais).mark_arc().encode(
            theta="reinvestment:Q",
            color="Pais:N",
            tooltip=["Pais", "reinvestment"]
        )
        st.altair_chart(chart_pais, use_container_width=True)

        st.subheader("Reinvestment by Gestión")
        kpi_gest = df_result.groupby("Gestion")["reinvestment"].sum().reset_index()
        st.dataframe(kpi_gest)

        chart_gest = alt.Chart(kpi_gest).mark_arc().encode(
            theta="reinvestment:Q",
            color="Gestion:N",
            tooltip=["Gestion", "reinvestment"]
        )
        st.altair_chart(chart_gest, use_container_width=True)

    # ------------------- EXPORT -------------------
    def to_excel(df):
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False)
        return output.getvalue()

    st.download_button(
        "⬇️ Download Excel",
        to_excel(df_result),
        "promotion_layout.xlsx"
    )
