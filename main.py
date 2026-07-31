import uvicorn

from src.application import create_app
from src.config import get_settings


settings = get_settings()
app = create_app(settings)


if __name__ == "__main__":
    uvicorn.run(app, host=settings.server_host, port=settings.server_port)
