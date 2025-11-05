import requests
import json
from datetime import datetime
import os
from typing import Dict, List, Optional

class ShiplogicService:
    """Service for integrating with multiple courier providers"""
    
    def __init__(self, provider='courier_guy_geneway'):
        self.provider = provider
        self.base_url = self._get_base_url()
        self.api_key = self._get_api_key()
        self.username = self._get_username()
        self.password = self._get_password()
        self.token = None
        self.headers = {
            'Content-Type': 'application/json'
        }
        # Authenticate to get token
        self._authenticate()
    
    def _get_base_url(self):
        """Get base URL based on provider"""
        # Using sandbox environment for testing
        urls = {
            'courier_guy_geneway': "https://api.shiplogic.com/v2",
            'courier_guy_healthy_me': "https://api.shiplogic.com/v2",
            'courier_guy_intelligene': "https://api.shiplogic.com/v2",
            'mds_geneway': "https://api.shiplogic.com/v2"  # Using same API for now
        }
        return urls.get(self.provider, "https://api.shiplogic.com/v2")
    
    def _get_api_key(self):
        """Get API key based on provider"""
        keys = {
            'courier_guy_geneway': '8caa9eed853a49f789b94d2ecb514fc5',  # Hardcoded for now
            'courier_guy_healthy_me': os.getenv('COURIER_GUY_HEALTHY_ME_API_KEY'),
            'courier_guy_intelligene': os.getenv('COURIER_GUY_INTELLIGENE_API_KEY'),
            'mds_geneway': os.getenv('MDS_GENEWAY_API_KEY')
        }
        return keys.get(self.provider)
    
    def _get_username(self):
        """Get username based on provider"""
        usernames = {
            'courier_guy_geneway': 'ciano@geneway.co.za',  # Hardcoded for now
            'courier_guy_healthy_me': os.getenv('COURIER_GUY_HEALTHY_ME_USERNAME'),
            'courier_guy_intelligene': os.getenv('COURIER_GUY_INTELLIGENE_USERNAME'),
            'mds_geneway': os.getenv('MDS_GENEWAY_USERNAME')
        }
        return usernames.get(self.provider)
    
    def _get_password(self):
        """Get password based on provider"""
        passwords = {
            'courier_guy_geneway': 'Cherician@7',  # Hardcoded for now
            'courier_guy_healthy_me': os.getenv('COURIER_GUY_HEALTHY_ME_PASSWORD'),
            'courier_guy_intelligene': os.getenv('COURIER_GUY_INTELLIGENE_PASSWORD'),
            'mds_geneway': os.getenv('MDS_GENEWAY_PASSWORD')
        }
        return passwords.get(self.provider)
    
    def _authenticate(self):
        """Authenticate with Shiplogic API to get token"""
        try:
            if not self.username or not self.password:
                print(f"Warning: No credentials for provider {self.provider}")
                return
            
            # Try different authentication endpoints
            auth_endpoints = [
                '/auth/login',
                '/login',
                '/authenticate',
                '/token'
            ]
            
            auth_payload = {
                'username': self.username,
                'password': self.password
            }
            
            for endpoint in auth_endpoints:
                try:
                    response = requests.post(
                        f"{self.base_url}{endpoint}",
                        headers=self.headers,
                        json=auth_payload,
                        timeout=30
                    )
                    
                    print(f"Trying {endpoint}: {response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        self.token = data.get('token') or data.get('access_token') or data.get('auth_token')
                        if self.token:
                            self.headers['Authorization'] = f'Bearer {self.token}'
                            print(f"Successfully authenticated with {self.provider} using {endpoint}")
                            return
                        else:
                            print(f"Authentication response: {data}")
                    else:
                        print(f"Authentication failed at {endpoint}: {response.status_code} - {response.text[:100]}")
                        
                except Exception as e:
                    print(f"Error trying {endpoint}: {e}")
                    continue
            
            # If no authentication endpoint works, try using API key directly
            if self.api_key:
                self.headers['Authorization'] = f'Bearer {self.api_key}'
                print(f"Using API key directly for {self.provider}")
                
        except Exception as e:
            print(f"Authentication error: {e}")
    
    def _parse_address(self, address_string: str) -> Dict:
        """
        Parse address string into Shiplogic format
        Based on Postman collection address structure
        """
        print(f"Parsing address: {address_string}")
        
        # Clean the address string
        address_string = address_string.strip()
        
        # Handle different address formats
        if ',' in address_string:
            parts = [part.strip() for part in address_string.split(',')]
        else:
            # If no commas, try to split by common separators
            parts = [part.strip() for part in address_string.replace(';', ',').split(',')]
        
        # Default values for South Africa
        default_city = 'Pretoria'
        default_zone = 'Gauteng'
        default_country = 'ZA'
        default_code = '0001'
        
        if len(parts) >= 4:
            # Full address with all components
            return {
                'type': 'business',
                'company': parts[0] or 'Unknown Company',
                'street_address': parts[1] or 'Unknown Street',
                'local_area': parts[2] or 'Unknown Area',
                'city': parts[3] or default_city,
                'zone': parts[4] if len(parts) > 4 else default_zone,
                'country': default_country,
                'code': parts[5] if len(parts) > 5 else default_code
            }
        elif len(parts) == 3:
            # Address with company, street, area
            return {
                'type': 'business',
                'company': parts[0] or 'Unknown Company',
                'street_address': parts[1] or 'Unknown Street',
                'local_area': parts[2] or 'Unknown Area',
                'city': default_city,
                'zone': default_zone,
                'country': default_country,
                'code': default_code
            }
        elif len(parts) == 2:
            # Address with company and street
            return {
                'type': 'business',
                'company': parts[0] or 'Unknown Company',
                'street_address': parts[1] or 'Unknown Street',
                'local_area': 'Unknown Area',
                'city': default_city,
                'zone': default_zone,
                'country': default_country,
                'code': default_code
            }
        else:
            # Single part address
            return {
                'type': 'business',
                'company': 'Unknown Company',
                'street_address': address_string or 'Unknown Street',
                'local_area': 'Unknown Area',
                'city': default_city,
                'zone': default_zone,
                'country': default_country,
                'code': default_code
            }
    
    def create_courier_booking(self, booking_data: Dict) -> Dict:
        """
        Create a new courier booking
        Based on Postman collection: POST /v2/shipments
        
        Args:
            booking_data: Dictionary containing booking details in Shiplogic API format
        
        Returns:
            Dict containing booking response or error
        """
        try:
            # Validate required fields based on Shiplogic API requirements
            required_fields = [
                'collection_address', 'collection_contact', 'delivery_address', 
                'delivery_contact', 'parcels', 'service_level_code'
            ]
            
            for field in required_fields:
                if field not in booking_data:
                    return {
                        'success': False,
                        'error': f'Missing required field: {field}'
                    }
            
            # Validate nested required fields
            collection_addr = booking_data['collection_address']
            delivery_addr = booking_data['delivery_address']
            collection_contact = booking_data['collection_contact']
            delivery_contact = booking_data['delivery_contact']
            
            # Check address fields
            address_fields = ['street_address', 'local_area', 'city', 'zone', 'code']
            for field in address_fields:
                if field not in collection_addr or not collection_addr[field] or not collection_addr[field].strip():
                    return {
                        'success': False,
                        'error': f'Missing collection address field: {field}'
                    }
                if field not in delivery_addr or not delivery_addr[field] or not delivery_addr[field].strip():
                    return {
                        'success': False,
                        'error': f'Missing delivery address field: {field}'
                    }
            
            # Check contact fields
            if not collection_contact.get('name') or not collection_contact.get('mobile_number'):
                return {
                    'success': False,
                    'error': 'Collection contact must have name and mobile_number'
                }
            
            if not delivery_contact.get('name') or not delivery_contact.get('mobile_number'):
                return {
                    'success': False,
                    'error': 'Delivery contact must have name and mobile_number'
                }
            
            # Use the booking data directly as it's already in the correct format
            payload = booking_data
            
            # Make API request
            response = requests.post(
                f"{self.base_url}/shipments",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'booking_id': data.get('id'),
                    'tracking_number': data.get('short_tracking_reference'),
                    'estimated_delivery': data.get('estimated_delivery_from'),
                    'cost': data.get('rate'),
                    'data': data
                }
            else:
                return {
                    'success': False,
                    'error': f'API Error: {response.status_code} - {response.text}'
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }
    
    def get_booking_status(self, tracking_reference: str) -> Dict:
        """
        Get the status of a courier booking
        Based on Postman collection: GET /v2/tracking/shipments
        
        Args:
            tracking_reference: The tracking reference to check
            
        Returns:
            Dict containing status information
        """
        try:
            response = requests.get(
                f"{self.base_url}/tracking/shipments",
                headers=self.headers,
                params={'tracking_reference': tracking_reference},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'status': data.get('status'),
                    'tracking_number': data.get('short_tracking_reference'),
                    'current_location': data.get('current_branch_name'),
                    'estimated_delivery': data.get('estimated_delivery_from'),
                    'updates': data.get('tracking_events', []),
                    'data': data
                }
            else:
                return {
                    'success': False,
                    'error': f'API Error: {response.status_code} - {response.text}'
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }
    
    def cancel_booking(self, tracking_reference: str) -> Dict:
        """
        Cancel a courier booking
        Based on Postman collection: POST /v2/shipments/cancel
        
        Args:
            tracking_reference: The tracking reference to cancel
            
        Returns:
            Dict containing cancellation result
        """
        try:
            payload = {'tracking_reference': tracking_reference}
            
            response = requests.post(
                f"{self.base_url}/shipments/cancel",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'message': 'Booking cancelled successfully',
                    'data': response.json()
                }
            else:
                return {
                    'success': False,
                    'error': f'API Error: {response.status_code} - {response.text}'
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }
    
    def get_service_pricing(self, pickup_address: str, delivery_address: str, 
                           parcel_weight: float = 1.0, parcel_length: float = 0, 
                           parcel_width: float = 0, parcel_height: float = 0,
                           parcel_type: str = None, service_type: str = None) -> Dict:
        """
        Get pricing for different service types from Shiplogic API
        Based on Postman collection: POST /v2/rates
        
        Args:
            pickup_address: Collection address
            delivery_address: Delivery address
            parcel_weight: Weight in kg
            parcel_length: Length in cm
            parcel_width: Width in cm
            parcel_height: Height in cm
            parcel_type: Parcel type (standard-flyer, stock-1, stock-2, etc.)
            service_type: Specific service type (LOF, LSF, LOX, LSE, SDX)
            
        Returns:
            Dict containing pricing information for all services or specific service
        """
        try:
            # Parse addresses into proper format
            collection_addr = self._parse_address(pickup_address)
            delivery_addr = self._parse_address(delivery_address)
            
            print(f"Collection address parsed: {collection_addr}")
            print(f"Delivery address parsed: {delivery_addr}")
            
            payload = {
                'collection_address': collection_addr,
                'delivery_address': delivery_addr,
                'parcels': [{
                    'submitted_length_cm': parcel_length,
                    'submitted_width_cm': parcel_width,
                    'submitted_height_cm': parcel_height,
                    'submitted_weight_kg': parcel_weight
                }],
                'declared_value': 0,
                'collection_min_date': datetime.now().strftime('%Y-%m-%d'),
                'delivery_min_date': datetime.now().strftime('%Y-%m-%d')
            }
            
            response = requests.post(
                f"{self.base_url}/rates",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            print(f"Rates API Response: {response.status_code}")
            print(f"Response Headers: {dict(response.headers)}")
            print(f"Request Payload: {payload}")
            print(f"Response Text: {response.text[:500]}...")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"Parsed JSON: {data}")
                    
                    # Convert Shiplogic response to our format
                    services = []
                    pricing = {}
                    
                    if 'rates' in data:
                        for rate_item in data['rates']:
                            service_level = rate_item.get('service_level', {})
                            service_name = service_level.get('name', 'Unknown Service')
                            service_code = service_level.get('code', 'UNK')
                            service_price = rate_item.get('rate', 0)
                            service_description = service_level.get('description', '')
                            
                            services.append({
                                'name': service_name,
                                'code': service_code,
                                'price': service_price,
                                'description': service_description,
                                'delivery_date_from': service_level.get('delivery_date_from', ''),
                                'delivery_date_to': service_level.get('delivery_date_to', ''),
                                'collection_cut_off_time': service_level.get('collection_cut_off_time', '')
                            })
                            pricing[service_code] = service_price
                    
                    if services:
                        return {
                            'success': True,
                            'services': services,
                            'pricing': pricing,
                            'data': data # Raw data for debugging
                        }
                    else:
                        print("No services found in response")
                        return {
                            'success': False,
                            'error': 'No services available for this route',
                            'services': [],
                            'pricing': {},
                            'data': data
                        }
                except json.JSONDecodeError as e:
                    return {
                        'success': False,
                        'error': f'Invalid JSON response: {e}'
                    }
            else:
                return {
                    'success': False,
                    'error': f'API Error: {response.status_code} - {response.text}'
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }
    
    def get_service_areas(self) -> Dict:
        """
        Get available service areas and pricing
        
        Returns:
            Dict containing service areas and pricing information
        """
        try:
            response = requests.get(
                f"{self.base_url}/service-areas",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'areas': response.json().get('areas', []),
                    'pricing': response.json().get('pricing', {}),
                    'data': response.json()
                }
            else:
                return {
                    'success': False,
                    'error': f'API Error: {response.status_code} - {response.text}'
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }

# Demo mode for testing without API key
def create_demo_booking(booking_data: Dict) -> Dict:
    """Create a demo booking for testing purposes"""
    # Validate the booking data format first
    required_fields = [
        'collection_address', 'collection_contact', 'delivery_address', 
        'delivery_contact', 'parcels', 'service_level_code'
    ]
    
    for field in required_fields:
        if field not in booking_data:
            return {
                'success': False,
                'error': f'Missing required field: {field}'
            }
    
    # Check if address fields are present
    collection_addr = booking_data['collection_address']
    delivery_addr = booking_data['delivery_address']
    
    address_fields = ['street_address', 'local_area', 'city', 'zone', 'code']
    for field in address_fields:
        if field not in collection_addr or not collection_addr[field] or not collection_addr[field].strip():
            return {
                'success': False,
                'error': f'Missing collection address field: {field}'
            }
        if field not in delivery_addr or not delivery_addr[field] or not delivery_addr[field].strip():
            return {
                'success': False,
                'error': f'Missing delivery address field: {field}'
            }
    
    # Check contact fields
    collection_contact = booking_data['collection_contact']
    delivery_contact = booking_data['delivery_contact']
    
    if not collection_contact.get('name') or not collection_contact.get('mobile_number'):
        return {
            'success': False,
            'error': 'Collection contact must have name and mobile_number'
        }
    
    if not delivery_contact.get('name') or not delivery_contact.get('mobile_number'):
        return {
            'success': False,
            'error': 'Delivery contact must have name and mobile_number'
        }
    
    # If all validations pass, create demo booking
    return {
        'success': True,
        'booking_id': f"DEMO_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        'tracking_number': f"TRK{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'estimated_delivery': (datetime.now().replace(hour=17, minute=0, second=0, microsecond=0)).isoformat(),
        'cost': 105.75,
        'data': {
            'status': 'confirmed',
            'pickup_time': (datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)).isoformat(),
            'delivery_time': (datetime.now().replace(hour=17, minute=0, second=0, microsecond=0)).isoformat()
        }
    }

def get_demo_pricing(pickup_address: str, delivery_address: str, 
                    parcel_weight: float = 1.0, parcel_length: float = 0,
                    parcel_width: float = 0, parcel_height: float = 0,
                    parcel_type: str = None, service_type: str = None) -> Dict:
    """Get demo pricing for testing purposes"""
    
    # Demo pricing data (these would come from The Courier Guy API)
    demo_services = [
        {
            'code': 'LOF',
            'name': 'Local Overnight (LOF)',
            'description': 'Collection must be booked by 14:00, and ready by 14:30, to be delivered during the next business day.',
            'price': 105.75,
            'deadline': '14:00 (ready by 14:30)',
            'delivery_time': 'Next business day',
            'available': True
        },
        {
            'code': 'LSF',
            'name': 'Local Same Day Flyer (LSF)',
            'description': 'Collection must be booked by 10:30, and ready by 11:00, to be delivered by 17:00 the same day.',
            'price': 125.75,
            'deadline': '10:30 (ready by 11:00)',
            'delivery_time': 'Same day by 17:00',
            'available': True
        },
        {
            'code': 'LOX',
            'name': 'Local Overnight Parcel (LOX)',
            'description': 'Collection must be booked by 14:00, and ready by 14:30, to be delivered during the next business day.',
            'price': 126.50,
            'deadline': '14:00 (ready by 14:30)',
            'delivery_time': 'Next business day',
            'available': True
        },
        {
            'code': 'LSE',
            'name': 'Local Same Day Economy (LSE)',
            'description': 'Collection must be booked by 10:30, and ready by 11:00, to be delivered by 17:00 the same day.',
            'price': 165.75,
            'deadline': '10:30 (ready by 11:00)',
            'delivery_time': 'Same day by 17:00',
            'available': True
        },
        {
            'code': 'SDX',
            'name': 'Same Day Express (SDX)',
            'description': 'To ensure timely processing, kindly book your shipment before 14:00. Our standard turnaround time is 8-10 hours, subject to flight availability. Please note that deliveries scheduled after 18:00 will incur an after-hours surcharge of R713.00 (VAT included).',
            'price': 0.0,  # Contact for quote
            'deadline': '14:00',
            'delivery_time': '8-10 hours (subject to flight availability)',
            'available': True
        }
    ]
    
    # If specific service requested, return only that service
    if service_type:
        service = next((s for s in demo_services if s['code'] == service_type), None)
        if service:
            return {
                'success': True,
                'services': [service],
                'pricing': {service_type: service['price']},
                'data': {
                    'pickup_address': pickup_address,
                    'delivery_address': delivery_address,
                    'parcel_weight': parcel_weight,
                    'service_type': service_type
                }
            }
        else:
            return {
                'success': False,
                'error': f'Service type {service_type} not found'
            }
    
    # Return all services
    return {
        'success': True,
        'services': demo_services,
        'pricing': {s['code']: s['price'] for s in demo_services},
        'data': {
            'pickup_address': pickup_address,
            'delivery_address': delivery_address,
            'parcel_weight': parcel_weight,
            'parcel_length': parcel_length,
            'parcel_width': parcel_width,
            'parcel_height': parcel_height,
            'parcel_type': parcel_type,
            'service_type': service_type
        }
    }

def get_demo_status(booking_id: str) -> Dict:
    """Get demo booking status"""
    return {
        'success': True,
        'status': 'in_transit',
        'tracking_number': booking_id.replace('DEMO_', 'TRK'),
        'current_location': 'Johannesburg Distribution Center',
        'estimated_delivery': (datetime.now().replace(hour=17, minute=0, second=0, microsecond=0)).isoformat(),
        'updates': [
            {
                'timestamp': datetime.now().isoformat(),
                'status': 'in_transit',
                'location': 'Johannesburg Distribution Center',
                'message': 'Package is in transit to destination'
            },
            {
                'timestamp': (datetime.now().replace(hour=9, minute=30)).isoformat(),
                'status': 'picked_up',
                'location': 'Pickup Location',
                'message': 'Package picked up successfully'
            }
        ],
        'data': {
            'booking_id': booking_id,
            'status': 'in_transit',
            'progress': 65
        }
    }
