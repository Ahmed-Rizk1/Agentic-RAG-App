import time
import httpx
import fitz
import os

# 1. Create a dummy PDF with some procurement text
def create_dummy_pdf():
    os.makedirs("uploads", exist_ok=True)
    pdf_path = "uploads/dummy_procurement.pdf"
    
    doc = fitz.open()
    # Page 1 - Title and general info
    page1 = doc.new_page()
    page1.insert_text((50, 50), "TENDER NO: MOF-2026-999\nORGANIZATION: Ministry of Health (MOH)\nTitle: Supply of Medical Equipment\nBudget: 2500000.00 SAR\nSubmission Deadline: 2026-11-20\nRequired Certifications: ISO 13485, Saudi FDA classification grade B.\n\nDescription: This tender is issued by the Ministry of Health for the purpose of acquiring advanced medical equipment for various regional hospitals in Riyadh and Jeddah.", fontsize=11)
    
    # Page 2 - Terms and details
    page2 = doc.new_page()
    page2.insert_text((50, 50), "Terms & Conditions:\n1. The bidder must submit a bid bond of 1% of the total value.\n2. All equipment must have a warranty of at least 3 years.\n3. The currency of the bid must be Saudi Riyals (SAR).\n4. All documentations should be submitted in Arabic or English.\n\nTechnical Specifications:\n- MRI Machine: 3 Tesla, high gradient.\n- CT Scanner: 128 slices, low dose technology.", fontsize=11)
    
    doc.save(pdf_path)
    doc.close()
    print(f"Created dummy PDF at {pdf_path}")
    return pdf_path

async def run_e2e_test():
    pdf_path = create_dummy_pdf()
    
    # Base URL for API
    base_url = "http://localhost:8000"
    
    # Use httpx client
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Login to get token
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
        
        # Step 2: Create a project
        project_res = await client.post(
            f"{base_url}/api/projects",
            headers=headers,
            json={"name": "Medical Equipment Project", "description": "Tracking healthcare procurement tenders"}
        )
        if project_res.status_code != 201:
            print(f"Project creation failed: {project_res.text}")
            return
            
        project = project_res.json()
        project_id = project["id"]
        print(f"Created project: {project['name']} (ID: {project_id})")
        
        # Step 3: Upload the PDF
        print("Uploading PDF...")
        with open(pdf_path, "rb") as f:
            upload_res = await client.post(
                f"{base_url}/api/projects/{project_id}/documents",
                headers=headers,
                files={"file": (os.path.basename(pdf_path), f, "application/pdf")}
            )
            
        if upload_res.status_code != 201:
            print(f"Upload failed: {upload_res.text}")
            return
            
        document = upload_res.json()
        doc_id = document["id"]
        print(f"Document uploaded. ID: {doc_id}. Status: {document['status']}")
        
        # Step 4: Poll status until ready or failed
        print("Polling document status...")
        for i in range(10):
            time.sleep(3)
            doc_detail_res = await client.get(
                f"{base_url}/api/projects/{project_id}/documents/{doc_id}",
                headers=headers
            )
            if doc_detail_res.status_code != 200:
                print(f"Failed to fetch details: {doc_detail_res.text}")
                break
                
            doc_detail = doc_detail_res.json()
            status = doc_detail["status"]
            print(f"Poll {i+1}: Status is {status}")
            if status in ("ready", "failed"):
                if status == "ready":
                    print("\nSuccess! Document fully processed.")
                    print(f"Doc Type: {doc_detail['doc_type']}")
                    print(f"Page Count: {doc_detail['page_count']}")
                    print("Metadata:")
                    for k, v in (doc_detail.get("metadata") or {}).items():
                        print(f"  {k}: {v}")
                else:
                    print(f"\nProcessing failed: {doc_detail['processing_error']}")
                break
        else:
            print("\nTimeout waiting for document processing.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_e2e_test())
