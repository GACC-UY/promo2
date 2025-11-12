###############################################
# 🎰 CASINO REINVESTMENT PROMOTION BUILDER
# ✅ FINAL STREAMLIT APP (per-country caps + % KPIs + % Pie Charts)
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
# HELPERS
###############################################
def clean(col):
    """Normalize column names"""
    if not isinstance(col, str):
        col = str(col)
    col = col.strip()
    col = "".join(c for c in unicodedata.normalize("NFKD", col) if not unicodedata.combining(c))
    col = re.sub(r"[^0-9A-Za-z_ ]", "", col)
    col = col.replace(" ", "_")
    col = re.sub(r"_+", "_", col)
    return col.strip("_")

def normalize_gestion(name):
    return str(name).strip().lower().replace("_", "").replace(" ", "")

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
    df["WxV"] = df["Pot_Visita"]
    df["Potencial"] = df[["TeoricoNeto", "WinTotalNeto"]].max(axis=1)

    # --- Normalize pct per country ---
    pct_norm = {normalize_gestion(k): v for k, v in pct_dict.items()}
    df["pct"] = df["Pais"].apply(lambda x: pct_norm.get(normalize_gestion(x), 0))

    # --- Eligibility base ---
    df["eligible"] = (pd.to_numeric(df["NG"], errors="coerce") == 0)

    # --- Raw reinvestment ---
    df["reinvestment_raw"] = df["Pot_Visita"] * df["pct"]

    # --- Apply country caps ---
    def apply_country_caps(row):
        pais = str(row.get("Pais", "")).strip()
        reinv = row.get("reinvestment_raw", 0)
        for key, rule in country_caps.items():
            if normalize_gestion(key) == normalize_gestion(pais):
                reinv = max(reinv, rule["min"])
                reinv = min(reinv, rule["max"])
                break
        return reinv

    df["reinvestment"] = df.apply(apply_country_caps, axis=1)

    # --- Apply global limits ---
    elig = df["eligible"]
    df.loc[elig, "reinvestment"] = df.loc[elig, "reinvestment"].clip(lower=min_wallet, upper=cap)
    df.loc[~elig, "reinvestment"] = 0

    # --- Eligibility refinement ---
    df.loc[df["Comps"] > 200, ["eligible", "reinvestment"]] = [False, 0]
    df.loc[df["reinvestment"] <= df["Promo2"], ["eligible", "reinvestment"]] = [False, 0]

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

    # --- If NO APLICA => eligible = 0 ---
    df.loc[df["Rango_Reinv"] == "NO APLICA", "eligible"] = False

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
            st.dataframe(df_result, use_container_width=True)

            ###############################################
            # KPIs — Improved Tables with %
            ###############################################
            st.subheader("📊 KPI Summary")
                        
            eligible_df = df_result[df_result["eligible"]]
            kpi_pais = eligible_df.groupby("Pais")["reinvestment"].sum().reset_index()
            kpi_gestion = eligible_df.groupby("Gestion")["reinvestment"].sum().reset_index()

            df_result["Eligible_Flag"] = df_result["eligible"].astype(int)
            df_result["Potencial_xVisita"] = df_result["Pot_Visita"]
            df_result["Potencial_xTrip"] = df_result["Pot_Trip"]

            total_reinv = df_result["reinvestment"].sum()
            total_pot_visita = df_result["Potencial_xVisita"].sum()
            total_pot_trip = df_result["Potencial_xTrip"].sum()

            avg_teo = eligible_df["TeoricoNeto"].sum()
            avg_win = eligible_df["WinTotalNeto"].sum()
            avg_trip = eligible_df["Pot_Trip"].sum()
            avg_visita = eligible_df["Visitas"].mean()

            c2.metric("📈 Total Theoretical Net", f"{avg_teo:,.0f}")
            c3.metric("🎯 Total Win Net", f"{avg_win:,.0f}")
            c4.metric("🧳 Total Pot Trip", f"{avg_trip:,.0f}")
            c5.metric("👣 Avg Visits", f"{avg_visita:,.2f}")

            
            st.subheader("🌍 Reinvestment Breakdown (Eligible Only)")
            st.dataframe(kpi_pais, use_container_width=True)
            st.dataframe(kpi_gestion, use_container_width=True)


            # --- Overall Summary ---
            summary = pd.DataFrame({
                "Eligible_Count": [df_result["Eligible_Flag"].sum()],
                "Total_Reinvestment": [total_reinv],
                "Total_Potencial_Visita": [total_pot_visita],
                "Total_Potencial_Trip": [total_pot_trip],
            })
            st.write("### 🔢 Overall Summary")
            st.dataframe(summary, use_container_width=True)

            # --- By Country ---
            pais_summary = df_result.groupby("Pais").agg(
                Eligible_Count=("Eligible_Flag", "sum"),
                Total_Reinvestment=("reinvestment", "sum"),
                Total_Potencial_Visita=("Potencial_xVisita", "sum"),
                Total_Potencial_Trip=("Potencial_xTrip", "sum"),
            ).reset_index()

            pais_summary["%_Reinvestment"] = (pais_summary["Total_Reinvestment"] / total_reinv * 100).round(2)
            pais_summary["%_Potencial_Visita"] = (pais_summary["Total_Potencial_Visita"] / total_pot_visita * 100).round(2)
            pais_summary["%_Potencial_Trip"] = (pais_summary["Total_Potencial_Trip"] / total_pot_trip * 100).round(2)

            st.write("### 🌎 By Country (with % of Total)")
            st.dataframe(pais_summary, use_container_width=True)

            # --- By Gestión ---
            gest_summary = df_result.groupby("Gestion").agg(
                Eligible_Count=("Eligible_Flag", "sum"),
                Total_Reinvestment=("reinvestment", "sum"),
                Total_Potencial_Visita=("Potencial_xVisita", "sum"),
                Total_Potencial_Trip=("Potencial_xTrip", "sum"),
            ).reset_index()

            gest_summary["%_Reinvestment"] = (gest_summary["Total_Reinvestment"] / total_reinv * 100).round(2)
            gest_summary["%_Potencial_Visita"] = (gest_summary["Total_Potencial_Visita"] / total_pot_visita * 100).round(2)
            gest_summary["%_Potencial_Trip"] = (gest_summary["Total_Potencial_Trip"] / total_pot_trip * 100).round(2)

            st.write("### 🏢 By Gestión (with % of Total)")
            st.dataframe(gest_summary, use_container_width=True)

            ###############################################
            # CHARTS — PIE WITH %
            ###############################################
            st.subheader("📈 Reinvestment Distribution")

            pais_summary["label"] = pais_summary.apply(
                lambda x: f"{x['Pais']} ({x['%_Reinvestment']}%)", axis=1
            )

            st.altair_chart(
                alt.Chart(pais_summary).mark_arc(outerRadius=150).encode(
                    theta=alt.Theta(field="Total_Reinvestment", type="quantitative"),
                    color=alt.Color(field="label", type="nominal"),
                    tooltip=[
                        alt.Tooltip("Pais:N"),
                        alt.Tooltip("Total_Reinvestment:Q", format=",.0f"),
                        alt.Tooltip("%_Reinvestment:Q", format=".2f")
                    ]
                ).properties(title="Reinvestment by Country (%)"),
                use_container_width=True
            )

            gest_summary["label"] = gest_summary.apply(
                lambda x: f"{x['Gestion']} ({x['%_Reinvestment']}%)", axis=1
            )

            st.altair_chart(
                alt.Chart(gest_summary).mark_arc(outerRadius=150).encode(
                    theta=alt.Theta(field="Total_Reinvestment", type="quantitative"),
                    color=alt.Color(field="label", type="nominal"),
                    tooltip=[
                        alt.Tooltip("Gestion:N"),
                        alt.Tooltip("Total_Reinvestment:Q", format=",.0f"),
                        alt.Tooltip("%_Reinvestment:Q", format=".2f")
                    ]
                ).properties(title="Reinvestment by Gestión (%)"),
                use_container_width=True
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
