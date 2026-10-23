import logging
import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.core.storage_errors import install_storage_handlers
from app.core.http_security import install_http_security
from app.repositories.google_sheets import (
    test_google_sheets_connection,
)
from app.routes.auth import router as auth_router
from app.electricity.routes import router as electricity_router
from app.history.routes import router as history_router
from app.appliances.routes import router as appliances_router
from app.analysis.routes import router as analysis_router
from app.settings.routes import router as settings_router
from app.advice.routes import router as advice_router
from app.reports.routes import router as reports_router
from app.dashboard.routes import router as dashboard_router

from app.dependencies.auth import (
    require_admin,
    get_current_user_for_page,
)

app = FastAPI(
    title="Electricity Tracker API",
    description="Backend API for Electricity Tracker",
    version="1.0.0",
    docs_url=None if os.getenv('APP_ENV') == 'production' else '/docs',
    redoc_url=None if os.getenv('APP_ENV') == 'production' else '/redoc',
    openapi_url=None if os.getenv('APP_ENV') == 'production' else '/openapi.json',
)
install_http_security(app)

# กำหนดเส้นทางสำหรับ API Authentication
app.include_router(auth_router)
install_storage_handlers(app)
app.include_router(electricity_router)
app.include_router(history_router)
app.include_router(appliances_router)
app.include_router(analysis_router)
app.include_router(settings_router)
app.include_router(advice_router)
app.include_router(reports_router)
app.include_router(dashboard_router)


# =========================================
# API TEST
# =========================================

@app.get("/api")
async def api_root():

    return {
        "message": "Electricity Tracker API is running"
    }


@app.get("/health")
async def health_check():

    return {
        "status": "ok"
    }

#endpoint เชื่อมต่อ กับ Google Sheets API
@app.get("/api/google-sheets/health")
def google_sheets_health(current_user: dict = Depends(require_admin)):

    try:

        sheet_info = test_google_sheets_connection()

        return {
            "status": "connected",
            "google_sheets": sheet_info,
        }

    except Exception as error:
        logging.getLogger(__name__).warning('Sheets diagnostic unavailable: %s', type(error).__name__)
        raise HTTPException(503, 'ระบบจัดเก็บข้อมูลไม่พร้อมใช้งาน') from None


# =========================================
# PAGE ROUTES
# =========================================

@app.get("/")
async def root():

    return FileResponse(
        "/frontend/login/login.html"
    )

# เส้นทางหน้า login 
@app.get("/login")
def login_page(
    current_user: dict | None = Depends(
        get_current_user_for_page
    ),
):

    # ยังไม่ได้ Login
    if not current_user:

        return FileResponse(
            "/frontend/login/login.html"
        )


    # User login อยู่แล้ว
    if current_user["role"] == "user":

        return RedirectResponse(
            url="/dashboard",
            status_code=302,
        )


    # Admin login อยู่แล้ว
    if current_user["role"] == "admin":

        return RedirectResponse(
            url="/admin/dashboard",
            status_code=302,
        )


    return FileResponse('/frontend/login/login.html', headers=no_cache_headers())

# เส้นทางหน้า register
@app.get("/register")
async def register_page():

    return FileResponse(
        "/frontend/register/register.html"
    )

# เส้นทางหน้า dashboard
@app.get("/dashboard")
def dashboard_page(
    current_user: dict | None = Depends(
        get_current_user_for_page
    ),
):

    # =====================================
    # NOT LOGGED IN
    # =====================================

    if not current_user:

        return RedirectResponse(
            url="/login",
            status_code=302,
        )


    # =====================================
    # ADMIN
    #
    # Admin ห้ามเข้า User Dashboard
    # =====================================

    if current_user["role"] == "admin":

        return RedirectResponse(
            url="/admin/dashboard",
            status_code=302,
        )


    # =====================================
    # USER ONLY
    # =====================================

    if current_user["role"] != "user":

        return RedirectResponse(
            url="/login",
            status_code=302,
        )


    return FileResponse(
        "/frontend/dashboard/dashboard.html"
    )

# No cache headers for static files
def no_cache_headers() -> dict:

    return {
        "Cache-Control":
            "no-store, no-cache, must-revalidate, max-age=0",

        "Pragma":
            "no-cache",

        "Expires":
            "0",
    }


# เส้นทางหน้า admin
@app.get("/admin/dashboard")
def admin_dashboard_page(
    current_user: dict | None = Depends(
        get_current_user_for_page
    ),
):

    # =====================================
    # NOT LOGGED IN
    # =====================================

    if not current_user:

        return RedirectResponse(
            url="/login",
            status_code=302,
        )


    # =====================================
    # USER
    #
    # User ห้ามเข้า Admin Dashboard
    # =====================================

    if current_user["role"] == "user":

        return RedirectResponse(
            url="/dashboard",
            status_code=302,
        )


    # =====================================
    # ADMIN ONLY
    # =====================================

    if current_user["role"] != "admin":

        return RedirectResponse(
            url="/login",
            status_code=302,
        )


    return FileResponse(
        "/frontend/admin_dashboard/admin_dashboard.html"
    )

# ==========================================
# ADD ELECTRICITY PAGE
# ==========================================

@app.get(
    "/add-electricity"
)
def add_electricity_page(
    current_user: dict | None = Depends(
        get_current_user_for_page
    ),
):

    # ======================================
    # NOT LOGGED IN
    # ======================================

    if not current_user:

        return RedirectResponse(
            url="/login",
            status_code=302,
        )


    # ======================================
    # ADMIN
    # ======================================

    if current_user["role"] == "admin":

        return RedirectResponse(
            url="/admin/dashboard",
            status_code=302,
        )


    # ======================================
    # USER ONLY
    # ======================================

    if current_user["role"] != "user":

        return RedirectResponse(
            url="/login",
            status_code=302,
        )


    return FileResponse(

        "/frontend/"
        "add_electricity/"
        "add_electricity.html",
        headers=no_cache_headers(),

    )

# =========================================
# STATIC FRONTEND FILES
# =========================================

app.mount(
    "/frontend",
    StaticFiles(directory="/frontend"),
    name="frontend"
)


