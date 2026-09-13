"""Anthropic- and OpenAI-compatible adapters for optional drafting and tool-driven tasks.

Existing provider environment variables are retained. No arbitrary code execution
or state mutations occur in this adapter; the application validates all tool calls.
Provider is chosen by LLM_PROVIDER ('anthropic', the default -- also covers any
Anthropic-Messages-API-compatible endpoint such as DeepSeek's, via LLM_BASE_URL --
or 'openai'). Provider SDKs are imported lazily so an environment only needs the
one package it actually uses installed.
"""
import json
import os
from llm_config import load_local_config

DEFAULT_MODELS = {'anthropic': 'claude-sonnet-5', 'openai': 'gpt-5'}


def _provider():
    load_local_config()
    return os.environ.get('LLM_PROVIDER', 'anthropic')


def _anthropic_client(timeout: float = 30):
    import anthropic
    api_key = os.environ.get('LLM_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError(
            'No API key found. Set ANTHROPIC_API_KEY for Anthropic, or LLM_API_KEY '
            '(+ optionally LLM_BASE_URL) for another Anthropic-Messages-API-compatible provider.')
    base_url = os.environ.get('LLM_BASE_URL') or None
    return anthropic.Anthropic(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)


def _openai_client(timeout: float = 30):
    import openai
    api_key = os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise RuntimeError(
            'No API key found. Set OPENAI_API_KEY, or LLM_API_KEY (+ optionally LLM_BASE_URL '
            'for an OpenAI-compatible endpoint) with LLM_PROVIDER=openai.')
    base_url = os.environ.get('LLM_BASE_URL') or None
    return openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)


def complete(system: str, user: str, *, max_tokens: int = 2048) -> str:
    """One-shot text completion, no tools, no streaming. Every call site parses and
    validates its own output -- this function never guesses at malformed responses."""
    provider = _provider()
    if provider == 'openai':return _complete_openai(system, user, max_tokens)
    if provider == 'anthropic':return _complete_anthropic(system, user, max_tokens)
    raise RuntimeError(f'Unknown LLM_PROVIDER: {provider!r}; expected anthropic or openai')


def _complete_anthropic(system, user, max_tokens):
    """No temperature/top_p here: installed anthropic SDK 1.4.0's Messages.create() no
    longer accepts them (verified by inspecting the installed signature directly --
    sampling controls appear to have moved off this endpoint). This is a client-side
    SDK shape, not a DeepSeek quirk -- it fails identically against real Anthropic.

    thinking is explicitly disabled: a reasoning model's internal thinking can
    consume the entire max_tokens budget before it ever emits a text block (seen in
    practice -- response.content was `['thinking']` with no text at all).
    """
    model = os.environ.get('LLM_MODEL', DEFAULT_MODELS['anthropic'])
    response = _anthropic_client().messages.create(
        model=model, max_tokens=max_tokens, thinking={'type': 'disabled'},
        system=system, messages=[{'role': 'user', 'content': user}])
    # A reasoning model may still return a ThinkingBlock ahead of the actual
    # TextBlock even with thinking disabled; content[0] isn't reliably the answer,
    # so find every text block instead.
    text_blocks = [block.text for block in response.content if block.type == 'text']
    if not text_blocks:
        raise RuntimeError(f'No text block in response; got block types: {[b.type for b in response.content]}')
    return ''.join(text_blocks)


def _complete_openai(system, user, max_tokens):
    """Text path verified by the user's live smoke test; tool runs are separate."""
    model = os.environ.get('LLM_MODEL', DEFAULT_MODELS['openai'])
    response = _openai_client().chat.completions.create(
        model=model, max_completion_tokens=max_tokens,
        messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}])
    message = response.choices[0].message
    if message.refusal:raise RuntimeError('Model refused: '+message.refusal)
    if not message.content:
        raise RuntimeError(f'No text in response; finish_reason={response.choices[0].finish_reason!r}')
    return message.content


