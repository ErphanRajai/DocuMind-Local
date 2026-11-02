import pytest

from app.services.context_budget import CONTEXT_TOKENS, OUTPUT_TOKENS, TEMPLATE_RESERVE, TokenCounter, build_prompt
from app.services.errors import GenerationError


@pytest.mark.parametrize("answer_length", ["short", "long"])
def test_question_and_each_source_survive_large_history_and_documents(answer_length):
    counter = TokenCounter()
    question = "Compare the opening dates and budgets."
    history = [{"role": "assistant", "content": "older history " * 1000}] * 8
    sources = [{"title": f"Document {index}", "text": f"Opening date {index}. Budget {index}. " * 5000} for index in range(3)]
    plan = build_prompt(counter, "Use only the provided sources.", question, history, sources, answer_length, spread=True)
    assert plan.messages[-1] == {"role": "user", "content": question}
    assert all(f"=== Document {index} ===" in plan.messages[0]["content"] for index in range(3))
    assert plan.metadata["history_messages_omitted"] > 0 and plan.metadata["excerpts_shortened"] == 3
    assert counter.messages(plan.messages) + OUTPUT_TOKENS[answer_length] + TEMPLATE_RESERVE <= CONTEXT_TOKENS
    assert plan.metadata["context_notice"]


def test_recent_history_is_preserved_in_order():
    history = [{"role": "user", "content": "old " * 2000}, {"role": "assistant", "content": "The budget is 4800 dollars."}]
    plan = build_prompt(TokenCounter(), "Help the user.", "What was the budget?", history)
    assert plan.messages[1] == history[-1]
    assert history[0] not in plan.messages


def test_current_question_is_rejected_instead_of_silently_truncated():
    with pytest.raises(GenerationError, match="question is too long"):
        build_prompt(TokenCounter(), "Answer accurately.", "🌱" * 2000)


def test_unicode_excerpt_boundaries_and_fallback_are_safe():
    counter = TokenCounter()
    text = "سلام 🌱 garden 中文 " * 1000
    result = counter.excerpt(text, 300, spread=True)
    assert counter.count(result) <= 300
    assert "\ufffd" not in result
    assert counter.count("🌱") == 4
    assert TokenCounter.from_metadata({"tokenizer.ggml.pre": "unknown"}).method == "utf8_upper_bound"


def test_short_sources_are_not_unnecessarily_cut():
    plan = build_prompt(TokenCounter(), "Use the source.", "When?", sources=[{"title": "Notes", "text": "The opening day is May 3."}])
    assert "The opening day is May 3." in plan.messages[0]["content"]
    assert plan.metadata["excerpts_shortened"] == 0


def test_qwen_tokenizer_splits_each_digit_using_local_metadata():
    counter=TokenCounter.from_metadata({'tokenizer.ggml.pre':'qwen2','tokenizer.ggml.tokens':list('0123456789')+['12'],'tokenizer.ggml.merges':['1 2']})
    assert counter.method=='qwen_bpe' and counter.count('123456')==6
