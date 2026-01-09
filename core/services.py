"""
Core Business Logic
Shared services between UI and backend functionality
"""
from datetime import datetime
from typing import List, Dict, Any


class DataService:
    """Service for managing application data"""
    
    def __init__(self):
        self._messages: List[Dict[str, Any]] = []
    
    def get_sample_data(self) -> Dict[str, Any]:
        """Get sample data"""
        return {
            "data": [
                {"id": 1, "name": "Item 1", "value": 100},
                {"id": 2, "name": "Item 2", "value": 200},
                {"id": 3, "name": "Item 3", "value": 300}
            ],
            "timestamp": datetime.now().isoformat(),
            "count": 3
        }
    
    def process_message(self, message: str) -> Dict[str, Any]:
        """Process and store a message"""
        message_data = {
            "received_message": message,
            "processed_at": datetime.now().isoformat(),
            "length": len(message),
            "response": f"Processed: '{message}'"
        }
        
        self._messages.append(message_data)
        
        return {
            "success": True,
            "message": "Message processed successfully",
            "data": message_data,
            "total_messages": len(self._messages)
        }
    
    def get_all_messages(self) -> Dict[str, Any]:
        """Get all stored messages"""
        return {
            "messages": self._messages,
            "total": len(self._messages),
            "timestamp": datetime.now().isoformat()
        }
    
    def clear_messages(self) -> Dict[str, Any]:
        """Clear all messages"""
        count = len(self._messages)
        self._messages.clear()
        return {
            "success": True,
            "message": f"Cleared {count} messages"
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status"""
        return {
            "status": "online",
            "message": "Qt Python Application",
            "timestamp": datetime.now().isoformat(),
            "messages_count": len(self._messages)
        }


class AnalyticsService:
    """Service for analytics and calculations"""
    
    @staticmethod
    def calculate_stats(values: List[float]) -> Dict[str, float]:
        """Calculate statistics from a list of values"""
        if not values:
            return {"count": 0, "sum": 0, "average": 0, "min": 0, "max": 0}
        
        return {
            "count": len(values),
            "sum": sum(values),
            "average": sum(values) / len(values),
            "min": min(values),
            "max": max(values)
        }
    
    @staticmethod
    def process_text(text: str) -> Dict[str, Any]:
        """Analyze text and return statistics"""
        words = text.split()
        return {
            "character_count": len(text),
            "word_count": len(words),
            "line_count": text.count('\n') + 1,
            "uppercase_count": sum(1 for c in text if c.isupper()),
            "lowercase_count": sum(1 for c in text if c.islower()),
            "digit_count": sum(1 for c in text if c.isdigit())
        }


# Singleton instance
_data_service = None

def get_data_service() -> DataService:
    """Get the singleton DataService instance"""
    global _data_service
    if _data_service is None:
        _data_service = DataService()
    return _data_service
