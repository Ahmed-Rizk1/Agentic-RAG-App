import asyncio
import httpx
import json

async def run_risk_test():
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
        
        # Step 4: Trigger risk report generation
        print("\nTriggering risk analysis...")
        risk_trigger_res = await client.post(
            f"{base_url}/api/projects/{project_id}/documents/{document_id}/risk-analysis",
            headers=headers
        )
        if risk_trigger_res.status_code != 201:
            print(f"Risk analysis trigger failed: {risk_trigger_res.status_code} - {risk_trigger_res.text}")
            return
            
        report = risk_trigger_res.json()
        print(f"Overall Risk Score: {report['overall_score'].upper()}")
        print(f"Extracted Risks count: {len(report['risks'])}")
        for idx, risk in enumerate(report['risks']):
            print(f"  Risk {idx+1}:")
            print(f"    Category: {risk['category']}")
            print(f"    Severity: {risk['severity']}")
            print(f"    Description: {risk['description']}")
            print(f"    Evidence: {risk['evidence']}")
            print(f"    Page: {risk['page']}")
            print("-" * 30)
            
        # Step 5: Test GET endpoint
        print("\nVerifying GET retrieval...")
        get_res = await client.get(
            f"{base_url}/api/projects/{project_id}/documents/{document_id}/risk-analysis",
            headers=headers
        )
        if get_res.status_code == 200:
            print("GET retrieved risk report successfully.")
        else:
            print(f"GET failed: {get_res.status_code}")

if __name__ == "__main__":
    asyncio.run(run_risk_test())
