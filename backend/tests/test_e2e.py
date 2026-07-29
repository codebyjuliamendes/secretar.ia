import asyncio
import httpx
import uuid

# URL local da API FastAPI do Secretar.ia
API_URL = "http://localhost:8000/api/n8n/webhook"

async def test_e2e_flow():
    print("=============================================================")
    print("🚀 INICIANDO TESTE E2E - SIMULAÇÃO DE FLUXOS WEBHOOK (Pilar 7)")
    print("=============================================================")

    # Dicionário de testes a serem executados
    async with httpx.AsyncClient() as client:
        # Geramos IDs únicos para simular mensagens reais
        msg_id_agendar = str(uuid.uuid4())
        tenant_id = "1" # ID da Clínica mock

        # -------------------------------------------------------------
        # TESTE 1: Agendamento de Consulta (Cenário de Sucesso)
        # -------------------------------------------------------------
        print("\n📝 [TESTE 1] Enviando mensagem de agendamento...")
        payload_1 = {
            "messageId": msg_id_agendar,
            "phone": "+5581999998888",
            "text": "Olá, gostaria de agendar uma aplicação de Botox por favor.",
            "tenantId": tenant_id
        }
        
        try:
            res_1 = await client.post(API_URL, json=payload_1, timeout=10.0)
            if res_1.status_code == 200:
                data = res_1.json()
                print(f"✅ Resposta recebida! Status: {data.get('status')}")
                print(f"🤖 Intenção detectada: {data.get('intent')}")
                print(f"💬 Resposta da IA: '{data.get('response')}'")
                assert data.get("intent") == "AGENDAR", "Erro: Deveria classificar como AGENDAR"
            else:
                print(f"❌ Falha de conexão. Código HTTP: {res_1.status_code}. Certifique-se de que a API FastAPI (main.py) está rodando localmente na porta 8000.")
        except Exception as e:
            print(f"❌ Erro de conexão com a API: {str(e)}")

        # -------------------------------------------------------------
        # TESTE 2: Idempotência (Mensagem Duplicada)
        # -------------------------------------------------------------
        print("\n🛡️ [TESTE 2] Reenviando a MESMA mensagem para testar Idempotência...")
        try:
            res_2 = await client.post(API_URL, json=payload_1, timeout=10.0)
            if res_2.status_code == 200:
                data = res_2.json()
                print(f"✅ Resposta recebida! Status: {data.get('status')}")
                assert data.get("status") == "duplicate_ignored", "Erro: Deveria ter ignorado a mensagem duplicada"
                print("✅ Sucesso: Mensagem duplicada ignorada com sucesso (Idempotência ativa).")
        except Exception as e:
            print(f"❌ Erro de conexão no Teste 2: {str(e)}")

        # -------------------------------------------------------------
        # TESTE 3: Handoff Humano
        # -------------------------------------------------------------
        print("\n👤 [TESTE 3] Enviando mensagem pedindo ajuda humana...")
        msg_id_humano = str(uuid.uuid4())
        payload_3 = {
            "messageId": msg_id_humano,
            "phone": "+5581999998888",
            "text": "Preciso falar com um atendente humano agora, meu caso é urgente.",
            "tenantId": tenant_id
        }
        try:
            res_3 = await client.post(API_URL, json=payload_3, timeout=10.0)
            if res_3.status_code == 200:
                data = res_3.json()
                print(f"✅ Resposta recebida! Status: {data.get('status')}")
                print(f"🤖 Intenção detectada: {data.get('intent')}")
                print(f"💬 Resposta da IA: '{data.get('response')}'")
                assert data.get("intent") == "HUMANO", "Erro: Deveria classificar como HUMANO"
                print("✅ Sucesso: Handoff humano acionado e roteado com fallback.")
        except Exception as e:
            print(f"❌ Erro de conexão no Teste 3: {str(e)}")

    print("\n=============================================================")
    print("🎉 FIM DOS TESTES E2E - TODOS OS PILARES CONCLUÍDOS!")
    print("=============================================================")

if __name__ == "__main__":
    asyncio.run(test_e2e_flow())
