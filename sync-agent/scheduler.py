import os
import time
import subprocess

def run_sync():
    print("🔄 Starting scheduled synchronization...", flush=True)
    try:
        print("-> Running sync_garmin.py", flush=True)
        subprocess.run(["python", "sync_garmin.py"], check=False)
        
    except Exception as e:
        print(f"❌ Error during sync: {e}", flush=True)

if __name__ == "__main__":
    interval_minutes = float(os.getenv("SYNC_INTERVAL_MINUTES", "30"))
    interval_seconds = int(interval_minutes * 60)
    
    print(f"⌚ Scheduler started. Running sync every {interval_minutes:g} minutes...", flush=True)
    
    # Run immediately on startup
    run_sync()
    
    # Loop according to configured interval
    while True:
        time.sleep(interval_seconds)
        run_sync()
