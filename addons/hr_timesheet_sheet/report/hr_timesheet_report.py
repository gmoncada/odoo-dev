# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import tools
from openerp.osv import fields,osv
from openerp.addons.decimal_precision import decimal_precision as dp


class hr_timesheet_report(osv.osv):
    _name = "hr.timesheet.report"
    _description = "Timesheet"
    _auto = False
    _columns = {
        'date': fields.date('Date', readonly=True),
        'name': fields.char('Description',readonly=True),
        'product_id' : fields.many2one('product.product', 'Product',readonly=True),
        'journal_id' : fields.many2one('account.analytic.journal', 'Journal',readonly=True),
        'general_account_id' : fields.many2one('account.account', 'General Account', readonly=True),
        'user_id': fields.many2one('res.users', 'User',readonly=True),
        'account_id': fields.many2one('account.analytic.account', 'Analytic Account',readonly=True),
        'company_id': fields.many2one('res.company', 'Company',readonly=True),
        'cost': fields.float('Cost',readonly=True, digits_compute=dp.get_precision('Account')),
        'quantity': fields.float('Time',readonly=True),
    }

    def init(self, cr):
        tools.drop_view_if_exists(cr, 'hr_timesheet_report')
        cr.execute("""
            create or replace view hr_timesheet_report as (
                select
                    min(t.id) as id,
                    l.date as date,
                    sum(l.amount) as cost,
                    sum(l.unit_amount) as quantity,
                    l.account_id as account_id,
                    l.journal_id as journal_id,
                    l.product_id as product_id,
                    l.general_account_id as general_account_id,
                    l.user_id as user_id,
                    l.company_id as company_id,
                    l.currency_id as currency_id
                from
                    hr_analytic_timesheet as t
                    left join account_analytic_line as l ON (t.line_id=l.id)
                group by
                    l.date,
                    l.account_id,
                    l.product_id,
                    l.general_account_id,
                    l.journal_id,
                    l.user_id,
                    l.company_id,
                    l.currency_id
            )
        """)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
