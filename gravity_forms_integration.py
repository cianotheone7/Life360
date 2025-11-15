#!/usr/bin/env python3
"""
Gravity Forms Integration for Life360 Dashboard
Pulls form submissions from Gravity Forms and syncs them with practitioners database
"""
import requests
import json
import hmac
import hashlib
import time
from datetime import datetime, timedelta
from app import app, db, Practitioner
import logging

# Gravity Forms API Configuration - Multiple Providers
GRAVITY_FORMS_PROVIDERS = {
    'geneway': {
        'base_url': 'https://geneway.co.za',
        'consumer_key': 'ck_6443cd021e6323df9b9048bd872c812fe75a19f0',
        'consumer_secret': 'cs_ef87bc5c99d660390fbf46efeb9e84b2e4b31eb1',
        'provider_name': 'Geneway',
        'target_forms': ['Applicant Information (Multistep)']  # Only sync this form
    },
    'optiway': {
        'base_url': 'https://optiway.co.za',
        'consumer_key': 'ck_8ac5d2f0e5df3005db1d5a9ec00613b8e56390fb',
        'consumer_secret': 'cs_effb53c5943679175f42d9244c1fdbe31b670d40',
        'provider_name': 'Optiway',
        'target_forms': ['PRACTITIONER INFORMATION']  # Only sync this form
    }
}

# Forms to sync (sync both providers by default)
DEFAULT_PROVIDERS_TO_SYNC = ['geneway', 'optiway']

