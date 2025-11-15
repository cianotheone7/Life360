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
        """Get current dashboard data for AI context."""
        try:
            # Lazy imports to avoid circular dependency
            from app import db, Practitioner, PractitionerFlag, Order, StockItem, StockUnit
            from sqlalchemy import func
            
            # Practitioners
            total_prac = db.session.query(func.count(Practitioner.id)).scalar() or 0
            onboarded = db.session.query(func.count(PractitionerFlag.id)).filter_by(onboarded=True).scalar() or 0
            pending_prac = total_prac - onboarded
            
            # Orders
            total_orders = db.session.query(Order).count()
            completed_orders = db.session.query(Order).filter(Order.status.ilike("%completed%")).count()
            cancelled_orders = db.session.query(Order).filter(Order.status.ilike("%cancel%")).count()
            pending_orders = total_orders - completed_orders - cancelled_orders
            
            # Stock
            total_stock_items = db.session.query(func.count(StockItem.id)).scalar() or 0
            total_stock_units = db.session.query(func.count(StockUnit.id)).filter(
                StockUnit.status == "In Stock"
            ).scalar() or 0
            
            # Get provider breakdown for orders
            providers_data = db.session.query(
                Order.provider,
                func.count(Order.id)
            ).group_by(Order.provider).all()
            
            provider_summary = ", ".join([f"{p[0]}: {p[1]} orders" for p in providers_data if p[0]]) if providers_data else "No data"
            
            context = f"""LIFE360 DASHBOARD DATA:

PRACTITIONERS:
- Total: {total_prac}
- Onboarded: {onboarded}
- Pending Onboarding: {pending_prac}

ORDERS:
- Total: {total_orders}
- Completed: {completed_orders}
- Pending: {pending_orders}
- Cancelled: {cancelled_orders}

STOCK:
- Total Items: {total_stock_items}
- Units In Stock: {total_stock_units}

PROVIDER BREAKDOWN:
{provider_summary}
"""
            return context
            
        except ImportError as e:
            # If imports fail, return basic info
            return "Dashboard data temporarily unavailable."
        except Exception as e:
            # Log but don't crash
            return f"Dashboard data retrieval error: {str(e)}"
    
    def is_configured(self) -> bool:
        """Check if AI service is properly configured."""
        return bool(self.api_key)
    
    def get_system_prompt(self) -> str:
        """Get the system prompt for AI responses."""
        return """You are an AI assistant for the Life360 Dashboard, a healthcare management system.
You help users understand their data about practitioners, orders, and stock inventory.

Key areas you can help with:
- Practitioner onboarding status and counts
- Order status, completion rates, and provider breakdown
- Stock inventory levels and availability
- General questions about the dashboard data

Provide accurate, helpful responses based on the dashboard data provided. Be concise but informative.
If asked about specific details not in the data, let the user know what information is available."""

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
