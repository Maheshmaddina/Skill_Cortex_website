"""ASGI entry point for serverless hosting (Vercel): the API served under /api, as the frontend expects.

The Docker setup strips /api in Caddy instead; here the prefix is handled by mounting the app.
"""

from starlette.applications import Starlette
from starlette.routing import Mount

from app.main import app as api_app

app = Starlette(routes=[Mount("/api", app=api_app)])
