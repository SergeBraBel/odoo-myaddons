# встроенные модули Python
import io                    # для записи файлов
import json                  # для парсинга/записи JSON
import os                    # для работы с путями
from datetime import datetime  # на случай, если нет id/number, используем timestamp
import logging               # для логов в odoo.log

# импорт Odoo
from odoo import http, tools   # http: маршруты; tools: конфигурация и util-функции
from odoo.http import request  # доступ к текущему HTTP-запросу и env

# инициализация логгера модуля
_logger = logging.getLogger(__name__)   # создаём логгер по имени текущего файла

class JumpsellerWebhookController(http.Controller):
    """Принимаем вебхуки Jumpseller по трём путям:
       1) /webhook/jumpseller/order  — исходный
       2) /jumpseller/webhook        — под Jumpseller UI
       3) /webhook                   — совместимость (у тебя именно такой вызов в логах)
    """

    def _handle_payload_and_save(self, payload: dict):
        """Общая логика: проверяем токен, сохраняем JSON, пишем запись в БД и лог.
        """
        # логируем начало обработки с кусочком payload (безопасно)
        _logger.info("WEBHOOK: start handle, keys=%s", list(payload.keys()))  # фиксируем ключи JSON

        icp = request.env["ir.config_parameter"].sudo()  # берём доступ к системным параметрам с sudo
        expected_token = (icp.get_param("webhook.jumpseller_token") or "").strip()  # ожидаемый токен из БД

        # читаем присланный токен: сначала заголовок, потом ?token=
        token = (
            request.httprequest.headers.get("X-Jumpseller-Token")  # токен в HTTP-заголовке
            or request.params.get("token")                         # токен как query-параметр
            or ""                                                  # иначе пустая строка
        ).strip()

        # сравнение токена (если настроен)
        if expected_token and token != expected_token:
            _logger.warning("WEBHOOK: invalid token; got='%s'", token)        # пишем предупреждение в лог
            request.env["webhook.log"].sudo().create({                        # фиксируем попытку в БД
                "event": payload.get("event") or "order.webhook",
                "order_number": str(payload.get("number") or ""),
                "order_id_raw": str(payload.get("id") or ""),
                "status": "error",
                "note": "Invalid token",
            })
            return http.Response("Unauthorized", status=401)                  # отвечаем 401

        # куда сохранять файлы
        orders_dir = (icp.get_param("webhook.orders_dir") or "").strip()      # смотрим явный путь из параметров
        if not orders_dir:                                                    # если не задан — собираем дефолт
            data_dir = tools.config.get("data_dir") or tools.config.filestore("webhook")  # базовая data-папка
            if data_dir.endswith("/filestore/webhook"):                       # если вернулся путь filestore/...
                data_dir = os.path.dirname(os.path.dirname(data_dir))         # поднимаемся на 2 уровня
            orders_dir = os.path.join(data_dir, "webhook", "orders")          # <data_dir>/webhook/orders

        # создаём папку при необходимости
        os.makedirs(orders_dir, exist_ok=True)                                # не упадём, если папка уже есть
        _logger.info("WEBHOOK: orders_dir=%s", orders_dir)                    # пишем путь в лог на всякий

        # имя файла: берём id из блока "order" → иначе number → иначе timestamp
        order_block = payload.get("order") or payload              # если JSON вида {"order": {...}}, берём вложенный блок
        order_id = order_block.get("id")                            # хотим строго ID (например, 4055)
        order_number = order_block.get("number")                    # запасной вариант — номер заказа

        if order_id:                                                # если есть id → используем его
            base_name = str(order_id)
        elif order_number:                                          # иначе берём номер
            base_name = str(order_number)
        else:                                                       # иначе timestamp (UTC)
            base_name = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")

        filename = f"{base_name}.json"                              # итоговое имя файла (например, 4055.json)
        abs_path = os.path.join(orders_dir, filename)               # полный путь до файла                         # полный путь

        # пробуем записать файл
        try:
            with io.open(abs_path, "w", encoding="utf-8") as f:               # открываем файл в UTF-8
                json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)  # красиво пишем JSON
            status = "ok"                                                     # помечаем успех
            note = f"Saved to {abs_path}"                                     # текст примечания
            _logger.info("WEBHOOK: saved file %s", abs_path)                  # логируем успешную запись
        except Exception as e:
            status = "error"                                                  # помечаем ошибку
            note = f"Write error: {e}"                                        # подробности ошибки
            _logger.exception("WEBHOOK: error writing file %s", abs_path)     # пишем stacktrace в лог

        # сохраняем строку лога в БД
        request.env["webhook.log"].sudo().create({
            "event": payload.get("event") or order_block.get("status") or "order.webhook",  # что-то осмысленное в event
            "order_number": str(order_block.get("number") or ""),                           # номер (если был)
            "order_id_raw": str(order_block.get("id") or ""),                               # id (если был)
            "filename": filename if status == "ok" else False,                              # имя сохранённого файла
            "status": status,                                                               # ok / error
            "note": note,                                                                   # примечание/ошибка
        })

        # возвращаем ответ отправителю
        return http.Response("OK", status=200) if status == "ok" else http.Response("Internal error", status=500)

    # === Роут 1: исходный ===
    @http.route("/webhook/jumpseller/order", type="http", auth="public", methods=["POST"], csrf=False)
    def webhook_jumpseller_order(self, **kwargs):
        raw = request.httprequest.data or request.httprequest.get_data()      # берём сырое тело запроса
        if not raw:
            return http.Response("Empty body", status=400)                    # тело пусто
        try:
            payload = json.loads(raw.decode("utf-8"))                         # парсим JSON
        except Exception:
            return http.Response("Invalid JSON", status=400)                  # невалидный JSON
        return self._handle_payload_and_save(payload)                         # общая обработка

    # === Роут 2: как в Jumpseller UI ===
    @http.route("/jumpseller/webhook", type="http", auth="public", methods=["POST", "GET"], csrf=False)
    def webhook_jumpseller_compat(self, **kwargs):
        if request.httprequest.method == "GET":                               # некоторые сервисы делают GET-проверку
            return http.Response("OK (send POST with JSON)", status=200)      # отвечаем, что живы
        raw = request.httprequest.data or request.httprequest.get_data()      # читаем тело
        if not raw:
            return http.Response("Empty body", status=400)                    # пусто
        try:
            payload = json.loads(raw.decode("utf-8"))                         # парсим JSON
        except Exception:
            return http.Response("Invalid JSON", status=400)                  # ошибка парсинга
        return self._handle_payload_and_save(payload)                         # общая обработка

    # === Роут 3: совместимость с /webhook (у тебя именно он в логе) ===
    @http.route("/webhook", type="http", auth="public", methods=["POST", "GET"], csrf=False)
    def webhook_root_compat(self, **kwargs):
        if request.httprequest.method == "GET":                                # GET-пинг
            return http.Response("OK (send POST with JSON)", status=200)       # отвечаем 200
        raw = request.httprequest.data or request.httprequest.get_data()       # читаем тело
        if not raw:
            return http.Response("Empty body", status=400)                     # пусто
        try:
            payload = json.loads(raw.decode("utf-8"))                          # парсим JSON
        except Exception:
            return http.Response("Invalid JSON", status=400)                   # не JSON
        return self._handle_payload_and_save(payload)                          # общая обработка
