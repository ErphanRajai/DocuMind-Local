from evaluation.run_quality import score, CASES, fixture_pdf
import fitz


def test_evaluation_requires_correct_fact_and_actually_cited_page():
    case=CASES[0]
    assert score(case,"240 dollars [S1]",[{"id":"S1","page":2}],"done")["passed"]
    assert not score(case,"240 dollars [S1]",[{"id":"S1","page":1}],"done")["passed"]
    assert not score(case,"99999 dollars [S1]",[{"id":"S1","page":2}],"done")["passed"]
    assert not score(case,"240 dollars [S1]",[{"id":"S1","page":2}],"error")["passed"]


def test_evaluation_fixture_has_five_actual_pages():
    with fitz.open(stream=fixture_pdf(),filetype="pdf") as doc:
        assert len(doc)==5
        assert "240 dollars" in doc[1].get_text()
        assert "superseded" in doc[3].get_text()
