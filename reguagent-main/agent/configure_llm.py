#!/usr/bin/env python3
"""Run in the terminal that already has the exported key; does not display it."""
import argparse
from llm_config import capture_deepseek_environment, capture_openai_environment

DEFAULT_MODELS={'deepseek':'deepseek-v4-flash','openai':'gpt-5'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-env',action='store_true',required=True)
    parser.add_argument('--provider',choices=['deepseek','openai'],default='deepseek')
    parser.add_argument('--model',default=None,help='Defaults to deepseek-v4-flash or gpt-5 depending on --provider.')
    args=parser.parse_args()
    model=args.model or DEFAULT_MODELS[args.provider]
    try:
        if args.provider=='openai':path=capture_openai_environment(model=model)
        else:path=capture_deepseek_environment(model=model)
    except FileExistsError:parser.exit(2,'Local .env.local already exists; preserved without overwriting.\n')
    except ValueError as exc:parser.exit(2,str(exc)+'\n')
    print(f'Configuration saved to {path} (provider={args.provider}, model={model}); key was not printed. File permissions: owner read/write.')


if __name__=='__main__':main()
