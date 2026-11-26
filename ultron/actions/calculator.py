"""calculator: local-first release action; discovered by the action registry."""
from ultron.core.productivity_api import dispatch


def calculator(parameters: dict, **kwargs) -> str:
    return dispatch("calculator", parameters)


TOOL = {'name': 'calculator',
 'description': 'Offline bounded Decimal arithmetic (+ - * / % integer powers) and unit '
                'conversion. No eval, code, functions, financial/live FX data. % means remainder. '
                'Numbers use dot decimal strings. Units: m cm mm km in ft mi kg g lb oz s min h '
                'day L mL C F K.',
 'parameters': {'type': 'OBJECT',
                'properties': {'action': {'type': 'STRING', 'description': 'calculate | convert'},
                               'expression': {'type': 'STRING',
                                              'description': 'Arithmetic expression, max 500 '
                                                             'characters'},
                               'value': {'type': 'STRING',
                                         'description': 'Decimal string for conversion'},
                               'from_unit': {'type': 'STRING',
                                             'description': 'Exact case-sensitive unit symbol'},
                               'to_unit': {'type': 'STRING',
                                           'description': 'Exact case-sensitive unit symbol'}},
                'required': ['action']},
    'handler': calculator,
}
