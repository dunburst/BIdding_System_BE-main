import asyncio
import os
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.model_clients import GoogleGeminiChatCompletionClient

# Import thêm các class thông điệp để kiểm tra kiểu dữ liệu
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.base import TaskResult


async def main() -> None:
    model_client = GoogleGeminiChatCompletionClient(
        model="gemini-2.5-flash", 
        api_key="AIzaSyCI1bbrKiJIkZBlTe2VxdYeRftNsTISFS8" 
    )

    coder = AssistantAgent(
        name="Coder",
        model_client=model_client,
        system_message="Bạn là một lập trình viên Python. Viết code giải quyết yêu cầu. Luôn để code trong block markdown.",
    )

    reviewer = AssistantAgent(
        name="Reviewer",
        model_client=model_client,
        system_message="Bạn là người kiểm duyệt. Nếu code có lỗi, hãy bắt sửa. Nếu tốt, trả lời duy nhất: 'DUYET'.",
    )

    termination = TextMentionTermination("DUYET")
    team = RoundRobinGroupChat(
        participants=[coder, reviewer], 
        termination_condition=termination
    )

    print("=== Team Dev AutoGen đã sẵn sàng! ===")
    
    while True:
        user_input = input("\nBạn: ")
        if user_input.lower() in ["exit", "quit"]:
            break
        
        if not user_input.strip():
            continue

        print("\n--- Bắt đầu ---\n")

        # --- ĐOẠN SỬA LỖI Ở ĐÂY ---
        async for message in team.run_stream(task=user_input):
            # 1. Kiểm tra nếu là tin nhắn văn bản (Bot nói chuyện)
            if isinstance(message, TextMessage):
                print(f"\033[1m[{message.source}]:\033[0m") 
                print(f"{message.content}\n")
                print("-" * 50)
            
            # 2. Kiểm tra nếu là kết quả cuối cùng (Hệ thống báo xong)
            elif isinstance(message, TaskResult):
                print(f"✅ [SYSTEM]: Kết thúc tác vụ. (Lý do dừng: {message.stop_reason})")
        # ---------------------------

        await team.reset()

if __name__ == "__main__":
    asyncio.run(main())