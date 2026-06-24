import asyncio
import httpx
import json

async def run_proposal_test():
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Login
        login_res = await client.post(
            f"{base_url}/api/auth/login",
            json={"email": "test@example.com", "password": "Test1234!"}
        )
        if login_res.status_code != 200:
            print(f"Login failed: {login_res.text}")
            return
            
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("Logged in successfully.")
        
        # Step 2: Get active projects
        projects_res = await client.get(f"{base_url}/api/projects", headers=headers)
        projects = projects_res.json()["projects"]
        if not projects:
            print("No projects found.")
            return
            
        project_id = projects[0]["id"]
        print(f"Using Project: {projects[0]['name']} (ID: {project_id})")
        
        # Step 3: Get active documents in this project
        docs_res = await client.get(f"{base_url}/api/projects/{project_id}/documents", headers=headers)
        documents = docs_res.json()
        if not documents:
            print("No documents found.")
            return
            
        document_id = documents[0]["id"]
        print(f"Using Document: {documents[0]['filename']} (ID: {document_id})")
        
        # Step 4: Trigger proposal generation
        print("\nTriggering proposal generation...")
        proposal_trigger_res = await client.post(
            f"{base_url}/api/projects/{project_id}/documents/{document_id}/proposal",
            headers=headers
        )
        if proposal_trigger_res.status_code != 201:
            print(f"Proposal generation trigger failed: {proposal_trigger_res.status_code} - {proposal_trigger_res.text}")
            return
            
        proposal = proposal_trigger_res.json()
        print("\nProposal Draft Generated Successfully:")
        print("=" * 60)
        print("EXECUTIVE SUMMARY:")
        print(proposal["executive_summary"])
        print("-" * 60)
        print("SCOPE UNDERSTANDING:")
        print(proposal["scope_understanding"])
        print("-" * 60)
        print("COMPLIANCE SECTION:")
        print(proposal["compliance_section"])
        print("-" * 60)
        print("REQUIRED DELIVERABLES:")
        print(proposal["required_deliverables"])
        print("=" * 60)
            
        # Step 5: Test GET endpoint
        print("\nVerifying GET retrieval...")
        get_res = await client.get(
            f"{base_url}/api/projects/{project_id}/documents/{document_id}/proposal",
            headers=headers
        )
        if get_res.status_code == 200:
            print("GET retrieved proposal draft successfully.")
        else:
            print(f"GET failed: {get_res.status_code} - {get_res.text}")

if __name__ == "__main__":
    asyncio.run(run_proposal_test())
