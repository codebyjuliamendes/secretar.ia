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
        tenants = await db.tenant.find_many(
            include={
                "appointments": True,
                "patients": True
            }
        )
        # Formata os dados para o dashboard
        formatted = []
        for t in tenants:
            formatted.append({
                "id": t.id,
                "name": t.name,
                "whatsapp": t.whatsapp,
                "status": t.status,
                "appointmentCount": len(t.appointments) if t.appointments else 0,
                "patientCount": len(t.patients) if t.patients else 0,
                "createdAt": t.createdAt.isoformat()
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
