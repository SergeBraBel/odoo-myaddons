# -*- coding: utf-8 -*-
from odoo import api, fields, models

class WebhookEvent(models.Model):
    _name = "webhook.event"
    _description = "Inbound Webhook Event"
    _order = "id desc"
    _rec_name = "name"

    # Человеко-читаемое имя записи (provider:type#id), вычисляется автоматически
    name = fields.Char(string="Name", compute="_compute_name")


    # Кто прислал (берём из сегмента URL /webhook/<provider>)
    provider = fields.Char(required=True, index=True)

    # Тип события (best-effort из заголовков/пейлоада)
    event_type = fields.Char(index=True)

    # Сырые данные и заголовки запроса (как текст/JSON-строки для аудита)
    raw_payload = fields.Text()
    headers = fields.Text()

    # Защита от дублей: уникальность в сочетании (provider, idempotency_key)
    idempotency_key = fields.Char(index=True)

    # Подпись провайдера (например, Stripe-Signature)
    signature = fields.Char()

    # Текущий статус обработки
    status = fields.Selection([
        ("received", "Received"),
        ("processing", "Processing"),
        ("done", "Done"),
        ("error", "Error"),
        ("retry", "Retry"),
    ], default="received", index=True, required=True)

    # Счётчик попыток
    retries = fields.Integer(default=0)

    # Таймстемпы
    received_at = fields.Datetime(default=fields.Datetime.now, required=True)
    processed_at = fields.Datetime()

    # Сообщение об ошибке (если было)
    error_message = fields.Text()

    @api.depends("provider", "event_type")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.provider or 'unknown'}:{rec.event_type or 'event'}#{rec.id or 0}"

    # Сервисные методы для изменения статуса
    def mark_processing(self):
        self.write({"status": "processing"})

    def mark_done(self):
        self.write({"status": "done", "processed_at": fields.Datetime.now()})

    def mark_error(self, message):
        self.write({
            "status": "error",
            "error_message": (message or "")[:2000],
        })

    # SQL-ограничение на уникальность дубликатов
    _sql_constraints = [
        ("webhook_event_unique_idem",
         "unique(provider, idempotency_key)",
         "Duplicate webhook (provider + idempotency)"),
    ]
