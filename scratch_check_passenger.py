import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from infrastructure.supabase_client import get_supabase

def check():
    supabase = get_supabase()
    if not supabase:
        print("Supabase client not available.")
        return

    try:
        res = supabase.table("passenger_registrations").select("*").execute()
        print("Passenger registrations count:", len(res.data))
        print("Columns: ", res.data[0] if res.data else "No records")
    except Exception as e:
        print("Error fetching passenger_registrations:", e)

if __name__ == "__main__":
    check()
