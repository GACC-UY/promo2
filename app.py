###############################################
# ✅ FINAL APP.PY — FULLY FIXED FOR NEW SCHEMA
###############################################

import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import altair as alt
import unicodedata
import re

###############################################
# CONFIG
###############################################
st.set_page_config(page_title="Reinvestment Promotion Builder", layout="wide")
st.title("🎰 Casino Reinvestment Promotion Builder")

###############################################
# CLEAN / NORMALIZE COLUMN NAMES
###############################################
def clean(col):
    if not isinstance(col, str):
        col = str(col)
    col = col.strip()
    col = "".join(c for c in unicodedata.normalize("NFKD", col) if not unicodedata.combining(c))
    col = re.sub(r"[^0-9A-Za-z_ ]", "", col)
    col = col.replace(" ", "_")
    col = re.sub(r"_+", "_", col)
    return col.strip("_")


###############################################
# GESTION NORMALIZER
###############################################
def normalize_gestion(val):
    if not isinstance(val, str):
        val = str(val)
    val = "".join(c for c in unicodedata.normalize("NFKD", val) if not unicodedata.combining(c))
    val = val.strip().replace(" ", "_").upper()
    return re.sub(r"[^0-9A-Za-z_]", "", val)


###############################################
# MAIN REINVESTMENT ENGINE
###############################################
def apply_reinvestment(df, pct_dict, min_wallet, cap):
    df = df.copy()

    ###########################################
    # RENAME REAL COLUMNS → INTERNAL NAMES
    ###########################################
    rename_map = {
        "Pot_xVisita": "Pot_Visita",
        "Prom_TeoNeto_Trip": "TeoricoNeto",
        "Prom_WinNeto_Trip": "WinTotalNeto",
        "Prom_Visita_Trip": "Visitas",
        "Pot_Trip": "Pot_Trip",
    }
    df = df.rename(columns=rename_map)

    ###########################################
    # CREATE WxV (potencial per visit)
    ###########################################
    if "Pot_Visita" in df.columns:
        df["WxV"] = pd.to_numeric(df["Pot_Visita"], errors="coerce").fillna(0)
    else:
        st.error("Column Pot_xVisita / Pot_Visita not found.")
        return None

    ###########################################
    # REQUIRED COLUMNS
    ###########################################
    required = [
        "Gestion", "Pais", "NG",
        "TeoricoNeto", "WinTotalNeto", "Visitas",
        "Pot_Trip", "Pot_Visita",
        "Promo2", "Comps"
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"❌ Missing required columns: {missing}")
        st.write("✅ Available columns:", list(df.columns))
        return None

    ###########################################
    # CLEAN NUMERIC COLUMNS
    ###########################################
    numeric_cols = [
        "TeoricoNeto", "WinTotalNeto", "Visitas",
        "Pot_Trip", "Pot_Visita", "WxV",
        "Promo2", "Comps"
    ]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    ###########################################
    # BASELINE KPIs
    ###########################################
    df["Potencial"] = df[["TeoricoNeto", "WinTotalNeto"]].max(axis=1)
    df["GESTION_KEY"] = df["Gestion"].apply(normalize_gestion)

    ###########################################
    # SELECT POT BASED ON GESTION
    ###########################################
    def choose_pot(row):
        if row["GESTION_KEY"] in ("URY_LOCAL", "URY_RESTO"):
            return row["Pot_Visita"]
        return row["Pot_Trip"]

    df["pot_used"] = df.apply(choose_pot, axis=1)

    ###########################################
    # PERCENTAGE MAPPING
    ###########################################
    pct_norm = {normalize_gestion(k): v for k, v in pct_dict.items()}
    df["pct"] = df["GESTION_KEY"].map(pct_norm).fillna(0)

    ###########################################
    # INITIAL ELIGIBILITY (NG == 0)
    ###########################################
    df["eligible"] = (pd.to_numeric(df["NG"], errors="coerce") == 0)

    ###########################################
    # RAW REINVESTMENT
    ###########################################
    df["reinvestment_raw"] = df["pot_used"] * df["pct"]
    df["reinvestment"] = 0.0

    elig = df["eligible"]

    df.loc[elig, "reinvestment"] = df.loc[elig, "reinvestment_raw"]
    df.loc[elig & (df["reinvestment"] < min_wallet), "reinvestment"] = min_wallet
    df.loc[elig, "reinvestment"] = df.loc[elig, "reinvestment"].clip(upper=cap)

    ###########################################
    # INELIGIBLE CONDITIONS
    ###########################################

    # 1. Comps > 200
    df.loc[df["Comps"] > 200, ["eligible", "reinvestment"]] = [False, 0]

    # 2. reinvestment <= Promo2
    df.loc[df["reinvestment"] <= df["Promo2"], ["eligible", "reinvestment"]] = [False, 0]

    # 3. reinvestment > WxV
    df.loc[df["reinvestment"] > df["WxV"], ["eligible", "reinvestment"]] = [False, 0]

    ###########################################
    # REINVESTMENT RANGE
    ###########################################
    conditions = [
        df["reinvestment"] == 0,
        df["reinvestment"] <= df["WxV"] * 0.5,
        df["reinvestment"] <= df["WxV"]
    ]
    choices = ["NO APLICA", "<50%", "50-100%"]
    df["Rango_Reinv"] = np.select(conditions, choices, default="NO APLICA")

    df["reinvestment"] = df["reinvestment"].round(2)

    return df


