"""Allowlisted expression trees, bounded child processes, and checkable results.

No eval, sympify(string), parse_expr, generated Python, filesystem or network tools.
The language is deliberately smaller than Python and smaller than LaTeX.
"""
import ast
import asyncio
import math
import multiprocessing
import re
from .languages import normalize_digits
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

Expression = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class MathRequest(BaseModel):
    operation: Literal['solve', 'simplify', 'factor', 'differentiate', 'integrate', 'numeric', 'matrix', 'check', 'units'] = 'solve'
    expression: Expression = 'x^2 - 5*x + 6 = 0'
    variable: str = Field('x', pattern=r'^[a-zA-Z]$')
    variables: list[Annotated[str, StringConstraints(pattern=r'^[a-zA-Z]$')]] = Field(default_factory=list, max_length=4)
    domain: Literal['real', 'complex'] = 'real'
    equations: list[Expression] = Field(default_factory=list, max_length=4)
    lower: Expression | None = None
    upper: Expression | None = None
    expected: Expression | None = None
    working: list[Expression] = Field(default_factory=list, max_length=12)
    matrix: list[list[float]] = Field(default_factory=list, max_length=6)
    matrix_action: Literal['determinant', 'inverse', 'eigenvalues'] = 'determinant'
    magnitude: float = Field(default=1, ge=-1e12, le=1e12, allow_inf_nan=False)
    from_unit: str = Field(default='m', max_length=60)
    to_unit: str = Field(default='cm', max_length=60)
    @model_validator(mode='after')
    def bounds(self):
        if self.matrix and (any(len(row) != len(self.matrix) for row in self.matrix) or any(not math.isfinite(v) or abs(v) > 1e9 for row in self.matrix for v in row)):
            raise ValueError('Use a finite square matrix, at most 6 by 6.')
        if (self.lower is None) != (self.upper is None):
            raise ValueError('Supply both integration bounds, or neither.')
        return self


def parse_expression(text, symbols, denominators=None):
    import sympy as s
    text = normalize_digits(text).strip().strip('$').replace('\\left', '').replace('\\right', '')
    for _ in range(8):
        text = re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'((\1)/(\2))', text)
        text = re.sub(r'\\sqrt\{([^{}]+)\}', r'sqrt(\1)', text)
        text = re.sub(r'\^\{([^{}]+)\}', r'^(\1)', text)
    text = text.replace('\\cdot', '*').replace('\\times', '*').replace('\\pi', 'pi')
    text = re.sub(r'\\(sin|cos|tan|log|exp)\b', r'\1', text)
    normalized = text.replace('−', '-').replace('×', '*').replace('÷', '/').replace('π', 'pi').replace('²','^2').replace('³','^3').replace('^', '**')
    normalized = re.sub(r'([0-9])([a-df-zA-DF-Z(])', r'\1*\2', normalized)
    try:
        tree = ast.parse(normalized, mode='eval')
    except (SyntaxError, ValueError) as exc:
        raise ValueError('Use notation such as x^2, 2*x, sqrt(x), sin(x), or pi. Edit the equation preview if needed.') from exc
    if len(list(ast.walk(tree))) > 90:
        raise ValueError('This expression is too complex for the local calculator.')
    funcs = {'sin': s.sin, 'cos': s.cos, 'tan': s.tan, 'asin': s.asin, 'acos': s.acos, 'atan': s.atan,
             'sqrt': s.sqrt, 'log': s.log, 'exp': s.exp, 'abs': s.Abs}
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if not math.isfinite(node.value) or abs(node.value) > 1e12:
                raise ValueError('Numbers must be finite and at most 10^12 in magnitude.')
            return s.Rational(str(node.value))
        if isinstance(node, ast.Name):
            if node.id in symbols:
                return symbols[node.id]
            if node.id in {'pi', 'E', 'I'}:
                return {'pi': s.pi, 'E': s.E, 'I': s.I}[node.id]
            raise ValueError(f'Unknown symbol {node.id}. Declare its variable or use an approved function.')
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div):
                if right == 0: raise ValueError('Division by zero is undefined.')
                if denominators is not None: denominators.append(right)
                return s.Mul(left, s.Pow(right, -1, evaluate=False), evaluate=False)
            if isinstance(node.op, ast.Pow):
                if not right.is_number or abs(complex(right.evalf())) > 12:
                    raise ValueError('Use numeric exponents between -12 and 12.')
                # Bound the unevaluated syntax before a nested power can expand.
                if isinstance(node.left, ast.BinOp) and isinstance(node.left.op, ast.Pow):
                    raise ValueError('Nested powers must be simplified first.')
                if denominators is not None and right.is_negative: denominators.append(left)
                return left ** right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in funcs and len(node.args) == 1 and not node.keywords:
            return funcs[node.func.id](visit(node.args[0]))
        raise ValueError('Only numbers, declared variables, arithmetic and approved one-argument functions are accepted.')
    return visit(tree.body)


