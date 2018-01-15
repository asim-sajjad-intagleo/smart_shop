# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request


class WebsiteSearch(http.Controller):
    @http.route(['/products/search/<string:search>'], type='http', auth='none', methods=['GET'])
    def search(self, search=False, **kw):
        response = {
            'products': False,
        }

        if search:
            domain = self.get_search_domain(search)
            products = request.env['product.template'].sudo().search(domain)
            if products:
                response['products'] = []
                for product in products:
                    response['products'].append({
                        'store_name': product.store_name,
                        'product_name': product.name,
                        'product_description': product.description_sale,
                        'product_url': product.store_url,
                    })

        return json.dumps(response)

    # TODO: improve search parameters
    def get_search_domain(self, search):
        domain = []
        for srch in search.split(' '):
            domain += [
                '|',
                ('name', 'ilike', srch),
                ('description_sale', 'ilike', srch),
            ]
        return domain
