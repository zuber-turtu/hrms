from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.dependencies import require_auth
from app.models.employee import Employee

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: Employee = Depends(require_auth),
):
    return templates.TemplateResponse(request, "dashboard/dashboard.html", {"user": current_user})
