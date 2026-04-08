import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.services import change_request_service

router = APIRouter()


def _nested_get(data: dict[str, Any], *path: str) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _extract_token(payload: dict[str, Any], header_token: str | None) -> str | None:
    return (
        header_token
        or payload.get("token")
        or _nested_get(payload, "header", "token")
        or _nested_get(payload, "event", "token")
    )


def _extract_callback_payload(payload: dict[str, Any]) -> dict[str, Any]:
    action_value = _nested_get(payload, "event", "action", "value")
    if not isinstance(action_value, dict):
        action_value = {}

    operator = _nested_get(payload, "event", "operator")
    if not isinstance(operator, dict):
        operator = {}

    return {
        "action": action_value.get("action") or payload.get("action"),
        "request_id": action_value.get("request_id") or payload.get("request_id"),
        "approver_user_id": action_value.get("approver_user_id") or payload.get("approver_user_id"),
        "reason": action_value.get("reason") or payload.get("reason"),
        "actor_identifiers": {
            "local_user_id": action_value.get("approver_user_id") or payload.get("approver_user_id"),
            "username": (
                action_value.get("approver_username")
                or operator.get("username")
                or operator.get("name")
                or payload.get("approver_username")
            ),
            "email": action_value.get("approver_email") or operator.get("email") or payload.get("approver_email"),
            "open_id": action_value.get("open_id") or operator.get("open_id") or payload.get("open_id"),
            "union_id": action_value.get("union_id") or operator.get("union_id") or payload.get("union_id"),
            "user_id": action_value.get("user_id") or operator.get("user_id") or payload.get("user_id"),
            "employee_id": action_value.get("employee_id") or operator.get("employee_id") or payload.get("employee_id"),
        },
    }


def _build_idempotent_callback_response(
    change_request,
    approver,
) -> dict[str, Any]:
    status_text_map = {
        change_request_service.STATUS_SUCCEEDED: "该变更单已处理完成，无需重复操作",
        change_request_service.STATUS_REJECTED: "该变更单已被拒绝，无需重复操作",
        change_request_service.STATUS_CANCELLED: "该变更单已取消，无需重复操作",
        change_request_service.STATUS_FAILED: "该变更单已执行失败，无需重复操作",
    }
    result_note_map = {
        change_request_service.STATUS_SUCCEEDED: f"已由 {change_request.approver_name or approver.username} 审批通过并执行完成。",
        change_request_service.STATUS_REJECTED: (
            f"已由 {change_request.approver_name or approver.username} 拒绝。"
            f"{' 原因: ' + change_request.rejection_reason if change_request.rejection_reason else ''}"
        ),
        change_request_service.STATUS_CANCELLED: "该变更单已取消。",
        change_request_service.STATUS_FAILED: (
            f"已由 {change_request.approver_name or approver.username} 审批通过，但执行失败。"
            f"{' 错误: ' + change_request.error_message if change_request.error_message else ''}"
        ),
    }
    return {
        "ok": True,
        "request_id": change_request.id,
        "status": change_request.status,
        "approver_user_id": change_request.approver_user_id or approver.id,
        "idempotent": True,
        "toast": {
            "type": "info",
            "content": status_text_map.get(change_request.status, "该变更单已处理，无需重复操作"),
        },
        "card": change_request_service.build_feishu_change_request_card(
            change_request,
            include_actions=False,
            result_note=result_note_map.get(change_request.status, "该变更单已处理。"),
        ),
    }


def _verify_signature(
    raw_body: bytes,
    signature: str | None,
    timestamp: str | None,
    nonce: str | None,
) -> None:
    encrypt_key = settings.FEISHU_APPROVAL_ENCRYPT_KEY
    if not encrypt_key:
        return

    if not signature or not timestamp or not nonce:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Feishu callback signature headers")

    try:
        timestamp_int = int(timestamp)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Feishu callback timestamp")

    now = int(time.time())
    tolerance = settings.FEISHU_APPROVAL_SIGNATURE_TOLERANCE_SECONDS
    if abs(now - timestamp_int) > tolerance:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired Feishu callback timestamp")

    string_to_sign = f"{timestamp}{nonce}{encrypt_key}".encode("utf-8") + raw_body
    digest = hmac.new(encrypt_key.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Feishu callback signature")


@router.post("/feishu/change-requests")
async def handle_feishu_change_request_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_feishu_token: str | None = Header(default=None),
    x_lark_signature: str | None = Header(default=None),
    x_lark_request_timestamp: str | None = Header(default=None),
    x_lark_request_nonce: str | None = Header(default=None),
):
    raw_body = await request.body()
    try:
        body = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    challenge = body.get("challenge")
    if challenge:
        return {"challenge": challenge}

    expected_token = settings.FEISHU_APPROVAL_CALLBACK_TOKEN
    if expected_token:
        callback_token = _extract_token(body, x_feishu_token)
        if callback_token != expected_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Feishu callback token")

    _verify_signature(raw_body, x_lark_signature, x_lark_request_timestamp, x_lark_request_nonce)

    callback = _extract_callback_payload(body)
    action = callback["action"]
    request_id = callback["request_id"]
    reason = callback["reason"]

    if not action or request_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid callback payload")

    try:
        request_id_int = int(request_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid callback identifiers")

    change_request = await change_request_service.get_change_request_by_id(db, request_id_int)
    if not change_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")

    approver = await change_request_service.resolve_admin_user(
        db,
        callback["actor_identifiers"],
    )
    if not approver:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approver is not an active admin")

    try:
        if action == "approve":
            updated = await change_request_service.approve_change_request(db, change_request, approver)
            toast_message = f"审批通过，变更单 #{updated.request_no} 已执行"
            result_note = f"已由 {approver.display_name or approver.username} 审批通过。"
        elif action == "reject":
            updated = await change_request_service.reject_change_request(
                db,
                change_request,
                approver,
                reason or "Rejected from Feishu callback",
            )
            toast_message = f"已拒绝变更单 #{updated.request_no}"
            result_note = (
                f"已由 {approver.display_name or approver.username} 拒绝。"
                f"{' 原因: ' + updated.rejection_reason if updated.rejection_reason else ''}"
            )
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported callback action")
    except ValueError as exc:
        refreshed = await change_request_service.get_change_request_by_id(db, request_id_int)
        if refreshed and change_request_service.is_change_request_processed(refreshed):
            return _build_idempotent_callback_response(refreshed, approver)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return {
        "ok": True,
        "request_id": updated.id,
        "status": updated.status,
        "approver_user_id": approver.id,
        "toast": {
            "type": "success",
            "content": toast_message,
        },
        "card": change_request_service.build_feishu_change_request_card(
            updated,
            include_actions=False,
            result_note=result_note,
        ),
    }
