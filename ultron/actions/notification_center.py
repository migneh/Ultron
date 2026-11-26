"""notification_center: local-first release action; discovered by the action registry."""
from ultron.core.productivity_api import dispatch


def notification_center(parameters: dict, **kwargs) -> str:
    return dispatch("notification_center", parameters)


TOOL = {'name': 'notification_center',
 'description': 'Persistent LOCAL notification inbox for productivity task events. digest returns '
                'up to 100 notices and quiet-hours state; acknowledge(notice_id), '
                'clear_acknowledged, quiet_hours(timezone,start_hour,end_hour). Optional generic local HUD counts require host CLI opt-in; no model tool can enable delivery. '
                'No external channels; explicit digest remains readable during '
                'quiet hours. Unread notices expire after 30 days.',
 'parameters': {'type': 'OBJECT',
                'properties': {'action': {'type': 'STRING',
                                          'description': 'digest | acknowledge | '
                                                         'clear_acknowledged | quiet_hours'},
                               'notice_id': {'type': 'STRING',
                                             'description': 'Full host-issued notice ID'},
                               'timezone': {'type': 'STRING',
                                            'description': 'IANA timezone, e.g. Africa/Tunis'},
                               'start_hour': {'type': 'INTEGER', 'description': 'Local hour 0–23'},
                               'end_hour': {'type': 'INTEGER',
                                            'description': 'Local hour 0–23; equal start/end '
                                                           'disables quiet hours'},
                               'limit': {'type': 'INTEGER', 'description': '1–100; default 20'}},
                'required': ['action']},
    'handler': notification_center,
}
