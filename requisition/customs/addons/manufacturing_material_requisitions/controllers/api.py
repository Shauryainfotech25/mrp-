from odoo import http, _
from odoo.http import request
import json
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class ManufacturingRequisitionAPI(http.Controller):

    def _authenticate_api_user(self, api_key=None):
        """Authenticate API user"""
        if not api_key:
            return False
        
        # Check API key in user preferences or company settings
        user = request.env['res.users'].sudo().search([
            ('api_key', '=', api_key),
            ('active', '=', True)
        ], limit=1)
        
        return user if user else False

    def _validate_api_access(self, api_key):
        """Validate API access and return user"""
        user = self._authenticate_api_user(api_key)
        if not user:
            return {
                'success': False,
                'error': 'Invalid API key',
                'code': 401
            }
        
        # Set user context
        request.env = request.env(user=user.id)
        return {'success': True, 'user': user}

    @http.route('/api/v1/manufacturing/requisitions', type='json', auth='none', methods=['GET'], csrf=False)
    def get_requisitions(self, **kwargs):
        """Get manufacturing requisitions via API"""
        api_key = request.httprequest.headers.get('X-API-Key')
        auth_result = self._validate_api_access(api_key)
        
        if not auth_result['success']:
            return auth_result
        
        try:
            # Parse query parameters
            limit = int(kwargs.get('limit', 50))
            offset = int(kwargs.get('offset', 0))
            state = kwargs.get('state')
            department_id = kwargs.get('department_id')
            date_from = kwargs.get('date_from')
            date_to = kwargs.get('date_to')
            
            # Build domain
            domain = []
            if state:
                domain.append(('state', '=', state))
            if department_id:
                domain.append(('department_id', '=', int(department_id)))
            if date_from:
                domain.append(('create_date', '>=', date_from))
            if date_to:
                domain.append(('create_date', '<=', date_to))
            
            # Search requisitions
            requisitions = request.env['manufacturing.material.requisition'].search(
                domain, limit=limit, offset=offset, order='create_date desc'
            )
            
            # Format response
            data = []
            for req in requisitions:
                data.append({
                    'id': req.id,
                    'name': req.name,
                    'state': req.state,
                    'priority': req.priority,
                    'requisition_type': req.requisition_type,
                    'department': req.department_id.name if req.department_id else None,
                    'requested_by': req.requested_by.name,
                    'request_date': req.request_date.isoformat() if req.request_date else None,
                    'required_date': req.required_date.isoformat() if req.required_date else None,
                    'total_amount': req.total_amount,
                    'currency': req.currency_id.name,
                    'manufacturing_order': req.manufacturing_order_id.name if req.manufacturing_order_id else None,
                    'line_count': len(req.line_ids),
                })
            
            return {
                'success': True,
                'data': data,
                'count': len(data),
                'total': request.env['manufacturing.material.requisition'].search_count(domain)
            }
            
        except Exception as e:
            _logger.error(f"API get_requisitions error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'code': 500
            }

    @http.route('/api/v1/manufacturing/requisitions/<int:requisition_id>', type='json', auth='none', methods=['GET'], csrf=False)
    def get_requisition_detail(self, requisition_id, **kwargs):
        """Get requisition details via API"""
        api_key = request.httprequest.headers.get('X-API-Key')
        auth_result = self._validate_api_access(api_key)
        
        if not auth_result['success']:
            return auth_result
        
        try:
            requisition = request.env['manufacturing.material.requisition'].browse(requisition_id)
            
            if not requisition.exists():
                return {
                    'success': False,
                    'error': 'Requisition not found',
                    'code': 404
                }
            
            # Format lines
            lines = []
            for line in requisition.line_ids:
                lines.append({
                    'id': line.id,
                    'product_id': line.product_id.id,
                    'product_name': line.product_id.name,
                    'product_code': line.product_id.default_code,
                    'qty_required': line.qty_required,
                    'qty_available': line.qty_available,
                    'qty_to_purchase': line.qty_to_purchase,
                    'unit_price': line.unit_price,
                    'price_total': line.price_total,
                    'vendor': line.vendor_id.name if line.vendor_id else None,
                    'required_date': line.required_date.isoformat() if line.required_date else None,
                })
            
            data = {
                'id': requisition.id,
                'name': requisition.name,
                'state': requisition.state,
                'priority': requisition.priority,
                'requisition_type': requisition.requisition_type,
                'production_stage': requisition.production_stage,
                'department': {
                    'id': requisition.department_id.id,
                    'name': requisition.department_id.name
                } if requisition.department_id else None,
                'requested_by': {
                    'id': requisition.requested_by.id,
                    'name': requisition.requested_by.name
                },
                'request_date': requisition.request_date.isoformat() if requisition.request_date else None,
                'required_date': requisition.required_date.isoformat() if requisition.required_date else None,
                'reason': requisition.reason,
                'total_amount': requisition.total_amount,
                'currency': requisition.currency_id.name,
                'manufacturing_order': {
                    'id': requisition.manufacturing_order_id.id,
                    'name': requisition.manufacturing_order_id.name
                } if requisition.manufacturing_order_id else None,
                'lines': lines,
                'approvals': {
                    'shop_floor_approved': requisition.shop_floor_approved,
                    'supervisor_approved': requisition.supervisor_approved,
                    'manager_approved': requisition.manager_approved,
                    'procurement_approved': requisition.procurement_approved,
                },
                'inventory_available': requisition.inventory_available,
                'purchase_order_count': requisition.purchase_order_count,
                'picking_count': requisition.picking_count,
            }
            
            return {
                'success': True,
                'data': data
            }
            
        except Exception as e:
            _logger.error(f"API get_requisition_detail error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'code': 500
            }

    @http.route('/api/v1/manufacturing/requisitions', type='json', auth='none', methods=['POST'], csrf=False)
    def create_requisition(self, **kwargs):
        """Create requisition via API"""
        api_key = request.httprequest.headers.get('X-API-Key')
        auth_result = self._validate_api_access(api_key)
        
        if not auth_result['success']:
            return auth_result
        
        try:
            data = kwargs
            
            # Validate required fields
            required_fields = ['requisition_type', 'department_id', 'required_date', 'reason', 'lines']
            for field in required_fields:
                if field not in data:
                    return {
                        'success': False,
                        'error': f'Missing required field: {field}',
                        'code': 400
                    }
            
            # Create requisition
            requisition_vals = {
                'requisition_type': data['requisition_type'],
                'department_id': data['department_id'],
                'required_date': data['required_date'],
                'reason': data['reason'],
                'priority': data.get('priority', 'medium'),
                'production_stage': data.get('production_stage', 'raw_material'),
            }
            
            # Optional fields
            if data.get('manufacturing_order_id'):
                requisition_vals['manufacturing_order_id'] = data['manufacturing_order_id']
            if data.get('location_id'):
                requisition_vals['location_id'] = data['location_id']
            if data.get('dest_location_id'):
                requisition_vals['dest_location_id'] = data['dest_location_id']
            
            requisition = request.env['manufacturing.material.requisition'].create(requisition_vals)
            
            # Create lines
            for line_data in data['lines']:
                line_vals = {
                    'requisition_id': requisition.id,
                    'product_id': line_data['product_id'],
                    'qty_required': line_data['qty_required'],
                    'required_date': line_data.get('required_date', data['required_date']),
                    'reason': line_data.get('reason', ''),
                }
                
                if line_data.get('vendor_id'):
                    line_vals['vendor_id'] = line_data['vendor_id']
                if line_data.get('unit_price'):
                    line_vals['unit_price'] = line_data['unit_price']
                
                request.env['manufacturing.material.requisition.line'].create(line_vals)
            
            return {
                'success': True,
                'data': {
                    'id': requisition.id,
                    'name': requisition.name,
                    'state': requisition.state
                }
            }
            
        except Exception as e:
            _logger.error(f"API create_requisition error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'code': 500
            }

    @http.route('/api/v1/manufacturing/requisitions/<int:requisition_id>/approve', type='json', auth='none', methods=['POST'], csrf=False)
    def approve_requisition(self, requisition_id, **kwargs):
        """Approve requisition via API"""
        api_key = request.httprequest.headers.get('X-API-Key')
        auth_result = self._validate_api_access(api_key)
        
        if not auth_result['success']:
            return auth_result
        
        try:
            requisition = request.env['manufacturing.material.requisition'].browse(requisition_id)
            
            if not requisition.exists():
                return {
                    'success': False,
                    'error': 'Requisition not found',
                    'code': 404
                }
            
            approval_type = kwargs.get('approval_type', 'auto')
            
            if approval_type == 'shop_floor' or requisition.state == 'submitted':
                requisition.action_shop_floor_approve()
            elif approval_type == 'supervisor' or requisition.state == 'supervisor_approval':
                requisition.action_supervisor_approve()
            elif approval_type == 'manager' or requisition.state == 'manager_approval':
                requisition.action_manager_approve()
            elif approval_type == 'procurement' or requisition.state == 'procurement_approval':
                requisition.action_procurement_approve()
            else:
                return {
                    'success': False,
                    'error': f'Cannot approve requisition in state: {requisition.state}',
                    'code': 400
                }
            
            return {
                'success': True,
                'data': {
                    'id': requisition.id,
                    'name': requisition.name,
                    'state': requisition.state
                }
            }
            
        except Exception as e:
            _logger.error(f"API approve_requisition error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'code': 500
            }

    @http.route('/api/v1/shop_floor/emergency', type='json', auth='none', methods=['POST'], csrf=False)
    def create_emergency_requisition(self, **kwargs):
        """Create emergency requisition via API"""
        api_key = request.httprequest.headers.get('X-API-Key')
        auth_result = self._validate_api_access(api_key)
        
        if not auth_result['success']:
            return auth_result
        
        try:
            data = kwargs
            
            # Validate required fields
            required_fields = ['machine_id', 'materials', 'production_impact']
            for field in required_fields:
                if field not in data:
                    return {
                        'success': False,
                        'error': f'Missing required field: {field}',
                        'code': 400
                    }
            
            # Create emergency requisition
            requisition = request.env['shop.floor.requisition'].create_emergency_requisition(
                machine_id=data['machine_id'],
                operator_id=auth_result['user'].id,
                materials=data['materials'],
                impact=data['production_impact']
            )
            
            return {
                'success': True,
                'data': {
                    'id': requisition.id,
                    'name': requisition.name,
                    'state': requisition.state,
                    'is_emergency': requisition.is_emergency,
                    'production_impact': requisition.production_impact
                }
            }
            
        except Exception as e:
            _logger.error(f"API create_emergency_requisition error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'code': 500
            }

    @http.route('/api/v1/products/search', type='json', auth='none', methods=['GET'], csrf=False)
    def search_products(self, **kwargs):
        """Search products via API"""
        api_key = request.httprequest.headers.get('X-API-Key')
        auth_result = self._validate_api_access(api_key)
        
        if not auth_result['success']:
            return auth_result
        
        try:
            search_term = kwargs.get('search_term', '')
            limit = int(kwargs.get('limit', 20))
            
            domain = [
                '|', ('name', 'ilike', search_term),
                ('default_code', 'ilike', search_term)
            ]
            
            products = request.env['product.product'].search(domain, limit=limit)
            
            data = []
            for product in products:
                data.append({
                    'id': product.id,
                    'name': product.name,
                    'default_code': product.default_code,
                    'barcode': product.barcode,
                    'uom_name': product.uom_id.name,
                    'standard_price': product.standard_price,
                    'qty_available': product.qty_available,
                    'categ_id': product.categ_id.id,
                    'categ_name': product.categ_id.name,
                })
            
            return {
                'success': True,
                'data': data,
                'count': len(data)
            }
            
        except Exception as e:
            _logger.error(f"API search_products error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'code': 500
            }

    @http.route('/api/v1/analytics/dashboard', type='json', auth='none', methods=['GET'], csrf=False)
    def get_analytics_dashboard(self, **kwargs):
        """Get analytics dashboard data via API"""
        api_key = request.httprequest.headers.get('X-API-Key')
        auth_result = self._validate_api_access(api_key)
        
        if not auth_result['success']:
            return auth_result
        
        try:
            # Get date range
            date_from = kwargs.get('date_from')
            date_to = kwargs.get('date_to')
            
            if not date_from or not date_to:
                date_to = datetime.now().date()
                date_from = date_to - timedelta(days=30)
            
            # Get analytics data
            analytics = request.env['manufacturing.requisition.analytics'].search([
                ('requisition_date', '>=', date_from),
                ('requisition_date', '<=', date_to)
            ])
            
            # Calculate KPIs
            total_requisitions = len(analytics)
            completed_requisitions = len(analytics.filtered(lambda r: r.state == 'completed'))
            avg_cycle_time = sum(analytics.mapped('total_cycle_time')) / total_requisitions if total_requisitions else 0
            total_cost = sum(analytics.mapped('total_cost'))
            on_time_delivery_count = len(analytics.filtered(lambda r: r.on_time_delivery))
            
            # Get emergency requisitions
            emergency_count = len(analytics.filtered(lambda r: r.requisition_type == 'emergency'))
            
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
            
            # Get department performance
            dept_data = {}
            for record in analytics:
                if record.department_id:
                    dept_id = record.department_id.id
                    if dept_id not in dept_data:
                        dept_data[dept_id] = {
                            'name': record.department_id.name,
                            'count': 0,
                            'avg_cycle_time': 0,
                            'total_cost': 0
                        }
                    dept_data[dept_id]['count'] += 1
                    dept_data[dept_id]['total_cost'] += record.total_cost
            
            # Calculate average cycle times for departments
            for dept_id, dept_info in dept_data.items():
                dept_analytics = analytics.filtered(lambda r: r.department_id.id == dept_id)
                dept_info['avg_cycle_time'] = sum(dept_analytics.mapped('total_cycle_time')) / len(dept_analytics)
            
            data = {
                'period': {
                    'date_from': date_from.isoformat() if hasattr(date_from, 'isoformat') else str(date_from),
                    'date_to': date_to.isoformat() if hasattr(date_to, 'isoformat') else str(date_to)
                },
                'kpis': {
                    'total_requisitions': total_requisitions,
                    'completed_requisitions': completed_requisitions,
                    'completion_rate': (completed_requisitions / total_requisitions * 100) if total_requisitions else 0,
                    'avg_cycle_time': avg_cycle_time,
                    'total_cost': total_cost,
                    'on_time_delivery_rate': (on_time_delivery_count / total_requisitions * 100) if total_requisitions else 0,
                    'emergency_count': emergency_count,
                    'emergency_rate': (emergency_count / total_requisitions * 100) if total_requisitions else 0
                },
                'top_products': top_products,
                'department_performance': list(dept_data.values())
            }
            
            return {
                'success': True,
                'data': data
            }
            
        except Exception as e:
            _logger.error(f"API get_analytics_dashboard error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'code': 500
            }

    @http.route('/api/v1/machines/status', type='json', auth='none', methods=['GET'], csrf=False)
    def get_machines_status(self, **kwargs):
        """Get machines status via API"""
        api_key = request.httprequest.headers.get('X-API-Key')
        auth_result = self._validate_api_access(api_key)
        
        if not auth_result['success']:
            return auth_result
        
        try:
            # Get machines for current user or all if admin
            user = auth_result['user']
            if user.has_group('manufacturing_material_requisitions.group_manufacturing_manager'):
                machines = request.env['maintenance.equipment'].search([])
            else:
                machines = request.env['maintenance.equipment'].search([
                    ('operator_ids', 'in', [user.id])
                ])
            
            data = []
            for machine in machines:
                # Get pending requisitions
                pending_requisitions = request.env['shop.floor.requisition'].search_count([
                    ('machine_id', '=', machine.id),
                    ('state', 'not in', ['completed', 'cancelled'])
                ])
                
                # Get current downtime
                current_downtime = request.env['maintenance.downtime'].search([
                    ('equipment_id', '=', machine.id),
                    ('end_time', '=', False)
                ], limit=1)
                
                data.append({
                    'id': machine.id,
                    'name': machine.name,
                    'category': machine.category_id.name if machine.category_id else None,
                    'location': machine.location,
                    'maintenance_state': machine.maintenance_state,
                    'last_maintenance': machine.last_maintenance_date.isoformat() if machine.last_maintenance_date else None,
                    'next_maintenance': machine.next_action_date.isoformat() if machine.next_action_date else None,
                    'pending_requisitions': pending_requisitions,
                    'is_down': bool(current_downtime),
                    'downtime_start': current_downtime.start_time.isoformat() if current_downtime else None,
                    'work_center': machine.workcenter_id.name if machine.workcenter_id else None,
                })
            
            return {
                'success': True,
                'data': data,
                'count': len(data)
            }
            
        except Exception as e:
            _logger.error(f"API get_machines_status error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'code': 500
            }

    @http.route('/api/v1/health', type='json', auth='none', methods=['GET'], csrf=False)
    def health_check(self, **kwargs):
        """API health check endpoint"""
        return {
            'success': True,
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0'
        } 