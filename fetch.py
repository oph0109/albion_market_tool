import requests
import time
from datetime import datetime, timezone
from dateutil.parser import parse, ParserError
from tabulate import tabulate
import os

API_URL = "https://west.albion-online-data.com/api/v2/stats/prices/"
CITIES = ["Black Market", "Caerleon"]
QUALITIES = {
    1: "Normal",       # Quality level 1
    2: "Good",         # Quality level 2
    3: "Outstanding",  # Quality level 3
    4: "Excellent",    # Quality level 4
    5: "Masterpiece"   # Quality level 5
}
MAX_AGE_BM = 100  # Maximum age in minutes
MAX_AGE_CITY = 100  # Maximum age in minutes
MIN_PROFIT = 1000  # Minimum profit to consider
POLL_INTERVAL = 4  # Polling interval in seconds

# Function to read the items from the file and create the ITEM_NAME_MAP dictionary
def read_items(file_path):
    item_map = {}
    with open(file_path, 'r') as file:
        for line in file:
            parts = line.strip().split(':')
            if len(parts) == 3:
                item_id = parts[1].strip()
                item_name = parts[2].strip()
                item_map[item_id] = item_name
    return item_map

# Function to filter tier 6, 7, and 8 items
def filter_items_by_tier(item_map, tiers):
    return {item_id: name for item_id, name in item_map.items() if any(item_id.startswith(tier) for tier in tiers)}

# Read the item names from the items.txt file
script_dir = os.path.dirname(__file__)
items_file_path = os.path.join(script_dir, 'items.txt')
ITEM_NAME_MAP = read_items(items_file_path)

# Filter tier 6, 7, and 8 items
TIERS = ["T6", "T7", "T8"]
FILTERED_ITEMS = filter_items_by_tier(ITEM_NAME_MAP, TIERS)

def get_current_time():
    response = requests.get("http://worldtimeapi.org/api/timezone/Etc/UTC")
    return parse(response.json()['datetime'])

def get_age(current_time, item_time):
    if not item_time or item_time.startswith("0001-01-01"):
        return float('inf')
    try:
        item_time_obj = parse(item_time).astimezone(timezone.utc)
        age = (current_time - item_time_obj).total_seconds() / 60
        return age + 300  # Normalize and add 300 to each value
    except ParserError as e:
        print(f"Parser error: {e}")
        print(f"Item time: {item_time}")
        return float('inf')
    except Exception as e:
        print(f"Unexpected error: {e}")
        print(f"Item time: {item_time}")
        return float('inf')

def fetch_data(items, cities, qualities):
    results = []
    chunk_size = 250  # Adjust the chunk size as needed
    for i in range(0, len(items), chunk_size):
        items_chunk = items[i:i+chunk_size]
        item_ids = ','.join(items_chunk)
        url = f"{API_URL}{item_ids}?locations={','.join(cities)}&qualities={','.join(map(str, qualities.keys()))}"
        #print(f"Fetching data from URL...")  # Debug statement
        response = requests.get(url)
        if response.status_code == 200:
            results.extend(response.json())
        else:
            print(f"Failed to fetch data for chunk: {response.status_code}")  # Debug statement
    return results

def process_data(data, current_time):
    table_data = []
    headers = ["Name", "Enchantment", "Quality", "BM Age (mins)", "Caerleon Age (mins)", "BM Price", "Caerleon Price", "Profit"]
    
    bm_prices = {q: {} for q in QUALITIES.keys()}
    for item in data:
        item_id = item['item_id']
        quality = item['quality']
        city = item['city']
        price = item.get("buy_price_max", 0) if city == "Black Market" else item.get("sell_price_min", 0)
        if city == "Black Market":
            bm_prices[quality][item_id] = price

    item_data = {}
    for item in data:
        item_id = item['item_id']
        quality = item['quality']
        city = item['city']
        key = (item_id, quality, city)
        item_data[key] = item

    filtered_data = []
    for (item_id, quality, city), item in item_data.items():
        if city == "Caerleon":
            caerleon_price = item.get("sell_price_min", 0)
            bm_age = get_age(current_time, item_data.get((item_id, quality, "Black Market"), {}).get("buy_price_max_date", ""))
            caerleon_age = get_age(current_time, item.get("sell_price_min_date", ""))
            item_base_id = item_id.split('@')[0]
            enchantment = item_id.split('@')[1] if '@' in item_id else 0
            item_name = ITEM_NAME_MAP.get(item_base_id, "Unknown Item")

            highest_bm_price = bm_prices[quality].get(item_id, 0)
            profit = highest_bm_price * 0.97 - caerleon_price  # Assuming 3% tax for premium

            if bm_age < MAX_AGE_BM and caerleon_age < MAX_AGE_CITY:
                table_data.append([item_name, enchantment, QUALITIES[quality], bm_age, caerleon_age, highest_bm_price, caerleon_price, profit])
                if bm_age != float('inf') and caerleon_age != float('inf') and highest_bm_price > 0 and caerleon_price > 0 and profit > 0:
                    filtered_data.append([item_name, enchantment, QUALITIES[quality], bm_age, caerleon_age, highest_bm_price, caerleon_price, profit])

    sorted_filtered_data = sorted(filtered_data, key=lambda x: x[-1], reverse=True)
    
    with open("full_table.txt", "w") as f:
        f.write(tabulate(table_data, headers=headers, tablefmt="pretty"))
    
    if sorted_filtered_data:
        print(tabulate(sorted_filtered_data, headers=headers, tablefmt="pretty"))
    else:
        print("No profitable items found.")

def main():
    while True:
        current_time = get_current_time()
        items = list(FILTERED_ITEMS.keys())
        data = fetch_data(items, CITIES, QUALITIES)
        process_data(data, current_time)
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
