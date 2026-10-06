import json
import urllib.parse
from typing import Optional, List, Dict
from fastapi import Request, Response
from fastapi.responses import RedirectResponse


COOKIE_NAME = "hrms_flash_msg"


def set_flash_message(response: Response, message: str, category: str = "success") -> None:
    """
    Sets a short-lived, one-time flash notification cookie on the response.
    Category can be 'success', 'error', 'warning', or 'info'.
    """
    payload = json.dumps({"message": str(message), "category": str(category)})
    encoded = urllib.parse.quote(payload)
    response.set_cookie(
        key=COOKIE_NAME,
        value=encoded,
        max_age=15,          # Short-lived (15s) so it only survives until the immediate redirect GET
        path="/",
        httponly=False,      # Accessible to frontend for instant cleanup/rendering
        samesite="lax",
    )


def flash_redirect(
    url: str,
    message: str,
    category: str = "success",
    status_code: int = 303,
) -> RedirectResponse:
    """
    Creates a clean HTTP 303 RedirectResponse without query parameters
    and attaches a one-time flash message cookie.
    """
    response = RedirectResponse(url=url, status_code=status_code)
    set_flash_message(response=response, message=message, category=category)
    return response


def extract_flash_messages(request: Request) -> List[Dict[str, str]]:
    """
    Extracts flash messages from both the temporary cookie and query params.
    Returns a list of dicts: [{"message": "...", "category": "success"}, ...]
    """
    messages: List[Dict[str, str]] = []

    # 1. Check flash cookie
    cookie_val = request.cookies.get(COOKIE_NAME)
    if cookie_val:
        try:
            decoded = urllib.parse.unquote(cookie_val)
            data = json.loads(decoded)
            if isinstance(data, dict) and "message" in data:
                messages.append({
                    "message": data["message"],
                    "category": data.get("category", "success"),
                })
        except Exception:
            pass

    # 2. Check fallback query parameters (for backwards compatibility)
    if "success" in request.query_params:
        messages.append({
            "message": request.query_params["success"],
            "category": "success",
        })
    if "error" in request.query_params:
        messages.append({
            "message": request.query_params["error"],
            "category": "error",
        })
    if "warning" in request.query_params:
        messages.append({
            "message": request.query_params["warning"],
            "category": "warning",
        })
    if "info" in request.query_params:
        messages.append({
            "message": request.query_params["info"],
            "category": "info",
        })

    return messages
