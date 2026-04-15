import os
from jira import JIRA
from dotenv import load_dotenv

load_dotenv()

# Connect to Jira
jira = JIRA(
    server=os.getenv("JIRA_URL"), 
    basic_auth=(os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN"))
)

print("Searching for the 'Agent' field ID...")
for field in jira.fields():
    if "Agent" in field['name']:
        print(f"FOUND IT! -> Field Name: {field['name']} | ID: {field['id']}")