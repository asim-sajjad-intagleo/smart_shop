# -*- coding: utf-8 -*-
from odoo import models, fields, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    external_product = fields.Boolean(string=_('External Product'), readonly=True, default=False)
    store_name = fields.Char(string=_('Store Name'), readonly=True)
    store_url = fields.Char(string=_('Store URL'), readonly=True)
    store_product_id = fields.Integer(string=_('Store Product ID'), readonly=True, index=True)

    # TODO: only xmlrpc user should be able to delete products with external_product=True
