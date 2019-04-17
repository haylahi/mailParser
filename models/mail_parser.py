# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo
#    Copyright (C) 2018 iCode (<http://icode.by>).
#
##############################################################################

from odoo import api, fields, models, tools, exceptions
import logging
import re
import lxml
from collections import namedtuple

_logger = logging.getLogger(__name__)

MODELS_FIELDS_MAPPING = (
    ('name', 'name', 'str'),
    ('company-name', 'company_name', 'str'),
    ('email', 'email', 'str'),
    ('phone', 'mobile', 'str'),
    ('Message', 'message', 'str'),
)

MODELS_FIELDS_SURVEY_MAPPING = (
    ('name', 'name', 'str'),
    ('company-name', 'company_name', 'str'),
    ('email', 'email', 'str'),
    ('phone', 'mobile', 'str'),
    ('Message', 'message', 'str'),
)


class EmailParser(models.AbstractModel):
    _name = 'mail.survey_parser'
    MappingRulesRecord = namedtuple(
        'MappingRulesRecord', 'field_name, inner_field_name, field_type'
    )

    @staticmethod
    def _parse_mail_to_dict(message=""):
        """
        function receives the message and returns a dictionary
        :param message: string
        :return: dict fields_found[field_name] = field_val
        """
        # FIXME: Test this <Pavel 2018-06-29>
        message = lxml.html.fromstring(message).text_content()
        # message = message.replace('<pre>', '')
        # message = message.replace('</pre>', '')
        message_list = list(map(lambda x: x.strip(), message.split('-----')))

        fields_found = {}
        for line in [item for item in message_list if ':' in item]:
            field_name, field_val = list(
                map(lambda x: x.strip(), line.split(':', 1))
            )
            fields_found[field_name] = field_val
        return fields_found

    def find_or_create(
            self, model='res.users', domain=None, default_value=None):
        """
        Find or create record in model field
        :param model: string - name of model
        :param domain: string - domain
        :param default_value: value or dict - default value for create record
        :return: ([res.model(6,),], False)
        """
        no_create_models = ('res.country',)
        create = False
        domain = [] if domain is None else domain
        default_value = {'name': default_value} if not isinstance(default_value, dict) else default_value
        result = self.env[model].search(domain, limit=1)
        if not len(result) and (default_value is not None) and model not in no_create_models:
            result = [self.env[model].create(default_value)]
            create = True
        return result, create

    def get_field_info(self, model, field_name):
        FieldInfo = namedtuple('FieldInfo', 'ttype, relation, relation_field')
        ir_model_obj = self.env['ir.model.fields']
        ir_model_field = ir_model_obj.search(
            [('model', '=', model), ('name', '=', field_name)]
        )
        field_type = ir_model_field.ttype
        field_relation = ir_model_field.relation
        field_relation_field = ir_model_field.relation_field
        result = FieldInfo(field_type, field_relation, field_relation_field)
        return result

    @staticmethod
    def get_first_match(value_key_array, search_key, default_value=None):
        return next(
            (value for value, key in value_key_array if key == search_key),
            default_value
        )

    def parse_msg_body(self, message, mapping_rules, TARGET_MODEL):
        fields_found = self._parse_mail_to_dict(message)
        mapping_rules = [
            self.MappingRulesRecord(*item) for item in mapping_rules
        ]
        selection_fields = self.env[TARGET_MODEL].SELECTION_FIELDS
        write_dict = {}
        for item_field_name, item_field_val in fields_found.items():
            mapping_rules_record = next(
                (item for item in mapping_rules
                 if item.field_name == item_field_name), None
            )

            if not mapping_rules_record:
                continue

            if mapping_rules_record.inner_field_name in selection_fields:
                field_val = self.get_first_match(
                    selection_fields[mapping_rules_record.inner_field_name][0],
                    item_field_val,
                    selection_fields[mapping_rules_record.inner_field_name][1]
                )
                if field_val:
                    write_dict.update(
                        {mapping_rules_record.inner_field_name: field_val}
                    )
            elif mapping_rules_record.field_type in [
                'str', 'int', 'float', 'dict']:
                write_dict.update(
                    {mapping_rules_record.inner_field_name: item_field_val}
                )
            elif mapping_rules_record.field_type == 'date':
                write_dict.update(
                    {
                        mapping_rules_record.inner_field_name:
                            fields.Date.from_string(item_field_val)
                    }
                )
            elif mapping_rules_record.field_type == 'datetime':
                write_dict.update(
                    {
                        mapping_rules_record.inner_field_name:
                            fields.Datetime.from_string(item_field_val)
                    }
                )
            elif mapping_rules_record.field_type == 'bool':
                write_dict.update(
                    {
                        mapping_rules_record.inner_field_name:
                            True if item_field_val in ['Yes', 'True', 'true']
                            else False
                    }
                )
            # partner_description, contact_type

            elif mapping_rules_record.field_type == 'm2o':
                if mapping_rules_record.field_name == 'country':
                    countries = self.env['res.country'].search(
                        [('name', 'ilike', item_field_val)], limit=1
                    )
                    if len(countries):
                        write_dict.update(
                            {
                                mapping_rules_record.inner_field_name:
                                    countries[0].id
                            }
                        )
            elif mapping_rules_record.field_type == 'm2m':
                field_info = self.get_field_info(
                    TARGET_MODEL, mapping_rules_record.inner_field_name
                )
                if field_info.ttype == 'many2many':
                    records, create = self.find_or_create(
                        model=field_info.relation,
                        domain=[('name', 'ilike', item_field_val)],
                        default_value=item_field_val
                    )
                    if len(records):
                        write_dict[mapping_rules_record.inner_field_name] = write_dict.get(
                            mapping_rules_record.inner_field_name, [])
                        write_dict[mapping_rules_record.inner_field_name].append((4, records[0].id))
        return write_dict


