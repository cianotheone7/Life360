#!/usr/bin/env python3
"""
Fillout Integration for Life360 Dashboard
Pulls form submissions from Fillout and syncs them with the local database as orders
"""
import requests
import json
from datetime import datetime, timedelta
from app import app, db, Order
import logging

# Fillout API Configuration - Multiple Forms
FILLOUT_FORMS = {
    'umvuzo_intelligence': {
        'api_key': 'sk_prod_Obu52hFB7sNbd3J53yNKwHuxcIgRJcUzOJ8u6W1je2UYyMG8Xc0v0fWnAIypxhvezv9U1BpVltuirpQvgo3opmvTEnsSR4FnT1t_32425',
        'form_id': 'mtETEnSwyius',
        'provider_name': 'Umvuzo Intelligene'
    },
    'healthy_me': {
        'api_key': 'sk_prod_BpHnl0XBuJ6dvL55KzjZNGJ9QZzNBmdMiaPF5wpoGTYcan9UzCT85Ex6X6dnH5JtRXWoYTUEQ0EeLhkVj8qt66v72spdOuY5pdX_35176',
        'form_id': 'v2FcQMTq4Fus',  # Healthy Me form
        'provider_name': 'Healthy Me'
    }
}

FILLOUT_BASE_URL = 'https://api.fillout.com/v1/api'

# Default form to sync (only Healthy Me)
DEFAULT_FORMS_TO_SYNC = ['healthy_me']

class FilloutAPI:
    """Fillout REST API client"""
    
    def __init__(self, form_key='umvuzo_intelligence'):
        """
        Initialize Fillout API client
        
        Args:
            form_key: Key from FILLOUT_FORMS dict (default: 'umvuzo_intelligence')
        """
        form_config = FILLOUT_FORMS.get(form_key, FILLOUT_FORMS['umvuzo_intelligence'])
        self.api_key = form_config['api_key']
        self.base_url = FILLOUT_BASE_URL
        self.form_id = form_config['form_id']
        self.provider_name = form_config['provider_name']
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
    
    def get_form_submissions(self, limit=150, offset=0, after=None):
        """
        Get form submissions from Fillout
        
        Args:
            limit: Number of submissions to retrieve (max 150)
            offset: Number of submissions to skip
            after: ISO8601 date to get submissions after this date
        """
        url = f"{self.base_url}/forms/{self.form_id}/submissions"
        params = {
            'limit': limit,
            'offset': offset,
            'sort': 'desc'  # Sort by newest first
        }
        
        if after:
            params['after'] = after
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Fillout API error: {e}")
            return {'responses': []}
    
    def get_form_metadata(self):
        """Get form metadata to understand the form structure"""
        url = f"{self.base_url}/forms/{self.form_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Fillout API error getting form metadata: {e}")
            return None

def map_fillout_to_local_order(submission, provider_name='Umvuzo Intelligene'):
    """
    Map Fillout submission data to local Order model format
    
    Args:
        submission: Fillout submission data
        provider_name: Provider name to use for this order
    """
    import json
    
    # Store the complete raw API response
    raw_api_data = json.dumps(submission, indent=2, default=str)
    
    # Extract submission data
    submission_id = submission.get('submissionId', '')
    submission_time = submission.get('submissionTime', '')
    questions = submission.get('questions', [])
    
    # Create a dictionary of question responses for easy access
    responses = {}
    for question in questions:
        field_id = question.get('id', '')
        field_name = question.get('name', '')
        field_value = question.get('value', '')
        
        # Use field name if available, otherwise use field ID
        key = field_name if field_name else field_id
        responses[key.lower().replace(' ', '_')] = field_value
    
    # Extract common fields (adjust these based on your form structure)
    full_name = responses.get('full_name', '') or responses.get('name', '')
    surname = responses.get('surname', '') or responses.get('last_name', '')
    
    # Format names to proper case
    if full_name:
        full_name = full_name.title()
    if surname:
        surname = surname.title()
    
    # Create customer_name from full_name and surname
    if full_name and surname:
        customer_name = f"{full_name} {surname}"
    elif full_name:
        customer_name = full_name
    else:
        customer_name = 'Unknown Customer'
    
    customer_email = (
        responses.get('email', '') or 
        responses.get('email_address', '') or
        ''
    )
    
    customer_phone = (
        responses.get('phone', '') or 
        responses.get('phone_number', '') or
        responses.get('contact_number', '') or
        ''
    )
    
    # Try to extract service/product information
    service_requested = (
        responses.get('service', '') or
        responses.get('product', '') or
        responses.get('service_requested', '') or
        responses.get('inquiry_type', '') or
        'General Inquiry'
    )
    
    # Try to extract message/notes
    message = (
        responses.get('message', '') or
        responses.get('comments', '') or
        responses.get('additional_information', '') or
        responses.get('details', '') or
        ''
    )
    
    # Parse submission time
    try:
        if submission_time:
            order_date = datetime.fromisoformat(submission_time.replace('Z', '+00:00'))
        else:
            order_date = datetime.utcnow()
    except:
        order_date = datetime.utcnow()
    
    # Create comprehensive notes with all form data
    all_responses = []
    for question in questions:
        field_name = question.get('name', question.get('id', 'Unknown Field'))
        field_value = question.get('value', '')
        if field_value:
            all_responses.append(f"{field_name}: {field_value}")
    
    comprehensive_notes = "\n".join(all_responses)
    if message and message not in comprehensive_notes:
        comprehensive_notes += f"\n\nMessage: {message}"
    
    return {
        'provider': provider_name,
        'name': full_name or 'Unknown',
        'surname': surname or '',
        'customer_name': customer_name,
        'customer_email': customer_email,
        'customer_phone': customer_phone,
        'items_description': service_requested,
        'notes': comprehensive_notes,
        'status': 'Pending',  # All new submissions start as Pending
        'ordered_at': order_date,
        'order_date': order_date,
        'fillout_submission_id': submission_id,  # Store original submission ID
        'total_amount': 0.0,  # Forms typically don't have amounts
        'payment_method': 'Form Submission',
        'address': responses.get('address', '') or responses.get('location', '') or '',
        'raw_api_data': raw_api_data  # Store complete API response
    }

