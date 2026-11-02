"""Benchmark metrics must distinguish retrieved pages from cited evidence."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('exam_benchmark', Path(__file__).resolve().parents[1] / 'evaluation/exam_benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)

CASE = {'kind': 'lookup', 'expected': 'public-code', 'source_pages': [119], 'language': 'en'}
SOURCES = [{'id': 'S1', 'page': 119}, {'id': 'S2', 'page': 66}]

def test_retrieval_alone_is_not_a_citation():
    result = benchmark.score(CASE, {'answer': 'public-code', 'sources': SOURCES})
    assert result['correct'] and result['retrieved_expected_page']
    assert not result['citation_present'] and not result['cited_expected_page']

def test_citing_a_different_retrieved_page_does_not_pass():
    result = benchmark.score(CASE, {'answer': 'public-code [S2]', 'sources': SOURCES})
    assert result['citation_present'] and not result['cited_expected_page']

def test_native_digits_and_code_examples_are_handled():
    result = benchmark.score(CASE, {'answer': 'public-code `[S1]` [س۲]', 'sources': SOURCES})
    assert not result['cited_expected_page']
    assert benchmark.score(CASE, {'answer': 'public-code [س۱]', 'sources': SOURCES})['cited_expected_page']
