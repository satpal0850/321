import requests
import time
from datetime import datetime

URL = "https://fb-reel-downloader.onrender.com"
INTERVAL = 40  # seconds

def ping():
    while True:
        try:
            response = requests.get(URL)
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Pinged {URL} - Status Code: {response.status_code}")
        except Exception as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Error pinging {URL}: {str(e)}")
        
        time.sleep(INTERVAL)

if __name__ == "__main__":
    print(f"Starting self-pinger for {URL} every {INTERVAL} seconds...")
    ping()
