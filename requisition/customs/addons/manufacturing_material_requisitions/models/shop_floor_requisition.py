from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import json
import logging

_logger = logging.getLogger(__name__)


class ShopFloorRequisition(models.Model):
    _name = 'shop.floor.requisition'
    _inherit = ['manufacturing.material.requisition']
    _description = 'Shop Floor Material Requisition'
    _order = 'is_emergency desc, priority desc, create_date desc'

    # Shop Floor Specific Fields
    operator_id = fields.Many2one('res.users', 'Machine Operator', required=True, tracking=True)
    machine_id = fields.Many2one('maintenance.equipment', 'Machine/Equipment', tracking=True)
    work_center_id = fields.Many2one('mrp.workcenter', 'Work Center', required=True, tracking=True)
    downtime_id = fields.Many2one('maintenance.downtime', 'Related Downtime')
    
    # Real-time tracking
    shop_floor_terminal_id = fields.Many2one('shop.floor.terminal', 'Shop Floor Terminal')
    barcode_scan_log = fields.Text('Barcode Scan History')
    rfid_tag = fields.Char('RFID Tag')
    
    # Emergency requisition
    is_emergency = fields.Boolean('Emergency Requisition', default=True, tracking=True)
    production_impact = fields.Selection([
        ('no_impact', 'No Production Impact'),
        ('minor_delay', 'Minor Delay (<1 hour)'),
        ('major_delay', 'Major Delay (1-4 hours)'),
        ('production_stop', 'Production Stop (>4 hours)'),
        ('safety_risk', 'Safety Risk')
    ], string='Production Impact', required=True, default='minor_delay', tracking=True)
    
    # Shift Information
    shift_id = fields.Many2one('manufacturing.shift', 'Manufacturing Shift', 
                              default=lambda self: self._get_current_shift())
    shift_supervisor_id = fields.Many2one('res.users', 'Shift Supervisor',
                                         related='shift_id.supervisor_id', readonly=True)
    
    # Location Context
    current_location = fields.Char('Current Location')
    gps_coordinates = fields.Char('GPS Coordinates')
    
    # Mobile Integration
    mobile_device_id = fields.Char('Mobile Device ID')
    offline_created = fields.Boolean('Created Offline', default=False)
    sync_status = fields.Selection([
        ('pending', 'Pending Sync'),
        ('synced', 'Synced'),
        ('error', 'Sync Error')
    ], string='Sync Status', default='synced')
    
    # Voice Integration
    voice_request = fields.Text('Voice Request Transcript')
    voice_confidence = fields.Float('Voice Recognition Confidence')
    
    # Image/Photo Documentation
    photo_ids = fields.One2many('shop.floor.photo', 'requisition_id', 'Photos')
    
    # Escalation
    escalated = fields.Boolean('Escalated', default=False, tracking=True)
    escalation_reason = fields.Text('Escalation Reason')
    escalated_to = fields.Many2one('res.users', 'Escalated To')
    escalation_date = fields.Datetime('Escalation Date')
    
    # Response Time Tracking
    response_time_target = fields.Float('Response Time Target (Minutes)', default=15.0)
    actual_response_time = fields.Float('Actual Response Time (Minutes)', compute='_compute_response_time')
    response_sla_met = fields.Boolean('Response SLA Met', compute='_compute_response_time')
    
    @api.model
    def _get_current_shift(self):
        """Get current manufacturing shift"""
        current_time = fields.Datetime.now()
        shift = self.env['manufacturing.shift'].search([
            ('start_time', '<=', current_time.time()),
            ('end_time', '>=', current_time.time()),
            ('active', '=', True)
        ], limit=1)
        return shift.id if shift else False
    
    @api.depends('create_date', 'shop_floor_approval_date')
    def _compute_response_time(self):
        for record in self:
            if record.shop_floor_approval_date and record.create_date:
                time_diff = record.shop_floor_approval_date - record.create_date
                record.actual_response_time = time_diff.total_seconds() / 60  # Convert to minutes
                record.response_sla_met = record.actual_response_time <= record.response_time_target
            else:
                record.actual_response_time = 0
                record.response_sla_met = False
    
    @api.model
    def create(self, vals):
        # Auto-set work center based on machine
        if vals.get('machine_id') and not vals.get('work_center_id'):
            machine = self.env['maintenance.equipment'].browse(vals['machine_id'])
            if machine.workcenter_id:
                vals['work_center_id'] = machine.workcenter_id.id
        
        # Auto-set department based on work center
        if vals.get('work_center_id') and not vals.get('department_id'):
            work_center = self.env['mrp.workcenter'].browse(vals['work_center_id'])
            if work_center.department_id:
                vals['department_id'] = work_center.department_id.id
        
        # Set emergency priority
        if vals.get('is_emergency'):
            vals['priority'] = 'urgent'
            vals['urgency_level'] = 'emergency'
        
        # Auto-set locations based on work center
        if vals.get('work_center_id'):
            work_center = self.env['mrp.workcenter'].browse(vals['work_center_id'])
            if not vals.get('location_id') and work_center.default_location_src_id:
                vals['location_id'] = work_center.default_location_src_id.id
            if not vals.get('dest_location_id') and work_center.default_location_dest_id:
                vals['dest_location_id'] = work_center.default_location_dest_id.id
        
        requisition = super().create(vals)
        
        # Trigger emergency notifications
        if requisition.is_emergency:
            requisition._trigger_emergency_notifications()
        
        # Log barcode scan if provided
        if vals.get('barcode_scan_log'):
            requisition._process_barcode_scans()
        
        return requisition
    
    @api.model
    def create_emergency_requisition(self, machine_id, operator_id, materials, impact='production_stop'):
        """Create emergency requisition from shop floor"""
        machine = self.env['maintenance.equipment'].browse(machine_id)
        operator = self.env['res.users'].browse(operator_id)
        
        requisition_vals = {
            'name': f"EMERGENCY-{fields.Datetime.now().strftime('%Y%m%d-%H%M%S')}",
            'operator_id': operator_id,
            'machine_id': machine_id,
            'work_center_id': machine.workcenter_id.id if machine.workcenter_id else False,
            'requisition_type': 'emergency',
            'production_stage': 'maintenance',
            'is_emergency': True,
            'production_impact': impact,
            'priority': 'critical',
            'urgency_level': 'emergency',
            'required_date': fields.Datetime.now() + timedelta(hours=1),
            'reason': f'Emergency breakdown on {machine.name}',
            'state': 'submitted',  # Skip draft state for emergencies
        }
        
        requisition = self.create(requisition_vals)
        
        # Create requisition lines
        for material in materials:
            line_vals = {
                'requisition_id': requisition.id,
                'product_id': material['product_id'],
                'qty_required': material['qty'],
                'required_date': fields.Datetime.now() + timedelta(minutes=30),
                'reason': material.get('reason', 'Emergency breakdown repair'),
            }
            self.env['manufacturing.material.requisition.line'].create(line_vals)
        
        # Auto-approve if within operator limits
        if requisition._check_auto_approval_limits():
            requisition.action_auto_approve()
        
        return requisition
    
    def _check_auto_approval_limits(self):
        """Check if requisition can be auto-approved based on operator limits"""
        operator_limits = self.env['shop.floor.approval.limits'].search([
            ('user_id', '=', self.operator_id.id),
            ('work_center_id', '=', self.work_center_id.id)
        ], limit=1)
        
        if not operator_limits:
            return False
        
        # Check amount limit
        if self.total_amount > operator_limits.max_amount:
            return False
        
        # Check emergency approval rights
        if self.is_emergency and not operator_limits.can_approve_emergency:
            return False
        
        return True
    
    def action_auto_approve(self):
        """Auto-approve emergency requisition"""
        self.write({
            'state': 'approved',
            'shop_floor_approved': True,
            'shop_floor_approver_id': self.operator_id.id,
            'shop_floor_approval_date': fields.Datetime.now(),
        })
        
        # Create immediate stock moves if materials available
        if self.inventory_available:
            self._create_emergency_transfers()
        else:
            self._create_emergency_purchase_orders()
    
    def _create_emergency_transfers(self):
        """Create immediate stock transfers for emergency requisitions"""
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id.company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not picking_type:
            return
        
        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': self.location_id.id,
            'location_dest_id': self.dest_location_id.id,
            'requisition_id': self.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'priority': '1',  # Urgent priority
            'immediate_transfer': True,
        }
        
        picking = self.env['stock.picking'].create(picking_vals)
        
        for line in self.line_ids:
            if line.product_id and line.qty_required > 0:
                move_vals = {
                    'name': f"EMERGENCY: {line.product_id.name}",
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.qty_required,
                    'product_uom': line.product_id.uom_id.id,
                    'location_id': self.location_id.id,
                    'location_dest_id': self.dest_location_id.id,
                    'picking_id': picking.id,
                    'requisition_id': self.id,
                    'requisition_line_id': line.id,
                    'company_id': self.company_id.id,
                    'priority': '1',
                }
                self.env['stock.move'].create(move_vals)
        
        if picking.move_ids:
            picking.action_confirm()
            picking.action_assign()
            # Auto-validate if all products are available
            if all(move.state == 'assigned' for move in picking.move_ids):
                picking.button_validate()
    
    def _create_emergency_purchase_orders(self):
        """Create emergency purchase orders with expedited delivery"""
        vendors = {}
        
        for line in self.line_ids:
            if line.vendor_id and line.qty_to_purchase > 0:
                if line.vendor_id not in vendors:
                    vendors[line.vendor_id] = []
                vendors[line.vendor_id].append(line)
        
        for vendor, lines in vendors.items():
            po_vals = {
                'partner_id': vendor.id,
                'requisition_id': self.id,
                'origin': f"EMERGENCY: {self.name}",
                'company_id': self.company_id.id,
                'currency_id': vendor.property_purchase_currency_id.id or self.company_id.currency_id.id,
                'date_planned': fields.Datetime.now() + timedelta(hours=4),  # Emergency delivery
                'priority': '3',  # Urgent
                'notes': f"EMERGENCY REQUISITION - Machine: {self.machine_id.name} - Impact: {self.production_impact}",
            }
            
            purchase_order = self.env['purchase.order'].create(po_vals)
            
            for line in lines:
                po_line_vals = {
                    'order_id': purchase_order.id,
                    'product_id': line.product_id.id,
                    'product_qty': line.qty_to_purchase,
                    'product_uom': line.product_id.uom_po_id.id,
                    'price_unit': line.unit_price * 1.2,  # Accept 20% premium for emergency
                    'date_planned': fields.Datetime.now() + timedelta(hours=4),
                    'requisition_line_id': line.id,
                }
                self.env['purchase.order.line'].create(po_line_vals)
            
            purchase_order.button_confirm()
            
            # Send urgent notification to vendor
            self._send_emergency_vendor_notification(purchase_order)
    
    def _trigger_emergency_notifications(self):
        """Send immediate notifications for emergency requisitions"""
        # Notify maintenance team
        maintenance_team = self.env['maintenance.team'].search([
            ('equipment_ids', 'in', [self.machine_id.id])
        ], limit=1)
        
        # Notify warehouse team
        warehouse_team = self.env['stock.warehouse'].search([
            ('company_id', '=', self.company_id.id)
        ], limit=1).warehouse_team_ids
        
        # Notify production manager
        production_manager = self.work_center_id.department_id.manager_id
        
        # Notify shift supervisor
        shift_supervisor = self.shift_supervisor_id
        
        recipients = maintenance_team.member_ids + warehouse_team + production_manager + shift_supervisor
        
        # Send SMS for critical emergencies
        if self.production_impact in ['production_stop', 'safety_risk']:
            self._send_emergency_sms(recipients)
        
        # Send email notifications
        for recipient in recipients:
            self.env['mail.message'].create({
                'subject': f'🚨 EMERGENCY REQUISITION: {self.name}',
                'body': self._get_emergency_notification_body(),
                'partner_ids': [(4, recipient.partner_id.id)],
                'message_type': 'email',
                'subtype_id': self.env.ref('mail.mt_comment').id,
            })
        
        # Create urgent activities
        for recipient in recipients:
            self.activity_schedule(
                'manufacturing_material_requisitions.mail_activity_emergency_requisition',
                user_id=recipient.id,
                summary=f'🚨 EMERGENCY: {self.name}',
                note=self._get_emergency_notification_body(),
                date_deadline=fields.Date.today(),
            )
    
    def _get_emergency_notification_body(self):
        """Get emergency notification message body"""
        return f"""
        <div style="background-color: #ff4444; color: white; padding: 10px; border-radius: 5px;">
            <h3>🚨 EMERGENCY MATERIAL REQUISITION</h3>
        </div>
        <br/>
        <p><strong>Requisition:</strong> {self.name}</p>
        <p><strong>Machine:</strong> {self.machine_id.name}</p>
        <p><strong>Operator:</strong> {self.operator_id.name}</p>
        <p><strong>Work Center:</strong> {self.work_center_id.name}</p>
        <p><strong>Production Impact:</strong> {dict(self._fields['production_impact'].selection)[self.production_impact]}</p>
        <p><strong>Required Materials:</strong> {len(self.line_ids)} items</p>
        <p><strong>Estimated Cost:</strong> {self.currency_id.symbol}{self.total_amount:,.2f}</p>
        <br/>
        <p><strong>Reason:</strong> {self.reason}</p>
        <br/>
        <p><a href="/web#id={self.id}&model=shop.floor.requisition" 
              style="background-color: #ff4444; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
              VIEW EMERGENCY REQUISITION
           </a></p>
        """
    
    def _send_emergency_sms(self, recipients):
        """Send SMS notifications for critical emergencies"""
        sms_body = f"🚨 EMERGENCY: Machine {self.machine_id.name} down. Requisition {self.name} created. Impact: {self.production_impact}. Check Odoo immediately."
        
        for recipient in recipients:
            if recipient.mobile:
                self.env['sms.sms'].create({
                    'number': recipient.mobile,
                    'body': sms_body,
                    'partner_id': recipient.partner_id.id,
                })
    
    def _send_emergency_vendor_notification(self, purchase_order):
        """Send emergency notification to vendor"""
        template = self.env.ref('manufacturing_material_requisitions.email_template_emergency_vendor', False)
        if template:
            template.with_context(purchase_order=purchase_order).send_mail(purchase_order.id, force_send=True)
    
    def _process_barcode_scans(self):
        """Process barcode scan history"""
        if not self.barcode_scan_log:
            return
        
        try:
            scan_data = json.loads(self.barcode_scan_log)
            for scan in scan_data:
                product = self.env['product.product'].search([
                    '|', ('barcode', '=', scan['barcode']),
                    ('default_code', '=', scan['barcode'])
                ], limit=1)
                
                if product:
                    # Check if line already exists
                    existing_line = self.line_ids.filtered(lambda l: l.product_id.id == product.id)
                    if existing_line:
                        existing_line.qty_required += scan.get('qty', 1)
                    else:
                        # Create new line
                        self.env['manufacturing.material.requisition.line'].create({
                            'requisition_id': self.id,
                            'product_id': product.id,
                            'qty_required': scan.get('qty', 1),
                            'required_date': self.required_date,
                            'reason': 'Scanned from shop floor',
                        })
        except (json.JSONDecodeError, KeyError) as e:
            _logger.warning(f"Failed to process barcode scans for requisition {self.name}: {str(e)}")
    
    @api.model
    def process_voice_requisition(self, voice_data, operator_id, machine_id):
        """Process voice-to-text requisition creation"""
        try:
            # Use AI service to process voice input
            ai_service = self.env['manufacturing.requisition.ai']
            processed_text = ai_service.process_voice_input(voice_data)
            requisition_data = ai_service.extract_requisition_intent(processed_text)
            
            if requisition_data.get('products'):
                requisition_vals = {
                    'operator_id': operator_id,
                    'machine_id': machine_id,
                    'voice_request': processed_text['transcript'],
                    'voice_confidence': processed_text['confidence'],
                    'reason': requisition_data.get('reason', 'Voice requisition'),
                    'is_emergency': requisition_data.get('is_emergency', False),
                    'production_impact': requisition_data.get('impact', 'minor_delay'),
                }
                
                requisition = self.create(requisition_vals)
                
                # Create lines from voice data
                for product_data in requisition_data['products']:
                    product = self.env['product.product'].search([
                        '|', ('name', 'ilike', product_data['name']),
                        ('default_code', 'ilike', product_data['name'])
                    ], limit=1)
                    
                    if product:
                        self.env['manufacturing.material.requisition.line'].create({
                            'requisition_id': requisition.id,
                            'product_id': product.id,
                            'qty_required': product_data.get('quantity', 1),
                            'required_date': requisition.required_date,
                            'reason': 'Voice requisition',
                        })
                
                return {
                    'success': True,
                    'requisition_id': requisition.id,
                    'message': f'Voice requisition {requisition.name} created successfully'
                }
            
            return {
                'success': False,
                'message': 'Could not understand requisition requirements from voice input'
            }
            
        except Exception as e:
            _logger.error(f"Voice requisition processing failed: {str(e)}")
            return {
                'success': False,
                'message': f'Voice processing failed: {str(e)}'
            }
    
    def action_escalate(self, reason):
        """Escalate emergency requisition"""
        escalation_target = self._get_escalation_target()
        
        self.write({
            'escalated': True,
            'escalation_reason': reason,
            'escalated_to': escalation_target.id,
            'escalation_date': fields.Datetime.now(),
        })
        
        # Send escalation notification
        self.activity_schedule(
            'manufacturing_material_requisitions.mail_activity_requisition_escalation',
            user_id=escalation_target.id,
            summary=f'Escalated Emergency Requisition: {self.name}',
            note=f'Emergency requisition escalated. Reason: {reason}',
            date_deadline=fields.Date.today(),
        )
    
    def _get_escalation_target(self):
        """Get escalation target based on hierarchy"""
        # First try department manager
        if self.department_id.manager_id:
            return self.department_id.manager_id
        
        # Then try plant manager
        plant_manager = self.env['res.users'].search([
            ('groups_id', 'in', self.env.ref('manufacturing_material_requisitions.group_plant_manager').id)
        ], limit=1)
        
        if plant_manager:
            return plant_manager
        
        # Finally, try any manufacturing manager
        return self.env['res.users'].search([
            ('groups_id', 'in', self.env.ref('mrp.group_mrp_manager').id)
        ], limit=1)
    
    def action_mark_received(self):
        """Mark materials as received on shop floor"""
        self.state = 'received'
        
        # Update machine status if linked to downtime
        if self.downtime_id:
            self.downtime_id.write({
                'material_available': True,
                'material_received_date': fields.Datetime.now(),
            })
        
        # Notify operator
        self.operator_id.notify_info(
            message=f'Materials for requisition {self.name} have been received',
            title='Materials Received'
        )
    
    def action_complete_emergency(self):
        """Complete emergency requisition"""
        self.state = 'completed'
        
        # Log completion time for analytics
        completion_time = fields.Datetime.now() - self.create_date
        self.env['shop.floor.analytics'].create({
            'requisition_id': self.id,
            'completion_time': completion_time.total_seconds() / 3600,  # Hours
            'sla_met': completion_time.total_seconds() / 60 <= self.response_time_target,
            'production_impact': self.production_impact,
        })
        
        # Update machine status
        if self.machine_id:
            self.machine_id.write({
                'maintenance_state': 'normal',
                'last_emergency_requisition': self.id,
            })


