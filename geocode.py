import urllib.request
import json
import urllib.parse
from dotenv import load_dotenv
import os

load_dotenv(".env")
TOMTOM_KEY = os.getenv("VITE_TOMTOM_API_KEY")

locations = [
    "Thiruporur, Chennai", "Velachery, Chennai", "T Nagar, Chennai",
    "Kelambakkam, Chennai", "OMR, Chennai", "Broadway, Chennai",
    "Tambaram, Chennai", "GST Road, Chennai", "Mamallapuram, Chennai",
    "Koyambedu, Chennai", "Vadapalani, Chennai", "Adyar, Chennai",
    "Chennai Central", "Egmore, Chennai", "Perambur, Chennai", "Ambattur, Chennai",
    "Guindy, Chennai", "Chromepet, Chennai"
]

results = {}

for loc in locations:
    query = urllib.parse.quote(loc)
    url = f"https://api.tomtom.com/search/2/geocode/{query}.json?key={TOMTOM_KEY}&countrySet=IN&limit=1"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data['results']:
                pos = data['results'][0]['position']
                results[loc] = [pos['lon'], pos['lat']]
            else:
                results[loc] = None
    except Exception as e:
        results[loc] = str(e)

print(json.dumps(results, indent=2))
