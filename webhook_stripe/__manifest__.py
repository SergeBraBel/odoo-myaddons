# -*- coding: utf-8 -*-
{
    "name": "Webhook Stripe (adapter, minimal)",
    "summary": "Consume Stripe webhook.events and archive payment JSON",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "author": "Serge + ChatGPT",
    "depends": ["webhook_gateway", "payments_archive"],
    "data": [
        "data/ir_cron.xml"
    ],
    "installable": True,
    "application": False,
}
