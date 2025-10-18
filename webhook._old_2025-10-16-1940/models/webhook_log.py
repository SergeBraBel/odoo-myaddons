# импорт API Odoo
from odoo import fields, models

class WebhookLog(models.Model):
    _name = "webhook.log"                 # техническое имя модели
    _description = "Log de Webhooks"      # описание модели в интерфейсе
    _order = "create_date desc"           # сортировка по дате создания

    event = fields.Char(string="Событие")             # тип события (напр., order.created)
    order_number = fields.Char(string="Номер заказа") # номер заказа из payload
    order_id_raw = fields.Char(string="ID")           # сырой ID заказа
    filename = fields.Char(string="Файл")             # имя сохранённого файла
    status = fields.Selection(                        # статус обработки вебхука
        [("ok", "OK"), ("skipped", "Skipped"), ("error", "Error")],
        default="ok",
        string="Статус",
    )
    note = fields.Text(string="Примечание")           # произвольная заметка/ошибка
