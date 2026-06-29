"""Service layer: reusable async business logic shared by the HTTP routers and the
realtime (Socket.IO) transport.

Keeping invite resolution and BoardState assembly here means both entry points
behave identically (same auth rules, same snapshot shape) instead of duplicating
logic in the transport layer.
"""
