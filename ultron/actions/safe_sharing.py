"""safe_sharing: local-first release action; discovered by the action registry."""
from ultron.core.productivity_api import dispatch


def safe_sharing(parameters: dict, **kwargs) -> str:
    return dispatch("safe_sharing", parameters)


TOOL = {'name': 'safe_sharing',
 'description': 'Plain-text safe-sharing preview, not automatic sharing. preview(path, optional '
                'literals) detects candidate emails/phones and selected exact literals; review '
                'entire output for omissions/false positives. publish(preview_id,destination) '
                'requests HUD approval to write a verified NEW .txt copy under approved roots; no '
                'overwrite/upload. Preview expires in one hour. discard(preview_id) removes stored '
                'preview. txt/md/csv only; no PDF/Office/image redaction or anonymization '
                'guarantee.',
 'parameters': {'type': 'OBJECT',
                'properties': {'action': {'type': 'STRING',
                                          'description': 'preview | publish | discard'},
                               'path': {'type': 'STRING',
                                        'description': 'Absolute approved source path, UTF-8 '
                                                       'txt/md/csv up to 24000 bytes'},
                               'literals': {'type': 'ARRAY',
                                            'description': 'At most 30 exact strings to redact; no '
                                                           'regexes',
                                            'items': {'type': 'STRING'}},
                               'preview_id': {'type': 'STRING',
                                              'description': 'Full host-issued preview ID'},
                               'destination': {'type': 'STRING',
                                               'description': 'Absolute new .txt path under an '
                                                              'approved root'}},
                'required': ['action']},
    'handler': safe_sharing,
}
