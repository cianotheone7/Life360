#!/usr/bin/env python3
"""
WooCommerce Configuration Settings
"""

# Sync Settings
SYNC_INTERVAL_SECONDS = 30  # How often to check for new orders
SYNC_LOOKBACK_HOURS = 1     # How far back to look for orders each sync (1 hour)
INITIAL_SYNC_DAYS = 3       # How many days to sync on first run

# API Settings
WOOCOMMERCE_CONFIG = {
    'base_url': 'https://geneway.co.za',
    'consumer_key': 'ck_ce467c6d4f0b3d980124440c6b28fb26faa06817',
    'consumer_secret': 'cs_05d08a784db62bd25f2346c8e02dd01ae8ba33de',
    'api_version': 'wc/v3',
    'timeout': 30  # API request timeout in seconds
}

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

