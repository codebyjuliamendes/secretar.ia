import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Callable
from db import db

# Dicionário global para registrar os executores das tarefas
_registry = {}

def register_task(name: str):
    """
    Decorator para registrar funções executoras de tarefas na fila.
    """
    def decorator(func: Callable):
        _registry[name] = func
        return func
    return decorator

async def send_job(name: str, payload: Dict[str, Any], max_retries: int = 5, delay_seconds: int = 0):
    """
    Adiciona um novo Job na fila persistida no banco de dados.
    """
    try:
        run_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
        job = await db.job.create(
            data={
                "name": name,
                "payload": json.dumps(payload),
                "maxRetries": max_retries,
                "runAt": run_at,
                "status": "PENDING"
            }
        )
        print(f"[QUEUE] Job '{name}' enfileirado com ID: {job.id}. Executa em: {run_at}")
        return job.id
    except Exception as e:
        print(f"[QUEUE ERROR] Falha ao enfileirar Job: {str(e)}")
        return None

async def worker_loop():
    """
    Loop infinito rodando em background que consome e executa os Jobs.
    """
    print("[QUEUE WORKER] Iniciando fila de retentativas nativa do banco de dados...")
    while True:
        try:
            # Busca um job pendente que já passou do horário de execução
            job = await db.job.find_first(
                where={
                    "status": "PENDING",
                    "runAt": {
                        "lte": datetime.utcnow()
                    }
                },
                order_by={
                    "createdAt": "asc"
                }
            )

            if not job:
                await asyncio.sleep(2) # Dorme se a fila estiver vazia
                continue

            # Lock imediato no banco alterando o status para RUNNING
            # Evita que múltiplas threads executem o mesmo job
            await db.job.update(
                where={"id": job.id},
                data={"status": "RUNNING"}
            )

            print(f"[QUEUE WORKER] Processando Job {job.id} ({job.name})...")
            payload = json.loads(job.payload)
            
            # Busca a função executora registrada
            executor = _registry.get(job.name)
            
            if not executor:
                raise ValueError(f"Nenhum executor registrado para o Job '{job.name}'")

            # Executa o Job
            await executor(payload)

            # Completa com sucesso
            await db.job.update(
                where={"id": job.id},
                data={
                    "status": "COMPLETED",
                    "error": None
                }
            )
            print(f"[QUEUE WORKER] Job {job.id} ({job.name}) concluído com sucesso!")

        except Exception as e:
            if 'job' in locals() and job:
                retries = job.retries + 1
                error_msg = str(e)
                
                if retries >= job.maxRetries:
                    # Falha definitiva
                    await db.job.update(
                        where={"id": job.id},
                        data={
                            "status": "FAILED",
                            "retries": retries,
                            "error": f"Erro crítico final: {error_msg}"
                        }
                    )
                    print(f"[QUEUE WORKER] Job {job.id} ({job.name}) falhou definitivamente após {retries} tentativas: {error_msg}")
                else:
                    # Backoff exponencial: 2, 4, 8, 16, 32 segundos...
                    delay = 2 ** retries
                    next_run = datetime.utcnow() + timedelta(seconds=delay)
                    await db.job.update(
                        where={"id": job.id},
                        data={
                            "status": "PENDING",
                            "retries": retries,
                            "runAt": next_run,
                            "error": error_msg
                        }
                    )
                    print(f"[QUEUE WORKER] Job {job.id} ({job.name}) falhou. Agendando tentativa {retries + 1} para {next_run}. Erro: {error_msg}")
            
            await asyncio.sleep(2)

# -------------------------------------------------------------
# EXEMPLO DE REGISTRO E DEFINIÇÃO DE TAREFAS RESILIENTES
# -------------------------------------------------------------

@register_task("enviar-whatsapp")
async def task_send_whatsapp(payload: Dict[str, Any]):
    """
    Tarefa de envio de WhatsApp resiliente à falha da API da Meta/Evolution.
    """
    phone = payload.get("phone")
    message = payload.get("message")
    
    # Simulação de envio real de API
    print(f"[WHATSAPP SENDER API] Enviando para {phone}: {message}")
    # Se houver falha, lança exceção para a fila fazer o retry exponencial
    # raise Exception("Rate Limit da Meta atingido") 
