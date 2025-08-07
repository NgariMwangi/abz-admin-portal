import requests

url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"

params = {
    "input": "kandara",
    "key": "AIzaSyAkl_0VqCsZLCHhbww7YwRgoosGCV35miM",
    "components": "country:ke"
}

response = requests.get(url, params=params)

if response.status_code == 200:
    data = response.json()
    print(data)
else:
    print(f"Request failed with status code: {response.status_code}")
    print(response.text)
