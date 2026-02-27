import streamlit as st
import requests
import pandas as pd

st.set_page_config(
    page_title="AP Invoice Triage",
    layout="wide"
)

st.title("🧾 AP Invoice Triage Automation")
st.caption("Simple rule-based triage (GenAI-ready)")

# User input
query = st.text_input(
    "Ask a question",
    placeholder="Show duplicate invoices for Vendor X"
)

# Run button
# Run button
if st.button("Run"):
    try:
        r = requests.post(
            "https://ap-invoice-triage.onrender.com/triage",
            json={"question": query},
            timeout=30
        )

        st.write("Status:", r.status_code)

        if not r.ok:
            st.error(r.text)
        else:
            response = r.json()

            st.subheader("📌 Duplicate Invoices")
            if response.get("duplicates"):
                st.dataframe(pd.DataFrame(response["duplicates"]), use_container_width=True)
            else:
                st.success("No duplicate invoices found")

            st.subheader("💰 High Value Invoices")
            if response.get("high_value"):
                st.dataframe(pd.DataFrame(response["high_value"]), use_container_width=True)
            else:
                st.success("No high value invoices found")

            st.info(f"Why flagged: {response.get('reason', '')}")

    except Exception as e:
        st.error(str(e))
