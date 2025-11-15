"""
AI Service for Life360 Dashboard using A4F API
"""

import requests
from typing import Dict, Any, Tuple


class Life360AIService:
    """AI service using A4F API."""
    
    def __init__(self):
        # A4F API configuration
        self.api_key = "ddc-a4f-c56fc7b02b3d485c94d5f8024554922f"
        self.url = "https://api.a4f.co/v1/chat/completions"  # Fixed endpoint
        self.model = "provider-5/gpt-4o-mini"
    
    def get_dashboard_context(self) -> str:
        """Get current dashboard data for AI context - COMPLETE ACCESS TO ALL DATA."""
        try:
            # Lazy imports to avoid circular dependency
            from app import db, Practitioner, PractitionerFlag, Order, OrderItem, StockItem, StockUnit
            from sqlalchemy import func
            
            # ===== PRACTITIONERS - ALL OF THEM =====
            total_prac = db.session.query(func.count(Practitioner.id)).scalar() or 0
            onboarded = db.session.query(func.count(PractitionerFlag.id)).filter_by(onboarded=True).scalar() or 0
            pending_prac = total_prac - onboarded
            
            # Get ALL practitioners with full details
            practitioners_list = db.session.query(Practitioner, PractitionerFlag).outerjoin(
                PractitionerFlag, Practitioner.id == PractitionerFlag.pid
            ).all()  # NO LIMIT - ALL PRACTITIONERS
            
            prac_details = []
            for p, f in practitioners_list:
                status = "Onboarded" if (f and f.onboarded) else "Pending"
                training = "Yes" if (f and f.training) else "No"
                website = "Yes" if (f and f.website) else "No"
                whatsapp = "Yes" if (f and f.whatsapp) else "No"
                email = p.email or "No email"
                phone = p.phone or "No phone"
                prac_details.append(
                    f"ID:{p.id} | {p.title or ''} {p.first_name} {p.last_name} | "
                    f"Provider: {p.provider} | Status: {status} | Email: {email} | Phone: {phone} | "
                    f"Training: {training} | Website: {website} | WhatsApp: {whatsapp}"
                )
            
            # ===== ORDERS - ALL OF THEM =====
            total_orders = db.session.query(Order).count()
            completed_orders = db.session.query(Order).filter(Order.status.ilike("%completed%")).count()
            cancelled_orders = db.session.query(Order).filter(Order.status.ilike("%cancel%")).count()
            pending_orders = total_orders - completed_orders - cancelled_orders
            
            # Get ALL recent orders with items
            orders_list = db.session.query(Order).order_by(Order.created_at.desc()).all()  # ALL ORDERS
            order_details = []
            for o in orders_list[:100]:  # Show last 100 orders to keep context manageable
                # Get order items safely
                order_items = db.session.query(OrderItem).filter_by(order_id=o.id).all()
                items = [f"{item.sku}(x{item.qty})" for item in order_items]
                items_str = ", ".join(items) if items else "No items"
                order_details.append(
                    f"Order #{o.id} | Customer: {o.name} {o.surname} | Practitioner: {o.practitioner_name or 'None'} | "
                    f"Provider: {o.provider} | Status: {o.status} | Items: {items_str} | "
                    f"Sent: {o.sent_out} | Received: {o.received_back} | Registered: {o.kit_registered} | "
                    f"Results Sent: {o.results_sent} | Paid: {o.paid} | Created: {o.created_at.strftime('%Y-%m-%d') if o.created_at else 'Unknown'}"
                )
            
            # ===== STOCK - ALL ITEMS WITH FULL DETAILS =====
            total_stock_items = db.session.query(func.count(StockItem.id)).scalar() or 0
            total_stock_units = db.session.query(func.count(StockUnit.id)).filter(
                StockUnit.status == "In Stock"
            ).scalar() or 0
            
            # Get ALL stock items with quantities and expiry dates
            stock_items = db.session.query(StockItem).all()  # NO LIMIT - ALL STOCK
            stock_details = []
            for item in stock_items:
                in_stock = db.session.query(func.count(StockUnit.id)).filter(
                    StockUnit.item_id == item.id,
                    StockUnit.status == "In Stock"
                ).scalar() or 0
                
                assigned = db.session.query(func.count(StockUnit.id)).filter(
                    StockUnit.item_id == item.id,
                    StockUnit.status == "Assigned"
                ).scalar() or 0
                
                used = db.session.query(func.count(StockUnit.id)).filter(
                    StockUnit.item_id == item.id,
                    StockUnit.status == "Used"
                ).scalar() or 0
                
                expiry = item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else 'No expiry'
                received = item.received_date.strftime('%Y-%m-%d') if item.received_date else 'Unknown'
                
                stock_details.append(
                    f"ID:{item.id} | {item.name} | Provider: {item.provider} | "
                    f"In Stock: {in_stock} | Assigned: {assigned} | Used: {used} | "
                    f"Expiry: {expiry} | Received: {received} | Code Type: {item.code_type or 'N/A'}"
                )
            
            # ===== PROVIDER STATISTICS =====
            providers_data = db.session.query(
                Order.provider,
                func.count(Order.id)
            ).group_by(Order.provider).all()
            
            provider_summary = ", ".join([f"{p[0]}: {p[1]} orders" for p in providers_data if p[0]]) if providers_data else "No data"
            
            context = f"""COMPLETE LIFE360 DASHBOARD DATA:

========== PRACTITIONERS SUMMARY ==========
- Total: {total_prac}
- Onboarded: {onboarded}
- Pending Onboarding: {pending_prac}

========== ALL PRACTITIONERS (FULL LIST) ==========
{chr(10).join(prac_details) if prac_details else 'No practitioners in database'}

========== ORDERS SUMMARY ==========
- Total: {total_orders}
- Completed: {completed_orders}
- Pending: {pending_orders}
- Cancelled: {cancelled_orders}

========== RECENT ORDERS (Last 100) ==========
{chr(10).join(order_details) if order_details else 'No orders in database'}

========== STOCK SUMMARY ==========
- Total Items: {total_stock_items}
- Units In Stock: {total_stock_units}

========== ALL STOCK ITEMS (FULL LIST) ==========
{chr(10).join(stock_details) if stock_details else 'No stock items in database'}

========== PROVIDER BREAKDOWN ==========
{provider_summary}

You have COMPLETE access to all data above. Answer ANY question about practitioners, orders, stock, providers, or any other dashboard information.
"""
            return context
            
        except ImportError as e:
            return "Dashboard data temporarily unavailable due to import error."
        except Exception as e:
            return f"Dashboard data retrieval error: {str(e)}"
    
    def is_configured(self) -> bool:
        """Check if AI service is properly configured."""
        return bool(self.api_key)
    
    def get_system_prompt(self) -> str:
        """Get the system prompt for AI responses."""
        return """You are an AI assistant for the Life360 Dashboard, a healthcare management system.
You have COMPLETE ACCESS to ALL dashboard data including:

- EVERY practitioner with full details (name, email, phone, provider, onboarding status, training, website, WhatsApp)
- ALL orders with complete information (customer details, items, status, dates, payment, practitioner assignments)
- ALL stock items with inventory levels (in stock, assigned, used, expiry dates, batch numbers)
- Provider statistics and breakdowns
- Any other data visible on the dashboard

Your capabilities:
- Answer questions about specific practitioners by name, ID, provider, or any other field
- Provide order details, track order status, identify orders by customer name or practitioner
- Report stock levels, expiry dates, and availability for any item
- Generate summaries, statistics, and analytics from the data
- Search and filter data based on any criteria the user asks about
- Answer ANY question about the dashboard data - nothing is off limits

Be precise, detailed, and comprehensive. When users ask about specific items, give them exact data.
If they ask for lists or summaries, provide organized, clear information.
You have access to EVERYTHING - use it to help users effectively manage their operations."""

    def query_ai(self, user_prompt: str, include_context: bool = True) -> Tuple[bool, str, str]:
        """Query A4F API with user prompt and optional dashboard context."""
        if not self.is_configured():
            return False, "", "AI service not configured"
        
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            messages = [{"role": "system", "content": self.get_system_prompt()}]
            
            # Add dashboard context if requested (disabled by default to prevent errors)
            if include_context:
                try:
                    context = self.get_dashboard_context()
                    messages.append({"role": "system", "content": context})
                except Exception as ctx_error:
                    # Log but continue without context
                    pass
            
            messages.append({"role": "user", "content": user_prompt})
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                self.url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                choices = result.get('choices', [])
                if not choices:
                    return False, "", "No response from AI service"
                
                content = choices[0].get('message', {}).get('content', '')
                if not content:
                    return False, "", "Empty response from AI service"
                
                return True, content, ""
            
            elif response.status_code == 401:
                return False, "", "API key invalid or expired"
            elif response.status_code == 429:
                return False, "", "Rate limit exceeded. Please try again later."
            else:
                error_text = response.text[:200] if response.text else "Unknown error"
                return False, "", f"API error ({response.status_code}): {error_text}"
                
        except requests.exceptions.Timeout:
            return False, "", "Request timeout. Please try again."
        except requests.exceptions.ConnectionError:
            return False, "", "Connection error. Please check your internet connection."
        except Exception as e:
            return False, "", f"Unexpected error: {str(e)}"
    
    def process_query(self, user_query: str) -> Dict[str, Any]:
        """Process a user query and return formatted response."""
        if not user_query or not user_query.strip():
            return {"ok": False, "error": "Please provide a question"}
        
        success, answer, error = self.query_ai(user_query.strip())
        
        if success:
            return {"ok": True, "answer": answer}
        else:
            return {"ok": False, "error": error or "Failed to get AI response"}


# Global instance
ai_service = Life360AIService()