class GravityFormsAPI:
    """Gravity Forms REST API client - supports both v1 and v2"""
    
    def __init__(self, provider_key='geneway'):
        """
        Initialize Gravity Forms API client
        
        Args:
            provider_key: Key from GRAVITY_FORMS_PROVIDERS dict
        """
        provider_config = GRAVITY_FORMS_PROVIDERS.get(provider_key, GRAVITY_FORMS_PROVIDERS['geneway'])
        self.base_url = provider_config['base_url']
        self.provider_name = provider_config['provider_name']
        
        # Check which API version to use based on credentials provided
        if 'consumer_key' in provider_config:
            # REST API v2 - uses WooCommerce-style Basic Auth
            self.api_version = 'v2'
            self.consumer_key = provider_config['consumer_key']
            self.consumer_secret = provider_config['consumer_secret']
            self.auth = (self.consumer_key, self.consumer_secret)
            self.api_base = f"{self.base_url}/wp-json/gf/v2"
        else:
            # Web API v1 - uses signature-based auth
            self.api_version = 'v1'
            self.api_key = provider_config['api_key']
            self.api_secret = provider_config['api_secret']
            self.api_base = f"{self.base_url}/gravityformsapi"
    
    def _generate_signature(self, string_to_sign, private_key):
        """Generate HMAC signature for Gravity Forms API v1"""
        hash_obj = hmac.new(
            private_key.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha1
        )
        return hash_obj.hexdigest()
    
    def _get_auth_params(self, route):
        """Get authentication parameters for Gravity Forms API v1"""
        expires = int(time.time()) + 3600  # 1 hour from now
        string_to_sign = f"{self.api_key}:{route}:{expires}"
        signature = self._generate_signature(string_to_sign, self.api_secret)
        
        return {
            'api_key': self.api_key,
            'signature': signature,
            'expires': expires
        }
    
    def get_forms(self):
        """Get all forms"""
        if self.api_version == 'v2':
            # REST API v2
            url = f"{self.api_base}/forms"
            try:
                response = requests.get(url, auth=self.auth, timeout=30)
                response.raise_for_status()
                data = response.json()
                # v2 returns dict with form IDs as keys, convert to list
                if isinstance(data, dict):
                    return list(data.values())
                return data
            except requests.exceptions.RequestException as e:
                logging.error(f"Gravity Forms API v2 error getting forms: {e}")
                return []
        else:
            # Web API v1
            route = 'forms'
            url = f"{self.api_base}/{route}"
            params = self._get_auth_params(route)
            
            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                return data.get('response', []) if isinstance(data, dict) else data
            except requests.exceptions.RequestException as e:
                logging.error(f"Gravity Forms API v1 error getting forms: {e}")
                return []
    
    def get_form_entries(self, form_id, page=1, page_size=20, search_criteria=None):
        """
        Get entries for a specific form
        
        Args:
            form_id: The form ID
            page: Page number (default: 1)
            page_size: Number of entries per page (default: 20)
            search_criteria: Optional search criteria dict
        """
        if self.api_version == 'v2':
            # REST API v2
            url = f"{self.api_base}/forms/{form_id}/entries"
            params = {
                'per_page': page_size,
                'page': page
            }
            
            if search_criteria:
                params['search'] = json.dumps(search_criteria)
            
            try:
                response = requests.get(url, auth=self.auth, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                # v2 returns dict with entry IDs as keys, convert to list
                if isinstance(data, dict) and 'entries' in data:
                    return data['entries']
                elif isinstance(data, dict):
                    return list(data.values())
                return data if isinstance(data, list) else []
            except requests.exceptions.RequestException as e:
                logging.error(f"Gravity Forms API v2 error getting entries: {e}")
                return []
        else:
            # Web API v1
            route = f'forms/{form_id}/entries'
            url = f"{self.api_base}/{route}"
            params = self._get_auth_params(route)
            
            params['paging[page_size]'] = str(page_size)
            params['paging[current_page]'] = str(page)
            
            if search_criteria:
                params['search'] = json.dumps(search_criteria)
            
            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                return data.get('response', {}).get('entries', []) if isinstance(data, dict) else data
            except requests.exceptions.RequestException as e:
                logging.error(f"Gravity Forms API v1 error getting entries: {e}")
                return []

def map_gravity_form_to_practitioner(entry, provider_name):
    """
    Map Gravity Forms entry to Practitioner model format
    
    Args:
        entry: Gravity Forms entry data
        provider_name: Provider name (Geneway, Optiway, etc.)
    """
    # Gravity Forms stores data in numbered fields
    # We'll need to extract common practitioner fields
    # Field IDs may vary - this is a generic mapping
    
    # Try to extract name from common field patterns
    first_name = (entry.get('1.3') or entry.get('1') or entry.get('first_name') or '').strip()
    last_name = (entry.get('1.6') or entry.get('2') or entry.get('last_name') or '').strip()
    
    # Try title
    title = (entry.get('title') or entry.get('3') or '').strip()
    
    # Email - usually field 3 or 4
    email = (entry.get('3') or entry.get('4') or entry.get('email') or '').strip()
    
    # Phone - usually field 4 or 5
    phone = (entry.get('4') or entry.get('5') or entry.get('phone') or '').strip()
    
    # Notes - collect all other fields
    notes_parts = []
    for key, value in entry.items():
        if key not in ['id', 'form_id', 'date_created', 'is_starred', 'is_read', 'ip', 'source_url', 'user_agent']:
            if value and str(value).strip():
                notes_parts.append(f"{key}: {value}")
    
    notes = "\n".join(notes_parts) if notes_parts else ""
    
    return {
        'provider': provider_name,
        'title': title or 'Dr',
        'first_name': first_name or 'Unknown',
        'last_name': last_name or 'Practitioner',
        'email': email,
        'phone': phone,
        'notes': notes,
        'gravity_form_entry_id': entry.get('id'),  # Store original entry ID
        'created_at': datetime.utcnow()
    }

def sync_gravity_forms_practitioners(hours_back=24, provider_keys=None):
    """
    Sync Gravity Forms entries to practitioners database
    
    Args:
        hours_back: Number of hours back to sync entries (default: 24)
        provider_keys: List of provider keys to sync. If None, syncs DEFAULT_PROVIDERS_TO_SYNC
    """
    if provider_keys is None:
        provider_keys = DEFAULT_PROVIDERS_TO_SYNC
    elif isinstance(provider_keys, str):
        provider_keys = [provider_keys]
    
    with app.app_context():
        total_all_synced = 0
        total_all_new = 0
        
        for provider_key in provider_keys:
            if provider_key not in GRAVITY_FORMS_PROVIDERS:
                print(f"Unknown provider key: {provider_key}")
                continue
            
            provider_config = GRAVITY_FORMS_PROVIDERS[provider_key]
            gf_api = GravityFormsAPI(provider_key)
            provider_name = provider_config['provider_name']
            
            print(f"\nSyncing {provider_name} Gravity Forms practitioners...")
            
            try:
                # Get all forms
                forms = gf_api.get_forms()
                
                if not forms:
                    print(f"{provider_name}: No forms found")
                    continue
                
                total_synced = 0
                total_new = 0
                
                # Get target forms for this provider
                target_forms = provider_config.get('target_forms', [])
                
                # Sync entries from each form
                for form in forms:
                    form_id = form.get('id')
                    form_title = form.get('title', 'Unknown Form')
                    
                    # Skip if not in target forms list (if target forms are specified)
                    if target_forms and form_title not in target_forms:
                        print(f"  Skipping form: {form_title} (not in target list)")
                        continue
                    
                    print(f"  Form: {form_title} (ID: {form_id})")
                    
                    # Get recent entries (last 3 to avoid overload)
                    entries = gf_api.get_form_entries(form_id, page_size=3)
                    
                    for entry in entries:
                        try:
                            # Map entry to practitioner format
                            practitioner_data = map_gravity_form_to_practitioner(entry, provider_name)
                            
                            # Check if practitioner already exists by email or name
                            existing_practitioner = None
                            if practitioner_data.get('email'):
                                existing_practitioner = Practitioner.query.filter_by(
                                    email=practitioner_data['email']
                                ).first()
                            
                            if not existing_practitioner and practitioner_data.get('first_name') and practitioner_data.get('last_name'):
                                existing_practitioner = Practitioner.query.filter_by(
                                    first_name=practitioner_data['first_name'],
                                    last_name=practitioner_data['last_name'],
                                    provider=practitioner_data['provider']
                                ).first()
                            
                            if existing_practitioner:
                                # Skip existing practitioners - only want new ones
                                print(f"    Skipped existing: {practitioner_data['first_name']} {practitioner_data['last_name']}")
                                continue
                            else:
                                # Create new practitioner
                                # Remove gravity_form_entry_id as it's not in the model
                                entry_id = practitioner_data.pop('gravity_form_entry_id', None)
                                if entry_id:
                                    # Add to notes
                                    practitioner_data['notes'] = f"Gravity Form Entry #{entry_id}\n" + (practitioner_data.get('notes') or '')
                                
                                new_practitioner = Practitioner(**practitioner_data)
                                db.session.add(new_practitioner)
                                total_new += 1
                                print(f"    ✓ Added: {practitioner_data['first_name']} {practitioner_data['last_name']}")
                            
                            total_synced += 1
                            
                        except Exception as e:
                            print(f"    Error processing entry #{entry.get('id', 'unknown')}: {e}")
                            continue
                
                # Commit changes for this provider
                db.session.commit()
                
                print(f"{provider_name} sync completed: {total_synced} processed, {total_new} new")
                total_all_synced += total_synced
                total_all_new += total_new
                
            except Exception as e:
                db.session.rollback()
                print(f"{provider_name} sync failed: {e}")
                continue
        
        # Final summary
        print(f"\nAll Gravity Forms sync completed!")
        print(f"   Total processed: {total_all_synced}")
        print(f"   New practitioners: {total_all_new}")
        
        return {
            'success': True,
            'total_synced': total_all_synced,
            'new_practitioners': total_all_new
        }

if __name__ == "__main__":
    print("Gravity Forms Integration for Life360 Dashboard")
    print("=" * 50)
    
    # Test sync
    result = sync_gravity_forms_practitioners(hours_back=24)
    print(f"\nSync result: {result}")
