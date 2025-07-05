import json
import os

def get_api_key():
    with open('/home/ub3rmensch/.secrets', 'r') as f:
        data = f.read()
        api_key = data.split('=')[1].strip()
    return api_key

def set_api_keys_env(secrets_file: str=None) -> None:
    data = {}
    if secrets_file is None:
        secrets_file = os.path.expanduser('~/secrets.json')
    try:
        with open(secrets_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading the secrets file: {secrets_file} - {e}")
    for key, value in data.items():
        # print(f"Setting environment variable: {key} = {value}")
        os.environ[key] = value