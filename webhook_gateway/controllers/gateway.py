# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json

class WebhookGatewayController(http.Controller):
    @http.route(
        ["/webhook/<string:provider>", "/webhook/<string:provider>/"],
        type="http", auth="public", methods=["GET", "POST"], csrf=False
    )
    def receive(self, provider, **kwargs):
        """
        GET  → healthcheck (не пишет в БД, просто отвечает 200)
        POST → сохраняет сырые данные в webhook.event и сразу отвечает 200
        """
        # 1) Healthcheck
        if request.httprequest.method == "GET":
            payload = {"ok": True, "provider": provider}
            return request.make_response(
                json.dumps(payload, ensure_ascii=False),
                headers=[("Content-Type", "application/json")]
            )

        # 2) POST: приём и запись события
        httpreq = request.httprequest

        # Тело запроса (bytes → str)
        raw_bytes = httpreq.get_data() or b""
        try:
            raw_text = raw_bytes.decode(httpreq.charset or "utf-8", errors="replace")
        except Exception:
            raw_text = raw_bytes.decode("utf-8", errors="replace")

        # Заголовки (lower-case ключи для удобства)
        headers = {k.lower(): v for k, v in httpreq.headers.items()}

        # Подсказки по типу/идемпотентности/подписи
        event_type = (
            ("stripe" if headers.get("stripe-signature") else None)
            or headers.get("x-github-event")
            or headers.get("x-event-type")
            or kwargs.get("event")
            or "unknown"
        )

        idem_key = (
            headers.get("idempotency-key")
            or headers.get("stripe-signature")
            or headers.get("x-request-id")
            or headers.get("x-event-id")
            or ""
        )

        signature = (
            headers.get("stripe-signature")
            or headers.get("x-payzen-signature")
            or headers.get("paypal-transmission-sig")
            or ""
        )

        # Создаём запись webhook.event
        ev = request.env["webhook.event"].sudo().create({
            "provider": provider,
            "event_type": str(event_type)[:128],
            "raw_payload": raw_text,
            "headers": json.dumps(headers, ensure_ascii=False),
            "idempotency_key": idem_key[:256] if idem_key else False,
            "signature": signature[:512] if signature else False,
            "status": "received",
        })

        # Быстрый ответ клиенту — обработка позже (cron/очередь)
        return request.make_response(
            json.dumps({"stored": True, "id": ev.id}, ensure_ascii=False),
            headers=[("Content-Type", "application/json")]
        )
