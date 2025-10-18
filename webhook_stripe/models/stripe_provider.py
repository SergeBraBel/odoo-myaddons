# -*- coding: utf-8 -*-
import hmac
import hashlib
from odoo import api, models

class StripeProvider(models.AbstractModel):
    """
    Провайдер Stripe:
    - verify(event_record): верифицирует подпись вебхука, если секрет настроен.
    - Использует стандарт Stripe: заголовок `Stripe-Signature` содержит t=..., v1=...
      Проверка: HMAC_SHA256(secret, f"{t}.{raw_body}") == v1
    """
    _name = "stripe.provider"
    _inherit = "webhook.provider.mixin"
    _description = "Stripe provider: signature verify & normalization"

    @api.model
    def _get_secret(self):
        """
        Берём секрет из System Parameters:
          key = 'stripe.webhook_secret'
        Пустое значение => проверку пропускаем (полезно на тестовом стенде).
        """
        return self.env["ir.config_parameter"].sudo().get_param("stripe.webhook_secret", "").strip()

    @api.model
    def _get_header_dict(self, event_record):
        """
        Наш gateway сохранил заголовки как JSON-строку (lower-case ключи).
        Вернём dict с удобным доступом. Если парсинг не удался — пустой dict.
        """
        try:
            import json
            return json.loads(event_record.headers or "{}") or {}
        except Exception:
            return {}

    @api.model
    def _parse_stripe_signature(self, sig_header):
        """
        Пример заголовка:
          t=1729074939,v1=9b59...,v0=...
        Возвращаем (timestamp_str, signature_hex) или (None, None).
        """
        if not sig_header:
            return None, None
        parts = {}
        for chunk in sig_header.split(","):
            if "=" in chunk:
                k, v = chunk.split("=", 1)
                parts[k.strip()] = v.strip()
        return parts.get("t"), parts.get("v1")

    @api.model
    def verify(self, event_record):
        """
        True  — если подпись валидна ИЛИ секрет пустой (режим обучения).
        False — если секрет задан и подпись не сошлась/неполна.
        """
        secret = self._get_secret()
        # Если секрет не настроен — позволяем пройти (чтобы не блокировать стенд),
        # но в реале стоит требовать секрет.
        if not secret:
            return True

        headers = self._get_header_dict(event_record)
        sig_header = headers.get("stripe-signature")
        if not sig_header:
            return False

        t, v1 = self._parse_stripe_signature(sig_header)
        if not t or not v1:
            return False

        # Строка, которую подписывал Stripe: "{timestamp}.{raw_body}"
        signed_payload = f"{t}.{event_record.raw_payload or ''}".encode("utf-8")
        digest = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

        # Сравнение HMAC в постоянном времени
        return hmac.compare_digest(digest, v1)
