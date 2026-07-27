import time
import subprocess

def run_sync():
    print("🔄 Starting scheduled synchronization...", flush=True)
    try:
        print("-> Running sync_workouts.py", flush=True)
        subprocess.run(["python", "sync_workouts.py"], check=False)
        
        print("-> Running sync_garmin.py", flush=True)
        subprocess.run(["python", "sync_garmin.py"], check=False)
        
    except Exception as e:
        print(f"❌ Error during sync: {e}", flush=True)

if __name__ == "__main__":
    print("⌚ Scheduler started. Running sync every 30 minutes...", flush=True)
    
    # Run immediately on startup
    run_sync()
    
    # Loop every 30 minutes
    while True:
        time.sleep(1800)
        run_sync()
