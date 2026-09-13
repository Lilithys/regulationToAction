"""Provider-independent request sizing and safe, bounded retry diagnostics."""
import copy
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from case_store import encode


class RequestTooLarge(ValueError):
    pass


class TokenWindow:
    """Conservative reservations for this case, shared by all its live roles.

    Estimates include the requested output allowance. This cannot account for
    another application using the same provider project; server hints still win.
    """
    def __init__(self):self.reservations=[]

    def record(self,at,tokens):self.reservations.append((at,tokens))

    def delay(self,now,tokens,limit):
        if not limit:return 0
        if tokens>limit:raise RequestTooLarge('One request exceeds the configured tokens-per-minute budget; reduce its size before sending.')
        self.reservations=sorted((at,n) for at,n in self.reservations if at+60>now)
        remaining=sum(n for _,n in self.reservations)
        if remaining+tokens<=limit:return 0
        for at,n in self.reservations:
            remaining-=n
            if remaining+tokens<=limit:return max(0,at+60-now)
        return 0


QUOTA_CODES = {'insufficient_quota', 'credit_balance_exhausted', 'billing_hard_limit_reached',
    'organization_spend_limit_exceeded', 'project_spend_limit_exceeded', 'organization_usage_limit_exceeded'}
CONTEXT_CODES = {'context_length_exceeded', 'max_context_length_exceeded', 'request_too_large'}
KNOWN_CODES = QUOTA_CODES | CONTEXT_CODES | {'rate_limit_exceeded', 'rate_limit_error', 'slow_down',
    'server_is_overloaded', 'invalid_api_key', 'invalid_request_error'}


def seconds(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def retry_after(value):
    result = seconds(value)
    if result is not None:return result
    if not isinstance(value, str):return None
    try:
        target = parsedate_to_datetime(value)
        if target.tzinfo is None:return None
        return max(0, (target-datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):return None


def duration(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:\d+(?:\.\d+)?(?:ms|s|m|h))+', value):return None
    return sum(float(n)*{'ms':.001,'s':1,'m':60,'h':3600}[unit]
               for n,unit in re.findall(r'(\d+(?:\.\d+)?)(ms|s|m|h)',value))


def error_diagnostic(exc):
    """Never return raw messages, bodies, headers, URLs, keys or request IDs."""
    status = getattr(exc, 'status_code', None)
    status = status if type(status) is int and 100 <= status <= 599 else None
    body = getattr(exc, 'body', None)
    body = body if isinstance(body, dict) else {}
    detail = body.get('error', body)
    detail = detail if isinstance(detail, dict) else {}
    raw_code = getattr(exc, 'code', None) or detail.get('code') or detail.get('type')
    code = raw_code if isinstance(raw_code, str) and raw_code in KNOWN_CODES else 'unknown'
    # Some compatible gateways omit a structured code. Only classify recognized
    # phrases locally; never retain their potentially sensitive message text.
    message = detail.get('message', '')
    message = message.lower() if isinstance(message, str) else ''
    category = 'provider_error'
    if code in QUOTA_CODES:category = 'quota_or_billing'
    elif code in CONTEXT_CODES or any(s in message for s in ('maximum context length', 'context length exceeded')):
        category = 'request_too_large'
    elif status == 429 and 'request too large' in message:category = 'request_too_large'
    elif status == 429:category = 'rate_limit'
    elif status in (500,502,503,504):category = 'temporary_server_error'
    elif type(exc).__name__ in ('APIConnectionError','APITimeoutError','TimeoutError'):category = 'connection_or_timeout'
    response = getattr(exc, 'response', None)
    headers = getattr(response, 'headers', {})
    headers = headers if hasattr(headers, 'get') else {}
    delay = retry_after(headers.get('retry-after'))
    if delay is None:
        milliseconds = seconds(headers.get('retry-after-ms'))
        if milliseconds is not None:delay = milliseconds / 1000
    resets = [duration(headers.get('x-ratelimit-reset-'+kind)) for kind in ('tokens','requests','project-tokens')]
    if delay is None:delay = max((s for s in resets if s is not None), default=None)
    limits = {}
    for kind in ('limit-tokens','remaining-tokens','limit-requests','remaining-requests','limit-project-tokens','remaining-project-tokens'):
        value = seconds(headers.get('x-ratelimit-'+kind))
        if value is not None:limits[kind] = value
    request_id = getattr(exc, 'request_id', None) or headers.get('x-request-id')
    result = dict(http_status=status, provider_code=code, category=category,
        retryable=category in ('rate_limit','temporary_server_error','connection_or_timeout'),
        retry_after_seconds=delay, rate_limits=limits)
    if isinstance(request_id, str):result['request_id_sha256'] = hashlib.sha256(request_id.encode()).hexdigest()
    return result


def estimated_input_tokens(system, messages, definitions):
    # Deliberately labeled an estimate, not the provider's tokenizer or TPM meter.
    return math.ceil(len(encode(dict(system=system,messages=messages,tools=definitions)).encode('utf-8'))/3)+128


def bounded_messages(system, messages, definitions, input_limit):
    """Compact older observations only, preserving complete tool-call/result pairs.

    Latest observation and system/task instructions remain intact. Full observations
    already live in the audit trail; placeholders tell the model to re-read, and
    never claim to contain the missing source text.
    """
    bounded = copy.deepcopy(messages)
    before = estimated_input_tokens(system,bounded,definitions)
    changes = []
    if before <= input_limit:return bounded, before, changes
    for index,message in enumerate(bounded[:-1]):
        if message.get('role') != 'user' or not isinstance(message.get('content'),list):continue
        for block in message['content']:
            if block.get('type') != 'tool_result' or block.get('is_error'):continue
            raw = block.get('content','')
            if not isinstance(raw,str) or len(raw) < 1200:continue
            try:observation = json.loads(raw)
            except ValueError:continue
            if not isinstance(observation,dict):continue
            rows = observation.get('results',observation.get('nodes',[]))
            rows = [row for row in rows if isinstance(row,dict)] if isinstance(rows,list) else []
            refs = [r['reference_id'] for r in [observation]+rows if isinstance(r.get('reference_id'),str)]
            records = [r['record_id'] for r in rows if isinstance(r.get('record_id'),str)]
            compact = encode(dict(status='context_compacted',reference_ids=refs[:12],record_ids=records[:12],
                note='Older observation omitted from this request. Re-read records/source/evidence through tools before relying on omitted content; full result remains in audit.'))
            if len(compact) >= len(raw):continue
            block['content'] = compact
            changes.append(dict(message_index=index,tool_call_id=block['tool_use_id'],original_chars=len(raw)))
            estimate = estimated_input_tokens(system,bounded,definitions)
            if estimate <= input_limit:return bounded,estimate,changes
    raise RequestTooLarge('Request exceeds configured input budget; narrow tool results or split the specialist task. No API call sent.')
