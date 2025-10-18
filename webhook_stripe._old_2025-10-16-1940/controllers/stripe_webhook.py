# -*- coding: utf-8 -*-
import os
import json
import time
import hmac
import hashlib
import logging

from odoo import http, tools
from odoo.http import request

_logger = logging.getLogger(__name__)


class StripeWebhookController(http.Controller):
    """
    Эндпоинт Stripe: POST /stripe/webhook
    - Проверка подписи в заголовке `Stripe-Signature` (если задан секрет).
    - Извлекаем order_id из metadata.order_id или client_reference_id.
    - Пишем полное событие в файл data_dir/webhook_stripe/payments/<order_id>.json
      в виде массива событий (append).
    """

    # ---- ПУБЛИЧНЫЙ РОУТ ДЛЯ STRIPE ----
    @http.route("/stripe/webhook", type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def stripe_webhook(self, **kwargs):
        # Сырый payload (нужен для проверки подписи)
        raw = request.httprequest.get_data()
        payload = raw.decode("utf-8", errors="ignore")
        sig_header = request.httprequest.headers.get("Stripe-Signature", "")

        # Настройки из Системных параметров
        icp = request.env["ir.config_parameter"].sudo()
        signing_secret = icp.get_param("webhook_stripe.signing_secret", default="")  # whsec_***
        custom_dir = icp.get_param("webhook_stripe.payments_dir", default="")

        # Базовая папка для сохранения: <data_dir>/webhook_stripe/payments
        try:
            data_dir = tools.config.get("data_dir") or "/var/lib/odoo"
        except Exception:
            data_dir = "/var/lib/odoo"

        base_dir = custom_dir or os.path.join(data_dir, "webhook_stripe", "payments")
        os.makedirs(base_dir, exist_ok=True)

        # 1) Проверяем подпись, если секрет указан
        if signing_secret and sig_header:
            try:
                self._verify_signature(payload, sig_header, signing_secret)
            except Exception as e:
                _logger.warning("Stripe signature verification failed: %s", e)
                return http.Response("invalid signature", status=400)

        # 2) Парсим JSON
        try:
            event = json.loads(payload)
        except Exception as e:
            _logger.exception("Stripe webhook: bad JSON: %s", e)
            return http.Response("bad json", status=400)

        # 3) Извлекаем order_id (несколько стратегий)
        order_id = self._extract_order_id(event)
        if not order_id:
            # Фоллбек: берём id объекта или самого события
            order_id = event.get("data", {}).get("object", {}).get("id") or event.get("id") or f"no_order_{int(time.time())}"

        # 4) Формируем запись события (для наглядности и стабильности)
        record = {
            "received_at_ts": int(time.time()),
            "event_id": event.get("id"),
            "event_type": event.get("type"),
            "payload": event,  # Полный JSON события
        }

        # 5) Пишем (append) в <order_id>.json (массив events)
        path = os.path.join(base_dir, f"{order_id}.json")
        try:
            # читаем, если уже есть
            events = []
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    if isinstance(existing, dict) and "events" in existing:
                        events = existing["events"]
                    elif isinstance(existing, list):
                        events = existing
                    else:
                        # если формат иной — аккуратно оборачиваем
                        events = [existing]

            events.append(record)
            wrapper = {"order_id": order_id, "events": events}

            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(wrapper, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)

            _logger.info("Stripe webhook saved: %s", path)
        except Exception as e:
            _logger.exception("Stripe webhook: failed to write file: %s", e)
            return http.Response("write error", status=500)

        # 6) Возвращаем 200 OK
        return http.Response("ok", status=200, mimetype="text/plain")

    # ---------------------------
    # Вспомогательные методы
    # ---------------------------
    def _verify_signature(self, payload: str, sig_header: str, secret: str, tolerance: int = 300):
        """
        Верификация Stripe-Signature без SDK.
        Заголовок вида: "t=1699999999,v1=<hex>,v1=<hex>..."
        Подпись считается по строке: f"{t}.{payload}", HMAC-SHA256(secret).
        """
        if not sig_header:
            raise ValueError("Missing Stripe-Signature header")

        parts = dict(x.split("=", 1) for x in sig_header.split(",") if "=" in x)
        t = parts.get("t")
        v1_all = [p.split("=", 1)[1] for p in sig_header.split(",") if p.strip().startswith("v1=")]

        if not t or not v1_all:
            raise ValueError("Invalid Stripe-Signature format")

        # Проверка времени (реплей-атаки)
        now = int(time.time())
        try:
            ts = int(t)
        except Exception:
            raise ValueError("Invalid timestamp in Stripe-Signature")
        if abs(now - ts) > tolerance:
            raise ValueError("Timestamp outside tolerance")

        signed_payload = f"{t}.{payload}".encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

        if expected not in v1_all:
            raise ValueError("Signature mismatch")

    def _extract_order_id(self, event: dict) -> str:
        """
        Пытаемся вытащить order_id из разных мест:
        - data.object.metadata.order_id
        - data.object.metadata.orderId
        - data.object.client_reference_id (для checkout.session.completed)
        - data.object.charges.data[0].metadata.order_id
        - data.object.payment_intent (если вы прокидываете order_id туда)
        """
        obj = (event or {}).get("data", {}).get("object", {}) or {}

        # metadata
        meta = obj.get("metadata") or {}
        for key in ("order_id", "orderId", "orderID", "pedido_id", "pedidoId"):
            if key in meta and meta[key]:
                return str(meta[key])

        # client_reference_id (checkout.session.*)
        if obj.get("client_reference_id"):
            return str(obj.get("client_reference_id"))

        # charges -> metadata
        charges = obj.get("charges", {}).get("data") or []
        if charges:
            cmeta = (charges[0] or {}).get("metadata") or {}
            if "order_id" in cmeta and cmeta["order_id"]:
                return str(cmeta["order_id"])

        # ничего не нашли
        return ""
