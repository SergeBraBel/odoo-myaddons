# -*- coding: utf-8 -*-
from odoo import api, models

class WebhookRetry(models.TransientModel):
    _name = "webhook.retry"
    _description = "Webhook retry job entry point"

    @api.model
    def cron_retry_failed(self, limit=100):
        """
        Простейшая заглушка: находит события со статусом 'error'
        и переводит их в 'retry', увеличивая счётчик попыток.
        Реальная обработка появится позже в webhook_gateway_sale.
        """
        Event = self.env["webhook.event"]
        failed = Event.search([("status", "=", "error")], limit=limit)
        for ev in failed:
            ev.write({"status": "retry", "retries": ev.retries + 1})
        return True
