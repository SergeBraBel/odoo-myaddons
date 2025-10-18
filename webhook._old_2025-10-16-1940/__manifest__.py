{
    "name": "Webhook (Jumpseller → Odoo)",
    "summary": "Принимает вебхуки Jumpseller и сохраняет JSON заказа в локальную папку",
    "version": "18.0.1.0.0",
    "category": "Tools",   
    "author": "Canopeia",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
    ],
    "application": True,
}
