# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo
#    Copyright (C) 2018 iCode (<http://icode.by>).
#
##############################################################################

import json
import logging
from odoo import api, fields, models, tools, exceptions

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'
    CONTACT_TYPES = (
        ('partner', 'Partner'),
        ('rental', 'Rental'),
        ('buyer', 'Buyer'),
    )
    # CONTACT_STATUSES = (
    #     ('Prospect', 'Prospect'),
    #     ('Lead', 'Lead'),
    #     ('Client', 'Client'),
    #     ('Client', 'Client'),
    #     ('PP', 'PP'),
    # )

    # partner-descriBtion —> Type category
    PARTNER_DESCRIPTIONS = (
        ('s_i', 'System Integrator'),
        ('a_a', 'Advertising agency'),
        ('c_c', 'Content creation'),
        ('r_d', 'R&D'),  # Other
    )
    SELECTION_FIELDS = {
        'partner_description': (PARTNER_DESCRIPTIONS, 'r_d'),  # (.., default_value)
        'contact_type': (CONTACT_TYPES, None),
    }

