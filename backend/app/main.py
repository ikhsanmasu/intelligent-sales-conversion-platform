from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.agents.alert.router import router as alert_router
from app.agents.browser.router import router as browser_router
from app.agents.chart.router import router as chart_router
from app.agents.compare.router import router as compare_router
from app.agents.database.router import router as database_router
from app.agents.memory.router import router as memory_router
from app.agents.report.router import router as report_router
from app.agents.timeseries.router import router as timeseries_router
from app.core.database import close_app_database, init_app_database
from app.core.logging import setup_logging
from app.middleware.cors import setup_cors
from app.modules.admin.router import router as admin_router
from app.modules.chatbot.router import router as chatbot_router

setup_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_app_database()
    try:
        yield
    finally:
        close_app_database()


app = FastAPI(title="M Agent API", lifespan=lifespan)

setup_cors(app)

app.include_router(chatbot_router)
app.include_router(database_router)
app.include_router(browser_router)
app.include_router(chart_router)
app.include_router(memory_router)
app.include_router(report_router)
app.include_router(timeseries_router)
app.include_router(compare_router)
app.include_router(alert_router)
app.include_router(admin_router)
