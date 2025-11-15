#!/usr/bin/env python3
"""
Multi-Provider WooCommerce Sync Service
Polls all three WooCommerce stores every 10 seconds for new orders
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta
from requests.auth import HTTPBasicAuth
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from woocommerce_config import WOOCOMMERCE_PROVIDERS, SYNC_INTERVAL_SECONDS, SYNC_LOOKBACK_HOURS
from app import app, db, Order, OrderItem
from woocommerce_integration import map_woocommerce_to_local_order

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MultiProviderWooCommerceSync:
    """Sync orders from multiple WooCommerce providers"""
    
    def __init__(self):
        self.last_sync = {}
        for provider in WOOCOMMERCE_PROVIDERS.keys():
            self.last_sync[provider] = datetime.now() - timedelta(days=1)
    
    def fetch_orders_from_provider(self, provider_name, config):
        """Fetch recent orders from a specific WooCommerce provider"""
        try:
            base_url = config['base_url']
            api_url = f"{base_url}/wp-json/wc/v3/orders"
            
            auth = HTTPBasicAuth(
                config['consumer_key'],
                config['consumer_secret']
            )
            
            # Calculate time range
            after = (datetime.now() - timedelta(hours=SYNC_LOOKBACK_HOURS)).isoformat()
            
            params = {
                'after': after,
                'per_page': 100,
                'orderby': 'date',
                'order': 'desc'
            }
            
            response = requests.get(
                api_url,
                auth=auth,
                params=params,
                timeout=config.get('timeout', 30)
            )
            
            if response.status_code == 200:
                orders = response.json()
                logger.info(f"{provider_name}: Found {len(orders)} orders")
                return orders
            else:
                logger.error(f"{provider_name}: API error {response.status_code} - URL: {response.url}")
                logger.error(f"{provider_name}: Response: {response.text[:200]}")
                # Try without 'after' parameter if 404 (some WooCommerce versions don't support it)
                if response.status_code == 404:
                    logger.info(f"{provider_name}: Retrying without 'after' parameter...")
                    params_no_after = {
                        'per_page': 100,
                        'orderby': 'date',
                        'order': 'desc'
                    }
                    retry_response = requests.get(
                        api_url,
                        auth=auth,
                        params=params_no_after,
                        timeout=config.get('timeout', 30)
                    )
                    if retry_response.status_code == 200:
                        orders = retry_response.json()
                        logger.info(f"{provider_name}: Found {len(orders)} orders (without date filter)")
                        return orders
                return []
                
        except Exception as e:
            logger.error(f"{provider_name}: Error fetching orders - {str(e)}")
            return []
    
    def sync_order_to_database(self, woo_order, provider_name):
        """Sync a single WooCommerce order to the database"""
        try:
            with app.app_context():
                # Map WooCommerce order to local format
                order_data = map_woocommerce_to_local_order(woo_order)
                
                # Ensure provider name is set
                if not order_data.get('provider'):
                    order_data['provider'] = provider_name.title()
                
                # Check if order already exists
                existing_order = Order.query.filter_by(
                    woocommerce_id=order_data['woocommerce_id']
                ).first()
                
                if existing_order:
                    # Update existing order
                    for key, value in order_data.items():
                        if key not in ['woocommerce_id', 'id', 'items']:
                            setattr(existing_order, key, value)
                    
                    # Update items if needed
                    existing_order.items = []
                    for item in order_data.get('items', []):
                        order_item = OrderItem()
                        order_item.sku = item['sku']
                        order_item.qty = item['qty']
                        existing_order.items.append(order_item)
                    
                    db.session.commit()
                    logger.info(f"✓ Updated order #{order_data['woocommerce_id']} from {provider_name}")
                    return 'updated'
                else:
                    # Create new order
                    items_data = order_data.pop('items', [])
                    new_order = Order(**order_data)
                    
                    for item in items_data:
                        order_item = OrderItem()
                        order_item.sku = item['sku']
                        order_item.qty = item['qty']
                        new_order.items.append(order_item)
                    
                    db.session.add(new_order)
                    db.session.commit()
                    logger.info(f"✓ NEW ORDER #{order_data['woocommerce_id']} from {provider_name}!")
                    return 'created'
                    
        except Exception as e:
            logger.error(f"Error syncing order: {str(e)}")
            db.session.rollback()
            return 'error'
    
    def sync_provider(self, provider_name, config):
        """Sync all recent orders from a provider"""
        try:
            orders = self.fetch_orders_from_provider(provider_name, config)
            
            stats = {'created': 0, 'updated': 0, 'error': 0}
            
            for woo_order in orders:
                result = self.sync_order_to_database(woo_order, provider_name)
                stats[result] = stats.get(result, 0) + 1
            
            if stats['created'] > 0 or stats['updated'] > 0:
                logger.info(
                    f"{provider_name}: Synced {stats['created']} new, "
                    f"{stats['updated']} updated, {stats['error']} errors"
                )
            
            self.last_sync[provider_name] = datetime.now()
            return stats
            
        except Exception as e:
            logger.error(f"{provider_name}: Sync failed - {str(e)}")
            return {'created': 0, 'updated': 0, 'error': 1}
    
    def run_sync_cycle(self):
        """Run one sync cycle for all providers"""
        logger.info("="*60)
        logger.info("Starting sync cycle...")
        
        total_stats = {'created': 0, 'updated': 0, 'error': 0}
        
        for provider_name, config in WOOCOMMERCE_PROVIDERS.items():
            stats = self.sync_provider(provider_name, config)
            for key in total_stats:
                total_stats[key] += stats.get(key, 0)
        
        if total_stats['created'] > 0 or total_stats['updated'] > 0:
            logger.info(
                f"✓ Cycle complete: {total_stats['created']} new orders, "
                f"{total_stats['updated']} updated"
            )
        else:
            logger.debug("No new orders found")
        
        return total_stats
    
    def start(self):
        """Start continuous sync loop"""
        logger.info("="*60)
        logger.info("MULTI-PROVIDER WOOCOMMERCE SYNC SERVICE")
        logger.info("="*60)
        logger.info(f"Providers: {', '.join(WOOCOMMERCE_PROVIDERS.keys())}")
        logger.info(f"Sync interval: {SYNC_INTERVAL_SECONDS} seconds")
        logger.info(f"Lookback window: {SYNC_LOOKBACK_HOURS} hours")
        logger.info("="*60)
        
        try:
            while True:
                self.run_sync_cycle()
                logger.debug(f"Sleeping for {SYNC_INTERVAL_SECONDS} seconds...")
                time.sleep(SYNC_INTERVAL_SECONDS)
                
        except KeyboardInterrupt:
            logger.info("\nSync service stopped by user")
        except Exception as e:
            logger.error(f"Fatal error: {str(e)}")
            raise


if __name__ == "__main__":
    sync_service = MultiProviderWooCommerceSync()
    sync_service.start()
