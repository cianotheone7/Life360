#!/usr/bin/env python3
"""
WooCommerce Configuration Settings - Multiple Providers
"""

# Sync Settings - BALANCED FOR PERFORMANCE AND COST
SYNC_INTERVAL_SECONDS = 60   # Check every 60 seconds (1 minute) - good balance
SYNC_LOOKBACK_HOURS = 1      # Look back 1 hour to catch any missed orders
INITIAL_SYNC_DAYS = 3        # How many days to sync on first run

# API Settings for ALL THREE PROVIDERS
WOOCOMMERCE_PROVIDERS = {
    'geneway': {
        'base_url': 'https://geneway.co.za',
        'consumer_key': 'ck_1eb17dc31b3e348ea8d78ebade88929869e75d41',
        'consumer_secret': 'cs_027121bb8ef73db63a25485a9b4fb139344258eb',
        'api_version': 'wc/v3',
        'timeout': 30
    },
    'optiway': {
        'base_url': 'https://optiway.co.za',
        'consumer_key': 'ck_d398fd9a05bb30c1a259c5dd8075b756e56c23b2',
        'consumer_secret': 'cs_2bd02cddd699ffff0c9bd80017ae1debb1a015b4',
        'api_version': 'wc/v3',
        'timeout': 30
    },
    'partner_portal': {
        'base_url': 'https://life360affiliate.health',
        'consumer_key': 'ck_d916da3e796a218919cc419fa3fa02dd4f487428',
        'consumer_secret': 'cs_22a25024dbc5c341f5507c6d2b44b6f60c586ca7',
        'api_version': 'wc/v3',
        'timeout': 30
    }
}

# Legacy config for backwards compatibility (defaults to Geneway)
WOOCOMMERCE_CONFIG = WOOCOMMERCE_PROVIDERS['geneway']

# Order Status Mapping (WooCommerce -> Life360)
ORDER_STATUS_MAPPING = {
    'pending': 'Pending',
    'processing': 'Processing', 
    'on-hold': 'On Hold',
    'completed': 'Completed',
    'cancelled': 'Cancelled',
    'refunded': 'Refunded',
    'failed': 'Failed'
}

# Logging Settings
LOG_SYNC_ACTIVITY = True    # Log every sync attempt
LOG_NO_CHANGES = False      # Log when no new orders found
LOG_ERRORS = True           # Log all errors

def get_sync_settings():
    """Get current sync settings"""
    return {
        'interval_seconds': SYNC_INTERVAL_SECONDS,
        'lookback_hours': SYNC_LOOKBACK_HOURS,
        'initial_sync_days': INITIAL_SYNC_DAYS,
        'log_activity': LOG_SYNC_ACTIVITY,
        'log_no_changes': LOG_NO_CHANGES
    }

def update_sync_interval(seconds):
    """Update sync interval (for runtime changes)"""
    global SYNC_INTERVAL_SECONDS
    SYNC_INTERVAL_SECONDS = max(10, min(3600, seconds))  # Between 10 seconds and 1 hour
    return SYNC_INTERVAL_SECONDS

def update_lookback_hours(hours):
    """Update how far back to look for orders"""
    global SYNC_LOOKBACK_HOURS
    SYNC_LOOKBACK_HOURS = max(0.1, min(24, hours))  # Between 6 minutes and 24 hours
    return SYNC_LOOKBACK_HOURS

