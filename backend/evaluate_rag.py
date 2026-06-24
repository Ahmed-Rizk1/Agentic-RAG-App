import asyncio
import httpx
import json
import os
import sys

# Reconfigure stdout to handle UTF-8 characters on Windows terminal
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure backend root is in PYTHONPATH so we can import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.llm import call_llm_json


# Test dataset of QA pairs for dummy_procurement.pdf
EVAL_DATASET = [
    {
        "question": "Who is the issuer of the medical equipment tender?",
        "gold_answer": "Ministry of Health (MOH)"
    },
    {
        "question": "What is the total budget for the Supply of Medical Equipment tender?",
        "gold_answer": "2,500,000.00 SAR (2.5 million Saudi Riyals)"
    },
    {
        "question": "What certifications must the bidder possess?",
        "gold_answer": "ISO 13485 and Saudi FDA classification grade B."
    },
    {
        "question": "What is the required warranty period for the equipment?",
        "gold_answer": "At least 3 years."
    },
    {
        "question": "What are the specifications of the MRI Machine and the CT Scanner?",
        "gold_answer": "MRI Machine: 3 Tesla, high gradient. CT Scanner: 128 slices, low dose technology."
    }
]

async def evaluate_context_precision(question: str, chunks: list[str]) -> float:
    """Evaluates what fraction of retrieved chunks are relevant to the question."""
    if not chunks:
        return 0.0
    
    chunks_str = "\n\n".join([f"Chunk {i+1}: {c}" for i, c in enumerate(chunks)])
    prompt = (
        f"Question: {question}\n\n"
        f"Retrieved Chunks:\n{chunks_str}\n\n"
        "Determine how many of these retrieved chunks are directly relevant to answering the question.\n"
        "Respond ONLY with a JSON object of this structure:\n"
        "{\n"
        "  \"relevant_count\": int,\n"
        "  \"total_count\": int,\n"
        "  \"explanation\": \"string\"\n"
        "}"
    )
    try:
        res = await call_llm_json(prompt, "You are a precision evaluator. Return JSON.", "eval_precision")
        relevant = int(res.get("relevant_count", 0))
        total = int(res.get("total_count", len(chunks)))
        if total == 0:
            return 0.0
        return min(1.0, max(0.0, relevant / total))
    except Exception as e:
        print(f"Error evaluating precision: {e}")
        return 0.5  # Neutral fallback

async def evaluate_context_recall(gold_answer: str, context: str) -> float:
    """Evaluates if the retrieved context contains the information in the gold standard answer."""
    prompt = (
        f"Gold standard answer: {gold_answer}\n\n"
        f"Retrieved Context:\n{context}\n\n"
        "Determine if the retrieved context contains all the key facts/information present in the gold standard answer.\n"
        "Respond ONLY with a JSON object of this structure:\n"
        "{\n"
        "  \"has_recall\": true | false,\n"
        "  \"explanation\": \"string\"\n"
        "}"
    )
    try:
        res = await call_llm_json(prompt, "You are a recall evaluator. Return JSON.", "eval_recall")
        return 1.0 if res.get("has_recall") else 0.0
    except Exception as e:
        print(f"Error evaluating recall: {e}")
        return 0.5

async def evaluate_faithfulness(context: str, generated_answer: str) -> float:
    """Evaluates if the generated answer is fully grounded in the retrieved context."""
    prompt = (
        f"Retrieved Context:\n{context}\n\n"
        f"Generated Answer: {generated_answer}\n\n"
        "Determine if the generated answer is fully grounded in and supported by the retrieved context alone.\n"
        "It must not contain outside knowledge or hallucinations.\n"
        "Respond ONLY with a JSON object of this structure:\n"
        "{\n"
        "  \"is_faithful\": true | false,\n"
        "  \"explanation\": \"string\"\n"
        "}"
    )
    try:
        res = await call_llm_json(prompt, "You are a faithfulness checker. Return JSON.", "eval_faithfulness")
        return 1.0 if res.get("is_faithful") else 0.0
    except Exception as e:
        print(f"Error evaluating faithfulness: {e}")
        return 0.5

