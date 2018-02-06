# -*- coding: utf-8 -*-
import base64
import json
import os
import werkzeug
import xmlrpclib
from subprocess import call

from cerberus import Validator
from odoo import http, _
from odoo.addons.website.controllers.main import Website
from odoo.http import request


class WebsiteIndex(Website):
    @http.route(['/page/homepage', '/'], type='http', auth='public', website=True)
    def index(self, **kw):
        env = request.env
        param = 'accessToken'

        # If accessToken, get DigitalTown OAuth user, update/create user in Odoo and authenticate
        if param in kw:
            try:
                ResUsers = env['res.users']
                # Get DigitalTown OAuth user info with the accessToken
                validation = ResUsers.request_oauth_user_info(kw[param])
                if validation:
                    # Get DigitalTown OAuth provider
                    digitaltown = env['auth.oauth.provider'].get_digitaltown_oauth_provider()
                    if digitaltown:
                        params = {'access_token': kw[param]}
                        user = ResUsers.sudo().search([('email', '=', validation['email'])], limit=1)
                        if user:
                            # Update user info
                            ResUsers.update_oauth_user_info(user[0], digitaltown.id, validation, params)
                        else:
                            user = ResUsers.sudo().search([('oauth_uid', '=', validation['user_id'])], limit=1)
                            if user:
                                # Update user info
                                ResUsers.update_oauth_user_info(user[0], digitaltown.id, validation, params)
                            else:
                                # Create user
                                values = ResUsers._generate_signup_values(digitaltown.id, validation, params)
                                ResUsers.sudo().signup(values)

                        # Commit changes, if the authenticate fails, the user is still updated/created
                        env.cr.commit()

                        # Authenticate user
                        request.session.authenticate(env.cr.dbname, user.login, user.oauth_access_token)
            except Exception:
                pass
            return werkzeug.utils.redirect('/')

        if request.website.user_id == env.user:
            return werkzeug.utils.redirect('/web/login?redirect=%2F')

        values = {
            'domain_name': env.ref('smart_shop_create_store.domain_name').value,
            'meta_description': _(
                'DigitalTown provides municipalities with the online infrastructure to more effectively manage their brand, spur economic development and partner with community'),
            'title': _('Create Store | DigitalTown'),
            'form': {
                'store_name': _('Choose your Store Name'),
                'store_email': _('Store Contact E-Mail'),
                'store_phone': _('Store Telephone Number'),
                'store_address': _('Store Address'),
                'store_hours': _('Store Opening Hours'),
                'submit_button': _('Create and Open Store'),
            },
            'error': {
                'empty_store_name': _('Please specify your store name.'),
                'empty_email': _('Please specify your email.'),
                'empty_phone': _('Please specify the store telephone number.'),
                'empty_address': _('Please specify the store address.'),
                'empty_hours': _('Please specify the store opening hours.'),
                'exists_store_name': _('Store name already exists.'),
                'invalid_store_name': _('Invalid store name.'),
                'invalid_email': _('Invalid email.'),
                'invalid_phone': _('Invalid store telephone number.'),
                'invalid_address': _('Invalid store address.'),
                'invalid_hours': _('Invalid store opening hours.'),
                'something_went_wrong': _('Something went wrong!'),
            },
        }
        return request.render('website.homepage', values)