def calculate(data):
    """Pure worker entry point, also used by the deterministic benchmark."""
    import sympy as s
    request = MathRequest.model_validate(data)
    names = list(dict.fromkeys(request.variables or [request.variable]))
    symbols = {name: s.Symbol(name, real=True) if request.domain == 'real' else s.Symbol(name) for name in names}
    x = symbols.get(request.variable, next(iter(symbols.values())))
    domain = s.S.Reals if request.domain == 'real' else s.S.Complexes
    denominators=[]
    def expr(text): return parse_expression(text, symbols, denominators)
    def equation(text):
        if text.count('=') > 1: raise ValueError('Each equation must have at most one equals sign.')
        left, _, right = text.partition('=')
        return expr(left) - (expr(right) if right else 0)
    def latex(value): return s.latex(value)
    checks, steps = [], []
    verified = False
    result = None
    if request.operation == 'units':
        import pint
        allowed = {'m', 'cm', 'mm', 'km', 's', 'min', 'h', 'kg', 'g', 'N', 'J', 'W', 'Pa', 'K', 'mol', 'A', 'Hz', 'rad', 'degree', 'liter', 'L'}
        for unit in (request.from_unit, request.to_unit):
            if not re.fullmatch(r'[A-Za-z0-9*/^ .()-]+', unit) or set(re.findall(r'[A-Za-z]+', unit)) - allowed:
                raise ValueError('Use supported SI units, such as m/s, km/h, N, J, kg, or cm^2.')
        registry = pint.UnitRegistry()
        quantity = registry.Quantity(request.magnitude, registry.Unit(request.from_unit))
        converted = quantity.to(registry.Unit(request.to_unit))
        result = f'{converted.magnitude:.12g} {request.to_unit}'
        checks = [{'label': 'Dimensions match', 'passed': True}]
        verified = True
        result_latex = rf'{converted.magnitude:.12g}\,\mathrm{{{request.to_unit}}}'
        steps = [f'Convert {request.magnitude} {request.from_unit} to {request.to_unit}.', 'The unit registry checked dimensional compatibility.']
    elif request.operation == 'matrix':
        if not request.matrix: raise ValueError('Supply a square matrix.')
        matrix = s.Matrix([[s.Rational(str(v)) for v in row] for row in request.matrix])
        if request.matrix_action == 'inverse':
            result = matrix.inv()
            verified = matrix * result == s.eye(matrix.rows)
            checks = [{'label': 'Original × inverse = identity', 'passed': verified}]
        elif request.matrix_action == 'eigenvalues':
            result = s.Tuple(*[s.Tuple(key, count) for key, count in matrix.eigenvals().items()])
            checks = [{'label': 'Eigenvalues computed; multiplicities included', 'passed': True}]
        else:
            result = matrix.det()
            verified = s.simplify(result - matrix.transpose().det()) == 0
            checks = [{'label': 'Determinant agrees with transpose determinant', 'passed': verified}]
        result_latex = latex(result)
        steps = [f'Apply {request.matrix_action} to the supplied matrix.']
    elif request.operation == 'solve':
        eqs = [equation(text) for text in (request.equations or [request.expression])]
        if len(eqs) > 1 or len(names) > 1:
            result = s.nonlinsolve(eqs, list(symbols.values()))
            candidates = list(result) if isinstance(result, s.FiniteSet) else []
            verified = bool(candidates) and all(not any(v.free_symbols for v in candidate) and all(s.simplify(eq.subs(dict(zip(symbols.values(), candidate)))) == 0 for eq in eqs) for candidate in candidates)
            if request.domain == 'real' and any(v.is_real is not True for candidate in candidates for v in candidate):
                raise ValueError('The system has non-real or unresolved values. Select complex domain or simplify the problem.')
            checks = [{'label': 'Substitution into every original equation', 'passed': verified}]
        else:
            result = s.solveset(eqs[0], x, domain=domain)
            for denominator in denominators:
                if denominator.free_symbols <= {x}: result = result - s.solveset(denominator,x,domain=domain)
            try:
                polynomial=s.Poly(eqs[0],x)
                if polynomial.degree()==2:
                    a,b,c=polynomial.all_coeffs()
                    steps.append(rf'Quadratic coefficients: $a={latex(a)}$, $b={latex(b)}$, $c={latex(c)}$. The discriminant is $b^2-4ac={latex(b*b-4*a*c)}$.')
            except s.PolynomialError: pass
            if isinstance(result, s.FiniteSet):
                for root in result:
                    valid = s.simplify(eqs[0].subs(x, root)) == 0
                    checks.append({'label': f'Substitute {x} = {root}', 'passed': bool(valid)})
                verified = all(c['passed'] for c in checks)
            elif result == s.S.EmptySet:
                checks = [{'label': f'No solutions returned in the {request.domain} domain', 'passed': True}]
                # Absence is a solver result, not independent proof.
            factored = s.factor(eqs[0])
            steps.append(rf'Write the equation as ${latex(eqs[0])}=0$.')
            if factored != eqs[0]: steps.append(rf'Factor: ${latex(factored)}=0$.')
        result_latex = latex(result)
        steps += [f'Solve over the {request.domain} numbers.', 'Check each finite candidate by substitution; domain restrictions still apply.']
    else:
        original = expr(request.expression)
        if request.operation == 'differentiate':
            result = s.diff(original, x)
            verified = s.simplify(s.diff(original - s.integrate(result, x), x)) == 0
            checks = [{'label': 'Derivative agrees after symbolic round trip', 'passed': verified}]
            if original.is_polynomial(x): steps.append(r'Apply the power rule to each term: $\frac{d}{dx}(a x^n)=a n x^{n-1}$; constants differentiate to zero.')
        elif request.operation == 'integrate':
            if request.lower is not None:
                low, high = expr(request.lower), expr(request.upper)
                if low.free_symbols or high.free_symbols: raise ValueError('Integration bounds must be numeric constants.')
                result = s.integrate(original, (x, low, high))
                checks = [{'label': 'Definite symbolic integral; singularities require review', 'passed': not result.has(s.Integral, s.oo, s.zoo, s.nan)}]
            else:
                result = s.integrate(original, x)
                verified = not result.has(s.Integral) and s.simplify(s.diff(result, x) - original) == 0
                checks = [{'label': 'Differentiate the antiderivative', 'passed': verified}]
                if original.is_polynomial(x): steps.append(r'Integrate each polynomial term using $\int a x^n\,dx=\frac{a x^{n+1}}{n+1}+C$ for $n\ne-1$.')
        elif request.operation == 'numeric':
            if original.free_symbols: raise ValueError('Replace variables with numbers before numerical evaluation.')
            if request.domain == 'real' and original.is_real is False: raise ValueError('This value is not real. Select the complex domain or change the expression.')
            result = original.evalf(12)
            checks = [{'label': 'Numerical approximation, 12 significant digits', 'passed': True}]
        elif request.operation == 'check':
            if not request.expected: raise ValueError('Supply an expected expression for equivalence checking.')
            result = s.simplify(original - expr(request.expected))
            verified = result == 0
            checks = [{'label': 'Expressions simplify to the same value on their shared domain', 'passed': verified}]
            steps.append('This tests expression equivalence, not the validity of a complete proof or all domain restrictions.')
        else:
            result = s.factor(original) if request.operation == 'factor' else s.simplify(original)
            verified = s.simplify(result - original) == 0
            checks = [{'label': 'Difference from original simplifies to zero on the shared domain', 'passed': verified}]
        result_latex = latex(result)
        if request.operation == 'integrate' and request.lower is None and not result.has(s.Integral): result_latex += ' + C'
        steps.insert(0, rf'Input: ${latex(original)}$.')
        steps.append(f'Apply {request.operation} with respect to {x}, where applicable.')
    working_checks = []
    for index, line in enumerate(request.working):
        previous = request.expression if index == 0 else request.working[index - 1]
        if '=' in previous or '=' in line:
            a, b = s.solveset(equation(previous), x, domain=domain), s.solveset(equation(line), x, domain=domain)
            same = a == b and not a.has(s.ConditionSet)
        else:
            same = s.simplify(expr(previous) - expr(line)) == 0
        working_checks.append({'step': index + 1, 'passed': bool(same), 'label': 'Same solution set / expression on the checked domain' if same else 'This step changes the result or could not be verified'})
    conditions = [rf'Original denominator must be nonzero: ${latex(d)}\ne0$.' for d in dict.fromkeys(denominators) if d.free_symbols][:8]
    if request.domain=='real' and any(word in request.expression for word in ['sqrt','log']): conditions.append('On the real domain, square-root arguments must be nonnegative and logarithm arguments positive.')
    return {'operation': request.operation, 'input': request.model_dump(), 'result': str(result), 'latex': result_latex,
            'verified': bool(verified), 'checks': checks, 'steps': steps, 'working_checks': working_checks,
            'assumptions': [f'Domain: {request.domain}.', 'Trigonometric arguments use radians.', *conditions, 'Symbolic checks apply on the common defined domain; this is not a proof checker.'],
            'engine': 'SymPy / Pint', 'kind': 'derived', 'version': 'math-1'}


def _child(data, pipe):
    try:
        pipe.send({'result': calculate(data)})
    except Exception as exc:
        pipe.send({'error': str(exc)[:350] if isinstance(exc, (ValueError, NotImplementedError, ZeroDivisionError)) else 'The calculator could not resolve this operation. Check its inputs and domain.'})
    finally:
        pipe.close()


def isolated_calculate(data, timeout=8):
    context = multiprocessing.get_context('spawn')
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(data, send), daemon=True)
    process.start()
    send.close()
    try:
        if not receive.poll(timeout): raise ValueError('Calculation exceeded the local time limit. Simplify the problem or split it into parts.')
        response = receive.recv()
        if 'error' in response: raise ValueError(response['error'])
        return response['result']
    finally:
        if process.is_alive(): process.terminate()
        process.join(timeout=2)
        receive.close()


_slots = asyncio.Semaphore(2)


async def solve_bounded(request):
    async with _slots:
        # A cancellation waits for the bounded child to be reaped before the slot
        # is released. No abandoned process can continue consuming CPU forever.
        task = asyncio.create_task(asyncio.to_thread(isolated_calculate, request.model_dump()))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
