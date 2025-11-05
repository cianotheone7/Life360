#!/usr/bin/env python3
"""
Dual WooCommerce Sync Service - Monitors both Geneway and Optiway stores
Runs continuously every 30 seconds
"""
import time
import signal
import sys
from datetime import datetime, timedelta
from dual_woocommerce_integration import sync_both_woocommerce_stores
from app import app

class DualWooCommerceSyncService:
    """Continuous sync service for both WooCommerce stores"""
    
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
        """Sync orders from both stores from the last hour"""
        try:
            # Only sync last 1 hour to be efficient
            result = sync_both_woocommerce_stores(days_back=0.042)  # 1 hour = 1/24 day
            
            if result['success']:
                if result['new_orders'] > 0 or result['updated_orders'] > 0:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                          f"Dual sync: {result['new_orders']} new, {result['updated_orders']} updated")
                else:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No new orders from either store")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Dual sync failed: {result.get('error', 'Unknown error')}")
                
            self.last_sync = datetime.now()
            return result['success']
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error during dual sync: {e}")
            return False
    
    def test_connections(self):
        """Test connections to both WooCommerce stores"""
        try:
            from dual_woocommerce_integration import DualWooCommerceAPI, GENEWAY_CONFIG, OPTIWAY_CONFIG
            
            print("Testing connections...")
            
            # Test Geneway
            geneway_api = DualWooCommerceAPI(GENEWAY_CONFIG)
            geneway_orders = geneway_api.get_orders(per_page=1)
            geneway_status = "OK" if geneway_orders else "FAILED"
            
            # Test Optiway
            optiway_api = DualWooCommerceAPI(OPTIWAY_CONFIG)
            optiway_orders = optiway_api.get_orders(per_page=1)
            optiway_status = "OK" if optiway_orders else "FAILED"
            
            print(f"Geneway API: {geneway_status}")
            print(f"Optiway API: {optiway_status}")
            
            return geneway_status == "OK" and optiway_status == "OK"
            
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
    
    def run(self):
        """Main service loop"""
        print("Dual WooCommerce Continuous Sync Service")
        print("==========================================")
        
        # Get sync interval from user or use default
        try:
            user_interval = input(f"Enter sync interval in seconds (default: {self.sync_interval}): ").strip()
            if user_interval:
                self.sync_interval = int(user_interval)
        except (ValueError, KeyboardInterrupt):
            pass
        
        print(f"Using sync interval: {self.sync_interval} seconds")
        print(f"Dual WooCommerce Sync Service Starting...")
        print(f"Sync interval: {self.sync_interval} seconds")
        print(f"Monitoring both Geneway and Optiway stores")
        print("Press Ctrl+C to stop")
        print("=" * 50)
        
        # Test connections first
        if not self.test_connections():
            print("WARNING: Some API connections failed. Continuing anyway...")
        
        # Perform initial sync
        print("Performing initial dual sync...")
        self.sync_recent_orders()
        
        # Main loop
        while self.running:
            try:
                time.sleep(self.sync_interval)
                if self.running:  # Check again in case we were interrupted during sleep
                    self.sync_recent_orders()
                    
            except KeyboardInterrupt:
                print("\nReceived interrupt signal. Shutting down...")
                self.running = False
            except Exception as e:
                print(f"Unexpected error in main loop: {e}")
                time.sleep(5)  # Wait a bit before retrying
        
        print("Dual WooCommerce sync service stopped.")

def main():
    """Entry point for the sync service"""
    service = DualWooCommerceSyncService()
    service.run()

if __name__ == "__main__":
    main()