class WebsiteHomepage(http.Controller):
    @http.route(['/create-store-request'], type='http', auth='public', methods=['POST'], csrf=False)
    def create_store_request(self, **post):
        env = request.env
        user = env.user

        schema = {
            'store_name': {
                'type': 'string',
                'regex': '^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]$',
                'required': True,
                'empty': False,
                'maxlength': 61,
            },
            'store_email': {
                'type': 'string',
                'regex': '^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$',
                'required': True,
                'empty': False,
                'maxlength': 100,
            },
            'store_phone': {
                'type': 'string',
                'required': True,
                'empty': False,
                'maxlength': 24,
            },
            'store_address': {
                'type': 'string',
                'required': True,
                'empty': False,
                'maxlength': 255,
            },
            'store_opening': {
                'type': 'string',
                'required': True,
                'empty': False,
                'maxlength': 255,
            },
            'oauth_access_token': {
                'type': 'string',
                'required': False,
                'empty': True,
                'maxlength': 2048,
            },
            'oauth_uuid': {
                'type': 'string',
                'required': False,
                'empty': True,
                'maxlength': 255,
            },
            'oauth_id': {
                'type': 'string',
                'required': False,
                'empty': True,
                'maxlength': 10,
            },
        }

        v = Validator(schema, purge_unknown=True)
        v.validate(post)

        response = {
            'redirect': False,
            'domain_exists': False,
            'store_name': True,
            'store_email': True,
            'store_phone': True,
            'store_address': True,
            'store_opening': True,
            'oauth_access_token': True,
            'oauth_uuid': True,
            'oauth_id': True,
        }

        if v.errors:
            for key in response:
                if key in v.errors:
                    response[key] = False
        else:
            oauth_access_token = False
            oauth_uuid = False
            oauth_id = False
            return_response = False
            is_logged_in = True if user and user.login != 'public' else False

            # Try to get oauth_access_token from post
            if 'oauth_access_token' in post and post['oauth_access_token']:
                oauth_access_token = post['oauth_access_token']
            # Try to get oauth_access_token from logged user
            elif is_logged_in:
                oauth_access_token = user.oauth_access_token
            else:
                return_response = True

            # Try to get oauth_uuid from post
            if 'oauth_uuid' in post and post['oauth_uuid']:
                oauth_uuid = post['oauth_uuid']
            # Try to get oauth_uuid from logged user
            elif is_logged_in:
                oauth_uuid = user.oauth_uuid
            else:
                return_response = True

            # Try to get oauth_id from post
            if 'oauth_id' in post and post['oauth_id']:
                oauth_id = post['oauth_id']
            # Try to get oauth_id from logged user
            elif is_logged_in:
                oauth_id = user.oauth_uid
            else:
                return_response = True

            # Return JSON response if oauth data doesn't exist in post and the user is not logged in
            if return_response:
                return json.dumps(response)

            subdomain_name = self.get_subdomain_name(post['store_name'])
            country_id = int(env.ref('smart_shop_create_store.default_country_id').value)

            # Create is store partner
            partner_id, local_partner_id = self.create_store_partner(post, subdomain_name, country_id)

            if partner_id:
                # Create and open store
                self.create_and_open_store(partner_id, oauth_access_token, oauth_uuid, subdomain_name, country_id, post,
                                           oauth_id)

                # Set Redirect URL
                response['redirect'] = 'https://%s/open-store?accessToken=%s' % (subdomain_name, oauth_access_token)

                # Send store created email
                template = env.ref('smart_shop_create_store.store_created_email')
                template.sudo().with_context(store_url='https://%s' % subdomain_name).send_mail(
                    local_partner_id,
                    force_send=True,
                    raise_exception=False)
            else:
                response['domain_exists'] = True

        return json.dumps(response)

    def get_subdomain_name(self, store_name):
        return '%s.%s' % (store_name.lower(), request.env.ref('smart_shop_create_store.domain_name').value)

    def create_store_partner(self, post, subdomain_name, country_id):
        env = request.env

        dir_path = os.path.dirname(os.path.realpath(__file__))

        with open('%s/../%s' % (dir_path, 'static/img/shop.png'), 'rb') as image_file:
            base64_image = base64.b64encode(image_file.read())

        # Credentials
        db_name = env.ref('smart_shop_common.master_db_name').value
        user = env.ref('smart_shop_common.master_xmlrpc_user').value
        pwd = env.ref('smart_shop_common.master_xmlrpc_pwd').value
        protocol = env.ref('smart_shop_common.master_xmlrpc_protocol').value
        host = env.ref('smart_shop_common.master_xmlrpc_host').value
        port = env.ref('smart_shop_common.master_xmlrpc_port').value

        # XML-RPC authentication
        com = xmlrpclib.ServerProxy('%s://%s:%s/xmlrpc/common' % (protocol, host, port))
        uid = com.login(db_name, user, pwd)
        sock = xmlrpclib.ServerProxy('%s://%s:%s/xmlrpc/object' % (protocol, host, port))

        # Check if partner already exists
        if sock.execute_kw(db_name, uid, pwd, 'res.partner', 'search_read',
                           [[['is_store', '=', True], ['store_name', '=', subdomain_name]]],
                           {'fields': ['id'], 'limit': 1}):
            return False, False

        # Create partner on master instance
        partner_id = sock.execute_kw(db_name, uid, pwd, 'res.partner', 'create', [{
            'image': base64_image,
            'name': subdomain_name,
            'street': post['store_address'],
            'country_id': country_id,
            'opening_hours': post['store_opening'],
            'website': 'https://%s' % subdomain_name,
            'phone': post['store_phone'],
            'email': post['store_email'],
            'is_store': True,
            'store_name': subdomain_name,
            'xmlrpc_dbname': subdomain_name,
            'xmlrpc_user': env.ref('smart_shop_create_store.client_xmlrpc_user').value,
            'xmlrpc_pwd': env.ref('smart_shop_create_store.client_xmlrpc_pwd').value,
            'xmlrpc_protocol': env.ref('smart_shop_create_store.client_xmlrpc_protocol').value,
            'xmlrpc_host': env.ref('smart_shop_create_store.client_xmlrpc_host').value,
            'xmlrpc_port': env.ref('smart_shop_create_store.client_xmlrpc_port').value,
        }])

        if not partner_id:
            return False, False

        # Create partner locally
        local_partner = env['res.partner'].sudo().create({
            'image': base64_image,
            'name': subdomain_name,
            'street': post['store_address'],
            'country_id': country_id,
            'opening_hours': post['store_opening'],
            'website': 'https://%s' % subdomain_name,
            'phone': post['store_phone'],
            'email': post['store_email'],
            'is_store': True,
            'store_name': subdomain_name,
        })

        return partner_id, local_partner.id

    def create_and_open_store(self, partner_id, access_token, uuid, subdomain_name, country_id, post, oauth_id):
        """
        Creates a new Odoo store instance.

        Odoo user must exist in /etc/sudoers with no password prompt, add "odoo ALL=(ALL) NOPASSWD: ALL" to /etc/sudoers
        Odoo user must also have permissions to createdb in postgres, this should be standard in a production environment
        """

        env = request.env

        AuthOauthProvider = env['auth.oauth.provider']

        # Get DigitalTown OAuth provider
        digitaltown = AuthOauthProvider.get_digitaltown_oauth_provider()

        # Create new DigitalTown OAuth client with the new instance callback
        response = AuthOauthProvider.create_digitaltown_oauth_client(access_token, uuid, subdomain_name)

        # Create database, filestore and nginx configuration
        self.create_database_filestore_and_nginx_config(partner_id, subdomain_name, country_id)

        # Credentials
        user = env.ref('smart_shop_create_store.client_xmlrpc_user').value
        pwd = env.ref('smart_shop_create_store.client_xmlrpc_pwd').value
        protocol = env.ref('smart_shop_create_store.client_xmlrpc_protocol').value
        host = env.ref('smart_shop_create_store.client_xmlrpc_host').value
        port = env.ref('smart_shop_create_store.client_xmlrpc_port').value

        # XML-RPC authentication
        com = xmlrpclib.ServerProxy('%s://%s:%s/xmlrpc/common' % (protocol, host, port))
        uid = com.login(subdomain_name, user, pwd)
        sock = xmlrpclib.ServerProxy('%s://%s:%s/xmlrpc/object' % (protocol, host, port))

        # Update config parameters
        self.update_config_parameters(sock, subdomain_name, uid, pwd, subdomain_name)
        # Update auth provider
        self.update_auth_oauth_provider(sock, subdomain_name, uid, pwd, digitaltown[0].auth_endpoint, response['id'],
                                        response['secret'])
        # Update company
        self.update_company(sock, subdomain_name, uid, pwd, post, subdomain_name, country_id)

        # Update auth client
        self.update_auth_client(sock, subdomain_name, uid, pwd, post, oauth_id, subdomain_name)

    def create_database_filestore_and_nginx_config(self, partner_id, subdomain_name, country_id):
        env = request.env

        # Templates
        nginx_config_template_name = env.ref('smart_shop_create_store.nginx_config_template_name').value
        database_template_name = env.ref('smart_shop_create_store.database_template_name').value

        # New Odoo instance
        nginx_config_name = subdomain_name
        database_name = subdomain_name

        CREATE_STORE_CMDS = [
            # Create new database with subdomain_name from the existing template
            'createdb -O odoo -T %s %s' % (database_template_name, database_name),
            # Copy filestore
            'sudo cp -r /opt/odoo/data/filestore/%s /opt/odoo/data/filestore/%s' % (
                database_template_name, database_name),
            'sudo chown -R odoo:odoo /opt/odoo/data/filestore/%s' % database_name,
            # Copy new nginx configuratipn from existing template
            'sudo cp /etc/nginx/sites-available/%s /etc/nginx/sites-available/%s' % (
                nginx_config_template_name, nginx_config_name),
            # Change domain and dbfilter header name on nginx configuration
            'sudo sed -i -e s/domain/%s/g /etc/nginx/sites-available/%s' % (database_name, nginx_config_name),
            # Change logs name on nginx configuration
            'sudo sed -i -e s/access\.log/%s\.access\.log/g /etc/nginx/sites-available/%s' % (
                database_name, nginx_config_name),
            'sudo sed -i -e s/error\.log/%s\.error\.log/g /etc/nginx/sites-available/%s' % (
                database_name, nginx_config_name),
            # Rename upstreams on nginx configuration
            'sudo sed -i -e s/odoosrv/odoosrv%s/g /etc/nginx/sites-available/%s' % (partner_id, nginx_config_name),
            'sudo sed -i -e s/odoolong/odoolong%s/g /etc/nginx/sites-available/%s' % (partner_id, nginx_config_name),
            # Enable nginx configuration
            'sudo ln -s /etc/nginx/sites-available/%s /etc/nginx/sites-enabled/%s' % (
                nginx_config_name, nginx_config_name),
            # Reload nginx configurations
            'sudo service nginx reload',
        ]

        for cmd in CREATE_STORE_CMDS:
            call(cmd.split())

    def update_config_parameters(self, sock, db_name, uid, pwd, subdomain_name):
        records = sock.execute_kw(db_name, uid, pwd, 'ir.config_parameter', 'search_read', [
            ['|', ['key', '=', 'store_name'], ['key', '=', 'web.base.url']]
        ], {'fields': ['id', 'key'], 'limit': 2})

        for record in records:
            # Update web.base.url
            if record['key'] == 'web.base.url':
                sock.execute_kw(db_name, uid, pwd, 'ir.config_parameter', 'write', [[record['id']], {
                    'value': 'https://%s' % subdomain_name,
                }])
            else:
                # Update store_name
                sock.execute_kw(db_name, uid, pwd, 'ir.config_parameter', 'write', [[record['id']], {
                    'value': subdomain_name,
                }])

    def update_auth_oauth_provider(self, sock, db_name, uid, pwd, auth_endpoint, client_id, client_secret):
        records = sock.execute_kw(db_name, uid, pwd, 'auth.oauth.provider', 'search_read', [
            [['auth_endpoint', '=', auth_endpoint]]
        ], {'fields': ['id'], 'limit': 1})

        for record in records:
            # Update DigitalTown OAuth provider
            sock.execute_kw(db_name, uid, pwd, 'auth.oauth.provider', 'write', [[record['id']], {
                'client_id': client_id,
                'client_secret': client_secret,
            }])

    def update_company(self, sock, db_name, uid, pwd, post, subdomain_name, country_id):
        # Update company
        sock.execute_kw(db_name, uid, pwd, 'res.company', 'write', [[1], {
            'name': subdomain_name,
            'street': post['store_address'],
            'opening_hours': post['store_opening'],
            'country_id': country_id,
            'website': 'https://%s' % subdomain_name,
            'phone': post['store_phone'],
            'email': post['store_email'],

        }])

    def update_auth_client(self, sock, db_name, uid, pwd, post, oauth_uid, subdomain_name):
        records = sock.execute_kw(db_name, uid, pwd, 'res.users', 'search_read', [
            [['id', '=', request.env.ref('smart_shop_common.res_users_client').id]]
        ], {'fields': ['id'], 'limit': 1})

        for record in records:
            # Update auth client
            sock.execute_kw(db_name, uid, pwd, 'res.users', 'write', [[record['id']], {
                'name': subdomain_name,
                'login': post['store_email'],
                'email': post['store_email'],
                'oauth_uid': oauth_uid,
                'oauth_provider_id': request.env.ref('smart_shop_oauth.auth_oauth_provider_digitaltown').id,
            }])
