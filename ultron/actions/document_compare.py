"""document_compare: local-first release action; discovered by the action registry."""
from ultron.core.productivity_api import dispatch


def document_compare(parameters: dict, **kwargs) -> str:
    return dispatch("document_compare", parameters)


TOOL = {'name': 'document_compare',
 'description': 'Read-only deterministic line comparison of two host-authorized UTF-8 txt/md/csv '
                'files, max 24000 bytes and 1000 lines each. Returns snapshot hashes and bounded '
                'unified diff with line numbers; marks truncation. CSV cell equality is '
                'positional, not a key join. No PDF/Office/OCR/semantic or legal analysis.',
 'parameters': {'type': 'OBJECT',
                'properties': {'action': {'type': 'STRING', 'description': 'compare'},
                               'left_path': {'type': 'STRING',
                                             'description': 'Absolute path under host-approved '
                                                            'document root'},
                               'right_path': {'type': 'STRING',
                                              'description': 'Absolute path under host-approved '
                                                             'document root'}},
                'required': ['action']},
    'handler': document_compare,
}
