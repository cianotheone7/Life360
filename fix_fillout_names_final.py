#!/usr/bin/env python3
"""
Fix Fillout names using the correct API structure
"""
from app import app, Order, db
import json

def fix_fillout_names_final():
    with app.app_context():
        fillout_orders = Order.query.filter(Order.fillout_submission_id.isnot(None)).all()
        
        print(f"Processing {len(fillout_orders)} Fillout orders...")
        
        for order in fillout_orders:
            if not order.raw_api_data:
                continue
                
            try:
                raw_data = json.loads(order.raw_api_data)
                questions = raw_data.get('questions', [])
                
                # Create responses dictionary using correct field names
                responses = {}
                for question in questions:
                    name = question.get('name', '')
                    value = question.get('value', '')
                    if name and value:
                        key = name.lower().replace(' ', '_')
                        responses[key] = value
                
                # Extract names from the API data
                full_name = responses.get('full_name', '')
                surname = responses.get('surname', '')
                
                print(f"\nOrder ID {order.id}:")
                print(f"  Raw Full Name: '{full_name}'")
                print(f"  Raw Surname: '{surname}'")
                
                # Format names properly
                if full_name:
                    first_name = full_name.title()
                    order.name = first_name
                    print(f"  Updated name: '{first_name}'")
                
                if surname:
                    formatted_surname = surname.title()
                    order.surname = formatted_surname
                    print(f"  Updated surname: '{formatted_surname}'")
                
                # Update customer_name with both names
                if full_name and surname:
                    order.customer_name = f"{full_name.title()} {surname.title()}"
                elif full_name:
                    order.customer_name = full_name.title()
                
                print(f"  Updated customer_name: '{order.customer_name}'")
                
            except Exception as e:
                print(f"Error processing order {order.id}: {e}")
        
        # Commit changes
        db.session.commit()
        print(f"\nSUCCESS: Updated Fillout order names")
        
        # Show final results
        print("\nFinal Fillout orders:")
        for order in fillout_orders:
            print(f"  - {order.customer_name} (Name: {order.name}, Surname: {order.surname})")

if __name__ == "__main__":
    fix_fillout_names_final()


