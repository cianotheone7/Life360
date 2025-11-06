#!/usr/bin/env python3
"""
Script to update opt_in_status to 'Opted In' for a list of people.
Matches by name and surname (case-insensitive, partial matching).
"""

import os
import sys

# Set Azure database connection
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

# Import models - this will use the app's database configuration
sys.path.insert(0, os.path.dirname(__file__))
from app import app, db, Order

# List of people to mark as "Opted In"
PEOPLE_TO_UPDATE = [
    "Reube Makgene",
    "Robin Peters",
    "Mduduzi Mathews Zitha",
    "Isaac Molatlhegi",
    "George Tshepo Modau",
    "Admire Shawn Madzivanyika",
    "Christine Kruger",
    "Matsiliso Makeki",
    "Sabelo Ndlovu",
    "Simonia Baadjies",
    "Adria.Daames",
    "Nhlanhla Thabethe",
    "Lumka Makamba",
    "Mosala Mokate",
    "Fanie",
    "Rian Loots",
    "Jose ulembe",
    "George Segone",
    "Sebenzile Gumede",
    "Ivy Maupa",
    "Keamogetsoe",
    "Kerishnie Cloete",
    "Helen Agenbag",
    "Jeanetta Grobler",
    "Busisiwe Mthimunye",
    "Brian Kgobe",
    "Relebogile Mashile",
    "Ettienne Bester",
    "Clyton Maravanyika",
    "Perumal Naidu",
    "Vile Pambani",
    "Promise Masango",
    "Corlia-An Erasmus",
]

def normalize_name(name):
    """Normalize name for matching (lowercase, strip extra spaces)"""
    return ' '.join(name.lower().split())

def match_order(order, search_name):
    """Check if order matches the search name"""
    order_full_name = ""
    if order.name:
        order_full_name += order.name.lower()
    if order.surname:
        order_full_name += " " + order.surname.lower()
    
    order_full_name = normalize_name(order_full_name)
    search_normalized = normalize_name(search_name.lower())
    
    # Check for exact match or if search name is contained in order name
    if search_normalized in order_full_name or order_full_name in search_normalized:
        return True
    
    # Also check individual parts
    search_parts = search_normalized.split()
    order_parts = order_full_name.split()
    
    # If all search parts are found in order (in any order)
    if len(search_parts) > 0:
        matches = 0
        for part in search_parts:
            if any(part in order_part or order_part in part for order_part in order_parts):
                matches += 1
        return matches >= min(len(search_parts), len(order_parts))
    
    return False

def update_opted_in_status():
    """Update opt_in_status for matching orders"""
    with app.app_context():
        updated_count = 0
        not_found = []
        
        for person_name in PEOPLE_TO_UPDATE:
            # Get all orders
            orders = Order.query.all()
            matched = False
            
            for order in orders:
                if match_order(order, person_name):
                    order.opt_in_status = "Opted In"
                    matched = True
                    updated_count += 1
                    print(f"[OK] Updated: {order.name} {order.surname} (Order #{order.id})")
            
            if not matched:
                not_found.append(person_name)
                print(f"[NOT FOUND] Could not find order for: {person_name}")
        
        db.session.commit()
        
        print(f"\n{'='*60}")
        print(f"Summary:")
        print(f"  Updated: {updated_count} orders")
        print(f"  Not found: {len(not_found)} people")
        if not_found:
            print(f"\n  People not found:")
            for name in not_found:
                print(f"    - {name}")
        print(f"{'='*60}")

if __name__ == "__main__":
    update_opted_in_status()

