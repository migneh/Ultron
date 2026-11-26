"""task_board: local-first release action; discovered by the action registry."""
from ultron.core.productivity_api import dispatch


def task_board(parameters: dict, **kwargs) -> str:
    return dispatch("task_board", parameters)


TOOL = {'name': 'task_board',
 'description': 'Local persistent tasks. create(title, optional notes/due_date YYYY-MM-DD), '
                'list(optional state/limit), get(task_id), update(task_id,expected_version, fields to change: state/title/notes/due_date). '
                'States todo/doing/done/archived. Due dates do not schedule reminders. Completion '
                'must be explicitly user-directed. No external accounts.',
 'parameters': {'type': 'OBJECT',
                'properties': {'action': {'type': 'STRING',
                                          'description': 'create | list | get | update'},
                               'title': {'type': 'STRING',
                                         'description': 'Task title, max 200 characters'},
                               'notes': {'type': 'STRING',
                                         'description': 'Optional notes, max 2000 characters'},
                               'due_date': {'type': 'STRING',
                                            'description': 'YYYY-MM-DD date only; not a reminder'},
                               'task_id': {'type': 'STRING',
                                           'description': 'Full host-issued task ID'},
                               'state': {'type': 'STRING',
                                         'description': 'todo | doing | done | archived'},
                               'expected_version': {'type': 'INTEGER',
                                                    'description': 'Version obtained from '
                                                                   'get/list, required for update'},
                               'limit': {'type': 'INTEGER', 'description': '1–100; default 20'}},
                'required': ['action']},
    'handler': task_board,
}
