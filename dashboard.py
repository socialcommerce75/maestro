import streamlit as st
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

st.set_page_config(page_title="Chief of Staff Dashboard", layout="wide")

st.title("🛡️ Maestro Agentic Command Center")

# --- GLOBAL SETTINGS ---
st.sidebar.header("System Settings")
current_mode = supabase.table("settings").select("value").eq("key", "workflow_mode").single().execute().data['value']

new_mode = st.sidebar.radio("Workflow Mode", ["MANUAL", "AUTO"], index=0 if current_mode == "MANUAL" else 1)

if new_mode != current_mode:
    supabase.table("settings").update({"value": new_mode}).eq("key", "workflow_mode").execute()
    st.sidebar.success(f"Mode switched to {new_mode}")

# --- AGENT MONITOR ---
st.header("Agent Grid")
agents_data = supabase.table("agents").select("*").order("id").execute().data

cols = st.columns(4)
for idx, agent in enumerate(agents_data):
    with cols[idx % 4]:
        status_color = "🟢" if agent['status'] == "FREE" else "🔴"
        st.subheader(f"{agent['name']}")
        st.write(f"**Role:** {agent['role']}")
        st.write(f"**Status:** {status_color} {agent['status']}")
        st.write(f"**Current Ticket:** {agent['current_ticket'] or 'None'}")
        st.divider()

# --- RECENT ACTIVITY (Placeholder) ---
st.header("Active PRs & Deployments")
st.info("Awaiting activity from Agents 4-8...")