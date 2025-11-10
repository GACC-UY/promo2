import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO


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
# SIDEBAR INPUTS
# ---------------------------------------------------------
st.sidebar.header("🔧 Input Parameters")

st.sidebar.subheader("Reinvestment Percentages (%)")
pct_arg = st.sidebar.number_input("ARG %", min_value=0.0, max_value=100.0, value=10.0)
pct_bra = st.sidebar.number_input("BRA %", min_value=0.0, max_value=100.0, value=15.0)
pct_ury_local = st.sidebar.number_input("URY Local %", min_value=0.0, max_value=100.0, value=8.0)
pct_ury_resto = st.sidebar.number_input("URY Resto %", min_value=0.0, max_value=100.0, value=5.0)

pct_dict = {
    "ARG": pct_arg / 100,
    "BRA": pct_bra / 100,
    "URY Local": pct_ury_local / 100,
    "URY Resto": pct_ury_resto / 100,
}

st.sidebar.subheader("Reinvestment Rules")
min_per_wallet = st.sidebar.number_input("Minimum Reinvestment Per Wallet", min_value=0.0, value=100.0)
cap_value = st.sidebar.number_input("Accumulated Cap", min_value=0.0, value=20000.0)


# ---------------------------------------------------------
# DATA SOURCE SELECTION
# ---------------------------------------------------------
st.subheader("📥 Load Base Data")

tab_excel, tab_sql = st.tabs(["Upload Excel", "Load From SQL"])

df_source = None

# -------- Option A: Upload Excel -------------------------------------------------

with tab_excel:
    uploaded_file = st.file_uploader("Upload Source Excel", type=["xlsx"])

    if uploaded_file is not None:
        df_source = pd.read_excel(uploaded_file)
        st.success("✅ Excel loaded successfully")
        st.dataframe(df_source)


# ---------------------------------------------------------
# CALCULATION FUNCTION
# ---------------------------------------------------------
def apply_reinvestment(df, pct_dict, min_wallet, cap):
    df = df.copy()

    # Ensure expected columns exist
    required_cols = ["Gestion", "Potencial", " Reinversion_Hospitality", " Reinversión_Juego"]
    for c in required_cols:
        if c not in df.columns:
            st.error(f"Missing column in data: {c}")
            return None

    # Map % per Gestion
    df["pct"] = df["Gestion"].map(pct_dict).fillna(0)

    # Base reinvestment
    df["reinvestment"] = df["Reinversión_Juego"] + df["Reinversion_Hospitality"] / df["Potencial"]

    # Apply minimum per wallet
    df.loc[df["reinvestment"] < min_wallet, "reinvestment"] = min_wallet

    # Apply global cap
    df["reinvestment"] = df["reinvestment"].clip(upper=cap)

    return df


# ---------------------------------------------------------
# PROCEED WITH CALCULATION
# ---------------------------------------------------------
st.subheader("Generate Promotion")

if df_source is None:
    st.warning("Upload Excel or Load From SQL to continue.")
else:
    if st.button("Generate Promotion Layout"):
        df_result = apply_reinvestment(
            df_source, pct_dict, min_per_wallet, cap_value
        )

        if df_result is not None:
            st.success("Promotion Layout Generated")
            st.dataframe(df_result, use_container_width=True)

            # Export to Excel
            def to_excel(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Promotion")
                return output.getvalue()

            excel_data = to_excel(df_result)

            st.download_button(
                "Download Excel Layout",
                data=excel_data,
                file_name="promotion_layout.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

