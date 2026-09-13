"""Minimal allowlisted local LLM configuration. Never evaluates shell syntax."""
import json
import os
from pathlib import Path

PROJECT_ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CONFIG=PROJECT_ROOT/'.env.local'
ALLOWED={'LLM_API_KEY','ANTHROPIC_API_KEY','OPENAI_API_KEY','LLM_BASE_URL','LLM_MODEL','LLM_PROVIDER'}


def load_local_config(path=DEFAULT_CONFIG,*,override=False):
    path=Path(path)
    if not path.exists():return False
    values={}
    for line_number,line in enumerate(path.read_text().splitlines(),1):
        line=line.strip()
        if not line or line.startswith('#'):continue
        if line.startswith('export '):line=line[7:].lstrip()
        if '=' not in line:raise ValueError(f'Invalid config assignment on line {line_number}')
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if key not in ALLOWED:raise ValueError(f'Unsupported config variable on line {line_number}')
        if value.startswith('"'):
            try:value=json.loads(value)
            except (ValueError,TypeError):raise ValueError(f'Invalid quoted value on line {line_number}') from None
        elif value.startswith("'") and value.endswith("'"):value=value[1:-1]
        if not isinstance(value,str) or any(c in value for c in ('\n','\r','\x00','“','”','‘','’')):
            raise ValueError(f'Invalid configuration value on line {line_number}; use ordinary ASCII quotes')
        values[key]=value
    for key,value in values.items():
        if override or not os.environ.get(key):os.environ[key]=value
    return True


def _write_config(path,values):
    path=Path(path)
    content='\n'.join(k+'='+json.dumps(v,ensure_ascii=True) for k,v in values.items())+'\n'
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as stream:stream.write(content)
    return path


def capture_deepseek_environment(path=DEFAULT_CONFIG,model='deepseek-v4-flash'):
    key=os.environ.get('LLM_API_KEY')
    if not key:raise ValueError('LLM_API_KEY is absent in this terminal; export it there first')
    if any(c in key for c in ('\n','\r','\x00','“','”','‘','’')):raise ValueError('API key contains invalid characters; use ordinary ASCII quotes in export')
    return _write_config(path,dict(LLM_API_KEY=key,LLM_BASE_URL='https://api.deepseek.com/anthropic',LLM_MODEL=model))


def capture_openai_environment(path=DEFAULT_CONFIG,model='gpt-5'):
    key=os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY')
    if not key:raise ValueError('LLM_API_KEY (or OPENAI_API_KEY) is absent in this terminal; export it there first')
    if any(c in key for c in ('\n','\r','\x00','“','”','‘','’')):raise ValueError('API key contains invalid characters; use ordinary ASCII quotes in export')
    return _write_config(path,dict(LLM_API_KEY=key,LLM_PROVIDER='openai',LLM_MODEL=model))
