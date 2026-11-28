"""evidence_ledger: local-first release action; discovered by the action registry."""
from ultron.core.productivity_api import dispatch


def evidence_ledger(parameters: dict, **kwargs) -> str:
    return dispatch("evidence_ledger", parameters)


TOOL = {'name': 'evidence_ledger',
 'description': 'Local source-linked evidence ledger. add(claim,url, optional quote/locator), '
                'get(evidence_id), list(optional limit). Sources and quotes are user-supplied '
                'UNVERIFIED data; this tool does not fetch or certify source support. Do not '
                'report entries as independently verified.',
 'parameters': {'type': 'OBJECT',
                'properties': {'action': {'type': 'STRING', 'description': 'add | get | list'},
                               'claim': {'type': 'STRING',
                                         'description': 'Claim, max 2000 characters'},
                               'url': {'type': 'STRING',
                                       'description': 'HTTPS source URL; no credentials; not '
                                                      'fetched'},
                               'quote': {'type': 'STRING',
                                         'description': 'User-supplied quote, max 4000 characters'},
                               'locator': {'type': 'STRING',
                                           'description': 'Page/section pointer, max 200 '
                                                          'characters'},
                               'evidence_id': {'type': 'STRING',
                                               'description': 'Full host-issued evidence ID'},
                               'limit': {'type': 'INTEGER', 'description': '1–100; default 20'}},
                'required': ['action']},
    'handler': evidence_ledger,
}
