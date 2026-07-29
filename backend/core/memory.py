from typing import List, Dict
from db import db

async def save_message(phone: str, tenantId: str, role: str, content: str):
    """
    Grava uma mensagem do histórico de conversas no banco de dados para formar a memória do Chatbot.
    """
    try:
        await db.message.create(
            data={
                "phone": phone,
                "tenantId": tenantId,
                "role": role, # 'user' ou 'assistant'
                "content": content
            }
        )
    except Exception as e:
        print(f"[MEMORY ERROR] Falha ao salvar mensagem: {str(e)}")

async def get_conversation_history(phone: str, tenantId: str, limit: int = 10) -> List[Dict[str, str]]:
    """
    Busca as últimas N mensagens da conversa de forma ordenada para injetar no prompt do LLM.
    """
    try:
        messages = await db.message.find_many(
            where={
                "phone": phone,
                "tenantId": tenantId
            },
            take=limit,
            order_by={
                "createdAt": "desc"
            }
        )
        # Inverte para retornar na ordem cronológica correta (mais antiga para mais recente)
        formatted = []
        for msg in reversed(messages):
            formatted.append({
                "role": msg.role,
                "content": msg.content
            })
        return formatted
    except Exception as e:
        print(f"[MEMORY ERROR] Falha ao buscar histórico: {str(e)}")
        return []
