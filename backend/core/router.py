import time
from typing import Dict, Any
from db import db
from core.memory import save_message
from core.queue import send_job

# -------------------------------------------------------------
# MOCK AGENTS (Espaço reservado para plugar as chamadas dos LLMs)
# -------------------------------------------------------------

class BaseAgent:
    def __init__(self, name: str):
        self.name = name

    async def processar(self, phone: str, tenantId: str, context: str) -> str:
        # Simula processamento cognitivo do LLM
        print(f"[{self.name.upper()} AGENT] Processando contexto...")
        if "erro" in context.lower():
            raise Exception(f"Simulação de falha cognitiva no agente {self.name}")
        
        if self.name == "agenda":
            return "Perfeito! Seu agendamento de Botox foi pré-confirmado para amanhã às 14:00. Posso confirmar?"
        elif self.name == "cancelamento":
            return "Compreendo. Seu agendamento foi desmarcado com sucesso. Deseja remarcar?"
        elif self.name == "info":
            return "Nossa clínica funciona de segunda a sexta, das 09:00 às 18:00. O valor do Botox é R$ 990."
        return "Olá! Sou a secretária virtual. Como posso te ajudar hoje?"

agenda_agent = BaseAgent("agenda")
cancelamento_agent = BaseAgent("cancelamento")
info_agent = BaseAgent("info")

# -------------------------------------------------------------
# MOTOR DE ROTEAMENTO E ESCALABILIDADE (FALLBACK)
# -------------------------------------------------------------

async def escalar_para_humano(phone: str, tenantId: str, context: str) -> str:
    """
    Fallback crítico: registra o transbordo humano e notifica a clínica.
    """
    try:
        # Registra no banco
        await db.log.create(
            data={
                "tenantId": tenantId,
                "level": "HUMANO",
                "message": f"Transbordo para atendimento humano acionado. Telefone: {phone}. Contexto: {context}"
            }
        )
        
        # Enfileira tarefa para alertar via WhatsApp da clínica (resiliência)
        await send_job("enviar-whatsapp", {
            "phone": phone,
            "message": "Olá! Nosso assistente virtual transferiu sua conversa para uma secretária humana. Em instantes entraremos em contato."
        })
        
        return "Vou te transferir agora mesmo para uma de nossas secretárias humanas continuarem seu atendimento. Um momento!"
    except Exception as e:
        print(f"[CRITICAL ERROR] Falha no Handoff Humano: {str(e)}")
        return "Houve um problema de instabilidade no sistema, mas já notificamos a equipe. Por favor, aguarde um instante."

async def rotear_conversa(intent: str, phone: str, tenantId: str, context: str) -> str:
    """
    Substitui o nó Switch do N8n. Roteia a conversa para o agente correto
    e aplica tratamento de erro total com fallback para humano.
    """
    start_time = time.time()
    agent_name = "default"
    response_text = ""
    error_occurred = None

    try:
        if intent == "AGENDAR":
            agent_name = "agenda"
            response_text = await agenda_agent.processar(phone, tenantId, context)
        elif intent == "CANCELAR":
            agent_name = "cancelamento"
            response_text = await cancelamento_agent.processar(phone, tenantId, context)
        elif intent == "INFO":
            agent_name = "info"
            response_text = await info_agent.processar(phone, tenantId, context)
        else:
            # Qualquer intenção não mapeada ou categorizada como Humana
            agent_name = "handoff"
            response_text = await escalar_para_humano(phone, tenantId, context)

    except Exception as e:
        # Tratamento de Erro Total: Se qualquer agente estourar erro, cai para humano
        error_occurred = str(e)
        print(f"[ROUTER EXCEPTION] Agente '{agent_name}' falhou. Acionando fallback humano. Erro: {error_occurred}")
        response_text = await escalar_para_humano(phone, tenantId, f"FALHA NO AGENTE {agent_name.upper()}: {error_occurred}")

    finally:
        # Observabilidade: Grava o log de execução estruturado no banco
        run_time_ms = int((time.time() - start_time) * 1000)
        try:
            await db.executionlog.create(
                data={
                    "tenantId": tenantId,
                    "agent": agent_name,
                    "input": context,
                    "output": response_text,
                    "error": error_occurred,
                    "runTimeMs": run_time_ms
                }
            )
            # Salva na memória conversacional persistente
            await save_message(phone, tenantId, "user", context)
            await save_message(phone, tenantId, "assistant", response_text)
        except Exception as log_err:
            print(f"[ROUTER LOG ERROR] Falha ao registrar log de execução: {str(log_err)}")

    return response_text
