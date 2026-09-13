"""Small strict JSON-schema subset used by local tool definitions (no dependencies)."""
import math


def validate(value,schema,path='input'):
    kind=schema.get('type')
    ok={'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),
        'number':type(value) in (int,float) and math.isfinite(value),'integer':type(value) is int,
        'boolean':type(value) is bool,'null':value is None}
    if kind not in ok or not ok[kind]:raise ValueError(f'{path}: expected {kind}')
    if 'enum' in schema and value not in schema['enum']:raise ValueError(f'{path}: invalid choice')
    if kind=='object':
        props=schema.get('properties',{})
        missing=set(schema.get('required',[]))-set(value)
        if missing:raise ValueError(f'{path}: missing {sorted(missing)}')
        if schema.get('additionalProperties') is False and set(value)-set(props):raise ValueError(f'{path}: unexpected fields')
        for key,v in value.items():
            if key in props:validate(v,props[key],path+'.'+key)
    if kind=='array':
        if not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',100):raise ValueError(f'{path}: invalid array size')
        for i,v in enumerate(value):validate(v,schema['items'],f'{path}[{i}]')
    if kind=='string' and not schema.get('minLength',0)<=len(value)<=schema.get('maxLength',6000):raise ValueError(f'{path}: invalid string length')
    if kind in ('integer','number') and not schema.get('minimum',-float('inf'))<=value<=schema.get('maximum',float('inf')):raise ValueError(f'{path}: out of range')


def obj(properties,required=None):return dict(type='object',properties=properties,required=list(properties) if required is None else required,additionalProperties=False)
def string(maximum=2000):return dict(type='string',minLength=1,maxLength=maximum)
def choice(*values):return dict(type='string',enum=list(values))
def array(items,minimum=0,maximum=20):return dict(type='array',items=items,minItems=minimum,maxItems=maximum)
def integer(lo,hi):return dict(type='integer',minimum=lo,maximum=hi)
