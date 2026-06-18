import httpx
import json
from typing import AsyncGenerator
import os

class LLMService:
    API_URL = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434/api/chat")

    @staticmethod
    async def stream_summarize_chunks(chunks: list[str]) -> AsyncGenerator[str, None]:
        """
        Executes a local Map-Reduce summarization pipeline.
        - Map Phase: Streams individual chunk analysis.
        - Reduce Phase: Synthesizes all summaries into an Executive Summary.
        """
        all_section_summaries = []
        
        async with httpx.AsyncClient(timeout=180.0) as client:

            for i, chunk in enumerate(chunks):
                current_chunk_summary = ""
                
                payload = {
                    "model": "llama3.2:3b",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are an elite research analysis assistant.\n"
                                "Summarize the text extract into precise markdown bullet points.\n"
                                "CRITICAL: Output ONLY bullet points with **keywords** bolded. No intros/outros."
                            )
                        },
                        {
                            "role": "user",
                            "content": f"Extract key insights from this text section:\n\n{chunk}"
                        }
                    ],
                    "options": {"temperature": 0.3},
                    "stream": True
                }
                
                try:
                    async with client.stream("POST", LLMService.API_URL, json=payload) as response:
                        if response.status_code == 200:
                            async for line in response.aiter_lines():
                                if line:
                                    data = json.loads(line)
                                    token = data.get("message", {}).get("content", "")
                                    yield token
                                    current_chunk_summary += token
                            
                            all_section_summaries.append(current_chunk_summary)
                            yield "\n\n---\n\n"
                        else:
                            yield f"\n\n[Error: Local Ollama returned status {response.status_code}]\n\n"
                except Exception as e:
                    print(f"DEBUG: Map exception for chunk {i+1}: {str(e)}")
                    yield f"\n\n[Connection Error: {str(e)}]\n\n"


            if len(all_section_summaries) > 1:
                yield "## 📊 GLOBAL EXECUTIVE SUMMARY (Map-Reduce Synthesis)\n"
                
                reduced_context = "\n\n".join(all_section_summaries)
                
                reduce_payload = {
                    "model": "llama3.2:3b",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a world-class principal research analyst.\n"
                                "You will be given a comprehensive collection of sub-summaries from a massive technical paper.\n"
                                "Your task is to synthesize these notes into a cohesive, high-level Executive Summary.\n\n"
                                "STRUCTURE REQUIREMENTS:\n"
                                "1. Start with an '### 📑 High-Level Overview' paragraph outlining the main objective.\n"
                                "2. Follow with a '### 🔑 Crucial Discoveries' bulleted list combining the most important breakthroughs.\n"
                                "3. End with a '### 💡 Architectural/Strategic Impact' paragraph.\n"
                                "Do NOT repeat technical details point-by-point; synthesize them globally."
                            )
                        },
                        {
                            "role": "user",
                            "content": f"Synthesize these extracted document notes into a master summary:\n\n{reduced_context}"
                        }
                    ],
                    "options": {"temperature": 0.4}, # Slightly higher temperature for better thematic synthesis
                    "stream": True
                }
                
                try:
                    async with client.stream("POST", LLMService.API_URL, json=reduce_payload) as response:
                        if response.status_code == 200:
                            async for line in response.aiter_lines():
                                if line:
                                    data = json.loads(line)
                                    token = data.get("message", {}).get("content", "")
                                    yield token
                        else:
                            yield f"\n\n[Error compiling executive summary: Status {response.status_code}]\n\n"
                except Exception as e:
                    print(f"DEBUG: Reduce phase exception: {str(e)}")
                    yield f"\n\n[Reduce Synthesis Connection Error: {str(e)}]\n\n"