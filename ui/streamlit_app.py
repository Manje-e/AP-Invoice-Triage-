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
if st.button("Run"):
    response = requests.post(
        "https://ap-invoice-triage.onrender.com/triage",
        json={"question": query}
    ).json()

    st.subheader("📌 Duplicate Invoices")
    if response["duplicates"]:
        st.dataframe(pd.DataFrame(response["duplicates"]), use_container_width=True)
    else:
        st.success("No duplicate invoices found")

    st.subheader("💰 High Value Invoices")
    if response["high_value"]:
        st.dataframe(pd.DataFrame(response["high_value"]), use_container_width=True)
    else:
        st.success("No high value invoices found")

    st.info(f"Why flagged: {response['reason']}")
