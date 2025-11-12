            ###############################################
            # KPIs — Improved Tables with %
            ###############################################
            st.subheader("📊 KPI Summary")

            df_result["Eligible_Flag"] = df_result["eligible"].astype(int)
            df_result["Potencial_xVisita"] = df_result["Pot_Visita"]
            df_result["Potencial_xTrip"] = df_result["Pot_Trip"]

            total_reinv = df_result["reinvestment"].sum()
            total_pot_visita = df_result["Potencial_xVisita"].sum()
            total_pot_trip = df_result["Potencial_xTrip"].sum()

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
