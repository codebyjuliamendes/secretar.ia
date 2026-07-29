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
    Loop infinito rodando em background que consome e executa os Jobs de forma concorrente.
    Implementa controle de backpressure usando Semáforo do asyncio para evitar sobrecarga.
    """
    print("[QUEUE WORKER] Iniciando fila de retentativas nativa concorrente (Max: 5 paralelizações)...")
    semaphore = asyncio.Semaphore(5)

    async def run_job_task(job_data):
        try:
            print(f"[QUEUE WORKER] Processando Job {job_data.id} ({job_data.name}) em background...")
            payload = json.loads(job_data.payload)
            
            # Busca a função executora registrada
            executor = _registry.get(job_data.name)
            if not executor:
                raise ValueError(f"Nenhum executor registrado para o Job '{job_data.name}'")

            # Executa a tarefa de forma assíncrona
            await executor(payload)

            # Completa com sucesso no banco de dados
            await db.job.update(
                where={"id": job_data.id},
                data={
                    "status": "COMPLETED",
                    "error": None
                }
            )
            print(f"[QUEUE WORKER] Job {job_data.id} ({job_data.name}) concluido com sucesso!")
        except Exception as e:
            retries = job_data.retries + 1
            error_msg = str(e)
            
            if retries >= job_data.maxRetries:
                # Falha definitiva
                await db.job.update(
                    where={"id": job_data.id},
                    data={
                        "status": "FAILED",
                        "retries": retries,
                        "error": f"Erro critico final: {error_msg}"
                    }
                )
                print(f"[QUEUE WORKER] Job {job_data.id} ({job_data.name}) falhou definitivamente apos {retries} tentativas: {error_msg}")
            else:
                # Backoff exponencial: 2, 4, 8, 16, 32 segundos...
                delay = 2 ** retries
                next_run = datetime.utcnow() + timedelta(seconds=delay)
                await db.job.update(
                    where={"id": job_data.id},
                    data={
                        "status": "PENDING",
                        "retries": retries,
                        "runAt": next_run,
                        "error": error_msg
                    }
                )
                print(f"[QUEUE WORKER] Job {job_data.id} ({job_data.name}) falhou. Agendando retry {retries + 1} para {next_run}. Erro: {error_msg}")
        finally:
            # Libera o slot do semáforo para a próxima tarefa
            semaphore.release()

    while True:
        try:
            # Adquire um slot no semáforo (bloqueia se já tiver 5 tarefas rodando)
            await semaphore.acquire()

            # Busca o próximo job pendente no horário correto
            job = await db.job.find_first(
                where={
                    "status": "PENDING",
                    "runAt": {
                        "lte": datetime.utcnow()
                    }
                },
                order={
                    "createdAt": "asc"
                }
            )

            if not job:
                # Libera o slot e aguarda se a fila estiver vazia
                semaphore.release()
                await asyncio.sleep(2)
                continue

            # Lock imediato no banco alterando o status para RUNNING
            # Evita que outros workers/pods concorrentes processem a mesma tarefa
            await db.job.update(
                where={"id": job.id},
                data={"status": "RUNNING"}
            )

            # Dispara a execução assíncrona sem bloquear o loop principal
            asyncio.create_task(run_job_task(job))

        except Exception as e:
            print(f"[QUEUE WORKER ERROR] Loop principal falhou: {str(e)}")
            # Liberação preventiva caso falhe no meio da transação do loop principal
            try:
                semaphore.release()
            except ValueError:
                pass
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