###############################################
# SIDEBAR INPUTS
###############################################
st.sidebar.header("Percentages (%)")

pct_dict = {
    "ARG": st.sidebar.number_input("ARG %", 0.0, 100.0, 10.0) / 100,
    "BRA": st.sidebar.number_input("BRA %", 0.0, 100.0, 15.0) / 100,
    "URY Local": st.sidebar.number_input("URY Local %", 0.0, 100.0, 8.0) / 100,
    "URY Resto": st.sidebar.number_input("URY Resto %", 0.0, 100.0, 8.0) / 100,
    "Otros": st.sidebar.number_input("Otros %", 0.0, 100.0, 5.0) / 100,
}

st.sidebar.subheader("Reinvestment Rules")
min_wallet = st.sidebar.number_input("Minimum reinvestment", 0.0, value=100.0)
cap_value = st.sidebar.number_input("Cap per wallet", 0.0, value=20000.0)

###############################################
# FILE UPLOAD
###############################################
st.subheader("📥 Upload CSV/XLSX")
uploaded = st.file_uploader("Select File", type=["csv", "xlsx"])

if uploaded:
    df_raw = (
        pd.read_csv(uploaded)
        if uploaded.name.endswith(".csv")
        else pd.read_excel(uploaded)
    )
    df_raw.columns = [clean(c) for c in df_raw.columns]

    st.success("✅ File loaded")
    st.write(df_raw.head())

    if st.button("Generate Promotion Layout"):
        df_result = apply_reinvestment(df_raw, pct_dict, min_wallet, cap_value)

        if df_result is not None:
            st.success("✅ Promotion Layout Created")
            st.dataframe(df_result, use_container_width=True)

            #############################
            # KPIS
            #############################
            with st.expander("📊 KPIs"):
                st.subheader("Reinvestment by País")
                kpais = df_result.groupby("Pais")["reinvestment"].sum().reset_index()
                st.dataframe(kpais)

                st.subheader("Reinvestment by Gestión")
                kgest = df_result.groupby("Gestion")["reinvestment"].sum().reset_index()
                st.dataframe(kgest)

                total_reinvestment = df_result["reinvestment"].sum()
            avg_teo = df_result["TeoricoNeto"].mean()
            avg_win = df_result["WinTotalNeto"].mean()

            st.metric("💰 Total Reinvestment", f"{total_reinvestment:,.0f}")
            st.metric("📈 Avg Theoretical Net", f"{avg_teo:,.0f}")
            st.metric("🎯 Avg Win Net", f"{avg_win:,.0f}")

            # Export Excel safely
            def to_excel(df):
                out = BytesIO()
                with pd.ExcelWriter(out, engine="xlsxwriter") as wr:
                    df.to_excel(wr, index=False)
                return out.getvalue()

                st.subheader("Pie Chart by País")
                st.altair_chart(
                    alt.Chart(kpais).mark_arc().encode(
                        theta="reinvestment",
                        color="Pais"
                    ),
                    use_container_width=True
                )

                st.subheader("Pie Chart by Gestión")
                st.altair_chart(
                    alt.Chart(kgest).mark_arc().encode(
                        theta="reinvestment",
                        color="Gestion"
                    ),
                    use_container_width=True
                )

            #############################
            # EXPORT
            #############################
            def to_excel(df):
                out = BytesIO()
                with pd.ExcelWriter(out, engine="xlsxwriter") as wr:
                    df.to_excel(wr, index=False)
                return out.getvalue()

            st.download_button(
                "⬇️ Download Excel",
                to_excel(df_result),
                "promotion_layout.xlsx"
            )
