import streamlit as st

from data_access import load_category_names, load_coins, load_last_sync_status

st.set_page_config(page_title="Crypto Intelligence Platform", layout="wide")

st.title("📊 Crypto Intelligence Platform")
st.caption("All coins listed on CoinMarketCap, cached locally and synced once every 24 hours.")

with st.sidebar:
    st.header("Filters")
    categories = ["All narratives"] + load_category_names()
    selected_category = st.selectbox("Group by CMC narrative", categories)

    st.divider()
    st.subheader("Last sync status")
    for entry in load_last_sync_status():
        icon = "✅" if entry["status"] == "success" else "❌"
        st.write(f"{icon} **{entry['type']}** — {entry['records_synced']} records")
        if entry["finished_at"]:
            st.caption(f"Finished: {entry['finished_at']}")
        if entry["error_message"]:
            st.caption(f"⚠️ {entry['error_message']}")

df = load_coins()

if df.empty:
    st.info("No cached coins yet. Waiting for the scheduler's first sync to complete.")
else:
    if selected_category != "All narratives":
        df = df[df["Narratives"].str.contains(selected_category, na=False)]

    st.metric("Coins shown", len(df))
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Price (USD)": st.column_config.NumberColumn(format="$%.4f"),
            "Market Cap (USD)": st.column_config.NumberColumn(format="$%,.0f"),
            "24h Volume (USD)": st.column_config.NumberColumn(format="$%,.0f"),
            "24h Change (%)": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
