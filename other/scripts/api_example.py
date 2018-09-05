import requests
from pprint import pprint as pp

res = requests.post('http://localhost:5000/auth', json = {'username':'a', 'password':'a'})

if 'access_token' in res.json():
    access_token = res.json()['access_token']

    res = requests.get('http://localhost:5000/api/monitors', headers={'Authorization':'JWT {}'.format(access_token)})
    pp(res.json())

    res = requests.get('http://localhost:5000/api/hijacks', headers={'Authorization':'JWT {}'.format(access_token)})
    pp(res.json())
