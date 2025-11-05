#!/usr/bin/env python3
"""
Fillout Sync Service - Runs continuously every 30 seconds
Checks for new form submissions and syncs only the 3 newest ones
"""
import time
import signal
import sys
from datetime import datetime, timedelta
from fillout_integration import sync_fillout_submissions, FilloutAPI
from app import app

class FilloutSyncService:
    """Continuous Fillout sync service"""
    
    def __init__(self, sync_interval=30):
        self.sync_interval = sync_interval  # seconds
        self.running = True
        self.last_sync = None
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        print(f"\nReceived signal {signum}. Shutting down gracefully...")
        self.running = False
    
    def sync_recent_submissions(self):
        """Sync the 3 newest form submissions"""
        try:
            # Sync only the last 3 submissions (newest ones)
            result = sync_fillout_submissions(hours_back=24*365)  # Look back far enough to get all submissions
            
            if result['success']:
                if result['new_orders'] > 0 or result['updated_orders'] > 0:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                          f"Fillout sync: {result['new_orders']} new, {result['updated_orders']} updated")
                else:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No new Fillout submissions")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fillout sync failed: {result.get('error', 'Unknown error')}")
                
            self.last_sync = datetime.now()
            return result['success']
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error during Fillout sync: {e}")
            return False
    
    def test_connection(self):
        """Test Fillout API connection"""
        try:
            fillout_api = FilloutAPI()
            form_metadata = fillout_api.get_form_metadata()
            return form_metadata is not None
        except Exception as e:
            print(f"Fillout connection test failed: {e}")
            return False
    
    def run(self):
        """Main service loop"""
        print("Fillout Sync Service Starting...")
        print(f"Sync interval: {self.sync_interval} seconds")
        print("Monitoring for the 3 newest form submissions")
        print("Press Ctrl+C to stop")
        print("=" * 50)
        
        # Test connection first
        if not self.test_connection():
            print("ERROR: Cannot connect to Fillout API. Please check your credentials.")
            return
        
        print("Connection test successful!")
        
        # Initial sync
        print("Performing initial sync...")
        self.sync_recent_submissions()
        
        # Main loop
        while self.running:
            try:
                # Wait for next sync
                for i in range(self.sync_interval):
                    if not self.running:
                        break
                    time.sleep(1)
                
                if self.running:
                    self.sync_recent_submissions()
                    
            except KeyboardInterrupt:
                print("\nShutdown requested by user")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
                print("Continuing in 30 seconds...")
                time.sleep(30)
        
        print("\nFillout Sync Service stopped.")

def main():
    """Main entry point"""
    print("Fillout Continuous Sync Service")
    print("=" * 40)
    
    # Use default 30 seconds interval - no user input required
    interval = 30
    print(f"Using default sync interval: {interval} seconds")
    
    # Start the service
    service = FilloutSyncService(sync_interval=interval)
    service.run()

if __name__ == "__main__":
    main()


