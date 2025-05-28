from odoo import http, _
from odoo.http import request
import json
import base64
import logging

_logger = logging.getLogger(__name__)


class ShopFloorController(http.Controller):

    @http.route('/shop_floor/dashboard', type='http', auth='user', website=True)
    def shop_floor_dashboard(self, **kwargs):
        """Shop floor dashboard for operators"""
        user = request.env.user
        
        # Get user's work center
        work_center = request.env['mrp.workcenter'].search([
            ('operator_ids', 'in', [user.id])
        ], limit=1)
        
        # Get active emergency requisitions
        emergency_requisitions = request.env['shop.floor.requisition'].search([
            ('is_emergency', '=', True),
            ('state', 'not in', ['completed', 'cancelled']),
            ('work_center_id', '=', work_center.id) if work_center else ('id', '>', 0)
        ])
        
        # Get pending requisitions
        pending_requisitions = request.env['shop.floor.requisition'].search([
            ('operator_id', '=', user.id),
            ('state', 'in', ['draft', 'submitted'])
        ])
        
        # Get machines assigned to user
        machines = request.env['maintenance.equipment'].search([
            ('operator_ids', 'in', [user.id])
        ])
        
        # Get current shift
        current_shift = request.env['manufacturing.shift']._get_current_shift()
        
        values = {
            'user': user,
            'work_center': work_center,
            'emergency_requisitions': emergency_requisitions,
            'pending_requisitions': pending_requisitions,
            'machines': machines,
            'current_shift': current_shift,
        }
        
        return request.render('manufacturing_material_requisitions.shop_floor_dashboard', values)

    @http.route('/shop_floor/emergency', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def create_emergency_requisition(self, **kwargs):
        """Create emergency requisition from shop floor"""
        if request.httprequest.method == 'POST':
            try:
                machine_id = int(kwargs.get('machine_id'))
                operator_id = request.env.user.id
                impact = kwargs.get('production_impact', 'production_stop')
                reason = kwargs.get('reason', 'Emergency breakdown')
                
                # Parse materials from form
                materials = []
                product_ids = kwargs.getlist('product_id[]')
                quantities = kwargs.getlist('quantity[]')
                
                for i, product_id in enumerate(product_ids):
                    if product_id and quantities[i]:
                        materials.append({
                            'product_id': int(product_id),
                            'qty': float(quantities[i]),
                            'reason': reason
                        })
                
                # Create emergency requisition
                requisition = request.env['shop.floor.requisition'].create_emergency_requisition(
                    machine_id=machine_id,
                    operator_id=operator_id,
                    materials=materials,
                    impact=impact
                )
                
                return request.redirect(f'/shop_floor/requisition/{requisition.id}')
                
            except Exception as e:
                _logger.error(f"Error creating emergency requisition: {str(e)}")
                return request.render('manufacturing_material_requisitions.error_template', {
                    'error': str(e)
                })
        
        # GET request - show form
        user = request.env.user
        machines = request.env['maintenance.equipment'].search([
            ('operator_ids', 'in', [user.id])
        ])
        
        # Get common spare parts for machines
        spare_parts = request.env['product.product'].search([
            ('categ_id.name', 'ilike', 'spare'),
            ('type', '=', 'product')
        ], limit=50)
        
        values = {
            'machines': machines,
            'spare_parts': spare_parts,
            'user': user,
        }
        
        return request.render('manufacturing_material_requisitions.emergency_form', values)

    @http.route('/shop_floor/requisition/<int:requisition_id>', type='http', auth='user', website=True)
    def view_shop_floor_requisition(self, requisition_id, **kwargs):
        """View shop floor requisition details"""
        requisition = request.env['shop.floor.requisition'].browse(requisition_id)
        
        if not requisition.exists():
            return request.not_found()
        
        values = {
            'requisition': requisition,
            'can_approve': request.env.user.has_group('manufacturing_material_requisitions.group_shop_floor_supervisor'),
        }
        
        return request.render('manufacturing_material_requisitions.shop_floor_requisition_detail', values)

    @http.route('/shop_floor/barcode_scan', type='json', auth='user')
    def process_barcode_scan(self, **kwargs):
        """Process barcode scan from shop floor terminal"""
        try:
            barcode = kwargs.get('barcode')
            terminal_id = kwargs.get('terminal_id')
            
            # Find product by barcode
            product = request.env['product.product'].search([
                '|', ('barcode', '=', barcode),
                ('default_code', '=', barcode)
            ], limit=1)
            
            if not product:
                return {
                    'success': False,
                    'message': f'Product not found for barcode: {barcode}'
                }
            
            # Get stock information
            stock_info = {
                'product_id': product.id,
                'product_name': product.name,
                'default_code': product.default_code,
                'qty_available': product.qty_available,
                'uom_name': product.uom_id.name,
                'standard_price': product.standard_price,
            }
            
            # Log scan activity
            if terminal_id:
                terminal = request.env['shop.floor.terminal'].browse(int(terminal_id))
                terminal.last_activity = request.env.cr.now()
            
            return {
                'success': True,
                'product': stock_info,
                'message': f'Product {product.name} scanned successfully'
            }
            
        except Exception as e:
            _logger.error(f"Barcode scan error: {str(e)}")
            return {
                'success': False,
                'message': f'Scan error: {str(e)}'
            }

    @http.route('/shop_floor/voice_requisition', type='json', auth='user')
    def process_voice_requisition(self, **kwargs):
        """Process voice-to-text requisition"""
        try:
            voice_data = kwargs.get('voice_data')
            machine_id = kwargs.get('machine_id')
            operator_id = request.env.user.id
            
            if not voice_data:
                return {
                    'success': False,
                    'message': 'No voice data provided'
                }
            
            # Process voice requisition
            result = request.env['shop.floor.requisition'].process_voice_requisition(
                voice_data=voice_data,
                operator_id=operator_id,
                machine_id=machine_id
            )
            
            return result
            
        except Exception as e:
            _logger.error(f"Voice requisition error: {str(e)}")
            return {
                'success': False,
                'message': f'Voice processing error: {str(e)}'
            }

    @http.route('/shop_floor/photo_upload', type='http', auth='user', methods=['POST'])
    def upload_photo(self, **kwargs):
        """Upload photo documentation for requisition"""
        try:
            requisition_id = int(kwargs.get('requisition_id'))
            description = kwargs.get('description', 'Shop floor photo')
            photo_file = kwargs.get('photo')
            
            if not photo_file:
                return json.dumps({
                    'success': False,
                    'message': 'No photo file provided'
                })
            
            # Create photo record
            photo_vals = {
                'requisition_id': requisition_id,
                'name': description,
                'image': base64.b64encode(photo_file.read()),
                'taken_by': request.env.user.id,
            }
            
            if kwargs.get('gps_location'):
                photo_vals['gps_location'] = kwargs.get('gps_location')
            
            photo = request.env['shop.floor.photo'].create(photo_vals)
            
            return json.dumps({
                'success': True,
                'photo_id': photo.id,
                'message': 'Photo uploaded successfully'
            })
            
        except Exception as e:
            _logger.error(f"Photo upload error: {str(e)}")
            return json.dumps({
                'success': False,
                'message': f'Upload error: {str(e)}'
            })

    @http.route('/shop_floor/machine_status', type='json', auth='user')
    def get_machine_status(self, **kwargs):
        """Get machine status for shop floor display"""
        try:
            machine_id = kwargs.get('machine_id')
            
            if not machine_id:
                return {'success': False, 'message': 'Machine ID required'}
            
            machine = request.env['maintenance.equipment'].browse(int(machine_id))
            
            if not machine.exists():
                return {'success': False, 'message': 'Machine not found'}
            
            # Get current maintenance requests
            maintenance_requests = request.env['maintenance.request'].search([
                ('equipment_id', '=', machine.id),
                ('stage_id.done', '=', False)
            ])
            
            # Get pending requisitions
            pending_requisitions = request.env['shop.floor.requisition'].search([
                ('machine_id', '=', machine.id),
                ('state', 'not in', ['completed', 'cancelled'])
            ])
            
            # Get downtime information
            current_downtime = request.env['maintenance.downtime'].search([
                ('equipment_id', '=', machine.id),
                ('end_time', '=', False)
            ], limit=1)
            
            status_data = {
                'machine_name': machine.name,
                'maintenance_state': machine.maintenance_state,
                'last_maintenance': machine.last_maintenance_date.isoformat() if machine.last_maintenance_date else None,
                'next_maintenance': machine.next_action_date.isoformat() if machine.next_action_date else None,
                'maintenance_requests_count': len(maintenance_requests),
                'pending_requisitions_count': len(pending_requisitions),
                'is_down': bool(current_downtime),
                'downtime_start': current_downtime.start_time.isoformat() if current_downtime else None,
            }
            
            return {
                'success': True,
                'status': status_data
            }
            
        except Exception as e:
            _logger.error(f"Machine status error: {str(e)}")
            return {
                'success': False,
                'message': f'Status error: {str(e)}'
            }

    @http.route('/shop_floor/approve/<int:requisition_id>', type='http', auth='user', methods=['POST'])
    def approve_shop_floor_requisition(self, requisition_id, **kwargs):
        """Approve shop floor requisition"""
        try:
            requisition = request.env['shop.floor.requisition'].browse(requisition_id)
            
            if not requisition.exists():
                return request.not_found()
            
            # Check approval rights
            if not request.env.user.has_group('manufacturing_material_requisitions.group_shop_floor_supervisor'):
                return request.redirect('/web/login')
            
            requisition.action_shop_floor_approve()
            
            return request.redirect(f'/shop_floor/requisition/{requisition_id}')
            
        except Exception as e:
            _logger.error(f"Approval error: {str(e)}")
            return request.render('manufacturing_material_requisitions.error_template', {
                'error': str(e)
            })

    @http.route('/shop_floor/escalate/<int:requisition_id>', type='http', auth='user', methods=['POST'])
    def escalate_requisition(self, requisition_id, **kwargs):
        """Escalate emergency requisition"""
        try:
            requisition = request.env['shop.floor.requisition'].browse(requisition_id)
            reason = kwargs.get('escalation_reason', 'Manual escalation from shop floor')
            
            if not requisition.exists():
                return request.not_found()
            
            requisition.action_escalate(reason)
            
            return request.redirect(f'/shop_floor/requisition/{requisition_id}')
            
        except Exception as e:
            _logger.error(f"Escalation error: {str(e)}")
            return request.render('manufacturing_material_requisitions.error_template', {
                'error': str(e)
            })

    @http.route('/shop_floor/terminal/<int:terminal_id>/status', type='json', auth='user')
    def terminal_status(self, terminal_id, **kwargs):
        """Get shop floor terminal status"""
        try:
            terminal = request.env['shop.floor.terminal'].browse(terminal_id)
            
            if not terminal.exists():
                return {'success': False, 'message': 'Terminal not found'}
            
            # Update last activity
            terminal.last_activity = request.env.cr.now()
            
            # Get terminal capabilities
            capabilities = {
                'has_barcode_scanner': terminal.has_barcode_scanner,
                'has_camera': terminal.has_camera,
                'has_microphone': terminal.has_microphone,
                'has_printer': terminal.has_printer,
            }
            
            # Get work center information
            work_center_info = {
                'name': terminal.work_center_id.name,
                'active_orders': len(terminal.work_center_id.order_ids.filtered(lambda o: o.state == 'progress')),
            }
            
            return {
                'success': True,
                'terminal': {
                    'name': terminal.name,
                    'location': terminal.location,
                    'capabilities': capabilities,
                    'work_center': work_center_info,
                }
            }
            
        except Exception as e:
            _logger.error(f"Terminal status error: {str(e)}")
            return {
                'success': False,
                'message': f'Terminal error: {str(e)}'
            }

    @http.route('/shop_floor/quick_requisition', type='json', auth='user')
    def create_quick_requisition(self, **kwargs):
        """Create quick requisition from shop floor"""
        try:
            product_id = kwargs.get('product_id')
            quantity = kwargs.get('quantity', 1)
            machine_id = kwargs.get('machine_id')
            urgency = kwargs.get('urgency', 'medium')
            
            if not product_id:
                return {
                    'success': False,
                    'message': 'Product ID required'
                }
            
            # Create quick requisition
            requisition_vals = {
                'operator_id': request.env.user.id,
                'machine_id': machine_id,
                'requisition_type': 'shop_floor',
                'priority': urgency,
                'reason': 'Quick requisition from shop floor',
                'required_date': request.env.cr.now(),
            }
            
            requisition = request.env['shop.floor.requisition'].create(requisition_vals)
            
            # Create requisition line
            line_vals = {
                'requisition_id': requisition.id,
                'product_id': int(product_id),
                'qty_required': float(quantity),
                'required_date': request.env.cr.now(),
                'reason': 'Quick requisition',
            }
            request.env['manufacturing.material.requisition.line'].create(line_vals)
            
            # Auto-submit if not emergency
            if urgency != 'emergency':
                requisition.action_submit()
            
            return {
                'success': True,
                'requisition_id': requisition.id,
                'message': f'Quick requisition {requisition.name} created'
            }
            
        except Exception as e:
            _logger.error(f"Quick requisition error: {str(e)}")
            return {
                'success': False,
                'message': f'Creation error: {str(e)}'
            } 