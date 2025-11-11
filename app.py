import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import re
import unicodedata
import xlsxwriter

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
# 1) HEADER + COLUMN NORMALIZATION FUNCTIONS
# ---------------------------------------------------------

def clean_column_name(col):
    """
    Normalize column names:
    - Remove accents
    - Replace spaces with _
    - Remove illegal characters
    - Strip leading/trailing spaces
    """
    if not isinstance(col, str):
        col = str(col)

    # Remove accents
    col = "".join(
        c for c in unicodedata.normalize('NFKD', col)
        if not unicodedata.combining(c)
    )

    # Replace spaces with _
    col = col.replace(" ", "_")

    # Remove non-alphanumeric/underscore characters
    col = re.sub(r"[^0-9a-zA-Z_]", "", col)

    # Collapse multiple underscores
    col = re.sub(r"_+", "_", col)

    return col.strip("_")


def fix_excel_headers(df):
    """
    Detects the first row with >=3 non-null entries and uses it as the header.
    Then normalizes all column names.
    """
    # 1) Find header row
    for i, row in df.iterrows():
        if row.notnull().sum() >= 3:
            header_row = i
            break

    # 2) Extract raw headers
    raw_headers = df.iloc[header_row].astype(str).tolist()

    # 3) Normalize
    cleaned_headers = [clean_column_name(h) for h in raw_headers]

    # 4) Apply headers
    df_fixed = df.iloc[header_row + 1:].reset_index(drop=True)
    df_fixed.columns = cleaned_headers

    return df_fixed


# ---------------------------------------------------------
# 2) CALCULATION FUNCTION
# ---------------------------------------------------------

def apply_reinvestment(df, pct_dict, min_wallet, cap):
    df = df.copy()

    required_cols = [
        "Gestion", "Reinversion_Hospitality", "Reinversion_Juego",
        "NG", "Visitas", "TeoricoNeto", "WinTotalNeto", "WxV",
        "Visitas_Est", "Trip_Esperado", "Potencial"
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"Missing columns: {missing}")
        return None

    # ---------------------------------------------------------
    # NG logic
    # ---------------------------------------------------------
    df["eligible"] = (df["NG"] == 0)

    df.loc[~df["eligible"], "reinvestment"] = 0
    df.loc[~df["eligible"], "Rango_Reinv"] = "NO APLICA"

    # ---------------------------------------------------------
    # % per segment
    # ---------------------------------------------------------
    df["pct"] = df["Gestion"].map(pct_dict).fillna(0)

    # ---------------------------------------------------------
    # Base reinvestment
    # ---------------------------------------------------------
    df.loc[df["eligible"], "reinvestment"] = df["Potencial"] * df["pct"]

    # ---------------------------------------------------------
    # Minimum per wallet
    # ---------------------------------------------------------
    df.loc[
        (df["eligible"]) &
        (df["reinvestment"] < min_wallet),
        "reinvestment"
    ] = min_wallet

    # ---------------------------------------------------------
    # Apply cap
    # ---------------------------------------------------------
    df.loc[df["eligible"], "reinvestment"] = df["reinvestment"].clip(upper=cap)

    # ---------------------------------------------------------
    # Trips calculation
    # ---------------------------------------------------------
    df["Trips_Calc"] = np.where(
        df["Visitas"] > 0,
        df["Visitas"] / 3,
        df["Visitas_Est"] / 3
    )

    # ---------------------------------------------------------
    # Rango Reinversion
    # ---------------------------------------------------------
    conditions = [
        df["reinvestment"] == 0,
        df["reinvestment"] <= df["WxV"] * 0.5,
        df["reinvestment"] <= df["WxV"],
        df["reinvestment"] > df["WxV"],
    ]
    choices = ["NO APLICA", "<50%", "50–100%", ">100%"]

    df["Rango_Reinv"] = np.select(conditions, choices, default="-")

    return df


# ---------------------------------------------------------
# 3) SIDEBAR INPUTS
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
# 4) LOAD DATA
# ---------------------------------------------------------
st.subheader("📥 Load Base Data")
tab_excel, tab_sql = st.tabs(["Upload Excel", "Load From SQL"])

df_source = None

with tab_excel:
    uploaded_file = st.file_uploader("Upload Source Excel", type=["xlsx"])
    if uploaded_file is not None:
        raw_df = pd.read_excel(uploaded_file, header=None)
        df_source = fix_excel_headers(raw_df)
        st.success("✅ Excel loaded, header fixed, columns normalized")
        st.dataframe(df_source)


# ---------------------------------------------------------
# 5) CALCULATE
# ---------------------------------------------------------
st.subheader("Generate Promotion")

if df_source is None:
    st.warning("Upload Excel or Load From SQL to continue.")
else:
    if st.button("Generate Promotion Layout"):
        df_result = apply_reinvestment(df_source, pct_dict, min_per_wallet, cap_value)

        if df_result is not None:
            st.success("Promotion Layout Generated")
            st.dataframe(df_result, use_container_width=True)

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
