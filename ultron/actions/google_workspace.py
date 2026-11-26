"""google_workspace: local-first release action; discovered by the action registry."""
from ultron.core.productivity_api import dispatch


def google_workspace(parameters: dict, **kwargs) -> str:
    return dispatch("google_workspace", parameters)


TOOL = {'name': 'google_workspace',
 'description': 'Optional READ-ONLY Google adapter. status checks local setup without network. '
                'drive_metadata/drive_text require an explicitly host-granted file_id and '
                'provider-authorized drive.file access. agenda/availability require an RFC3339 '
                'offset-aware time_min/time_max window <=31 days and host-enabled Calendar. No '
                'whole-Drive search, OAuth prompts, connect, send, writes or uploads from tools. '
                'Offline mode supports local status only; no account content cache.',
 'parameters': {'type': 'OBJECT',
                'properties': {'action': {'type': 'STRING',
                                          'description': 'status | drive_metadata | drive_text | '
                                                         'agenda | availability'},
                               'file_id': {'type': 'STRING',
                                           'description': 'Exact host-allowed Google Drive file '
                                                          'ID'},
                               'time_min': {'type': 'STRING',
                                            'description': 'RFC3339 timestamp including UTC '
                                                           'offset'},
                               'time_max': {'type': 'STRING',
                                            'description': 'RFC3339 timestamp including UTC '
                                                           'offset, after time_min and within 31 '
                                                           'days'}},
                'required': ['action']},
    'handler': google_workspace,
}
