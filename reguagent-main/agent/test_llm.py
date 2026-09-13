"""LLM provider adapters: message/tool-schema translation and response normalization,
tested without any real network call (mocked SDK objects) or real key (missing-key path)."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import llm


class ToOpenAIMessagesTests(unittest.TestCase):
    def test_plain_string_content_passes_through(self):
        messages=[{'role':'user','content':'{"task":"..."}'}]
        self.assertEqual(llm._to_openai_messages(messages),[{'role':'user','content':'{"task":"..."}'}])

    def test_assistant_text_and_tool_use_blocks_translate(self):
        messages=[{'role':'assistant','content':[
            {'type':'text','text':'Looking this up.'},
            {'type':'tool_use','id':'call_1','name':'get_record','input':{'record_id':'REQ-1'}}]}]
        result=llm._to_openai_messages(messages)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['role'],'assistant')
        self.assertEqual(result[0]['content'],'Looking this up.')
        self.assertEqual(result[0]['tool_calls'],[{'id':'call_1','type':'function',
            'function':{'name':'get_record','arguments':'{"record_id": "REQ-1"}'}}])

    def test_assistant_with_only_tool_use_has_no_text_content(self):
        messages=[{'role':'assistant','content':[{'type':'tool_use','id':'call_1','name':'x','input':{}}]}]
        result=llm._to_openai_messages(messages)
        self.assertIsNone(result[0]['content'])
        self.assertIn('tool_calls',result[0])

    def test_user_tool_result_becomes_a_tool_role_message(self):
        messages=[{'role':'user','content':[{'type':'tool_result','tool_use_id':'call_1','content':'{"status":"ok"}','is_error':False}]}]
        result=llm._to_openai_messages(messages)
        self.assertEqual(result,[{'role':'tool','tool_call_id':'call_1','content':'{"status":"ok"}'}])

    def test_multiple_tool_results_become_separate_tool_messages(self):
        messages=[{'role':'user','content':[
            {'type':'tool_result','tool_use_id':'call_1','content':'a','is_error':False},
            {'type':'tool_result','tool_use_id':'call_2','content':'b','is_error':False}]}]
        result=llm._to_openai_messages(messages)
        self.assertEqual(len(result),2)
        self.assertEqual([r['tool_call_id'] for r in result],['call_1','call_2'])

    def test_unsupported_role_is_rejected(self):
        with self.assertRaises(ValueError):llm._to_openai_messages([{'role':'system','content':[]}])

    def test_unsupported_user_block_type_is_rejected(self):
        with self.assertRaises(ValueError):
            llm._to_openai_messages([{'role':'user','content':[{'type':'mystery'}]}])


def fake_openai_response(*,text=None,tool_calls=(),refusal=None,finish_reason='stop',prompt_tokens=10,completion_tokens=5):
    message=SimpleNamespace(content=text,refusal=refusal,
        tool_calls=[SimpleNamespace(id=c['id'],function=SimpleNamespace(name=c['name'],arguments=c['arguments'])) for c in tool_calls] or None)
    choice=SimpleNamespace(message=message,finish_reason=finish_reason)
    usage=SimpleNamespace(prompt_tokens=prompt_tokens,completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice],usage=usage)


class OpenAIToolClientTests(unittest.TestCase):
    def test_missing_key_makes_zero_attempts(self):
        client=llm.OpenAIToolClient()
        with patch.dict(os.environ,{'LLM_PROVIDER':'openai'},clear=True):
            with self.assertRaises(RuntimeError):
                client.generate(role='coordinator',system='s',messages=[{'role':'user','content':'{}'}],
                    tools=[],max_tokens=100,timeout=5)
        self.assertEqual(client.request_attempts,0)

    def test_text_only_response_normalizes_to_a_text_block(self):
        client=llm.OpenAIToolClient()
        fake_client=MagicMock()
        fake_client.chat.completions.create.return_value=fake_openai_response(text='All done.',finish_reason='stop')
        with patch.dict(os.environ,{'LLM_PROVIDER':'openai','OPENAI_API_KEY':'test-key'}), \
             patch.object(llm,'_openai_client',return_value=fake_client):
            result=client.generate(role='coordinator',system='s',messages=[{'role':'user','content':'{}'}],
                tools=[],max_tokens=100,timeout=5)
        self.assertEqual(result['content'],[{'type':'text','text':'All done.'}])
        self.assertEqual(result['stop_reason'],'stop')
        self.assertEqual(result['usage'],{'input_tokens':10,'output_tokens':5})
        self.assertEqual(client.request_attempts,1)

    def test_tool_call_response_normalizes_to_a_tool_use_block_with_parsed_arguments(self):
        client=llm.OpenAIToolClient()
        fake_client=MagicMock()
        fake_client.chat.completions.create.return_value=fake_openai_response(
            tool_calls=[{'id':'call_1','name':'get_record','arguments':'{"record_id": "REQ-1"}'}],finish_reason='tool_calls')
        with patch.dict(os.environ,{'LLM_PROVIDER':'openai','OPENAI_API_KEY':'test-key'}), \
             patch.object(llm,'_openai_client',return_value=fake_client):
            result=client.generate(role='bank_investigator',system='s',messages=[{'role':'user','content':'{}'}],
                tools=[{'name':'get_record','description':'d','input_schema':{'type':'object'}}],max_tokens=100,timeout=5)
        self.assertEqual(result['content'],[{'type':'tool_use','id':'call_1','name':'get_record','input':{'record_id':'REQ-1'}}])
        passed_tools=fake_client.chat.completions.create.call_args.kwargs['tools']
        self.assertEqual(passed_tools,[{'type':'function','function':{'name':'get_record','description':'d','parameters':{'type':'object'}}}])
        self.assertIs(fake_client.chat.completions.create.call_args.kwargs['parallel_tool_calls'],False)

    def test_length_finish_reason_maps_to_max_tokens_stop_reason(self):
        client=llm.OpenAIToolClient()
        fake_client=MagicMock()
        fake_client.chat.completions.create.return_value=fake_openai_response(text='partial',finish_reason='length')
        with patch.dict(os.environ,{'LLM_PROVIDER':'openai','OPENAI_API_KEY':'test-key'}), \
             patch.object(llm,'_openai_client',return_value=fake_client):
            result=client.generate(role='coordinator',system='s',messages=[{'role':'user','content':'{}'}],
                tools=[],max_tokens=100,timeout=5)
        self.assertEqual(result['stop_reason'],'max_tokens')

    def test_refusal_maps_to_refusal_stop_reason_regardless_of_finish_reason(self):
        client=llm.OpenAIToolClient()
        fake_client=MagicMock()
        fake_client.chat.completions.create.return_value=fake_openai_response(refusal='cannot help with that',finish_reason='stop')
        with patch.dict(os.environ,{'LLM_PROVIDER':'openai','OPENAI_API_KEY':'test-key'}), \
             patch.object(llm,'_openai_client',return_value=fake_client):
            result=client.generate(role='coordinator',system='s',messages=[{'role':'user','content':'{}'}],
                tools=[],max_tokens=100,timeout=5)
        self.assertEqual(result['stop_reason'],'refusal')

    def test_non_json_tool_arguments_are_rejected(self):
        client=llm.OpenAIToolClient()
        fake_client=MagicMock()
        fake_client.chat.completions.create.return_value=fake_openai_response(
            tool_calls=[{'id':'call_1','name':'get_record','arguments':'not json'}],finish_reason='tool_calls')
        with patch.dict(os.environ,{'LLM_PROVIDER':'openai','OPENAI_API_KEY':'test-key'}), \
             patch.object(llm,'_openai_client',return_value=fake_client):
            with self.assertRaises(RuntimeError):
                client.generate(role='coordinator',system='s',messages=[{'role':'user','content':'{}'}],
                    tools=[],max_tokens=100,timeout=5)


class LiveClientFactoryTests(unittest.TestCase):
    def test_defaults_to_anthropic(self):
        with patch.dict(os.environ,{},clear=True), patch.object(llm,'load_local_config'):
            self.assertIsInstance(llm.live_client(),llm.AnthropicToolClient)

    def test_openai_provider_selects_openai_client(self):
        with patch.dict(os.environ,{'LLM_PROVIDER':'openai'},clear=True), patch.object(llm,'load_local_config'):
            self.assertIsInstance(llm.live_client(),llm.OpenAIToolClient)

    def test_unknown_provider_is_rejected(self):
        with patch.dict(os.environ,{'LLM_PROVIDER':'made-up'},clear=True), patch.object(llm,'load_local_config'):
            with self.assertRaises(RuntimeError):llm.live_client()

    def test_live_client_loads_local_config(self):
        with patch.object(llm,'load_local_config') as mock_load:
            llm.live_client()
        mock_load.assert_called_once()


if __name__=='__main__':unittest.main(verbosity=2)
