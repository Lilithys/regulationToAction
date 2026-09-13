"""Date selection shared by applicability and cost tools; no new legal inference."""
from datetime import date

DATE_EVENT_TYPES = {'application', 'institution_deadline', 'transition'}

def event_applies(event, snci):
    selector = event.get('extensions', {}).get('snci_selector')
    condition = event.get('condition', event.get('applies_to', ''))
    if selector is None and 'SNCI' not in condition:
        return True
    if type(snci) is not bool:
        return None
    if selector is not None:
        return snci is selector
    return not snci if 'other than' in condition.lower() else snci


def select_event(events, bank):
    applicable = []
    for event in events:
        if event.get('event_type') not in DATE_EVENT_TYPES:
            continue
        applies = event_applies(event, bank.get('snci_status'))
        if applies is None:
            return None
        if applies:
            applicable.append(event)
    if not applicable or any(not e.get('date') for e in applicable):
        return None
    try:
        return min(applicable, key=lambda e: date.fromisoformat(e['date']))
    except (ValueError, TypeError):
        return None
