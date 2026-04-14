"""Role-based access helpers and decorators.

Provides simple helpers usable by both UI code and FastAPI endpoints.

Functions:
- `has_role(user, role_name)` - check if user has role
- `require_roles(*roles)` - decorator that checks `user` kwarg or first arg
- `require_roles_dep(*roles)` - FastAPI dependency generator
"""
from functools import wraps
from typing import Callable, Any
from exceptions import AuthorizationError


def _extract_roles_from_user(user) -> list:
    if user is None:
        return []
    # Accept dict-like user with 'role' or 'roles'
    try:
        if isinstance(user, dict):
            if 'roles' in user and isinstance(user['roles'], (list, tuple)):
                return list(user['roles'])
            if 'role' in user and user.get('role'):
                return [user.get('role')]
    except Exception:
        pass
    # If SQLAlchemy User model with roles relationship, try to read
    try:
        roles_attr = getattr(user, 'roles', None)
        if roles_attr is None:
            # maybe a single role attribute
            r = getattr(user, 'role', None)
            return [r] if r else []
        return [getattr(r, 'name', str(r)) for r in roles_attr]
    except Exception:
        return []


def has_role(user, role_name: str) -> bool:
    roles = _extract_roles_from_user(user)
    return role_name in roles


def require_roles(*required_roles: str):
    """Decorator for functions that accept a `user` kwarg (or whose first arg is user).

    If the user does not have one of the required roles, raises `AuthorizationError`.
    """
    def decorator(fn: Callable[..., Any]):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = kwargs.get('user')
            if user is None and args:
                user = args[0]
            if user is None:
                raise AuthorizationError('Missing user for authorization')
            roles = _extract_roles_from_user(user)
            for r in required_roles:
                if r in roles:
                    return fn(*args, **kwargs)
            raise AuthorizationError('Insufficient permissions')
        return wrapper
    return decorator


def require_roles_dep(*required_roles: str):
    """Return a FastAPI dependency function that expects `user` to be provided by auth.

    Example:
        @app.get('/admin')
        async def admin_view(user: dict = Depends(require_roles_dep('admin'))):
            ...
    """
    def _dep(user= None):
        if user is None:
            raise AuthorizationError('Not authenticated')
        roles = _extract_roles_from_user(user)
        for r in required_roles:
            if r in roles:
                return user
        raise AuthorizationError('Insufficient permissions')

    return _dep
