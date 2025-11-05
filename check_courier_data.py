#!/usr/bin/env python3
"""
Script to check courier booking data
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, CourierBooking

def check_courier_data():
    """Check what courier bookings exist"""
    
    with app.app_context():
        # Find all courier bookings
        all_bookings = CourierBooking.query.all()
        
        print(f"Found {len(all_bookings)} courier bookings:")
        
        for booking in all_bookings:
            print(f"- ID: {booking.id}")
            print(f"  Tracking: {booking.tracking_number}")
            print(f"  Recipient: {booking.recipient_name}")
            print(f"  Cost: R{booking.cost}")
            print(f"  Created: {booking.created_at}")
            print(f"  Provider: {booking.provider}")
            print(f"  Status: {booking.status}")
            print()

if __name__ == "__main__":
    check_courier_data()
