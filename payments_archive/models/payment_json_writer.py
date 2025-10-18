# -*- coding: utf-8 -*-
import os
import json
from datetime import datetime
from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError

class PaymentJSONWriter(models.AbstractModel):
    _name = "payments.json.writer"
    _description = "Helper to write payment JSON files to disk"

    @api.model
    def _get_dir(self):
        """Читает путь из ir.config_parameter (archive.payments_dir) или даёт умолчание."""
        params = self.env["ir.config_parameter"].sudo()
        dflt = "/opt/odoo18/payments_json"
        path = params.get_param("archive.payments_dir", dflt)
        # Создадим каталог при необходимости
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            raise UserError(_("Cannot create archive dir: %s") % e)
        return path

    @api.model
    def save_payment_json(self, order_ref, event_dict, provider="unknown"):
        """
        Пишет JSON-файл оплаты.
        :param order_ref: строка (номер/ID заказа, можно None/"" если неизвестно)
        :param event_dict: dict (любой словарь, который хотим сохранить)
        :param provider: 'stripe' | 'payzen' | 'paypal' | ...
        :return: полный путь к созданному файлу
        """
        if not isinstance(event_dict, dict):
            raise UserError(_("event_dict must be a dict"))

        base_dir = self._get_dir()
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        safe_order = (order_ref or "noorder").replace("/", "_")
        fname = f"{ts}__{provider}__{safe_order}.json"
        fpath = os.path.join(base_dir, fname)

        # Записываем красиво (UTF-8, без ASCII-эскейпа)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(event_dict, f, ensure_ascii=False, indent=2)

        return fpath
