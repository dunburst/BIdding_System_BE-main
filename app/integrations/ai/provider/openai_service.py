# app/integrations/ai/provider/openai_service.py
import os
from typing import Optional
from openai import OpenAI

class OpenAIService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print("⚠️ Cảnh báo: Chưa cấu hình OPENAI_API_KEY")
        
        self.base_url = os.getenv("OPENAI_API_BASE")
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.model_name = "gpt-4o" 

    def get_client(self):
        return self.client

    def chat(self, prompt: str, system_role: Optional[str] = None) -> str:
        try:
            messages = []
            if system_role:
                messages.append({"role": "system", "content": system_role})
            else:
                messages.append({"role": "system", "content": "Bạn là trợ lý AI chuyên nghiệp."})
            
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.1,
                max_tokens=2000
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"❌ Lỗi OpenAI: {str(e)}"

# Singleton Instance
openai_service = OpenAIService()