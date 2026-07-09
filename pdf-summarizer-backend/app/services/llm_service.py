import httpx
import json
from typing import AsyncGenerator, Optional
import os

class LLMService:
    API_URL = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434/api/chat")

    # --- پرامپت فوق‌حرفه‌ای برای استخراج اطلاعات از هر چانک (Map Phase) ---
    MAP_SYSTEM_PROMPT = (
        "You are an elite AI Senior Research Scientist and Technical Analyst.\n"
        "Your task is to analyze the provided document extract and distill its core intelligence.\n\n"
        "ENFORCE STRICT MARKDOWN FORMATTING:\n"
        "- Use **Bold Text** for all critical entities, metrics, technical terminology, and dates.\n"
        "- Format findings into clean analytical paragraphs paired with high-density bullet points.\n"
        "- Never write walls of plain text. Keep paragraphs concise (2-3 sentences max).\n"
        "- Do NOT add conversational filler like 'Here is the summary' or 'Based on the text'."
    )

    # --- پرامپت فوق‌حرفه‌ای برای ترکیب نهایی و ساخت گزارش SOTA (Reduce Phase & Short Docs) ---
    REDUCE_SYSTEM_PROMPT = (
        "You are a Principal AI Executive Strategist producing a State-of-the-Art (SOTA) Intelligence Briefing.\n"
        "Synthesize the provided text into an executive-ready, highly structured analytical document.\n\n"
        "MANDATORY DOCUMENT STRUCTURE (Use exact Markdown headings):\n\n"
        "### 💎 Executive Synthesis\n"
        "Write a powerful, authoritative 2-paragraph summary capturing the overarching theme, objective, and paradigm shift.\n\n"
        "### ⚡ Key Strategic & Technical Breakthroughs\n"
        "Provide a detailed bulleted list. Start each bullet with a **Bold Action Concept** followed by a deep analytical explanation.\n\n"
        "### 📊 Analytical Implications & Next Steps\n"
        "Conclude with a structured paragraph evaluating practical applications, limitations, or future trajectories.\n\n"
        "FORMATTING LAWS:\n"
        "- Use rich Markdown rendering (headers, bold emphasis, blockquotes `>` for critical takeaways).\n"
        "- Maintain an academic yet executive, highly authoritative tone."
    )

    @staticmethod
    async def summarize_chunks(chunks: list[str]) -> str:
        """Non-streaming Map-Reduce summarization for background processing."""
        all_section_summaries = []
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            for i, chunk in enumerate(chunks):
                payload = {
                    "model": "llama3.2:3b",
                    "messages": [
                        {"role": "system", "content": LLMService.MAP_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Analyze and extract key intelligence from this section:\n\n{chunk}"}
                    ],
                    "options": {"temperature": 0.3},
                    "stream": False
                }
                try:
                    response = await client.post(LLMService.API_URL, json=payload)
                    if response.status_code == 200:
                        all_section_summaries.append(response.json().get("message", {}).get("content", ""))
                except Exception as e:
                    print(f"DEBUG: Map exception for chunk {i+1}: {str(e)}")
            
            if not all_section_summaries:
                return "خطا در تولید خلاصه."
                
            reduced_context = "\n\n---\n\n".join(all_section_summaries)
            
            reduce_payload = {
                "model": "llama3.2:3b",
                "messages": [
                    {"role": "system", "content": LLMService.REDUCE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Synthesize these extracted section notes into a master SOTA Executive Briefing:\n\n{reduced_context}"}
                ],
                "options": {"temperature": 0.4},
                "stream": False
            }
            try:
                response = await client.post(LLMService.API_URL, json=reduce_payload)
                if response.status_code == 200:
                    return response.json().get("message", {}).get("content", "")
            except Exception as e:
                print(f"DEBUG: Reduce phase exception: {str(e)}")
                
            return reduced_context

    @staticmethod
    async def stream_summarize_chunks(chunks: list[str], custom_prompt: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Adaptive streaming summarization pipeline with SOTA formatting."""
        total_word_count = sum(len(c.split()) for c in chunks)
        full_text_joined = "\n\n".join(chunks)

        async with httpx.AsyncClient(timeout=180.0) as client:
            # --- مسیر ۱: فایل‌های کوتاه یا پرامپت اختصاصی کاربر ---
            if total_word_count < 2500 or custom_prompt:
                system_instruction = (
                    custom_prompt if custom_prompt else LLMService.REDUCE_SYSTEM_PROMPT
                )
                payload = {
                    "model": "llama3.2:3b",
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": f"Document Text to Synthesize:\n\n{full_text_joined[:12000]}"}
                    ],
                    "options": {"temperature": 0.35},
                    "stream": True
                }
                try:
                    async with client.stream("POST", LLMService.API_URL, json=payload) as response:
                        if response.status_code == 200:
                            async for line in response.aiter_lines():
                                if line:
                                    data = json.loads(line)
                                    yield data.get("message", {}).get("content", "")
                        else:
                            yield f"[Error: Local Ollama returned status {response.status_code}]"
                except Exception as e:
                    yield f"[Connection Error: {str(e)}]"
                return

            # --- مسیر ۲: فایل‌های طولانی (Map-Reduce) ---
            all_section_summaries = []
            for i, chunk in enumerate(chunks):
                current_chunk_summary = ""
                payload = {
                    "model": "llama3.2:3b",
                    "messages": [
                        {"role": "system", "content": LLMService.MAP_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Extract key intelligence from this section:\n\n{chunk}"}
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
                    yield f"\n\n[Connection Error: {str(e)}]\n\n"

            if len(all_section_summaries) > 1:
                yield "\n\n> ⏳ **Compiling Master SOTA Executive Synthesis...**\n\n---\n\n"
                reduced_context = "\n\n".join(all_section_summaries)
                reduce_payload = {
                    "model": "llama3.2:3b",
                    "messages": [
                        {"role": "system", "content": LLMService.REDUCE_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Synthesize these extracted section notes into a master SOTA Executive Briefing:\n\n{reduced_context}"}
                    ],
                    "options": {"temperature": 0.4},
                    "stream": True
                }
                try:
                    async with client.stream("POST", LLMService.API_URL, json=reduce_payload) as response:
                        if response.status_code == 200:
                            async for line in response.aiter_lines():
                                if line:
                                    data = json.loads(line)
                                    yield data.get("message", {}).get("content", "")
                        else:
                            yield f"\n\n[Error compiling executive summary: Status {response.status_code}]\n\n"
                except Exception as e:
                    yield f"\n\n[Reduce Synthesis Connection Error: {str(e)}]\n\n"