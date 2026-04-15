import os
import datetime
from fastapi import FastAPI, HTTPException, Header, Request, BackgroundTasks
from supabase import create_client, Client
from anthropic import Anthropic
from jira import JIRA
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Maestro Orchestrator - Phase 3")

# --- Configuration & Clients ---
# Check if key exists to avoid Anthropic initialization errors
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
jira = JIRA(
    server=os.getenv("JIRA_URL"), 
    basic_auth=(os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN"))
)

# Initialize Anthropic only if key is present
anthropic = Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

# Set this to your specific Jira Custom Field ID
CUSTOM_FIELD_ID = "customfield_10039" 

def jira_audit_log(ticket_id: str, agent_name: str, action: str):
    """
    Writes to Jira. Uses Haiku if ANTHROPIC_KEY is present, 
    otherwise defaults to a professional text format.
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    if anthropic:
        try:
            prompt = f"Format a short, professional Jira audit comment for Agent: {agent_name}. Action: {action}. Timestamp: {timestamp}. Be concise and poetic."
            response = anthropic.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )
            audit_comment = response.content[0].text
        except Exception:
            audit_comment = f"⚠️ [FALLBACK] STAMP: {timestamp} | AGENT: {agent_name} | ACTION: {action}"
    else:
        # Generic non-LLM format to save tokens
        audit_comment = (
            f"🛠️ **MAESTRO AUDIT LOG**\n"
            f"**Timestamp:** {timestamp}\n"
            f"**Agent:** {agent_name}\n"
            f"**Action:** {action}"
        )
    
    jira.add_comment(ticket_id, audit_comment)


async def run_dispatcher(issue_key: str):
    """
    Phase 3 Dispatcher: Checks mode, matches role, locks agent, and updates Jira.
    """
    try:
        # 1. Fetch System Mode from Supabase 'settings' table
        response = supabase.table("settings") \
            .select("value") \
            .eq("key", "workflow_mode") \
            .single() \
            .execute()

        mode = response.data.get("value", "MANUAL") if response.data else "MANUAL"

        # 1.2 CASE: MANUAL MODE
        if mode == "MANUAL":
            print(f"LOG: [MANUAL MODE] Workflow for {issue_key} halted. No Jira action taken.")
            return

        # 1.3 CASE: AUTO MODE
        elif mode == "AUTO":
            print(f"LOG: [AUTO MODE] Starting assignment for {issue_key}...")

            # 2. IDENTIFY ROLE & LABELS
            issue = jira.issue(issue_key)
            labels = [l.lower() for l in issue.fields.labels]
            
            required_role = None
            if "frontend" in labels:
                required_role = "Frontend"
            elif "backend" in labels:
                required_role = "Backend"

            # 3. FIND AND ASSIGN AGENT
            query = supabase.table("agents").select("*").eq("status", "FREE")
            if required_role:
                query = query.eq("role", required_role)
            
            agent_query = query.limit(1).execute()
            
            if not agent_query.data:
                # Assuming jira_audit_log is a helper function you've defined elsewhere
                jira_audit_log(issue_key, "Dispatcher", f"Assignment Failed: No FREE {required_role or 'general'} agents.")
                return

            agent = agent_query.data[0]
            agent_id = agent["id"]
            agent_name = agent.get("name", f"Agent-{agent_id}")

            # 4. UPDATE JIRA (Board Move & Custom Field)
            try:
                # Move card to In Progress
                jira.transition_issue(issue, transition="In Progress")
                
                # Write Agent Name to your Custom Field
                issue.update(fields={CUSTOM_FIELD_ID: agent_name})
                print(f"Jira updated for {issue_key}: Status -> In Progress, Agent -> {agent_name}")
            except Exception as e:
                print(f"Jira UI update error: {e}")

            # 5. UPDATE SUPABASE STATE
            # We update the agent to BUSY and set their current_ticket at the same time
            supabase.table("agents").update({
                "status": "BUSY",
                "current_ticket": issue_key
            }).eq("id", agent_id).execute()
            
            # Record the link
            # We record the mapping in ticket_branches 
            # Using 'jira_id' and 'fork_branch_name' to match your schema
            supabase.table("ticket_branches").upsert({
                "jira_id": issue_key,
                "fork_branch_name": f"dev/{issue_key.lower()}",
                "agent_id": agent_id  # This makes your dashboard work perfectly
            }).execute()

            # 6. Final Audit
            # Using the correct Jira library method: add_comment
            jira.add_comment(issue_key, f"Ticket assigned to {agent_name}. Status moved to In Progress. Phase 3 Complete.")

    except Exception as e:
        print(f"CRITICAL ERROR in dispatcher: {str(e)}")
        jira.issue_add_comment(issue_key, f"❌ **Dispatcher Error**: {str(e)}")


@app.post("/webhooks/jira")
async def jira_webhook(request: Request, 
                       background_tasks: BackgroundTasks, 
                       token: str = None):
    # Check if the token in the URL matches your secret
    if token != os.getenv("ORCHESTRATOR_SECRET"):
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    issue_key = data.get("issue", {}).get("key")
    
    if issue_key:
        background_tasks.add_task(run_dispatcher, issue_key)
        return {"status": "accepted", "issue": issue_key}
    
    return {"status": "ignored"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)