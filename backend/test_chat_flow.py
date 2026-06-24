import asyncio
import httpx
import json

async def run_chat_test():
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
            print("No projects found. Please run test_manual_flow.py first.")
            return
            
        project_id = projects[0]["id"]
        print(f"Using Project: {projects[0]['name']} (ID: {project_id})")
        
        # Step 3: Call SSE chat stream
        # Ask a query about the medical equipment budget or deadline
        chat_payload = {
            "message": "What is the budget and deadline for the medical equipment tender?",
            "session_id": None,
            "document_ids": None
        }
        
        print("\n--- Starting SSE Stream ---")
        session_id = None
        
        # We use client.stream to handle SSE
        async with client.stream(
            "POST",
            f"{base_url}/api/projects/{project_id}/chats/stream",
            headers=headers,
            json=chat_payload
        ) as response:
            if response.status_code != 200:
                print(f"Failed to initiate stream: {response.status_code}")
                # read body
                body = await response.aread()
                print(body.decode("utf-8"))
                return
                
            current_event = None
            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("event: "):
                    current_event = line[7:]
                elif line.startswith("data: "):
                    data_str = line[6:]
                    data = json.loads(data_str)
                    
                    if current_event == "sources":
                        print(f"\n[Sources Received]: Found {len(data)} matching chunks:")
                        for idx, src in enumerate(data):
                            print(f"  {idx+1}. Page {src['page']}: {src['snippet']}")
                        print("\n[Assistant Typing]: ", end="", flush=True)
                    elif current_event == "token":
                        if data == "[CLEAR]":
                            # handle retraction/fallback
                            print("\n[Retracted/Cleared answer due to grounding failure]")
                            print("[Assistant Typing]: ", end="", flush=True)
                        else:
                            print(data, end="", flush=True)
                    elif current_event == "result":
                        print("\n")
                        print(f"[Result Received]:")
                        print(f"  Session ID: {data['session_id']}")
                        print(f"  Is Grounded: {data['is_grounded']}")
                        session_id = data["session_id"]
                    elif current_event == "error":
                        print(f"\n[Error Received]: {data['message']}")
                        
        # Step 4: Fetch chat history to verify persistence
        if session_id:
            print(f"\n--- Verifying Chat History for Session {session_id} ---")
            history_res = await client.get(
                f"{base_url}/api/projects/{project_id}/chats/{session_id}",
                headers=headers
            )
            if history_res.status_code != 200:
                print(f"Failed to fetch chat history: {history_res.text}")
                return
                
            messages = history_res.json()
            print(f"Retrieved {len(messages)} messages from history:")
            for msg in messages:
                print(f"  Role: {msg['role']}")
                print(f"  Content: {msg['content']}")
                if msg.get("sources"):
                    print(f"  Sources Count: {len(msg['sources'])}")
                print("-" * 40)

if __name__ == "__main__":
    asyncio.run(run_chat_test())