async def evaluate_answer_relevancy(question: str, generated_answer: str) -> float:
    """Evaluates if the generated answer directly addresses the question."""
    prompt = (
        f"Question: {question}\n\n"
        f"Generated Answer: {generated_answer}\n\n"
        "Determine if the generated answer directly and accurately addresses the question asked.\n"
        "Respond ONLY with a JSON object of this structure:\n"
        "{\n"
        "  \"is_relevant\": true | false,\n"
        "  \"explanation\": \"string\"\n"
        "}"
    )
    try:
        res = await call_llm_json(prompt, "You are an answer relevancy checker. Return JSON.", "eval_relevancy")
        return 1.0 if res.get("is_relevant") else 0.0
    except Exception as e:
        print(f"Error evaluating relevancy: {e}")
        return 0.5

async def run_evaluation():
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
        
        results = []
        
        print("\nStarting evaluation of RAG pipeline...")
        print("=" * 60)
        
        for idx, item in enumerate(EVAL_DATASET):
            question = item["question"]
            gold_answer = item["gold_answer"]
            
            print(f"\n[Test Case {idx+1}] Question: {question}")
            
            # Send message to chat stream and capture chunks + final answer
            chat_payload = {
                "message": question,
                "session_id": None,
                "document_ids": None
            }
            
            retrieved_chunks = []
            final_answer = ""
            is_grounded_check = None
            
            async with client.stream(
                "POST",
                f"{base_url}/api/projects/{project_id}/chats/stream",
                headers=headers,
                json=chat_payload
            ) as response:
                if response.status_code != 200:
                    print(f"  Stream failed: {response.status_code}")
                    continue
                    
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
                            retrieved_chunks = [src["snippet"] for src in data]
                        elif current_event == "token":
                            if data != "[CLEAR]":
                                final_answer += data
                        elif current_event == "result":
                            is_grounded_check = data["is_grounded"]
                            final_answer = data["final_response"]
            
            context_text = "\n\n".join(retrieved_chunks)
            
            # Run metrics
            precision = await evaluate_context_precision(question, retrieved_chunks)
            recall = await evaluate_context_recall(gold_answer, context_text)
            faithfulness = await evaluate_faithfulness(context_text, final_answer)
            relevancy = await evaluate_answer_relevancy(question, final_answer)
            
            print(f"  Generated Answer: {final_answer}")
            print(f"  Grounding Check (Grounded): {is_grounded_check}")
            print(f"  Metrics -> Precision: {precision:.2f} | Recall: {recall:.2f} | Faithfulness: {faithfulness:.2f} | Relevancy: {relevancy:.2f}")
            
            results.append({
                "question": question,
                "precision": precision,
                "recall": recall,
                "faithfulness": faithfulness,
                "relevancy": relevancy
            })
            
        # Summary
        print("\n" + "=" * 60)
        print("EVALUATION SUMMARY")
        print("=" * 60)
        
        avg_precision = sum(r["precision"] for r in results) / len(results) if results else 0
        avg_recall = sum(r["recall"] for r in results) / len(results) if results else 0
        avg_faithfulness = sum(r["faithfulness"] for r in results) / len(results) if results else 0
        avg_relevancy = sum(r["relevancy"] for r in results) / len(results) if results else 0
        
        print(f"Average Context Precision: {avg_precision:.2f} (Target: >0.75)")
        print(f"Average Context Recall:    {avg_recall:.2f} (Target: >0.70)")
        print(f"Average Faithfulness:     {avg_faithfulness:.2f} (Target: >0.85)")
        print(f"Average Answer Relevancy:  {avg_relevancy:.2f} (Target: >0.80)")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_evaluation())
