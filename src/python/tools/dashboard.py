import streamlit as st
import pandas as pd
import json
import time
import os

st.set_page_config(page_title="Aegis Explainability Dashboard", layout="wide")

st.title("🛡️ Aegis Explainability & Compliance Dashboard")
st.markdown("### Real-time Risk Monitoring & Decision Auditing")

AUDIT_FILE = "aegis_audit.jsonl"

def load_data():
    if not os.path.exists(AUDIT_FILE):
        return pd.DataFrame()

    data = []
    with open(AUDIT_FILE, "r") as f:
        for line in f:
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    return df

# Auto-refresh logic (Mocked with button for now to avoid extensive loops in single-pass script)
if st.button("Refresh Data"):
    st.rerun()

df = load_data()

if df.empty:
    st.warning("No audit data found. Start the Aegis Engine and AI Bridge to generate traffic.")
else:
    # --- METRICS ROW ---
    col1, col2, col3, col4 = st.columns(4)

    total_tx = len(df)
    high_risk = len(df[df['status'] == 'HIGH_RISK'])
    avg_score = df['risk_score'].mean()
    mule_alerts = len(df[df['reason_code'].str.contains("Mule", na=False)])

    col1.metric("Total Screened", total_tx)
    col2.metric("High Risk Alerts", high_risk, delta_color="inverse")
    col3.metric("Avg Risk Score", f"{avg_score:.2f}")
    col4.metric("Mule Phenotypes", mule_alerts, delta_color="inverse")

    # --- CHARTS ---
    st.markdown("---")

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Risk Score Distribution")
        st.bar_chart(df['risk_score'].value_counts().sort_index())

    with c2:
        st.subheader("Reason Codes (Rejection Factors)")
        reason_counts = df['reason_code'].value_counts()
        st.bar_chart(reason_counts)

    # --- DETAILED LOG ---
    st.markdown("---")
    st.subheader("Recent Audit Logs (GDPR Masked)")

    # Show latest first
    st.dataframe(
        df.sort_values(by='timestamp', ascending=False).head(50)[
            ['timestamp', 'request_id', 'entity_masked', 'status', 'risk_score', 'reason_code']
        ],
        use_container_width=True
    )

    # --- EXPLAINABILITY PANEL ---
    st.markdown("### 🧠 Decision Explainability")
    selected_id = st.selectbox("Select Request ID to Explain", df['request_id'].unique())

    if selected_id:
        record = df[df['request_id'] == selected_id].iloc[0]

        st.info(f"Analyzing Decision for Request #{selected_id}")

        c_exp1, c_exp2 = st.columns(2)

        with c_exp1:
            st.write("**Entity (Masked):**", record['entity_masked'])
            st.write("**Final Status:**", record['status'])
            st.write("**Risk Score:**", f"{record['risk_score']:.2f} / 10.0")

        with c_exp2:
            st.write("**Primary Reason:**", record['reason_code'])

            # Simulated Explanation Logic
            if "Mule" in record['reason_code'] or "RC_VELOCITY" in record['reason_code']:
                st.error("⚠️ **Logic Path:** Sequence Analysis (LSTM) detected dormant account sudden activation.")
                st.text("Rule: If Inactive > 180 days AND Flow > 50k -> Flag as Mule Herding.")
            elif "MICRO" in record['reason_code'] or "RC_STRUCTURING" in record['reason_code']:
                st.error("⚠️ **Logic Path:** Velocity Check detected structuring.")
                st.text("Rule: If 5+ tx < $100 in 60s -> Flag as Micro-Laundering.")
            elif "Sanctions" in record['reason_code']:
                st.error("⛔ **Logic Path:** Fuzzy String Match (AVX-512) hit denied list.")
                st.text(f"Distance < Threshold (3) against OFAC SDN List with Confidence > 90%.")
            elif "RC_BASELINE" in record['reason_code']:
                st.warning("⚠️ **Logic Path:** Aggregate Risk Threshold Exceeded.")
                st.text("Rule: Combination of factors exceeded 0.5 baseline.")
            else:
                st.success("✅ **Logic Path:** Score < Threshold (5.0). No phenotypes detected.")

st.markdown("---")
st.caption("Aegis v1.0 | Compliance & Explainability Module")
