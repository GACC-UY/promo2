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
# excel clean up
# ---------------------------------------------------------

def fix_excel_headers(df):
    """
    Detects the first row that contains ANY non-null values
    and uses it as the header.
    """
    # Find first row with real headers
    for i, row in df.iterrows():
        if row.notnull().sum() >= 3:  # at least 3 non-empty cells → header row
            header_row = i
            break

    # Extract headers
    new_header = df.iloc[header_row].astype(str).tolist()

    # Rebuild dataframe without that row
    df_fixed = df.iloc[header_row + 1:].reset_index(drop=True)
    df_fixed.columns = new_header

    return df_fixed

# ---------------------------------------------------------
# CALCULATION FUNCTION
# ---------------------------------------------------------

def apply_reinvestment(df, pct_dict, min_wallet, cap):
    df = df.copy()

    # ---------------------------------------------------------
    # 1. Ensure required columns exist
    # ---------------------------------------------------------
    required_cols = [
        "Gestion", "", "Reinversion_Hospitality", "Reinversión_Juego", 
        "NG", "Visitas", "TeoricoNeto", "WinTotalNeto", "WxV",
        "Visitas_Est", "Trip_Esperado"
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"Missing columns: {missing}")
        return None


    # ---------------------------------------------------------
    # 2. Eligibility (NG logic)
    # ---------------------------------------------------------
    df["eligible"] = (df["NG"] == 0)  # 1 = non gestionable

    # Non-gestionable → no reinvestment
    df.loc[df["eligible"] == False, "reinvestment"] = 0
    df.loc[df["eligible"] == False, "Rango_Reinv"] = "NO APLICA"


    # ---------------------------------------------------------
    # 3. % per segment
    # ---------------------------------------------------------
    df["pct"] = df["Gestion"].map(pct_dict).fillna(0)


    # ---------------------------------------------------------
    # 4. Base reinvestment for eligible players
    # ---------------------------------------------------------
    df.loc[df["eligible"], "reinvestment"] = (
        df["Potencial"] * df["pct"]
    )


    # ---------------------------------------------------------
    # 5. Minimum per wallet
    # ---------------------------------------------------------
    df.loc[
        (df["eligible"]) &
        (df["reinvestment"] < min_wallet),
        "reinvestment"
    ] = min_wallet


    # ---------------------------------------------------------
    # 6. Maximum cap
    # ---------------------------------------------------------
    df.loc[df["eligible"], "reinvestment"] = (
        df["reinvestment"].clip(upper=cap)
    )


    # ---------------------------------------------------------
    # 7. Expected Trips (3-day window)
    # ---------------------------------------------------------
    df["Trips_Calc"] = np.where(
        df["Visitas"] > 0,
        df["Visitas"] / 3,
        df["Visitas_Est"] / 3
    )


    # ---------------------------------------------------------
    # 8. Reinvestment Range Classification
    # ---------------------------------------------------------
    conditions = [
        df["reinvestment"] == 0,
        df["reinvestment"] <= df["WxV"] * 0.5,
        df["reinvestment"] <= df["WxV"],
        df["reinvestment"] > df["WxV"],
    ]

    choices = [
        "NO APLICA",
        "<50%",
        "50–100%",
        ">100%"
    ]

    df["Rango_Reinv"] = np.select(conditions, choices, default="-")


    # ---------------------------------------------------------
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

