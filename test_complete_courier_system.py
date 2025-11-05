#!/usr/bin/env python3
"""
Complete test of the courier booking system
Tests all validation and error handling
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, CourierBooking, Practitioner
from shiplogic_service import create_demo_booking
from datetime import datetime

def test_complete_courier_system():
    """Test the complete courier booking system with validation"""
    
    print("=== Complete Courier Booking System Test ===\n")
    
    with app.app_context():
        # 1. Test with missing required fields
        print("1. Testing validation with missing fields...")
        
        # Test missing collection address fields
        incomplete_booking = {
            'collection_address': {
                'type': 'residential',
                'company': '',
                'street_address': '',  # MISSING
                'local_area': 'Test Area',
                'city': 'Pretoria',
                'zone': 'Gauteng',
                'country': 'ZA',
                'code': '0001'
            },
            'collection_contact': {
                'name': 'Test Contact',
                'mobile_number': '0123456789',
                'email': 'test@example.com'
            },
            'delivery_address': {
                'type': 'residential',
                'company': '',
                'street_address': '123 Test Street',
                'local_area': 'Test Area',
                'city': 'Pretoria',
                'zone': 'Gauteng',
                'country': 'ZA',
                'code': '0001'
            },
            'delivery_contact': {
                'name': 'Test Recipient',
                'mobile_number': '0987654321',
                'email': 'recipient@example.com'
            },
            'parcels': [{
                'parcel_description': 'Test parcel',
                'submitted_length_cm': 30,
                'submitted_width_cm': 20,
                'submitted_height_cm': 10,
                'submitted_weight_kg': 1.0
            }],
            'service_level_code': 'ECO'
        }
        
        result = create_demo_booking(incomplete_booking)
        print(f"   Missing street_address: {result}")
        assert not result['success']
        assert 'Missing collection address field: street_address' in result['error']
        print("   ✅ Correctly caught missing street_address")
        
        # Test missing contact name
        incomplete_booking['collection_address']['street_address'] = '123 Test Street'
        incomplete_booking['collection_contact']['name'] = ''  # MISSING
        
        result = create_demo_booking(incomplete_booking)
        print(f"   Missing contact name: {result}")
        assert not result['success']
        assert 'Collection contact must have name and mobile_number' in result['error']
        print("   ✅ Correctly caught missing contact name")
        
        # Test missing mobile number
        incomplete_booking['collection_contact']['name'] = 'Test Contact'
        incomplete_booking['collection_contact']['mobile_number'] = ''  # MISSING
        
        result = create_demo_booking(incomplete_booking)
        print(f"   Missing mobile number: {result}")
        assert not result['success']
        assert 'Collection contact must have name and mobile_number' in result['error']
        print("   ✅ Correctly caught missing mobile number")
        
        # 2. Test with complete valid data
        print("\n2. Testing with complete valid data...")
        
        complete_booking = {
            'collection_address': {
                'type': 'residential',
                'company': 'Test Company',
                'street_address': '123 Collection Street',
                'local_area': 'Collection Area',
                'city': 'Pretoria',
                'zone': 'Gauteng',
                'country': 'ZA',
                'code': '0001'
            },
            'collection_contact': {
                'name': 'Collection Contact',
                'mobile_number': '0123456789',
                'email': 'collection@example.com'
            },
            'delivery_address': {
                'type': 'residential',
                'company': 'Delivery Company',
                'street_address': '456 Delivery Street',
                'local_area': 'Delivery Area',
                'city': 'Cape Town',
                'zone': 'Western Cape',
                'country': 'ZA',
                'code': '8000'
            },
            'delivery_contact': {
                'name': 'Delivery Recipient',
                'mobile_number': '0987654321',
                'email': 'delivery@example.com'
            },
            'parcels': [{
                'parcel_description': 'Medical supplies package',
                'submitted_length_cm': 30,
                'submitted_width_cm': 20,
                'submitted_height_cm': 10,
                'submitted_weight_kg': 1.5
            }],
            'special_instructions_collection': 'Please collect from reception',
            'special_instructions_delivery': 'Please deliver to reception',
            'declared_value': 0,
            'collection_min_date': '2025-01-24T00:00:00.000Z',
            'collection_after': '09:00',
            'collection_before': '17:00',
            'delivery_min_date': '2025-01-24T00:00:00.000Z',
            'delivery_after': '08:00',
            'delivery_before': '17:00',
            'custom_tracking_reference': 'TEST-REF-001',
            'customer_reference': 'ORDER-123',
            'service_level_code': 'ECO',
            'mute_notifications': False
        }
        
        result = create_demo_booking(complete_booking)
        print(f"   Complete booking result: {result}")
        assert result['success']
        assert 'booking_id' in result
        assert 'tracking_number' in result
        print("   ✅ Complete booking successful")
        
        # 3. Test database integration
        print("\n3. Testing database integration...")
        
        # Get or create a test practitioner
        practitioners = Practitioner.query.all()
        if not practitioners:
            test_practitioner = Practitioner(
                first_name="Test",
                last_name="Practitioner",
                email="test@example.com",
                phone="0123456789",
                provider="Test Provider"
            )
            db.session.add(test_practitioner)
            db.session.commit()
            practitioners = [test_practitioner]
        
        # Create a courier booking in the database
        courier_booking = CourierBooking(
            practitioner_id=practitioners[0].id,
            shiplogic_booking_id=result['booking_id'],
            tracking_number=result['tracking_number'],
            provider='courier_guy_geneway',
            pickup_address=f"{complete_booking['collection_address']['street_address']}, {complete_booking['collection_address']['local_area']}, {complete_booking['collection_address']['city']}",
            delivery_address=f"{complete_booking['delivery_address']['street_address']}, {complete_booking['delivery_address']['local_area']}, {complete_booking['delivery_address']['city']}",
            recipient_name=complete_booking['delivery_contact']['name'],
            recipient_phone=complete_booking['delivery_contact']['mobile_number'],
            package_description=complete_booking['parcels'][0]['parcel_description'],
            package_weight=complete_booking['parcels'][0]['submitted_weight_kg'],
            package_value=complete_booking['declared_value'],
            special_instructions=f"Collection: {complete_booking['special_instructions_collection']}. Delivery: {complete_booking['special_instructions_delivery']}",
            service_type=complete_booking['service_level_code'],
            service_cost=result['cost'],
            waybill_data='{"test": "data"}',
            waybill_generated=True,
            status='confirmed',
            estimated_delivery=datetime.fromisoformat(result['estimated_delivery'].replace('Z', '+00:00')),
            cost=result['cost']
        )
        
        db.session.add(courier_booking)
        db.session.commit()
        
        print(f"   ✅ Database booking created:")
        print(f"      - ID: {courier_booking.id}")
        print(f"      - Tracking: {courier_booking.tracking_number}")
        print(f"      - Recipient: {courier_booking.recipient_name}")
        print(f"      - Cost: R{courier_booking.cost}")
        
        # 4. Test field validation edge cases
        print("\n4. Testing edge cases...")
        
        # Test empty strings
        edge_case_booking = complete_booking.copy()
        edge_case_booking['collection_address']['street_address'] = '   '  # Only whitespace
        
        result = create_demo_booking(edge_case_booking)
        print(f"   Whitespace-only street address: {result}")
        assert not result['success']
        print("   ✅ Correctly caught whitespace-only field")
        
        # Test missing required top-level field
        edge_case_booking = complete_booking.copy()
        del edge_case_booking['service_level_code']  # Remove required field
        
        result = create_demo_booking(edge_case_booking)
        print(f"   Missing service_level_code: {result}")
        assert not result['success']
        assert 'Missing required field: service_level_code' in result['error']
        print("   ✅ Correctly caught missing top-level field")
        
        print("\n=== All Tests Passed! ===")
        print("✅ Field validation working correctly")
        print("✅ Error messages are specific and helpful")
        print("✅ Complete bookings work properly")
        print("✅ Database integration working")
        print("✅ Edge cases handled properly")
        
        return True

if __name__ == "__main__":
    success = test_complete_courier_system()
    if success:
        print("\n🎉 Complete courier booking system is working perfectly!")
        print("🔍 All validation and error handling is in place")
        print("📋 Users will get specific error messages for missing fields")
    else:
        print("\n❌ Tests failed! Check the errors above.")