class ShopFloorPhoto(models.Model):
    _name = 'shop.floor.photo'
    _description = 'Shop Floor Requisition Photo'

    requisition_id = fields.Many2one('shop.floor.requisition', 'Requisition', 
                                    required=True, ondelete='cascade')
    name = fields.Char('Description', required=True)
    image = fields.Image('Photo', required=True)
    taken_by = fields.Many2one('res.users', 'Taken By', default=lambda self: self.env.user)
    taken_date = fields.Datetime('Taken Date', default=fields.Datetime.now)
    gps_location = fields.Char('GPS Location')


class ShopFloorApprovalLimits(models.Model):
    _name = 'shop.floor.approval.limits'
    _description = 'Shop Floor Approval Limits'

    user_id = fields.Many2one('res.users', 'User', required=True)
    work_center_id = fields.Many2one('mrp.workcenter', 'Work Center')
    max_amount = fields.Monetary('Maximum Amount', required=True)
    currency_id = fields.Many2one('res.currency', 'Currency', 
                                 default=lambda self: self.env.company.currency_id)
    can_approve_emergency = fields.Boolean('Can Approve Emergency', default=False)
    active = fields.Boolean('Active', default=True)


class ShopFloorTerminal(models.Model):
    _name = 'shop.floor.terminal'
    _description = 'Shop Floor Terminal'

    name = fields.Char('Terminal Name', required=True)
    work_center_id = fields.Many2one('mrp.workcenter', 'Work Center', required=True)
    ip_address = fields.Char('IP Address')
    mac_address = fields.Char('MAC Address')
    location = fields.Char('Physical Location')
    active = fields.Boolean('Active', default=True)
    last_activity = fields.Datetime('Last Activity')
    
    # Hardware capabilities
    has_barcode_scanner = fields.Boolean('Has Barcode Scanner', default=True)
    has_camera = fields.Boolean('Has Camera', default=True)
    has_microphone = fields.Boolean('Has Microphone', default=False)
    has_printer = fields.Boolean('Has Printer', default=False)


