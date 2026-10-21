"""
Request guards.

Every state-changing endpoint requires the custom `X-Yashi: 1` header. Browsers
won't send a custom header cross-origin without a CORS preflight, and CORS only
allows the Yashi frontend - so a random website you visit can't change Yashi's
settings, keys or profile through your browser.
"""
from fastapi import Header, HTTPException


async def require_app(x_yashi: str = Header(default="")) -> None:
    if x_yashi != "1":
        raise HTTPException(status_code=403, detail="Missing X-Yashi header")
