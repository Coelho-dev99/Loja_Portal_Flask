from functools import wraps

from flask import redirect, request, session, url_for


def login_required(view):
    """Protege uma rota: so entra quem fez login no painel."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped
