"""Bound API concurrency before dependencies acquire database connections."""
import asyncio
from starlette.types import ASGIApp, Receive, Scope, Send


class DatabaseAdmissionMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app
        # The shared SQLAlchemy pool permits 15 connections. Reserve capacity
        # for readiness, retention and response cleanup. Waiting is asynchronous.
        self.slots = asyncio.Semaphore(10)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope['type'] == 'http' and scope['path'].startswith('/api/'):
            async with self.slots:
                # Hold the slot through response completion AND dependency cleanup.
                await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)