def sync_fillout_submissions(hours_back=24, form_keys=None):
    """
    Sync Fillout submissions to local database as orders
    
    Args:
        hours_back: Number of hours back to sync submissions (default: 24)
        form_keys: List of form keys to sync. If None, syncs only DEFAULT_FORMS_TO_SYNC
    """
    if form_keys is None:
        form_keys = DEFAULT_FORMS_TO_SYNC
    elif isinstance(form_keys, str):
        form_keys = [form_keys]
    
    with app.app_context():
        total_all_synced = 0
        total_all_new = 0
        total_all_updated = 0
        
        for form_key in form_keys:
            if form_key not in FILLOUT_FORMS:
                print(f"Unknown form key: {form_key}")
                continue
            
            form_config = FILLOUT_FORMS[form_key]
            fillout_api = FilloutAPI(form_key)
            provider_name = form_config['provider_name']
            
            # Calculate date to sync from
            sync_from = datetime.utcnow() - timedelta(hours=hours_back)
            sync_from_iso = sync_from.isoformat() + 'Z'
            
            print(f"\nSyncing {provider_name} from {sync_from.strftime('%Y-%m-%d %H:%M:%S')}")
            
            try:
                # Get form metadata first
                form_metadata = fillout_api.get_form_metadata()
                if form_metadata:
                    print(f"Form: {form_metadata.get('name', 'Unknown Form')}")
                
                # Get only the last 3 submissions from Fillout
                offset = 0
                limit = 3  # Only get the last 3 submissions
                total_synced = 0
                total_updated = 0
                total_new = 0
                
                print(f"Fetching last {limit} submissions...")
                response = fillout_api.get_form_submissions(
                    limit=limit,
                    offset=offset
                )
                
                submissions = response.get('responses', [])
                if submissions:
                    
                    for submission in submissions:
                        try:
                            # Map Fillout submission to local format
                            order_data = map_fillout_to_local_order(submission, provider_name)
                            
                            # Check if submission already exists (by Fillout submission ID)
                            existing_order = Order.query.filter_by(
                                fillout_submission_id=order_data['fillout_submission_id']
                            ).first()
                            
                            if existing_order:
                                # Skip existing submissions - only want new ones
                                print(f"Skipped existing submission #{order_data['fillout_submission_id']}")
                                continue
                            else:
                                # Create new order
                                new_order = Order(**order_data)
                                db.session.add(new_order)
                                total_new += 1
                                print(f"Added new submission #{order_data['fillout_submission_id']} - {order_data['customer_name']}")
                            
                            total_synced += 1
                            
                        except Exception as e:
                            print(f"Error processing submission #{submission.get('submissionId', 'unknown')}: {e}")
                            continue
                
                # Commit changes for this form
                db.session.commit()
                
                print(f"{provider_name} sync completed: {total_synced} processed, {total_new} new, {total_updated} updated")
                total_all_synced += total_synced
                total_all_new += total_new
                total_all_updated += total_updated
                
            except Exception as e:
                db.session.rollback()
                print(f"{provider_name} sync failed: {e}")
                continue
        
        # Final summary
        print(f"\nAll forms sync completed!")
        print(f"   Total processed: {total_all_synced}")
        print(f"   New submissions: {total_all_new}")
        print(f"   Updated submissions: {total_all_updated}")
        
        return {
            'success': True,
            'total_synced': total_all_synced,
            'new_orders': total_all_new,
            'updated_orders': total_all_updated
        }

def test_fillout_connection():
    """Test Fillout API connection"""
    print("Testing Fillout API connection...")
    
    fillout_api = FilloutAPI()
    
    try:
        # Try to get form metadata first
        form_metadata = fillout_api.get_form_metadata()
        
        if form_metadata:
            print("Connection successful!")
            print(f"   Form name: {form_metadata.get('name', 'Unknown')}")
            print(f"   Form ID: {form_metadata.get('id', 'Unknown')}")
            
            # Try to get submissions
            submissions = fillout_api.get_form_submissions(limit=1)
            submission_count = len(submissions.get('responses', []))
            print(f"   Recent submissions found: {submission_count}")
            
            if submission_count > 0:
                latest = submissions['responses'][0]
                print(f"   Latest submission: {latest.get('submissionId', 'Unknown')} at {latest.get('submissionTime', 'Unknown time')}")
            
            return True
        else:
            print("Failed to get form metadata")
            return False
            
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

if __name__ == "__main__":
    print("Fillout Integration for Life360 Dashboard")
    print("=" * 50)
    
    # Test connection first
    if test_fillout_connection():
        print("\n" + "=" * 50)
        
        # Ask user what to do
        print("Options:")
        print("1. Sync last 24 hours of submissions")
        print("2. Sync last 7 days of submissions") 
        print("3. Sync all submissions (be careful - might be a lot!)")
        
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice == "1":
            sync_fillout_submissions(hours_back=24)
        elif choice == "2":
            sync_fillout_submissions(hours_back=24*7)
        elif choice == "3":
            # For all submissions, we'll sync last 30 days
            sync_fillout_submissions(hours_back=24*30)
        else:
            print("Invalid choice")
    else:
        print("\nCannot proceed - fix connection issues first")
