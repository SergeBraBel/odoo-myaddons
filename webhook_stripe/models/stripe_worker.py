# -*- coding: utf-8 -*-
import json
from odoo import api, models

class StripeWebhookWorker(models.TransientModel):
    """
    Мини-воркер, который забирает необработанные события Stripe из webhook.event,
    сохраняет JSON через payments_archive и помечает событие как done.
    """
    _name = "stripe.webhook.worker"
    _description = "Stripe Webhook Consumer (minimal)"

    @api.model
    def cron_consume_stripe(self, limit=100):
        """
        Ищем события от Stripe со статусом 'received' и обрабатываем их по одному.
        """
        Event = self.env["webhook.event"].sudo()
        Writer = self.env["payments.json.writer"].sudo()

        # Берём пачку свежих событий
        events = Event.search([
            ("provider", "=", "stripe"),
            ("status", "=", "received"),
        ], order="id asc", limit=limit)

        for ev in events:
            try:
                # Пометим, что взяли в работу (на будущее для конкурентных воркеров)
                ev.mark_processing()

                # 1) Верифицируем подпись Stripe (если секрет настроен).
                provider = self.env["stripe.provider"].sudo()
                if not provider.verify(ev):
                    # Если секрет задан и подпись не прошла — фиксируем ошибку и пропускаем.
                    ev.mark_error("Stripe signature verification failed")
                    continue

                # Пробуем разобрать JSON body (если невалидный — кинет исключение)
                payload = json.loads(ev.raw_payload or "{}")

                # Достаём возможную ссылку на заказ
                order_ref = ""
                try:
                    order_ref = (
                        payload.get("data", {})
                               .get("object", {})
                               .get("metadata", {})
                               .get("order_id", "")
                    ) or ""
                except Exception:
                    order_ref = ""

                # Пишем на диск
                Writer.save_payment_json(order_ref=order_ref, event_dict=payload, provider="stripe")

                # Готово
                ev.mark_done()

            except Exception as e:
                # Фиксируем ошибку, оставим запись на ретрай (сделаем это позже кроном)
                ev.mark_error(str(e))
        return True