def _to_openai_messages(messages):
    """Translates the Anthropic content-block message history tool_runtime.py builds
    (and persists to the audit trail) into OpenAI's Chat Completions shape. The
    normalized generate() output going the other way is what tool_runtime.py actually
    stores, so this translation only has to run forward, never be inverted."""
    result = []
    for message in messages:
        role = message['role'];content = message['content']
        if isinstance(content, str):
            result.append({'role': role, 'content': content});continue
        if role == 'assistant':
            text = '\n'.join(b['text'] for b in content if b.get('type') == 'text') or None
            calls = [b for b in content if b.get('type') == 'tool_use']
            entry = {'role': 'assistant', 'content': text}
            if calls:
                entry['tool_calls'] = [dict(id=b['id'], type='function',
                    function=dict(name=b['name'], arguments=json.dumps(b['input']))) for b in calls]
            result.append(entry)
        elif role == 'user':
            for block in content:
                if block.get('type') != 'tool_result':
                    raise ValueError('Unsupported user content block for OpenAI translation')
                result.append({'role': 'tool', 'tool_call_id': block['tool_use_id'], 'content': block['content']})
        else:
            raise ValueError('Unsupported message role for OpenAI translation')
    return result


class AnthropicToolClient:
    """One HTTP attempt per generate call; bounded retry decisions live in the runner.

    Only normalized text/tool-use blocks leave the adapter. Hidden model reasoning
    is not persisted in the audit trail. There are no silent replay fallbacks.
    """
    mode = 'live'

    def __init__(self):
        self.request_attempts = 0

    def generate(self, *, role, system, messages, tools, max_tokens, timeout):
        client = _anthropic_client(timeout)
        model = os.environ.get('LLM_MODEL', DEFAULT_MODELS['anthropic'])
        if os.environ.get('LLM_BASE_URL') and not os.environ.get('LLM_MODEL'):
            raise RuntimeError('LLM_MODEL is required for a custom compatible endpoint')
        self.request_attempts += 1
        response = client.messages.create(model=model, max_tokens=max_tokens, system=system,
            messages=messages, tools=tools, tool_choice={'type':'auto'},
            thinking={'type':'disabled'}, timeout=timeout)
        blocks = []
        for block in response.content:
            if block.type == 'text':blocks.append({'type':'text','text':block.text})
            elif block.type == 'tool_use':blocks.append({'type':'tool_use','id':block.id,'name':block.name,'input':block.input})
            elif block.type != 'thinking':raise RuntimeError('Unsupported response content block type')
        return dict(content=blocks, stop_reason=response.stop_reason,
                    usage={'input_tokens':response.usage.input_tokens,'output_tokens':response.usage.output_tokens})


class OpenAIToolClient:
    """Same generate() contract as AnthropicToolClient -- normalizes OpenAI's Chat
    Completions tool-calling shape into the same content-block form (text/tool_use)
    tool_runtime.py builds, persists to the audit trail, and replays on. Live tool
    round trips have been verified; the full investigation is still being evaluated.
    """
    mode = 'live'

    def __init__(self):
        self.request_attempts = 0

    def generate(self, *, role, system, messages, tools, max_tokens, timeout):
        client = _openai_client(timeout)
        model = os.environ.get('LLM_MODEL', DEFAULT_MODELS['openai'])
        if os.environ.get('LLM_BASE_URL') and not os.environ.get('LLM_MODEL'):
            raise RuntimeError('LLM_MODEL is required for a custom compatible endpoint')
        openai_tools = [dict(type='function', function=dict(
            name=t['name'], description=t['description'], parameters=t['input_schema'])) for t in tools]
        self.request_attempts += 1
        response = client.chat.completions.create(model=model, max_completion_tokens=max_tokens,
            messages=[{'role': 'system', 'content': system}]+_to_openai_messages(messages),
            # One observation per turn prevents a large parallel batch from
            # overflowing the latest (deliberately untrimmed) context block.
            tools=openai_tools, tool_choice='auto', parallel_tool_calls=False, timeout=timeout)
        choice = response.choices[0];message = choice.message
        blocks = []
        if message.content:blocks.append({'type': 'text', 'text': message.content})
        for call in (message.tool_calls or []):
            try:arguments = json.loads(call.function.arguments)
            except (ValueError, TypeError):raise RuntimeError('Model returned non-JSON tool arguments')
            blocks.append({'type': 'tool_use', 'id': call.id, 'name': call.function.name, 'input': arguments})
        stop_reason = 'refusal' if message.refusal else {'length':'max_tokens'}.get(choice.finish_reason, choice.finish_reason)
        usage = response.usage
        return dict(content=blocks, stop_reason=stop_reason,
                    usage={'input_tokens': usage.prompt_tokens, 'output_tokens': usage.completion_tokens})


def live_client():
    provider = _provider()
    if provider == 'openai':return OpenAIToolClient()
    if provider == 'anthropic':return AnthropicToolClient()
    raise RuntimeError(f'Unknown LLM_PROVIDER: {provider!r}; expected anthropic or openai')
