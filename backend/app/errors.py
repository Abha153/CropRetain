"""
Backend error-code architecture -- i18n Phase 6.

WHY THIS EXISTS
----------------
Every `raise HTTPException(status_code=..., detail="Some English sentence")`
in this codebase (there are ~200 of them across app/routers/) puts a raw
English sentence directly into the JSON error body, and the frontend
currently displays that sentence verbatim (see frontend/src/api/client.js
`request()`: `detail = errJson.detail || detail`; then
`throw new Error(detail)`; then most pages do `setError(err.message)`).
That means every backend-originated error is unavoidably English, in
every language, for every user -- a real, structural i18n gap.

WHAT THIS MODULE DOES
----------------------
`AppError` is a drop-in HTTPException subclass: raise it exactly like
HTTPException, with the same human-readable `detail` string, so nothing
that already depends on `detail` being a plain English string breaks.
It additionally carries a stable, machine-readable `code`
(e.g. "PAYMENT_AMOUNT_MISMATCH"). The exception handler registered in
app/main.py (see `install_error_handlers`) adds that code as a sibling
`code` field in the JSON body -- `detail` is completely unchanged, so
this is purely additive:

    {"detail": "Payment amount must match the transaction total", "code": "PAYMENT_AMOUNT_MISMATCH"}

The frontend can start preferring `errJson.code` (translating it via
`t('errors.' + code)`) wherever it's present, while every endpoint that
hasn't been migrated to AppError yet keeps working exactly as before --
`errJson.code` is simply absent for those, and existing `detail`-based
error display is untouched either way.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-------------------------------------------
It does not migrate all ~200 raise sites. Per this phase's scope, the
architecture is what needed to exist first; migrating every call site is
listed as NOT YET DONE in I18N_STATUS.md. A handful of representative
call sites (in the routers touched by earlier fixes this session --
payments.py, logistics.py) were migrated as a proof of the pattern.

USAGE
-----
    from app.errors import AppError

    raise AppError(status_code=400, code="PAYMENT_AMOUNT_MISMATCH",
                    detail=f"Payment amount must match the transaction total (...)")

If a call site has no natural stable code yet, keep using plain
HTTPException -- do not invent a throwaway code just to satisfy this
module; an un-migrated site is honestly represented as such.
"""
from fastapi import HTTPException


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, detail: str, headers: dict | None = None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


def install_error_handlers(app) -> None:
    """Call once from app/main.py. Adds a `code` field to the JSON body
    of any AppError, leaving every plain HTTPException (the ~200
    un-migrated call sites) rendered exactly as FastAPI already does --
    this handler only fires for AppError specifically."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
            headers=exc.headers,
        )
