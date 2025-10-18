# -*- coding: utf-8 -*-
"""
Контроллер-алиас для Stripe:
- URL: /stripe/webhook  (+ вариант со слэшем на конце)
- Поведение: ровно как у /webhook/stripe из webhook_gateway — сохраняем событие в webhook.event.
Почему делаем отдельный контроллер?
- Некоторые интеграции Stripe по умолчанию ожидают именно /stripe/webhook.
- Мы НЕ повторяем бизнес-обработку — только приём и запись. Дальше заберёт воркер.
"""

from odoo import http
from odoo.http import request
import json

class StripeWebhookAliasController(http.Controller):
    @http.route(
        ["/stripe/webhook", "/stripe/webhook/"],
        type="http", auth="public", methods=["GET", "POST"], csrf=False
    )
    def receive_alias(self, **kwargs):
        """
        GET  → healthcheck (200 OK, полезно для быстрой проверки)
        POST → идентично /webhook/stripe: пишем raw body + headers в webhook.event с provider='stripe'
        """
        # Healthcheck
        if request.httprequest.method == "GET":
            return request.make_response(
                json.dumps({"ok": True, "provider": "stripe", "alias": True}, ensure_ascii=False),
                headers=[("Content-Type", "application/json")]
            )

        # POST-приём
        httpreq = request.httprequest

        raw_bytes = httpreq.get_data() or b""
        try:
            raw_text = raw_bytes.decode(httpreq.charset or "utf-8", errors="replace")
        except Exception:
            raw_text = raw_bytes.decode("utf-8", errors="replace")

        headers = {k.lower(): v for k, v in httpreq.headers.items()}

        # Подсказки/идемпотентность
        event_type = (
            ("stripe" if headers.get("stripe-signature") else None)
            or headers.get("x-event-type")
            or kwargs.get("event")
            or "unknown"
        )
        idem_key = (
            headers.get("idempotency-key")
            or headers.get("stripe-signature")  # валидация подписи потом в воркере/провайдере
            or headers.get("x-request-id")
            or headers.get("x-event-id")
            or ""
        )
        signature = headers.get("stripe-signature") or ""

        # Создаём запись так же, как это делает gateway, но жёстко ставим provider='stripe'
        ev = request.env["webhook.event"].sudo().create({
            "provider": "stripe",
            "event_type": str(event_type)[:128],
            "raw_payload": raw_text,
            "headers": json.dumps(headers, ensure_ascii=False),
            "idempotency_key": idem_key[:256] if idem_key else False,
            "signature": signature[:512] if signature else False,
            "status": "received",
        })

        return request.make_response(
            json.dumps({"stored": True, "id": ev.id}, ensure_ascii=False),
            headers=[("Content-Type", "application/json")]
        )