class EmailSurvey(models.TransientModel):
    _name = 'mail.survey_model'
    _inherit = ['mail.thread', 'mail.alias.mixin', 'mail.survey_parser']
    _description = 'Form Message Parser'
    _mail_post_access = 'read'

    def create_lead(self, partner, msg_data):
        lead = None
        try:
            _logger.info("Creation lead for {}".format(partner.email))
            opportunity_data = {
                'name': msg_data['Message'],
                # 'email_from': tools.email_split(self.email_from)[0],
                'team_id': False,
                'description': 'Created from questionnaire form',
                'partner_id': partner.id,
                'partner_name': partner.name,
            }
            self.env['crm.lead'].create(opportunity_data)
        except:
            _logger.exception(
                "Lead creation for {} failed.".format(partner.email)
            )
        else:
            _logger.info("Lead {} for {} successfully created".format(
                opportunity_data['name'],
                partner.email
            ))
        return lead

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """ Overrides mail_thread message_new that is called by the mailgateway
            through message_process.
            This override updates the document according to the email.
        """
        """
        Логика подмены партнера: 
        1. мы ищем партнера с кодом опросника. Он _должен_ уже быть. Если нет - создаем нового совсем
        2. Если у нас для партнера из 1(существующего) совпадают имя, фамилия, емейл - хорошо
           Если у партнера совпадают имя и фамилия, но емейл другой - емейл идет в поле допемейла
           Если у партнера другие емейл и что либо из (имя-фамилия), мы создаем нового партнера типа компания, 
           где имя=имя компании из опросника, найденного для найденного по коду акнеты ставим parent_id эту новую компанию,
           а уже текущий опросник создаем для нового, где parent_id также новый этот самый партнер.

        """

        # to_alias_name = tools.email_split(msg_dict.get('to'))[0].split('@', 1)[0]

        _logger.info('Start mail parsing')

        FIELDS_MAPPING = custom_values.pop('FIELDS_MAPPING', None)
        TARGET_MODEL = custom_values.pop('target_model', None)
        if not FIELDS_MAPPING or not TARGET_MODEL:
            _logger.error('No mapping fields for message {}'.format(msg_dict))
            return
        # write_dict = self.parse_msg_body(
        #     msg_dict.get('body'), FIELDS_MAPPING, TARGET_MODEL
        # )
        write_dict = self._parse_mail_to_dict(msg_dict.get('body'))

        # print(write_dict)

        _logger.info("Survey mail data:\n{}\n".format(write_dict))

        email = write_dict.pop('email', None)

        _logger.info("Email from survey data: {}".format(write_dict))
        _logger.info(
            "Email from: {}".format(msg_dict.get('from', 'not available'))
        )
        _logger.info(
            "Email to: {}".format(msg_dict.get('to', 'not available'))
        )

        # extract_emails = re.search(r'([\w+\.]+@[\w+\.]+\.\w+)', email).groups()
        # if extract_emails:
        #     email = extract_emails[0]

        if email:
            email_to_search = email
        else:
            email_to_search = tools.email_split(msg_dict.get('from'))
            write_dict = None

        _logger.info(
            "Email to search before processing email addr: {}".format(
                email_to_search
            )
        )

        if isinstance(email_to_search, list):
            email_to_search = list(
                map(str.lower, email_to_search)
            )
        elif isinstance(email_to_search, str):
            email_to_search = [email_to_search.lower()]

        partners = None
        for email in email_to_search:
            _logger.info("Searching contact by email: {}".format(email))
            partners = self.env[TARGET_MODEL].search(
                [('email', '=ilike', email)],
                limit=1
            )
            if partners:
                break

        _logger.info("Contact: {}".format(partners))

        email_to_search = email_to_search[0]  # get one email

        _logger.info("Email to search: {}".format(email_to_search))

        if 'linktopq' in write_dict and not partners:
            partners = self.env[TARGET_MODEL].search(
                [('linktopq', 'in', [write_dict.get('linktopq')])], limit=1
            )
            if partners:
                m_firstname = write_dict.get('firstname', None)
                m_company = write_dict.get('company_name', None)

                if not all(
                        (
                                partners.firstname,
                        )
                ):
                    pass
                elif all(
                        (
                                partners.firstname == m_firstname,
                                partners.email == email_to_search
                        )
                ):
                    pass
                elif all(
                        (
                                partners.firstname == m_firstname,
                        )
                ) and email_to_search:
                    write_dict.update(
                        {
                            'additional_emails':
                                partners.additional_emails +
                                email_to_search
                        }
                    )
                else:
                    p_p_name = m_company or partners.name
                    # parent_partner = self.env[TARGET_MODEL].create({'name':m_company or partners.name})
                    parent_partner, create = self.find_or_create(
                        model='res.partner',
                        domain=[
                            ('name', '=', p_p_name), ('is_company', '=', True)
                        ],
                        default_value={'name': p_p_name, 'is_company': True})
                    partners.update({'parent_id': parent_partner[0].id})
                    # we bind old record to parent company and create new
                    # partner_id for this questionare with the same parent_id
                    write_dict.update({'parent_id': parent_partner[0].id})
                    self.create_lead(partners, write_dict)
                    partners = None

        if not partners:
            _logger.info("Creating new contact.")
            defaults = {
                'email': email_to_search,
                'name': email_to_search,
            }
            partners = self.env[TARGET_MODEL].create(defaults)

        email_to_search = partners.email

        dest_aliases = self
        if dest_aliases and dest_aliases[0].alias_user_id:
            subscribe_user_id = dest_aliases[0].alias_user_id[0].id
        else:
            subscribe_user_id = None

        if not write_dict and subscribe_user_id:
            partners.message_subscribe_users(subscribe_user_id)
            # If you haven't specified alias owner, notifications goes to
            # currently subscribed users only.

        if write_dict:
            if not 'firstname' in write_dict.keys():
                write_dict['firstname'] = email_to_search
            partners.write(write_dict)
            try:
                partners.write(write_dict)
            except Exception as e:
                _logger.error('Error while writing survey message from %s' % email_to_search, [e])

        self.create_lead(partners, write_dict)

        # salesperson = self.env['hr.employee'].search([
        #     ('rm_country_ids.name', '=ilike', write_dict.get('country', ''))
        # ])
        # if salesperson:
        #     _logger.info("Found default buyers sales manager.")
        #     lead.user_id = salesperson.user_id
        #     partners.user_id = salesperson.user_id

        return partners


class WebFormSurvey(models.TransientModel):
    _name = 'mail.survey_website_form'
    _inherit = 'mail.survey_model'
    _description = 'Website Form Parser'
    _mail_post_access = 'read'

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        custom_values.update(
            {
                'FIELDS_MAPPING': MODELS_FIELDS_MAPPING,
                'target_model': 'res.partner'
            }
        )
        return super(WebFormSurvey, self).message_new(msg_dict, custom_values)


class QuestFormsSurvey(models.TransientModel):
    _name = 'mail.survey_questionnaire_form'
    _inherit = 'mail.survey_model'
    _description = 'Questionnaire Form Parser'
    _mail_post_access = 'read'

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        custom_values.update(
            {
                'FIELDS_MAPPING': MODELS_FIELDS_SURVEY_MAPPING,
                'target_model': 'res.partner'
            }
        )
        return super(QuestFormsSurvey, self).message_new(msg_dict, custom_values)