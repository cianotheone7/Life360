"""
AI Service for Life360 Dashboard - Enhanced OpenRouter Integration
Provides intelligent responses about stock, orders, and practitioner data.
"""

import os
import json
import requests
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session


class Life360AIService:
    """Enhanced AI service for Life360 dashboard queries."""
    
    def __init__(self):
        # Lazy import to avoid circular dependency
        from app import db, StockItem, StockUnit, Order, OrderItem, Practitioner, PractitionerFlag
        self.db = db
        self.StockItem = StockItem
        self.StockUnit = StockUnit
        self.Order = Order
        self.OrderItem = OrderItem
        self.Practitioner = Practitioner
        self.PractitionerFlag = PractitionerFlag
        
        # Use Puter's free OpenAI API proxy (no API key needed!)
        self.api_key = "no-key-needed"  # Puter doesn't require an API key
        self.url = "https://puter-llm-proxy.puter.com/v1/chat/completions"
        self.model = "gpt-4o-mini"  # Free model available through Puter
        self.site_url = ""
        self.title = "Life360 Dashboard Ask AI"
        
    def is_configured(self) -> bool:
        """Check if AI service is properly configured."""
        return True  # Puter is always available, no API key needed
    
    def get_system_prompt(self) -> str:
        """Get the system prompt for AI responses."""
        return """You are an AI assistant for the Life360 Dashboard, a healthcare management system. 
You have access to comprehensive data about:

1. STOCK MANAGEMENT:
   - Stock items with names, expiry dates, providers, current stock levels
   - Stock units with barcodes, batch numbers, and status (In Stock, Assigned, etc.)
   - Real-time stock counts and availability
   - Batch number tracking for inventory management

2. ORDERS:
   - Customer orders with provider, customer details, practitioner info
   - Order status (Pending, Completed, Cancelled)
   - Order items with SKUs and quantities
   - Order workflow flags (sent_out, received_back, kit_registered, results_sent, paid, invoiced)
   - Order call logs and notes

3. PRACTITIONERS:
   - Healthcare practitioners with provider affiliations
   - Contact information (email, phone)
   - Onboarding status and training flags
   - Notes and specializations

Provide accurate, helpful responses based on the data provided. Be concise but informative.
Format numbers clearly and highlight important information. If asked for specific data,
provide exact figures and details."""

    def get_comprehensive_data_context(self) -> Dict[str, Any]:
        """Get comprehensive data context for AI analysis."""
        try:
            # Stock data
            stock_items = self.db.session.query(self.StockItem).all()
            stock_data = []
            for item in stock_items:
                in_stock_count = self.db.session.query(func.count(self.StockUnit.id)).filter(
                    and_(self.StockUnit.item_id == item.id, self.StockUnit.status == "In Stock")
                ).scalar() or 0
                
                # Get batch number summary with quantities
                batch_data = self.db.session.query(
                    self.StockUnit.batch_number, 
                    func.count(self.StockUnit.id)
                ).filter(
                    and_(self.StockUnit.item_id == item.id, self.StockUnit.status == "In Stock", self.StockUnit.batch_number.isnot(None))
                ).group_by(self.StockUnit.batch_number).all()
                
                if batch_data:
                    if len(batch_data) == 1:
                        batch_summary = f"{batch_data[0][0]} ({batch_data[0][1]} units)"
                    else:
                        # Show all batch numbers with quantities
                        batch_summary = ", ".join([f"{batch[0]} ({batch[1]} units)" for batch in batch_data if batch[0]])
                else:
                    batch_summary = "-"
                
                stock_data.append({
                    "id": item.id,
                    "name": item.name,
                    "provider": item.provider,
                    "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
                    "received_date": item.received_date.isoformat() if item.received_date else None,
                    "current_stock": in_stock_count,
                    "code_type": item.code_type,
                    "batch_numbers": batch_summary
                })
            
            # Orders data
            orders = self.db.session.query(self.Order).order_by(self.Order.created_at.desc()).limit(100).all()
            orders_data = []
            for order in orders:
                items = [{"sku": item.sku, "qty": item.qty} for item in order.items]
                orders_data.append({
                    "id": order.id,
                    "provider": order.provider,
                    "customer_name": f"{order.name or ''} {order.surname or ''}".strip(),
                    "practitioner_name": order.practitioner_name,
                    "status": order.status,
                    "ordered_at": order.ordered_at.isoformat() if order.ordered_at else None,
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                    "completed_at": order.completed_at.isoformat() if order.completed_at else None,
                    "items": items,
                    "sent_out": order.sent_out,
                    "received_back": order.received_back,
                    "kit_registered": order.kit_registered,
                    "results_sent": order.results_sent,
                    "paid": order.paid,
                    "invoiced": order.invoiced,
                    "notes": order.notes
                })
            
            # Practitioners data
            practitioners = self.db.session.query(self.Practitioner).all()
            practitioners_data = []
            for practitioner in practitioners:
                # Get flags
                flags = self.PractitionerFlag.query.filter_by(pid=practitioner.id).first()
                practitioners_data.append({
                    "id": practitioner.id,
                    "provider": practitioner.provider,
                    "title": practitioner.title,
                    "first_name": practitioner.first_name,
                    "last_name": practitioner.last_name,
                    "email": practitioner.email,
                    "phone": practitioner.phone,
                    "notes": practitioner.notes,
                    "created_at": practitioner.created_at.isoformat() if practitioner.created_at else None,
                    "training": flags.training if flags else False,
                    "website": flags.website if flags else False,
                    "whatsapp": flags.whatsapp if flags else False,
                    "engagebay": flags.engagebay if flags else False,
                    "onboarded": flags.onboarded if flags else False
                })
            
            # Summary statistics
            total_orders = self.db.session.query(self.Order).count()
            completed_orders = self.db.session.query(self.Order).filter(self.Order.status.ilike("%completed%")).count()
            pending_orders = total_orders - completed_orders
            
            total_practitioners = self.db.session.query(self.Practitioner).count()
            onboarded_practitioners = self.db.session.query(self.PractitionerFlag).filter_by(onboarded=True).count()
            
            total_stock_units = self.db.session.query(func.count(self.StockUnit.id)).filter(self.StockUnit.status == "In Stock").scalar() or 0
            
            # Provider breakdown
            provider_stats = {}
            for provider in ["Geneway", "Optiway", "Enbiosis", "Intelligene", "Healthy Me", "Intelligene Fedhealth", "Geko", "Reboot"]:
                provider_orders = self.db.session.query(func.count(self.Order.id)).filter(self.Order.provider == provider).scalar() or 0
                provider_practitioners = self.db.session.query(func.count(self.Practitioner.id)).filter(self.Practitioner.provider == provider).scalar() or 0
                provider_stock = self.db.session.query(func.count(self.StockItem.id)).filter(self.StockItem.provider == provider).scalar() or 0
                provider_stats[provider] = {
                    "orders": provider_orders,
                    "practitioners": provider_practitioners,
                    "stock_items": provider_stock
                }
            
            return {
                "summary": {
                    "total_orders": total_orders,
                    "completed_orders": completed_orders,
                    "pending_orders": pending_orders,
                    "total_practitioners": total_practitioners,
                    "onboarded_practitioners": onboarded_practitioners,
                    "total_stock_units": total_stock_units,
                    "provider_stats": provider_stats
                },
                "stock_items": stock_data,
                "orders": orders_data,
                "practitioners": practitioners_data,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"Failed to retrieve data: {str(e)}"}
    
    def query_openrouter(self, user_prompt: str, context_data: Dict[str, Any]) -> Tuple[bool, str, str]:
        """Query Puter's free OpenAI API proxy with user prompt and context data."""
        try:
            # Prepare context
            context_str = json.dumps(context_data, indent=2)
            
            # Build the full prompt
            full_prompt = f"""Based on the following Life360 Dashboard data, please answer the user's question:

DATA CONTEXT:
{context_str}

USER QUESTION: {user_prompt}

Please provide a helpful, accurate response based on the data above. Be specific with numbers and details when relevant."""

            headers = {
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': self.model,
                'messages': [
                    {'role': 'system', 'content': self.get_system_prompt()},
                    {'role': 'user', 'content': full_prompt}
                ],
                'temperature': 0.3,
                'max_tokens': 1000
            }
            
            # Retry logic for rate limiting
            max_retries = 2
            retry_delay = 1
            
            for attempt in range(max_retries + 1):
                try:
                    response = requests.post(self.url, headers=headers, json=payload, timeout=60)
                    
                    if response.status_code == 200:
                        result = response.json()
                        choices = result.get('choices', [])
                        if not choices:
                            return False, "", "No response from AI service"
                        
                        content = choices[0].get('message', {}).get('content', '')
                        if not content:
                            return False, "", "Empty response from AI service"
                        
                        return True, content, ""
                    
                    elif response.status_code == 429:
                        # Rate limited - wait and retry
                        if attempt < max_retries:
                            import time
                            time.sleep(retry_delay * (attempt + 1))
                            continue
                        else:
                            return False, "", "API rate limit exceeded. Please wait a moment and try again."
                    
                    else:
                        # Other HTTP errors
                        try:
                            error_data = response.json()
                            error_msg = error_data.get('error', {}).get('message') or error_data.get('message') or str(error_data)
                        except:
                            error_msg = response.text[:500]
                        
                        if response.status_code == 401:
                            return False, "", "API authentication failed"
                        elif response.status_code == 403:
                            return False, "", "API access forbidden. Service may be temporarily unavailable."
                        else:
                            return False, "", f"API error {response.status_code}: {error_msg}"
                
                except requests.exceptions.Timeout:
                    if attempt < max_retries:
                        import time
                        time.sleep(retry_delay)
                        continue
                    else:
                        return False, "", "Request timeout. Please try again."
                
                except requests.exceptions.ConnectionError:
                    return False, "", "Network connection error. Please check your internet connection."
            
            return False, "", "Failed to get response after retries"
            
        except requests.exceptions.RequestException as e:
            return False, "", f"Network error: {str(e)}"
        except Exception as e:
            return False, "", f"Puter API error: {str(e)}"
    
    def get_quick_stats(self) -> Dict[str, Any]:
        """Get quick statistics for dashboard display."""
        try:
            total_orders = self.db.session.query(self.Order).count()
            completed_orders = self.db.session.query(self.Order).filter(self.Order.status.ilike("%completed%")).count()
            pending_orders = total_orders - completed_orders
            
            total_practitioners = self.db.session.query(self.Practitioner).count()
            onboarded_practitioners = self.db.session.query(self.PractitionerFlag).filter_by(onboarded=True).count()
            
            total_stock_units = self.db.session.query(func.count(self.StockUnit.id)).filter(self.StockUnit.status == "In Stock").scalar() or 0
            
            # Low stock items (<= 2 units)
            low_stock_items = []
            stock_counts = self.db.session.query(
                self.StockItem.id.label("item_id"),
                self.StockItem.name,
                self.StockItem.provider,
                func.count(self.StockUnit.id).label("in_stock")
            ).outerjoin(
                self.StockUnit,
                and_(self.StockUnit.item_id == self.StockItem.id, self.StockUnit.status == "In Stock")
            ).group_by(self.StockItem.id, self.StockItem.name, self.StockItem.provider).all()
            
            for item in stock_counts:
                if int(item.in_stock) <= 2:
                    low_stock_items.append({
                        "name": item.name,
                        "provider": item.provider,
                        "qty": int(item.in_stock)
                    })
            
            # Expiring items (next 30 days)
            today = date.today()
            horizon = today + timedelta(days=30)
            expiring_items = []
            for item in self.db.session.query(self.StockItem).filter(
                and_(self.StockItem.expiry_date != None, self.StockItem.expiry_date <= horizon)
            ).all():
                expiring_items.append({
                    "name": item.name,
                    "provider": item.provider,
                    "expiry_date": item.expiry_date.isoformat()
                })
            
            return {
                "orders": {
                    "total": total_orders,
                    "completed": completed_orders,
                    "pending": pending_orders
                },
                "practitioners": {
                    "total": total_practitioners,
                    "onboarded": onboarded_practitioners,
                    "pending": total_practitioners - onboarded_practitioners
                },
                "stock": {
                    "total_units": total_stock_units,
                    "low_stock_items": low_stock_items,
                    "expiring_items": expiring_items
                }
            }
            
        except Exception as e:
            return {"error": f"Failed to get stats: {str(e)}"}
    
    def process_query(self, user_query: str) -> Dict[str, Any]:
        """Process a user query and return AI response."""
        if not user_query.strip():
            return {"ok": False, "error": "Empty query"}
        
        # Get comprehensive data context
        context_data = self.get_comprehensive_data_context()
        
        if "error" in context_data:
            return {"ok": False, "error": context_data["error"]}
        
        # Query OpenRouter
        success, response, error = self.query_openrouter(user_query, context_data)
        
        if success:
            return {
                "ok": True,
                "answer": response,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "ok": False,
                "error": error,
                "fallback": "AI service temporarily unavailable. Please try again."
            }


# Lazy global instance to avoid circular import at module load time
_ai_service_instance = None

def get_ai_service():
    """Get or create the AI service instance."""
    global _ai_service_instance
    if _ai_service_instance is None:
        _ai_service_instance = Life360AIService()
    return _ai_service_instance

# For backward compatibility
class _AIServiceProxy:
    def __getattr__(self, name):
        return getattr(get_ai_service(), name)

ai_service = _AIServiceProxy()
