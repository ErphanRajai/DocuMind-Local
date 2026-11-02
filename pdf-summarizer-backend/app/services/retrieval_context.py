"""Resolve short conversational references without an extra model round trip."""
import re

REFERENCE = re.compile(r"\b(it|its|they|them|their|that|this|those|these|he|she|his|her|why|what about|how about|more|continue|second|first|latter|former)\b", re.I)


def retrieval_query(question, history):
    """Only previous USER turns provide search context; never trust generated facts."""
    if not history or not REFERENCE.search(question):
        return question, False
    previous = [message["content"] for message in history if message["role"] == "user"][-2:]
    if not previous:
        return question, False
    context = "\n".join(text[:700] for text in previous)
    return f"Earlier user questions:\n{context}\nCurrent question:\n{question}", True
