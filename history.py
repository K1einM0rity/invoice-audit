import json
import os

HISTORY_FILE = "invoice_history.json"

def load_history() -> set:
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r") as f:
        return set(json.load(f))

def save_history(numbers: set):
    with open(HISTORY_FILE, "w") as f:
        json.dump(list(numbers), f)