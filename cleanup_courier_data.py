#!/usr/bin/env python3
"""
Script to clean up dummy/test courier booking data
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, CourierBooking, Practitioner
from datetime import datetime

def cleanup_dummy_courier_data():
    """Remove dummy/test courier bookings"""
    
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
            print()
        
        # Ask for confirmation
        response = input("Do you want to delete ALL courier bookings? (yes/no): ")
        
        if response.lower() == 'yes':
            # Delete all courier bookings
            deleted_count = CourierBooking.query.delete()
            db.session.commit()
            
            print(f"✅ Deleted {deleted_count} courier bookings")
        else:
            print("❌ Operation cancelled")

if __name__ == "__main__":
    cleanup_dummy_courier_data()
