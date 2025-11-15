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
        self.url = "https://www.a4f.co/api/chat/completions"
        self.model = "provider-5/gpt-4o-mini"
        
    def is_configured(self) -> bool:
        """Check if AI service is properly configured."""
        return bool(self.api_key)
    
    def get_system_prompt(self) -> str:
        """Get the system prompt for AI responses."""
        return """You are an AI assistant for the Life360 Dashboard, a healthcare management system. 
Provide accurate, helpful responses. Be concise but informative."""

    def query_ai(self, user_prompt: str) -> Tuple[bool, str, str]:
        """Query A4F API with user prompt."""
        if not self.is_configured():
            return False, "", "AI service not configured"
        
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": user_prompt}
                ]
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