class ManufacturingShift(models.Model):
    _name = 'manufacturing.shift'
    _description = 'Manufacturing Shift'

    name = fields.Char('Shift Name', required=True)
    start_time = fields.Float('Start Time', required=True)
    end_time = fields.Float('End Time', required=True)
    supervisor_id = fields.Many2one('res.users', 'Shift Supervisor')
    work_center_ids = fields.Many2many('mrp.workcenter', string='Work Centers')
    active = fields.Boolean('Active', default=True)
    
    # Days of week
    monday = fields.Boolean('Monday', default=True)
    tuesday = fields.Boolean('Tuesday', default=True)
    wednesday = fields.Boolean('Wednesday', default=True)
    thursday = fields.Boolean('Thursday', default=True)
    friday = fields.Boolean('Friday', default=True)
    saturday = fields.Boolean('Saturday', default=False)
    sunday = fields.Boolean('Sunday', default=False)


class ShopFloorAnalytics(models.Model):
    _name = 'shop.floor.analytics'
    _description = 'Shop Floor Analytics'

    requisition_id = fields.Many2one('shop.floor.requisition', 'Requisition', required=True)
    completion_time = fields.Float('Completion Time (Hours)')
    sla_met = fields.Boolean('SLA Met')
    production_impact = fields.Selection([
        ('no_impact', 'No Production Impact'),
        ('minor_delay', 'Minor Delay (<1 hour)'),
        ('major_delay', 'Major Delay (1-4 hours)'),
        ('production_stop', 'Production Stop (>4 hours)'),
        ('safety_risk', 'Safety Risk')
    ], string='Production Impact')
    create_date = fields.Datetime('Date', default=fields.Datetime.now) 