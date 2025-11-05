#!/usr/bin/env python3
"""
Improved WooCommerce Sync Service with Configuration
"""
import time
import signal
import sys
from datetime import datetime, timedelta
from woocommerce_integration import sync_woocommerce_orders, WooCommerceAPI
from woocommerce_config import get_sync_settings, update_sync_interval, SYNC_INTERVAL_SECONDS
from app import app

class ImprovedWooCommerceSyncService:
    """Enhanced WooCommerce sync service with configuration"""
    
    def __init__(self):
        self.settings = get_sync_settings()
        self.running = True
        self.last_sync = None
        self.sync_count = 0
        self.error_count = 0
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        print(f"\nReceived signal {signum}. Shutting down gracefully...")
        self.running = False
    
    def sync_recent_orders(self):
        """Sync orders from the configured lookback period"""
        try:
            # Convert hours to days for the sync function
            days_back = self.settings['lookback_hours'] / 24.0
            
            result = sync_woocommerce_orders(days_back=days_back)
            
            if result['success']:
                self.sync_count += 1
                
                if result['new_orders'] > 0 or result['updated_orders'] > 0:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                          f"✅ Synced: {result['new_orders']} new, {result['updated_orders']} updated")
                elif self.settings['log_no_changes']:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ℹ️  No new orders")
            else:
                self.error_count += 1
                if self.settings['log_activity']:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Sync failed: {result.get('error', 'Unknown error')}")
                
            self.last_sync = datetime.now()
            return result['success']
            
        except Exception as e:
            self.error_count += 1
            if self.settings['log_activity']:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 💥 Error during sync: {e}")
            return False
    
    def test_connection(self):
        """Test WooCommerce API connection"""
        try:
            wc_api = WooCommerceAPI()
            orders = wc_api.get_orders(per_page=1)
            return len(orders) >= 0
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
    
    def show_status(self):
        """Show current service status"""
        uptime = datetime.now() - self.start_time if hasattr(self, 'start_time') else timedelta(0)
        print(f"\n📊 Service Status:")
        print(f"   Uptime: {uptime}")
        print(f"   Sync count: {self.sync_count}")
        print(f"   Error count: {self.error_count}")
        print(f"   Last sync: {self.last_sync.strftime('%Y-%m-%d %H:%M:%S') if self.last_sync else 'Never'}")
        print(f"   Interval: {self.settings['interval_seconds']} seconds")
        print(f"   Lookback: {self.settings['lookback_hours']} hours")
    
    def interactive_menu(self):
        """Show interactive menu for adjustments"""
        print("\n⚙️  Interactive Commands:")
        print("   's' - Show status")
        print("   'i' - Change sync interval")
        print("   'l' - Change lookback hours")
        print("   'n' - Sync now")
        print("   'q' - Quit")
        print("   Enter - Continue")
    
    def handle_user_input(self):
        """Handle user input for adjustments"""
        try:
            # Non-blocking input check
            import select
            import sys
            
            if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                user_input = sys.stdin.readline().strip().lower()
                
                if user_input == 's':
                    self.show_status()
                elif user_input == 'i':
                    try:
                        new_interval = int(input("Enter new sync interval (10-3600 seconds): "))
                        self.settings['interval_seconds'] = update_sync_interval(new_interval)
                        print(f"✅ Sync interval updated to {self.settings['interval_seconds']} seconds")
                    except ValueError:
                        print("❌ Invalid interval")
                elif user_input == 'l':
                    try:
                        new_hours = float(input("Enter new lookback hours (0.1-24): "))
                        if 0.1 <= new_hours <= 24:
                            self.settings['lookback_hours'] = new_hours
                            print(f"✅ Lookback updated to {new_hours} hours")
                        else:
                            print("❌ Hours must be between 0.1 and 24")
                    except ValueError:
                        print("❌ Invalid hours")
                elif user_input == 'n':
                    print("🔄 Syncing now...")
                    self.sync_recent_orders()
                elif user_input == 'q':
                    self.running = False
                    
        except:
            pass  # Non-blocking input not available on Windows
    
    def run(self):
        """Main service loop"""
        self.start_time = datetime.now()
        
        print("🚀 Improved WooCommerce Sync Service Starting...")
        print(f"⏱️  Sync interval: {self.settings['interval_seconds']} seconds")
        print(f"🔍 Lookback: {self.settings['lookback_hours']} hours")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        # Test connection first
        if not self.test_connection():
            print("❌ Cannot connect to WooCommerce API. Please check your credentials.")
            return
        
        print("✅ Connection test successful!")
        
        # Initial sync
        print("🔄 Performing initial sync...")
        self.sync_recent_orders()
        
        # Main loop
        next_sync = time.time() + self.settings['interval_seconds']
        
        while self.running:
            try:
                current_time = time.time()
                
                if current_time >= next_sync:
                    self.sync_recent_orders()
                    next_sync = current_time + self.settings['interval_seconds']
                
                # Handle user input (if available)
                self.handle_user_input()
                
                # Sleep for 1 second
                time.sleep(1)
                    
            except KeyboardInterrupt:
                print("\n🛑 Shutdown requested by user")
                break
            except Exception as e:
                print(f"💥 Unexpected error: {e}")
                print("⏳ Continuing in 30 seconds...")
                time.sleep(30)
        
        self.show_status()
        print("\n🏁 WooCommerce Sync Service stopped.")

def main():
    """Main entry point"""
    print("🛍️  WooCommerce Sync Service - Enhanced Version")
    print("=" * 50)
    
    # Quick setup options
    print("\n⚙️  Quick Setup Options:")
    print("1. Default (30 seconds, 1 hour lookback)")
    print("2. Fast (10 seconds, 30 minutes lookback)")  
    print("3. Slow (5 minutes, 6 hours lookback)")
    print("4. Custom")
    
    try:
        choice = input("\nEnter choice (1-4, default: 1): ").strip()
        
        if choice == "2":
            update_sync_interval(10)
            print("✅ Fast mode: 10 seconds, 30 minutes lookback")
        elif choice == "3":
            update_sync_interval(300)  # 5 minutes
            print("✅ Slow mode: 5 minutes, 6 hours lookback")
        elif choice == "4":
            interval = int(input("Sync interval (seconds): "))
            update_sync_interval(interval)
            print(f"✅ Custom: {interval} seconds")
        else:
            print("✅ Default: 30 seconds, 1 hour lookback")
            
    except (ValueError, KeyboardInterrupt):
        print("✅ Using defaults")
    
    # Start the service
    service = ImprovedWooCommerceSyncService()
    service.run()

if __name__ == "__main__":
    main()

