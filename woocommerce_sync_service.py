#!/usr/bin/env python3
"""
WooCommerce Sync Service - Runs continuously every 30 seconds
"""
import time
import signal
import sys
from datetime import datetime, timedelta
from woocommerce_integration import sync_woocommerce_orders, WooCommerceAPI
from app import app

class WooCommerceSyncService:
    """Continuous WooCommerce sync service"""
    
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
    
    def sync_recent_orders(self):
        """Sync orders from the last hour to catch any new ones"""
        try:
            # Only sync last 1 hour to be efficient
            result = sync_woocommerce_orders(days_back=0.042)  # 1 hour = 1/24 day
            
            if result['success']:
                if result['new_orders'] > 0 or result['updated_orders'] > 0:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                          f"Synced: {result['new_orders']} new, {result['updated_orders']} updated")
                else:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No new orders")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Sync failed: {result.get('error', 'Unknown error')}")
                
            self.last_sync = datetime.now()
            return result['success']
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error during sync: {e}")
            return False
    
    def test_connection(self):
        """Test WooCommerce API connection"""
        try:
            wc_api = WooCommerceAPI()
            orders = wc_api.get_orders(per_page=1)
            return len(orders) >= 0  # Even 0 orders means connection works
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
    
    def run(self):
        """Main service loop"""
        print("WooCommerce Sync Service Starting...")
        print(f"Sync interval: {self.sync_interval} seconds")
        print("Press Ctrl+C to stop")
        print("=" * 50)
        
        # Test connection first
        if not self.test_connection():
            print("ERROR: Cannot connect to WooCommerce API. Please check your credentials.")
            return
        
        print("Connection test successful!")
        
        # Initial sync
        print("Performing initial sync...")
        self.sync_recent_orders()
        
        # Main loop
        while self.running:
            try:
                # Wait for next sync
                for i in range(self.sync_interval):
                    if not self.running:
                        break
                    time.sleep(1)
                
                if self.running:
                    self.sync_recent_orders()
                    
            except KeyboardInterrupt:
                print("\nShutdown requested by user")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
                print("Continuing in 30 seconds...")
                time.sleep(30)
        
        print("\nWooCommerce Sync Service stopped.")

def main():
    """Main entry point"""
    print("WooCommerce Continuous Sync Service")
    print("=" * 40)
    
    # Use default 30 seconds interval - no user input required
    interval = 30
    print(f"Using default sync interval: {interval} seconds")
    
    # Start the service
    service = WooCommerceSyncService(sync_interval=interval)
    service.run()

if __name__ == "__main__":
    main()
