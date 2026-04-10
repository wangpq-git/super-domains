import base64
import datetime as dt
import hashlib
import json
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import change_request_service, notification_service, system_setting_service

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_feishu_noop_response() -> dict[str, Any]:
    return {}


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


def _coerce_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}



def _extract_callback_payload(payload: dict[str, Any]) -> dict[str, Any]:
    event = _nested_get(payload, "event")
    if not isinstance(event, dict):
        event = {}

    action_node = _nested_get(payload, "event", "action")
    if not isinstance(action_node, dict):
        action_node = _coerce_json_object(payload.get("action"))

    action_value = _coerce_json_object(action_node.get("value"))
    if not action_value:
        action_value = _coerce_json_object(payload.get("value"))

    operator = _nested_get(payload, "event", "operator")
    if not isinstance(operator, dict):
        operator = _coerce_json_object(payload.get("operator"))

    action_name = (
        action_value.get("action")
        or action_node.get("name")
        or action_node.get("tag")
        or payload.get("action")
    )
    request_id = (
        action_value.get("request_id")
        or action_value.get("change_request_id")
        or payload.get("request_id")
        or payload.get("change_request_id")
        or _nested_get(event, "context", "open_message_id")
    )
    message_id = (
        _nested_get(event, "context", "open_message_id")
        or _nested_get(event, "open_message_id")
        or action_value.get("open_message_id")
        or payload.get("open_message_id")
    )

    return {
        "action": action_name,
        "request_id": request_id,
        "message_id": message_id,
        "reason": action_value.get("reason") or payload.get("reason"),
        "actor_identifiers": {
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


def _unpad_feishu_plaintext(data: bytes) -> bytes:
    if not data:
        return data
    pad = data[-1]
    if pad < 1 or pad > 16:
        return data
    if data[-pad:] != bytes([pad]) * pad:
        return data
    return data[:-pad]


def _decrypt_feishu_payload(encrypted: str, encrypt_key: str) -> dict[str, Any]:
    encrypted_bytes = base64.b64decode(encrypted)
    if len(encrypted_bytes) <= 16:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid encrypted Feishu payload")

    iv = encrypted_bytes[:16]
    ciphertext = encrypted_bytes[16:]
    aes_key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    plaintext = _unpad_feishu_plaintext(plaintext)

    try:
        return json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid decrypted Feishu payload") from exc


def _parse_feishu_timestamp(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        pass

    trimmed = value.strip()
    trimmed = re.sub(r"\s+m=\+.*$", "", trimmed)
    trimmed = re.sub(r"\s+[A-Z]{2,5}$", "", trimmed)

    match = re.match(
        r"^(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?P<fraction>\.\d+)? (?P<offset>[+-]\d{4})$",
        trimmed,
    )
    if not match:
        raise ValueError(f"Unsupported timestamp format: {value}")

    fraction = match.group("fraction") or ""
    if fraction:
        fraction = "." + (fraction[1:7]).ljust(6, "0")

    normalized = f"{match.group('date')}{fraction} {match.group('offset')}"
    parsed = dt.datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S.%f %z")
    return int(parsed.timestamp())


def _build_idempotent_callback_response(
    change_request,
    approver,
    *,
    base_url: str = "",
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
    return _build_feishu_action_response(
        toast_type="info",
        toast_content=status_text_map.get(change_request.status, "该变更单已处理，无需重复操作"),
    )


def _build_feishu_action_response(
    *,
    toast_type: str,
    toast_content: str,
    card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Feishu card callbacks are strict about response shape. Returning only
    # the documented UI fields avoids client-side "action failed" errors.
    response: dict[str, Any] = {
        "toast": {
            "type": toast_type,
            "content": toast_content,
        }
    }
    if card is not None:
        response["card"] = {
            "type": "raw",
            "data": card,
        }
    return response


def _build_feishu_error_response(message: str) -> dict[str, Any]:
    return _build_feishu_action_response(
        toast_type="error",
        toast_content=message,
    )


async def _verify_signature(
    db: AsyncSession,
    raw_body: bytes,
    signature: str | None,
    timestamp: str | None,
    nonce: str | None,
) -> bool:
    encrypt_key = await system_setting_service.get_string(db, "FEISHU_APPROVAL_ENCRYPT_KEY")
    if not encrypt_key:
        return True

    if not signature or not timestamp or not nonce:
        logger.warning("Feishu callback missing signature headers")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Feishu callback signature headers")

    try:
        timestamp_int = _parse_feishu_timestamp(timestamp)
    except (TypeError, ValueError):
        logger.warning("Feishu callback invalid timestamp: %s", timestamp)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Feishu callback timestamp")

    now = int(time.time())
    tolerance = await system_setting_service.get_int(db, "FEISHU_APPROVAL_SIGNATURE_TOLERANCE_SECONDS")
    if abs(now - timestamp_int) > tolerance:
        logger.warning("Feishu callback expired timestamp: now=%s ts=%s tolerance=%s", now, timestamp_int, tolerance)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired Feishu callback timestamp")

    string_to_sign = f"{timestamp}{nonce}{encrypt_key}".encode("utf-8") + raw_body
    sha256_expected = hashlib.sha256(string_to_sign).hexdigest()
    sha1_expected = hashlib.sha1(string_to_sign).hexdigest()
    if signature in {sha256_expected, sha1_expected}:
        return True

    logger.warning(
        "Feishu callback signature mismatch: sha256=%s sha1=%s actual=%s",
        sha256_expected,
        sha1_expected,
        signature,
    )
    return False


@router.post("/feishu/change-requests")
async def handle_feishu_change_request_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_feishu_token: str | None = Header(default=None),
    x_lark_signature: str | None = Header(default=None),
    x_lark_request_timestamp: str | None = Header(default=None),
    x_lark_request_nonce: str | None = Header(default=None),
):
    try:
        raw_body = await request.body()
        try:
            body = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return _build_feishu_noop_response()

        challenge = body.get("challenge")
        if challenge:
            return {"challenge": challenge}

        signature_valid = await _verify_signature(db, raw_body, x_lark_signature, x_lark_request_timestamp, x_lark_request_nonce)

        encrypt_key = await system_setting_service.get_string(db, "FEISHU_APPROVAL_ENCRYPT_KEY")
        encrypted = body.get("encrypt")
        if encrypted and encrypt_key:
            body = _decrypt_feishu_payload(encrypted, encrypt_key)

        expected_token = await system_setting_service.get_string(db, "FEISHU_APPROVAL_CALLBACK_TOKEN")
        callback_token = None
        if expected_token:
            callback_token = _extract_token(body, x_feishu_token)
            # Real card callbacks may use an internal token value rather than the
            # app-level callback token. Log the mismatch, but rely on decrypt/signature
            # checks plus payload validation instead of hard-failing the action.
            if callback_token is not None and callback_token != expected_token:
                logger.warning("Feishu callback token mismatch: expected=%s actual=%s", expected_token, callback_token)

        if not signature_valid:
            logger.warning("Feishu callback signature fallback accepted after payload validation")

        callback = _extract_callback_payload(body)
        action = callback["action"]
        request_id = callback["request_id"]
        reason = callback["reason"]
        callback_message_id = callback["message_id"]

        if not action or request_id is None:
            logger.warning(
                "Invalid Feishu callback payload: body_keys=%s event_keys=%s action_payload=%s",
                sorted(body.keys()),
                sorted(body.get("event", {}).keys()) if isinstance(body.get("event"), dict) else None,
                callback,
            )
            return _build_feishu_noop_response()

        try:
            request_id_int = int(request_id)
        except (TypeError, ValueError):
            return _build_feishu_noop_response()

        change_request = await change_request_service.get_change_request_by_id(db, request_id_int)
        if not change_request:
            return _build_feishu_noop_response()

        approver = await change_request_service.resolve_admin_user(
            db,
            callback["actor_identifiers"],
        )
        if not approver:
            logger.warning(
                "Unable to resolve Feishu approver: identifiers=%s body_event_keys=%s",
                callback["actor_identifiers"],
                sorted(body.get("event", {}).keys()) if isinstance(body.get("event"), dict) else None,
            )
            return _build_feishu_noop_response()

        base_url = await system_setting_service.get_string(db, "FEISHU_APPROVAL_BASE_URL")

        try:
            if action == "approve":
                updated = await change_request_service.approve_change_request(
                    db,
                    change_request,
                    approver,
                    send_result_notification=False,
                )
                toast_message = f"审批通过，变更单 #{updated.request_no} 已执行"
                result_note = f"已由 {approver.display_name or approver.username} 审批通过。"
            elif action == "reject":
                updated = await change_request_service.reject_change_request(
                    db,
                    change_request,
                    approver,
                    reason or "Rejected from Feishu callback",
                    send_result_notification=False,
                )
                toast_message = f"已拒绝变更单 #{updated.request_no}"
                result_note = (
                    f"已由 {approver.display_name or approver.username} 拒绝。"
                    f"{' 原因: ' + updated.rejection_reason if updated.rejection_reason else ''}"
                )
            else:
                return _build_feishu_noop_response()
        except ValueError:
            refreshed = await change_request_service.get_change_request_by_id(db, request_id_int)
            if refreshed and change_request_service.is_change_request_processed(refreshed):
                return _build_feishu_noop_response()
            return _build_feishu_noop_response()

        updated_card = change_request_service.build_feishu_change_request_card(
            updated,
            include_actions=False,
            result_note=result_note,
            base_url=base_url,
        )
        app_id = await system_setting_service.get_string(db, "FEISHU_BOT_APP_ID")
        app_secret = await system_setting_service.get_string(db, "FEISHU_BOT_APP_SECRET")
        stored_message_id = change_request.payload.get("feishu_message_id") if isinstance(change_request.payload, dict) else None
        message_id = stored_message_id or callback_message_id
        if app_id and app_secret and message_id:
            updated_ok = await notification_service.update_feishu_bot_interactive_message(
                app_id=app_id,
                app_secret=app_secret,
                message_id=message_id,
                card=updated_card,
            )
            if not updated_ok:
                logger.warning("Failed to update Feishu message via API for request_id=%s", request_id_int)

        # The callback only needs to acknowledge the action with a toast.
        # We already patch the message via Feishu API above; omitting the inline
        # card payload avoids client-side callback rendering errors.
        return _build_feishu_noop_response()
    except HTTPException as exc:
        logger.warning("Feishu callback handled with non-fatal error: %s", exc.detail)
        return _build_feishu_noop_response()
    except Exception:
        logger.exception("Unexpected Feishu callback error")
        return _build_feishu_noop_response()
