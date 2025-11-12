###############################################
# 🎰 CASINO REINVESTMENT PROMOTION BUILDER
# ✅ FINAL STREAMLIT APP (with per-country caps)
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
# NORMALIZE GESTION / PAIS KEYS
###############################################
def normalize_gestion(val):
    if not isinstance(val, str):
        val = str(val)
    val = "".join(c for c in unicodedata.normalize("NFKD", val) if not unicodedata.combining(c))
    val = val.strip().replace(" ", "_").upper()
    return re.sub(r"[^0-9A-Za-z_]", "", val)


###############################################
# 🧠 MAIN REINVESTMENT ENGINE
###############################################
def apply_reinvestment(df, pct_dict, min_wallet, cap, country_caps):
    df = df.copy()

    # --- Standardize column names ---
    rename_map = {
        "Pot_xVisita": "Pot_Visita",
        "Prom_TeoNeto_Trip": "TeoricoNeto",
        "Prom_WinNeto_Trip": "WinTotalNeto",
        "Prom_Visita_Trip": "Visitas",
        "Pot_Trip": "Pot_Trip",
    }
    df.rename(columns=rename_map, inplace=True)

    # --- Validate required columns ---
    required_cols = ["Gestion", "Pais", "NG", "TeoricoNeto", "WinTotalNeto",
                     "Visitas", "Pot_Trip", "Pot_Visita", "Promo2", "Comps"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"❌ Missing required columns: {missing}")
        return None

    # --- Convert numerics safely ---
    num_cols = ["TeoricoNeto", "WinTotalNeto", "Visitas", "Pot_Trip",
                "Pot_Visita", "Promo2", "Comps"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # --- Derived fields ---
    df["WxV"] = pd.to_numeric(df.get("Pot_Visita", 0), errors="coerce").fillna(0)
    df["Potencial"] = df[["TeoricoNeto", "WinTotalNeto"]].max(axis=1)
    df["GESTION_KEY"] = df["Gestion"].apply(normalize_gestion)

    # --- Choose correct pot based on GESTION ---
    df["pot_used"] = np.where(df["GESTION_KEY"].isin(["URY_LOCAL", "URY_RESTO"]),
                              df["Pot_Visita"], df["Pot_Trip"])

    # --- Map percentage per country ---
    pct_norm = {normalize_gestion(k): v for k, v in pct_dict.items()}
    df["pct"] = df["GESTION_KEY"].map(pct_norm).fillna(0)

    # --- Eligibility ---
    df["eligible"] = (pd.to_numeric(df["NG"], errors="coerce") == 0)

    # --- Calculate reinvestment raw ---
    df["reinvestment_raw"] = df["pot_used"] * df["pct"]

    # --- Apply global min/cap ---
    elig = df["eligible"]
    df.loc[elig, "reinvestment"] = df.loc[elig, "reinvestment_raw"]
    df.loc[elig & (df["reinvestment"] < min_wallet), "reinvestment"] = min_wallet
    df.loc[elig, "reinvestment"] = df.loc[elig, "reinvestment"].clip(upper=cap)

    # --- Ineligibility rules ---
    df.loc[df["Comps"] > 200, ["eligible", "reinvestment"]] = [False, 0]
    df.loc[df["reinvestment"] <= df["Promo2"], ["eligible", "reinvestment"]] = [False, 0]
  

    # --- Apply per-country min/max caps ---
    def apply_country_caps(row):
        pais = str(row.get("Pais", "")).strip()
        reinv = row.get("reinvestment", 0)
        for key, rule in country_caps.items():
            if normalize_gestion(key) == normalize_gestion(pais):
                reinv = max(reinv, rule["min"])
                reinv = min(reinv, rule["max"])
                break
        return reinv

    df["reinvestment"] = df.apply(apply_country_caps, axis=1)

    # --- Reinvestment range label ---
    df["Rango_Reinv"] = np.select(
        [
            df["reinvestment"] == 0,
            df["reinvestment"] <= df["WxV"] * 0.5,
            df["reinvestment"] <= df["WxV"],
        ],
        ["NO APLICA", "<50%", "50-100%"],
        default="NO APLICA",
    )

    df["reinvestment"] = df["reinvestment"].round(2)
    return df


###############################################
# SIDEBAR CONFIG
###############################################
st.sidebar.header("Percentages (%)")
pct_dict = {
    "ARG": st.sidebar.number_input("ARG %", 0.0, 100.0, 10.0) / 100,
    "BRA": st.sidebar.number_input("BRA %", 0.0, 100.0, 15.0) / 100,
    "URY Local": st.sidebar.number_input("URY Local %", 0.0, 100.0, 8.0) / 100,
    "URY Resto": st.sidebar.number_input("URY Resto %", 0.0, 100.0, 8.0) / 100,
    "Otros": st.sidebar.number_input("Otros %", 0.0, 100.0, 5.0) / 100,
}

st.sidebar.subheader("Country Reinvestment Caps")
country_caps = {}
for pais in ["URY Local", "URY Resto", "ARG", "BRA", "Otros"]:
    st.sidebar.markdown(f"**{pais}**")
    min_val = st.sidebar.number_input(f"{pais} Min", 0.0, 50000.0, 100.0 if "URY" in pais else 200.0)
    max_val = st.sidebar.number_input(f"{pais} Max", 0.0, 100000.0, 10000.0)
    country_caps[pais] = {"min": min_val, "max": max_val}

st.sidebar.subheader("Global Reinvestment Rules")
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

    st.success("✅ File loaded successfully!")
    st.write(df_raw.head())

    if st.button("🚀 Generate Promotion Layout"):
        df_result = apply_reinvestment(df_raw, pct_dict, min_wallet, cap_value, country_caps)

        if df_result is not None:
            st.success("✅ Promotion Layout Created")
            st.dataframe(df_result, width="stretch")

            ###############################################
            # KPIs
            ###############################################
            st.subheader("📊 KPIs")
            kpais = df_result.groupby("Pais")["reinvestment"].sum().reset_index()
            kgest = df_result.groupby("Gestion")["reinvestment"].sum().reset_index()

            total_reinvestment = df_result["reinvestment"].sum()
            avg_teo = df_result["TeoricoNeto"].mean()
            avg_win = df_result["WinTotalNeto"].mean()

            st.metric("💰 Total Reinvestment", f"{total_reinvestment:,.0f}")
            st.metric("📈 Avg Theoretical Net", f"{avg_teo:,.0f}")
            st.metric("🎯 Avg Win Net", f"{avg_win:,.0f}")

            ###############################################
            # CHARTS
            ###############################################
            st.subheader("Pie Chart by País")
            st.altair_chart(
                alt.Chart(kpais).mark_arc().encode(
                    theta="reinvestment",
                    color="Pais"
                ),
                width="stretch"
            )

            st.subheader("Pie Chart by Gestión")
            st.altair_chart(
                alt.Chart(kgest).mark_arc().encode(
                    theta="reinvestment",
                    color="Gestion"
                ),
                width="stretch"
            )

            ###############################################
            # EXPORT
            ###############################################
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
