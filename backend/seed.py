import asyncio
from db import db

async def seed():
    print("[INFO] Conectando ao PostgreSQL na Neon para semear dados iniciais...")
    await db.connect()
    
    # Cria ou atualiza os Tenants (Clínicas) básicas no banco de dados da nuvem
    try:
        t1 = await db.tenant.upsert(
            where={"whatsapp": "5581999998888"},
            data={
                "create": {
                    "id": "1",
                    "name": "Clinica Harmonize",
                    "whatsapp": "5581999998888",
                    "prompt": "Voce e a secretaria virtual da Clinica Harmonize, elegante, educada e prestativa.",
                    "prices": "Botox (Toxina): R$ 990, Preenchimento Labial: R$ 1200",
                    "businessHours": "09:00 - 18:00",
                    "status": "ACTIVE"
                },
                "update": {
                    "id": "1",
                    "name": "Clinica Harmonize",
                    "status": "ACTIVE"
                }
            }
        )
        print("[OK] Clinica 'Clinica Harmonize' (ID: 1) criada/atualizada com sucesso!")
        
        t2 = await db.tenant.upsert(
            where={"whatsapp": "5581988887777"},
            data={
                "create": {
                    "id": "2",
                    "name": "Dra. Fernanda Estetica",
                    "whatsapp": "5581988887777",
                    "prompt": "Voce e a assistente clinica da Dra. Fernanda, atenciosa e objetiva.",
                    "prices": "Botox: R$ 990, Preenchimento: R$ 1200",
                    "businessHours": "09:00 - 18:00",
                    "status": "TRIAL"
                },
                "update": {
                    "id": "2",
                    "name": "Dra. Fernanda Estetica",
                    "status": "TRIAL"
                }
            }
        )
        print("[OK] Clinica 'Dra. Fernanda Estetica' (ID: 2) criada/atualizada com sucesso!")
        
        # Cria um paciente mock para a Clínica 1 para popular os dashboards iniciais
        patient = await db.patient.upsert(
            where={
                "tenantId_phone": {
                    "tenantId": "1",
                    "phone": "+5581999998888"
                }
            },
            data={
                "create": {
                    "tenantId": "1",
                    "phone": "+5581999998888",
                    "name": "Amanda Silva"
                },
                "update": {
                    "name": "Amanda Silva"
                }
            }
        )
        
        # Cria um agendamento mock para a Amanda Silva
        from datetime import datetime, timezone
        await db.appointment.create(
            data={
                "tenantId": "1",
                "patientId": patient.id,
                "service": "Toxina Botulinica (Botox)",
                "date": datetime(2026, 7, 29, 14, 0, 0, tzinfo=timezone.utc),
                "status": "Confirmado"
            }
        )
        print("[OK] Paciente e agendamento de teste criados com sucesso!")

    except Exception as e:
        print(f"[ERROR] Falha ao semear banco de dados: {str(e)}")
    finally:
        if db.is_connected():
            await db.disconnect()

if __name__ == "__main__":
    asyncio.run(seed())
