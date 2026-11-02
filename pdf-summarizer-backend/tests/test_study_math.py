import json
import pytest
import sympy as s
from pydantic import ValidationError

from app.services.math_engine import calculate, parse_expression, MathRequest, isolated_calculate
from app.services.study_assistant import paper_questions, calculation_markdown
from app.services.advanced_retrieval import subqueries
from app.services.synthesis import batches


@pytest.mark.parametrize('expression,expected', [
    ('x^2-5*x+6=0','{2, 3}'),('x^2+1=0','EmptySet'),('2*x+4=0','{-2}'),
    ('x^3-x=0','{-1, 0, 1}'),('x/2=3','{6}'),('sqrt(x)=3','{9}'),
    ('x^2=4','{-2, 2}'),('x-0.5=0','{1/2}'),('2x=8','{4}'),
    ('\\frac{x}{2}=3','{6}'),('\\sqrt{x}=3','{9}'),('x^{2}=9','{-3, 3}'),
])
def test_exact_roots(expression,expected):
    result=calculate({'expression':expression})
    assert result['result']==expected
    if expected!='EmptySet': assert result['verified']


@pytest.mark.parametrize('operation,expression,expected', [
    ('differentiate','x^3','3*x**2'),('differentiate','sin(x)','cos(x)'),
    ('differentiate','exp(x)','exp(x)'),('differentiate','log(x)','1/x'),
    ('integrate','2*x','x**2'),('integrate','cos(x)','sin(x)'),
    ('integrate','x^2','x**3/3'),('factor','x^2-1','(x - 1)*(x + 1)'),
    ('simplify','sin(x)^2+cos(x)^2','1'),('simplify','x+x','2*x'),
    ('factor','x^2+2*x+1','(x + 1)**2'),
])
def test_symbolic_tools_with_checks(operation,expression,expected):
    result=calculate({'operation':operation,'expression':expression})
    assert result['result']==expected and result['verified']


@pytest.mark.parametrize('bad', [
    '__import__("os")','x.__class__','[x for x in range(100)]','open("secret")',
    'lambda: 1','2**(12**12)','x**x','x[0]','sin(x,y)','sin(x, evaluate=False)',
    'unknown+1','1/0','1e999','(x**2)**3','x;print(1)',
])
def test_expression_language_rejects_execution_and_expansion(bad):
    with pytest.raises((ValueError,OverflowError)):
        calculate({'operation':'simplify','expression':bad})


def test_system_domain_matrices_bounds_units_and_equivalence():
    assert calculate({'variables':['x','y'],'equations':['x+y=5','x-y=1']})['result']=='{(3, 2)}'
    assert calculate({'expression':'x^2+1=0','domain':'complex'})['result']=='{-I, I}'
    assert calculate({'operation':'matrix','matrix':[[1,2],[3,4]],'matrix_action':'inverse'})['verified']
    assert calculate({'operation':'matrix','matrix':[[1,2],[3,4]]})['result']=='-2'
    assert calculate({'operation':'matrix','matrix':[[1,0],[0,2]],'matrix_action':'eigenvalues'})['result']=='((1, 1), (2, 1))'
    assert calculate({'operation':'integrate','expression':'x','lower':'0','upper':'2'})['result']=='2'
    assert calculate({'operation':'numeric','expression':'sqrt(2)'})['result'].startswith('1.414213')
    assert calculate({'operation':'units','magnitude':36,'from_unit':'km/h','to_unit':'m/s'})['result']=='10 m/s'
    assert calculate({'operation':'check','expression':'x+x','expected':'2*x'})['verified']
    assert not calculate({'operation':'check','expression':'x+1','expected':'x+2'})['verified']
    result=calculate({'expression':'x^2=4','working':['x=2']})
    assert not result['working_checks'][0]['passed']
    rational=calculate({'expression':'x/x=1'})
    assert '0' in rational['result'] and rational['result']!='Reals'
    assert any('nonzero' in condition for condition in rational['assumptions'])


@pytest.mark.parametrize('data', [
    {'operation':'numeric','expression':'x+2'}, {'operation':'matrix'},
    {'operation':'check'}, {'operation':'integrate','lower':'0'},
    {'operation':'matrix','matrix':[[1,2]]}, {'operation':'solve','expression':'x=2=3'},
    {'operation':'units','from_unit':'__class__'},
])
def test_actionable_invalid_inputs(data):
    with pytest.raises((ValueError,ValidationError)): calculate(data)


def test_process_boundary_and_failure():
    assert isolated_calculate({'expression':'2*x=6'})['result']=='{3}'
    with pytest.raises(ValueError): isolated_calculate({'expression':'bad'})
    with pytest.raises(ValueError,match='time limit'): isolated_calculate({'expression':'x=1'},timeout=0)


def test_hints_do_not_include_calculated_result():
    result=calculate({'expression':'x=987'})
    assert '987' not in calculation_markdown(result,'hint')
    assert '987' in calculation_markdown(result)


def test_paper_boundaries_marks_subparts_and_query_budget():
    questions=paper_questions([{'pdf_id':1,'page':2,'text':'Question 1 Solve x=3 [2 marks]\n(a) Explain.\nQuestion 2 Differentiate x^2 (3 marks)'}])
    assert len(questions)==2 and questions[0]['page']==2
    assert questions[0]['marks']==2 and questions[1]['marks']==3
    assert questions[0]['subparts']==['a']
    assert len(subqueries('Find the formula; explain the assumptions; also compare the methods; also calculate the result'))<=3
    text='[S1] '+'é'*10000
    values=list(batches([text]))
    assert len(values)>1 and all('[S1]' in value for value in values)
