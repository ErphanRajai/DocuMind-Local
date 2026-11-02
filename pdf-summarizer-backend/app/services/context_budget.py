"""Build prompts that leave room for the answer inside the local 8K context."""

from dataclasses import dataclass

from .errors import GenerationError

CONTEXT_TOKENS = 8192
TEMPLATE_RESERVE = 512
OUTPUT_TOKENS = {"short": 512, "long": 1536}


class TokenCounter:
    """Rebuild supported tokenizers from local GGUF metadata; otherwise use a byte bound."""

    def __init__(self, tokenizer=None, method='llama_bpe'):
        self.tokenizer = tokenizer
        self.method = method if tokenizer is not None else "utf8_upper_bound"

    @classmethod
    def from_metadata(cls, info):
        family = info.get("tokenizer.ggml.pre")
        if family not in {'llama-bpe','qwen2'}:
            return cls()
        vocab = info.get("tokenizer.ggml.tokens")
        merges = info.get("tokenizer.ggml.merges")
        if not vocab or not merges:
            return cls()
        from tokenizers import Regex, Tokenizer, decoders, models, pre_tokenizers

        tokenizer = Tokenizer(models.BPE(
            vocab={token: index for index, token in enumerate(vocab)},
            merges=[tuple(merge.split(" ", 1)) for merge in merges],
            ignore_merges=family == 'llama-bpe',
        ))
        # Llama 3's pre-tokenization pattern, documented by Meta:
        # https://github.com/meta-llama/llama3/blob/main/llama/tokenizer.py
        pattern = r"(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}{1,3}| ?[^\s\p{L}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+"
        if family == 'qwen2':
            # Qwen team's tokenizer: digits are split individually, unlike Llama 3.
            # https://github.com/huggingface/transformers/blob/v4.51.3/src/transformers/models/qwen2/tokenization_qwen2.py
            pattern = r"(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}| ?[^\s\p{L}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+"
        tokenizer.pre_tokenizer = pre_tokenizers.Sequence([
            pre_tokenizers.Split(Regex(pattern), behavior="isolated"),
            pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False),
        ])
        tokenizer.decoder = decoders.ByteLevel()
        return cls(tokenizer, method='qwen_bpe' if family == 'qwen2' else 'llama_bpe')

    def count(self, text):
        if self.tokenizer is None:
            return len(text.encode("utf-8"))
        return len(self.tokenizer.encode(text, add_special_tokens=False).ids)

    def messages(self, messages):
        # Roles, separators, BOS and the assistant generation header. The
        # separate 512-token reserve covers template differences / model metadata.
        return 32 + sum(16 + self.count(message["content"]) for message in messages)

    def prefix(self, text, budget):
        if budget <= 0:
            return ""
        if self.count(text) <= budget:
            return text
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if self.count(text[:middle]) <= budget:
                low = middle
            else:
                high = middle - 1
        result = text[:low]
        while result and self.count(result) > budget:
            result = result[:-1]
        return result

    def excerpt(self, text, budget, spread=False):
        if self.count(text) <= budget:
            return text
        marker = "\n[... excerpt omitted ...]\n"
        room = max(0, budget - 2 * self.count(marker) - 12)
        if not spread or room < 90:
            return self.prefix(text, max(0, budget - self.count(marker))) + marker if budget > self.count(marker) else ""
        third = len(text) // 3
        pieces = [text[:third], text[third:2 * third], text[2 * third:]]
        allowance = room // 3
        # Preserve some ending material rather than always cutting long PDFs
        # at the beginning. Decode on character boundaries via prefix().
        ending = pieces[2]
        low, high = 0, len(ending)
        while low < high:
            middle = (low + high + 1) // 2
            if self.count(ending[len(ending) - middle:]) <= allowance:
                low = middle
            else:
                high = middle - 1
        return marker.join([self.prefix(pieces[0], allowance), self.prefix(pieces[1], allowance), ending[len(ending) - low:]])


@dataclass
class PromptPlan:
    messages: list
    metadata: dict


def build_prompt(counter, system, question, history=None, sources=None, answer_length="short", spread=False):
    history, sources = history or [], sources or []
    output = OUTPUT_TOKENS[answer_length]
    input_limit = CONTEXT_TOKENS - output - TEMPLATE_RESERVE
    style = (
        "Default to a brief, direct answer: a few sentences or short bullets. Follow the user's requested format."
        if answer_length == "short" else "Provide a detailed, well-organized answer within the available response length."
    )
    base_system = system + "\n" + style
    base_messages = [{"role": "system", "content": base_system}, {"role": "user", "content": question}]
    remaining = input_limit - counter.messages(base_messages)
    if remaining < (128 if sources else 0):
        raise GenerationError("Your question is too long for this model's 8,192-token context. Please shorten it.")

    def recent_history(allowance):
        selected = []
        for message in reversed(history):
            cost = counter.count(message["content"]) + 16
            if cost > allowance:
                break
            selected.insert(0, message)
            allowance -= cost
        return selected

    selected = recent_history(min(1500, remaining // 3) if sources else remaining)
    history_cost = sum(counter.count(message["content"]) + 16 for message in selected)
    sections, shortened, included_sources = [], 0, []
    if sources:
        source_room = remaining - history_cost - counter.count("\n\n[SOURCE CONTEXT]\n") - 32
        for index, source in enumerate(sources):
            heading = f"\n=== {source['title']} ===\n"
            share = max(0, source_room // (len(sources) - index))
            text = counter.excerpt(source["text"], max(0, share - counter.count(heading) - 8), spread)
            if text != source["text"]:
                shortened += 1
            section = heading + text
            if text.strip():
                sections.append(section)
                source_room -= counter.count(section) + 4
                if "id" in source:
                    included_sources.append({key: source[key] for key in ("id", "pdf_id", "page", "filename")})
                    included_sources[-1]["excerpt"] = text
    full_system = base_system + ("\n\n[SOURCE CONTEXT]\n" + "\n".join(sections) if sections else "")
    available_history = input_limit - counter.messages([
        {"role": "system", "content": full_system}, {"role": "user", "content": question}
    ])
    selected = recent_history(max(0, available_history))
    messages = [{"role": "system", "content": full_system}, *selected, {"role": "user", "content": question}]
    # Do not rely on Ollama silently truncating important question/context text.
    if counter.messages(messages) > input_limit:
        raise GenerationError("The selected excerpts do not fit this answer. Please ask a more specific question.")
    omitted = len(history) - len(selected)
    notices = []
    if shortened:
        notices.append("Some document excerpts were shortened to fit this answer.")
    if omitted:
        notices.append("Older conversation messages were omitted to leave room for your question and sources.")
    return PromptPlan(messages, {
        "context_tokens": CONTEXT_TOKENS, "max_output_tokens": output,
        "budgeted_input_tokens": counter.messages(messages), "budget_counting": counter.method,
        "history_messages_omitted": omitted, "excerpts_shortened": shortened,
        "context_notice": " ".join(notices), "answer_length": answer_length,
        "sources": included_sources,
    })
