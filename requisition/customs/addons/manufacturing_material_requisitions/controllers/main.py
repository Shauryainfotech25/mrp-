from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
import json
import logging

_logger = logging.getLogger(__name__)


class ManufacturingRequisitionController(http.Controller):

    @http.route('/manufacturing/requisition/dashboard', type='http', auth='user', website=True)
    def requisition_dashboard(self, **kwargs):
        """Main dashboard for manufacturing requisitions"""
        user = request.env.user
        
        # Get user's department requisitions
        domain = []
        if user.department_id:
            domain.append(('department_id', '=', user.department_id.id))
        
        # Get recent requisitions
        recent_requisitions = request.env['manufacturing.material.requisition'].search(
            domain, limit=10, order='create_date desc'
        )
        
        # Get pending approvals
        pending_approvals = request.env['manufacturing.material.requisition'].search([
            ('state', 'in', ['submitted', 'supervisor_approval', 'manager_approval']),
            '|', ('supervisor_id', '=', user.id), ('manager_id', '=', user.id)
        ])
        
        # Get emergency requisitions
        emergency_requisitions = request.env['shop.floor.requisition'].search([
            ('is_emergency', '=', True),
            ('state', 'not in', ['completed', 'cancelled'])
        ])
        
        # Get KPIs
        kpis = request.env['manufacturing.requisition.kpi'].search([
            ('period_start', '<=', request.env.context.get('today', '2024-01-01')),
            ('period_end', '>=', request.env.context.get('today', '2024-01-01'))
        ], limit=1)
        
        values = {
            'recent_requisitions': recent_requisitions,
            'pending_approvals': pending_approvals,
            'emergency_requisitions': emergency_requisitions,
            'kpis': kpis,
            'user': user,
        }
        
        return request.render('manufacturing_material_requisitions.dashboard_template', values)

    @http.route('/manufacturing/requisition/create', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def create_requisition(self, **kwargs):
        """Create new requisition form"""
        if request.httprequest.method == 'POST':
            try:
                # Create requisition from form data
                requisition_vals = {
                    'requisition_type': kwargs.get('requisition_type'),
                    'department_id': int(kwargs.get('department_id')),
                    'location_id': int(kwargs.get('location_id')),
                    'dest_location_id': int(kwargs.get('dest_location_id')),
                    'required_date': kwargs.get('required_date'),
                    'priority': kwargs.get('priority'),
                    'reason': kwargs.get('reason'),
                }
                
                if kwargs.get('manufacturing_order_id'):
                    requisition_vals['manufacturing_order_id'] = int(kwargs.get('manufacturing_order_id'))
                
                requisition = request.env['manufacturing.material.requisition'].create(requisition_vals)
                
                # Create requisition lines
                products = kwargs.get('products', '[]')
                if isinstance(products, str):
                    products = json.loads(products)
                
                for product_data in products:
                    line_vals = {
                        'requisition_id': requisition.id,
                        'product_id': int(product_data['product_id']),
                        'qty_required': float(product_data['qty_required']),
                        'required_date': kwargs.get('required_date'),
                        'reason': product_data.get('reason', ''),
                    }
                    request.env['manufacturing.material.requisition.line'].create(line_vals)
                
                return request.redirect(f'/manufacturing/requisition/{requisition.id}')
                
            except Exception as e:
                _logger.error(f"Error creating requisition: {str(e)}")
                return request.render('manufacturing_material_requisitions.error_template', {
                    'error': str(e)
                })
        
        # GET request - show form
        departments = request.env['hr.department'].search([])
        locations = request.env['stock.location'].search([('usage', '=', 'internal')])
        manufacturing_orders = request.env['mrp.production'].search([
            ('state', 'in', ['draft', 'confirmed', 'progress'])
        ])
        
        values = {
            'departments': departments,
            'locations': locations,
            'manufacturing_orders': manufacturing_orders,
        }
        
        return request.render('manufacturing_material_requisitions.create_form_template', values)

    @http.route('/manufacturing/requisition/<int:requisition_id>', type='http', auth='user', website=True)
    def view_requisition(self, requisition_id, **kwargs):
        """View requisition details"""
        requisition = request.env['manufacturing.material.requisition'].browse(requisition_id)
        
        if not requisition.exists():
            return request.not_found()
        
        # Check access rights
        if not requisition.check_access_rights('read', raise_exception=False):
            return request.redirect('/web/login')
        
        values = {
            'requisition': requisition,
            'can_approve': requisition._can_user_approve(request.env.user),
            'can_edit': requisition._can_user_edit(request.env.user),
        }
        
        return request.render('manufacturing_material_requisitions.requisition_detail_template', values)

    @http.route('/manufacturing/requisition/<int:requisition_id>/approve', type='http', auth='user', website=True, methods=['POST'])
    def approve_requisition(self, requisition_id, **kwargs):
        """Approve requisition"""
        requisition = request.env['manufacturing.material.requisition'].browse(requisition_id)
        
        if not requisition.exists():
            return request.not_found()
        
        try:
            if requisition.state == 'submitted':
                requisition.action_shop_floor_approve()
            elif requisition.state == 'supervisor_approval':
                requisition.action_supervisor_approve()
            elif requisition.state == 'manager_approval':
                requisition.action_manager_approve()
            elif requisition.state == 'procurement_approval':
                requisition.action_procurement_approve()
            
            return request.redirect(f'/manufacturing/requisition/{requisition_id}')
            
        except Exception as e:
            _logger.error(f"Error approving requisition {requisition_id}: {str(e)}")
            return request.render('manufacturing_material_requisitions.error_template', {
                'error': str(e)
            })

    @http.route('/manufacturing/requisition/analytics', type='http', auth='user', website=True)
    def analytics_dashboard(self, **kwargs):
        """Analytics dashboard"""
        # Get date range
        date_from = kwargs.get('date_from')
        date_to = kwargs.get('date_to')
        
        if not date_from or not date_to:
            from datetime import datetime, timedelta
            date_to = datetime.now().date()
            date_from = date_to - timedelta(days=30)
        
        # Get analytics data
        analytics = request.env['manufacturing.requisition.analytics'].search([
            ('requisition_date', '>=', date_from),
            ('requisition_date', '<=', date_to)
        ])
        
        # Calculate metrics
        total_requisitions = len(analytics)
        completed_requisitions = len(analytics.filtered(lambda r: r.state == 'completed'))
        avg_cycle_time = sum(analytics.mapped('total_cycle_time')) / total_requisitions if total_requisitions else 0
        total_cost = sum(analytics.mapped('total_cost'))
        
        # Get top products
        product_data = {}
        for record in analytics:
            if record.product_id.id not in product_data:
                product_data[record.product_id.id] = {
                    'name': record.product_id.name,
                    'count': 0,
                    'total_cost': 0
                }
            product_data[record.product_id.id]['count'] += 1
            product_data[record.product_id.id]['total_cost'] += record.total_cost
        
        top_products = sorted(product_data.values(), key=lambda x: x['count'], reverse=True)[:10]
        
        values = {
            'analytics': analytics,
            'total_requisitions': total_requisitions,
            'completed_requisitions': completed_requisitions,
            'completion_rate': (completed_requisitions / total_requisitions * 100) if total_requisitions else 0,
            'avg_cycle_time': avg_cycle_time,
            'total_cost': total_cost,
            'top_products': top_products,
            'date_from': date_from,
            'date_to': date_to,
        }
        
        return request.render('manufacturing_material_requisitions.analytics_template', values)

    @http.route('/manufacturing/requisition/search', type='json', auth='user')
    def search_requisitions(self, **kwargs):
        """Search requisitions via AJAX"""
        domain = []
        
        if kwargs.get('search_term'):
            domain.append(['name', 'ilike', kwargs['search_term']])
        
        if kwargs.get('state'):
            domain.append(['state', '=', kwargs['state']])
        
        if kwargs.get('department_id'):
            domain.append(['department_id', '=', int(kwargs['department_id'])])
        
        requisitions = request.env['manufacturing.material.requisition'].search(domain, limit=20)
        
        results = []
        for req in requisitions:
            results.append({
                'id': req.id,
                'name': req.name,
                'state': req.state,
                'priority': req.priority,
                'total_amount': req.total_amount,
                'required_date': req.required_date.isoformat() if req.required_date else None,
                'url': f'/manufacturing/requisition/{req.id}'
            })
        
        return {'results': results}

    @http.route('/manufacturing/requisition/product/search', type='json', auth='user')
    def search_products(self, **kwargs):
        """Search products for requisition lines"""
        search_term = kwargs.get('search_term', '')
        
        domain = [
            '|', ('name', 'ilike', search_term),
            ('default_code', 'ilike', search_term)
        ]
        
        products = request.env['product.product'].search(domain, limit=20)
        
        results = []
        for product in products:
            results.append({
                'id': product.id,
                'name': product.name,
                'default_code': product.default_code,
                'uom_name': product.uom_id.name,
                'standard_price': product.standard_price,
                'qty_available': product.qty_available,
            })
        
        return {'results': results}


class ManufacturingRequisitionPortal(CustomerPortal):
    
    def _prepare_home_portal_values(self, counters):
        """Add requisition counters to portal home"""
        values = super()._prepare_home_portal_values(counters)
        
        if 'requisition_count' in counters:
            partner = request.env.user.partner_id
            requisition_count = request.env['manufacturing.material.requisition'].search_count([
                ('requested_by', '=', request.env.user.id)
            ])
            values['requisition_count'] = requisition_count
        
        return values

    @http.route(['/my/requisitions', '/my/requisitions/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_requisitions(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        """Portal page for user's requisitions"""
        values = self._prepare_portal_layout_values()
        
        domain = [('requested_by', '=', request.env.user.id)]
        
        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]
        
        # Sorting
        searchbar_sortings = {
            'date': {'label': _('Newest'), 'order': 'create_date desc'},
            'name': {'label': _('Name'), 'order': 'name'},
            'state': {'label': _('Status'), 'order': 'state'},
        }
        
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']
        
        # Paging
        requisition_count = request.env['manufacturing.material.requisition'].search_count(domain)
        pager = request.website.pager(
            url="/my/requisitions",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby},
            total=requisition_count,
            page=page,
            step=self._items_per_page
        )
        
        requisitions = request.env['manufacturing.material.requisition'].search(
            domain, order=order, limit=self._items_per_page, offset=pager['offset']
        )
        
        values.update({
            'date': date_begin,
            'date_end': date_end,
            'requisitions': requisitions,
            'page_name': 'requisition',
            'archive_groups': [],
            'default_url': '/my/requisitions',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby
        })
        
        return request.render("manufacturing_material_requisitions.portal_my_requisitions", values)

    @http.route(['/my/requisition/<int:requisition_id>'], type='http', auth="public", website=True)
    def portal_requisition_page(self, requisition_id, access_token=None, **kw):
        """Portal page for requisition details"""
        try:
            requisition_sudo = self._document_check_access('manufacturing.material.requisition', requisition_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        
        values = {
            'requisition': requisition_sudo,
            'token': access_token,
        }
        
        return request.render("manufacturing_material_requisitions.portal_requisition_page", values) 