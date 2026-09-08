"""Compatibilidade: `uvicorn main:app` continua funcionando. O app vive em app.main."""

from app.main import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn

    from app.config import get_settings

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=s.app_env == "development")
