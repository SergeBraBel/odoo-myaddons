# -*- coding: utf-8 -*-
from odoo import models

class WebhookProviderMixin(models.AbstractModel):
    _name = "webhook.provider.mixin"
    _description = "Interface for webhook provider adapters"

    def verify(self, event_record):
        """
        Должен вернуть True/False.
        Адаптер провайдера (Stripe/PayZen/PayPal) переопределит эту логику и проверит подпись.
        event_record: recordset webhook.event (одна запись)
        """
        return True

    def normalize(self, event_record):
        """
        Должен вернуть Питон-словарь с унифицированными ключами,
        например: {"kind": "payment.succeeded", "provider": "...", "payload": {...}}
        """
        return {}
