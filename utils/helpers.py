def get_api_key():
    with open('/home/ub3rmensch/.secrets', 'r') as f:
        data = f.read()
        api_key = data.split('=')[1].strip()
    return api_key