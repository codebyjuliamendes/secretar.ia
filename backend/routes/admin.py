from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db import db

router = APIRouter()

class TenantCreate(BaseModel):
    name: str
    whatsapp: str
    prompt: str
    prices: Optional[str] = None
    businessHours: Optional[str] = None

@router.get("/tenants")
async def list_tenants():
    try:
        # Consulta SQL bruta otimizada (Database Optimizer & Backend Architect)
        # Executa as junções e contagens direto no PostgreSQL, evitando carregar e serializar
        # milhares de registros em memória no servidor Python.
        raw_tenants = await db.query_raw('''
            SELECT 
                t.id, 
                t.name, 
                t.whatsapp, 
                t.status, 
                t."createdAt",
                COALESCE(app.cnt, 0) as "appointmentCount",
                COALESCE(pat.cnt, 0) as "patientCount"
            FROM "Tenant" t
            LEFT JOIN (
                SELECT "tenantId", COUNT(*) as cnt 
                FROM "Appointment" 
                GROUP BY "tenantId"
            ) app ON app."tenantId" = t.id
            LEFT JOIN (
                SELECT "tenantId", COUNT(*) as cnt 
                FROM "Patient" 
                GROUP BY "tenantId"
            ) pat ON pat."tenantId" = t.id
            ORDER BY t."createdAt" DESC
        ''')
        
        # Formata os dados para o dashboard
        formatted = []
        for t in raw_tenants:
            created_at_val = t.get("createdAt")
            if created_at_val and not isinstance(created_at_val, str):
                created_at_str = created_at_val.isoformat()
            else:
                created_at_str = created_at_val or ""

            formatted.append({
                "id": t.get("id"),
                "name": t.get("name"),
                "whatsapp": t.get("whatsapp"),
                "status": t.get("status"),
                "appointmentCount": int(t.get("appointmentCount") or 0),
                "patientCount": int(t.get("patientCount") or 0),
                "createdAt": created_at_str
            })
        return {"success": True, "tenants": formatted}
    except Exception as e:
        print(f"[ADMIN ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tenants")
async def create_tenant(data: TenantCreate):
    try:
        tenant = await db.tenant.create(
            data={
                "name": data.name,
                "whatsapp": data.whatsapp,
                "prompt": data.prompt,
                "prices": data.prices,
                "businessHours": data.businessHours,
                "status": "TRIAL"
            }
        )
        return {"success": True, "tenant": tenant}
    except Exception as e:
        print(f"[ADMIN ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
