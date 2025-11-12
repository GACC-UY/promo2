import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import unicodedata
import re

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
    return col.strip("_").lower()  # lowercased for safety


def normalize_gestion(val):
    if not isinstance(val, str):
        val = str(val)
    val = "".join(c for c in unicodedata.normalize("NFKD", val) if not unicodedata.combining(c))
    val = val.strip().replace(" ", "_").upper()
    return re.sub(r"[^0-9A-Za-z_]", "", val)

###############################################
# FLEXIBLE COLUMN RENAME (handles Excel quirks)
###############################################
def rename_columns(df):
    cols = {c.lower(): c for c in df.columns}
    mapping = {
        "pot_xvisita": "Pot_Visita",
        "prom_teoneto_trip": "TeoricoNeto",
        "prom_winneto_trip": "WinTotalNeto",
        "prom_visita_trip": "Visitas",
        "pot_trip": "Pot_Trip",
    }

    for key, val in mapping.items():
        if key in cols:
            df.rename(columns={cols[key]: val}, inplace=True)
    return df

###############################################
# MAIN REINVESTMENT ENGINE
###############################################
def apply_reinvestment(df, pct_dict, min_wallet, cap, country_caps):
    df = df.copy()
    df = rename_columns(df)

    if "Pot_Visita" in df.columns:
        df["WxV"] = pd.to_numeric(df["Pot_Visita"], errors="coerce").fillna(0)
    else:
        st.error("Column Pot_xVisita / Pot_Visita not found.")
        return None

    required = ["Gestion", "Pais", "NG", "TeoricoNeto", "WinTotalNeto", "Visitas", "Pot_Trip", "Pot_Visita", "Promo2", "Comps"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"❌ Missing required columns: {missing}")
        st.write("Available:", list(df.columns))
        return None

    num_cols = ["TeoricoNeto", "WinTotalNeto", "Visitas", "Pot_Trip", "Pot_Visita", "WxV", "Promo2", "Comps"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    df["Potencial"] = df[["TeoricoNeto", "WinTotalNeto"]].max(axis=1)
    df["GESTION_KEY"] = df["Gestion"].apply(normalize_gestion)

    def choose_pot(row):
        if row["GESTION_KEY"] in ("URY_LOCAL", "URY_RESTO"):
            return row["Pot_Visita"]
        return row["Pot_Trip"]

    df["pot_used"] = df.apply(choose_pot, axis=1)
    pct_norm = {normalize_gestion(k): v for k, v in pct_dict.items()}
    df["pct"] = df["GESTION_KEY"].map(pct_norm).fillna(0)
    df["eligible"] = (pd.to_numeric(df["NG"], errors="coerce") == 0)

    df["reinvestment_raw"] = df["pot_used"] * df["pct"]
    df["reinvestment"] = 0.0

    elig = df["eligible"]
    df.loc[elig, "reinvestment"] = df.loc[elig, "reinvestment_raw"]
    df.loc[elig & (df["reinvestment"] < min_wallet), "reinvestment"] = min_wallet
    df.loc[elig, "reinvestment"] = df.loc[elig, "reinvestment"].clip(upper=cap)

    # Ineligibility rules
    df.loc[df["Comps"] > 200, ["eligible", "reinvestment"]] = [False, 0]
    df.loc[df["reinvestment"] <= df["Promo2"], ["eligible", "reinvestment"]] = [False, 0]
    df.loc[df["reinvestment"] > df["WxV"], ["eligible", "reinvestment"]] = [False, 0]

    # Apply country caps
    def apply_caps(row):
        pais = str(row.get("Pais", "")).strip()
        reinv = row.get("reinvestment", 0)
        for key, rule in country_caps.items():
            if key.replace(" ", "_").upper() == pais.replace(" ", "_").upper():
                reinv = max(reinv, rule["min"])
                reinv = min(reinv, rule["max"])
                break
        return reinv

    df["reinvestment"] = df.apply(apply_caps, axis=1)

    df["Rango_Reinv"] = np.select(
        [df["reinvestment"] == 0, df["reinvestment"] <= df["WxV"] * 0.5, df["reinvestment"] <= df["WxV"]],
        ["NO APLICA", "<50%", "50-100%"],
        default="NO APLICA"
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

st.sidebar.subheader("Reinvestment Rules")
min_wallet = st.sidebar.number_input("Minimum reinvestment", 0.0, value=100.0)
cap_value = st.sidebar.number_input("Cap per wallet", 0.0, value=20000.0)

###############################################
# FILE UPLOAD
###############################################
st.subheader("📥 Upload CSV/XLSX")
uploaded = st.file_uploader("Select File", type=["csv", "xlsx"])

if uploaded:
    try:
        df_raw = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        st.stop()

    df_raw.columns = [clean(c) for c in df_raw.columns]
    st.success("✅ File loaded successfully")
    st.write(df_raw.head())

    if st.button("Generate Promotion Layout"):
        df_result = apply_reinvestment(df_raw, pct_dict, min_wallet, cap_value, country_caps)
        if df_result is not None:
            st.success("✅ Promotion Layout Created")
            st.dataframe(df_result)

            st.subheader("📊 KPI Summary")
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

            st.download_button("⬇️ Download Excel", to_excel(df_result), "promotion_layout.xlsx")
