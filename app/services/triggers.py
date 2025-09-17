from datetime import datetime, timezone
from app.services.storage import save_version, mark_old_version_as_stale, load_versions, log_action
from app.models.schemas.user import RefreshToken

def on_user_suspended(user_id: str, reason: str, admin_id: str):
    """
    Trigger executed whenever a user is suspended.
    """
    # Invalidate refresh tokens
    tokens = load_versions("refresh_tokens", RefreshToken)
    active_tokens = tokens[(tokens["user_id"] == str(user_id)) & (tokens["is_current"])]
    for _, token in active_tokens.iterrows():
        mark_old_version_as_stale("refresh_tokens", token["refresh_token_id"], "refresh_token_id")

    # Log action
    log_action(admin_id, "suspend", "users", str(user_id), {"reason": reason})


def on_user_unsuspended(user_id: str, admin_id: str):
    """
    Trigger executed whenever a user is unsuspended.
    """
    log_action(admin_id, "unsuspend", "users", str(user_id))


def on_password_change(user_id: str):
    """
    Trigger executed whenever a password is changed.
    """
    # Invalidate all refresh tokens (force re-login everywhere)
    tokens = load_versions("refresh_tokens", RefreshToken)
    active_tokens = tokens[(tokens["user_id"] == str(user_id)) & (tokens["is_current"])]
    for _, token in active_tokens.iterrows():
        mark_old_version_as_stale("refresh_tokens", token["refresh_token_id"], "refresh_token_id")

    log_action(user_id, "change_password", "users", str(user_id))
