from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import json
import logging

_logger = logging.getLogger(__name__)


class ManufacturingMaterialRequisition(models.Model):
    _name = 'manufacturing.material.requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = 'Manufacturing Material Requisition'
    _order = 'priority desc, required_date asc, create_date desc'
    _rec_name = 'display_name'

    # Basic Information
    name = fields.Char('Requisition Number', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'), tracking=True)
    display_name = fields.Char('Display Name', compute='_compute_display_name', store=True)
    
    # Manufacturing Integration Fields
    manufacturing_order_id = fields.Many2one('mrp.production', 'Manufacturing Order',
                                            tracking=True, index=True)
    work_order_id = fields.Many2one('mrp.workorder', 'Work Order', tracking=True)
    workstation_id = fields.Many2one('mrp.workcenter', 'Workstation', tracking=True)
    bom_id = fields.Many2one('mrp.bom', 'Bill of Materials', tracking=True)
    routing_id = fields.Many2one('mrp.routing', 'Routing', tracking=True)
    
    # Production Context
    production_stage = fields.Selection([
        ('planning', 'Production Planning'),
        ('raw_material', 'Raw Material Preparation'),
        ('work_in_progress', 'Work in Progress'),
        ('quality_control', 'Quality Control'),
        ('finished_goods', 'Finished Goods'),
        ('maintenance', 'Maintenance & Repair'),
        ('tooling', 'Tooling & Equipment'),
        ('safety', 'Safety Equipment')
    ], string='Production Stage', required=True, default='raw_material', tracking=True)
    
    requisition_type = fields.Selection([
        ('production_material', 'Production Material'),
        ('maintenance_material', 'Maintenance Material'),
        ('tooling_equipment', 'Tooling & Equipment'),
        ('quality_material', 'Quality Control Material'),
        ('consumables', 'Manufacturing Consumables'),
        ('safety_equipment', 'Safety Equipment'),
        ('spare_parts', 'Spare Parts'),
        ('emergency', 'Emergency Requisition')
    ], string='Requisition Type', required=True, default='production_material', tracking=True)
    
    # Organizational Fields
    company_id = fields.Many2one('res.company', 'Company', required=True,
                                default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', 'Department', required=True, tracking=True)
    location_id = fields.Many2one('stock.location', 'Source Location', required=True,
                                 domain=[('usage', '=', 'internal')], tracking=True)
    dest_location_id = fields.Many2one('stock.location', 'Destination Location', required=True,
                                      domain=[('usage', '=', 'internal')], tracking=True)
    
    # Request Information
    requested_by = fields.Many2one('res.users', 'Requested By', required=True,
                                  default=lambda self: self.env.user, tracking=True)
    request_date = fields.Datetime('Request Date', required=True,
                                  default=fields.Datetime.now, tracking=True)
    required_date = fields.Datetime('Required Date', required=True, tracking=True)
    
    # Priority and Urgency
    priority = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
        ('critical', 'Critical')
    ], string='Priority', default='medium', required=True, tracking=True)
    
    urgency_level = fields.Selection([
        ('routine', 'Routine'),
        ('expedite', 'Expedite'),
        ('emergency', 'Emergency'),
        ('critical_path', 'Critical Path')
    ], string='Urgency Level', default='routine', tracking=True)
    
    # State Management
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('shop_floor_review', 'Shop Floor Review'),
        ('supervisor_approval', 'Supervisor Approval'),
        ('manager_approval', 'Manager Approval'),
        ('inventory_check', 'Inventory Check'),
        ('procurement_approval', 'Procurement Approval'),
        ('vendor_selection', 'Vendor Selection'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('partial_received', 'Partially Received'),
        ('received', 'Received'),
        ('quality_check', 'Quality Check'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected')
    ], string='Status', default='draft', required=True, tracking=True)
    
    # Approval Workflow
    shop_floor_approved = fields.Boolean('Shop Floor Approved', tracking=True)
    shop_floor_approver_id = fields.Many2one('res.users', 'Shop Floor Approver')
    shop_floor_approval_date = fields.Datetime('Shop Floor Approval Date')
    
    supervisor_approved = fields.Boolean('Supervisor Approved', tracking=True)
    supervisor_id = fields.Many2one('res.users', 'Supervisor', tracking=True)
    supervisor_approval_date = fields.Datetime('Supervisor Approval Date')
    
    manager_approved = fields.Boolean('Manager Approved', tracking=True)
    manager_id = fields.Many2one('res.users', 'Manager', tracking=True)
    manager_approval_date = fields.Datetime('Manager Approval Date')
    
    procurement_approved = fields.Boolean('Procurement Approved', tracking=True)
    procurement_approver_id = fields.Many2one('res.users', 'Procurement Approver')
    procurement_approval_date = fields.Datetime('Procurement Approval Date')
    
    # Inventory Integration
    inventory_available = fields.Boolean('Inventory Available', compute='_compute_inventory_status')
    inventory_check_date = fields.Datetime('Inventory Check Date')
    inventory_notes = fields.Text('Inventory Notes')
    
    # Purchase Integration
    purchase_order_ids = fields.One2many('purchase.order', 'requisition_id', 'Purchase Orders')
    purchase_order_count = fields.Integer('Purchase Orders', compute='_compute_purchase_count')
    
    # Stock Integration
    stock_move_ids = fields.One2many('stock.move', 'requisition_id', 'Stock Moves')
    picking_ids = fields.One2many('stock.picking', 'requisition_id', 'Pickings')
    picking_count = fields.Integer('Pickings', compute='_compute_picking_count')
    
    # Line Items
    line_ids = fields.One2many('manufacturing.material.requisition.line', 'requisition_id',
                              'Requisition Lines', copy=True)
    
    # Financial Information
    currency_id = fields.Many2one('res.currency', 'Currency', required=True,
                                 default=lambda self: self.env.company.currency_id)
    total_amount = fields.Monetary('Total Amount', compute='_compute_amounts', store=True)
    estimated_cost = fields.Monetary('Estimated Cost', compute='_compute_amounts', store=True)
    actual_cost = fields.Monetary('Actual Cost', compute='_compute_amounts', store=True)
    
    # Budget Integration
    budget_line_id = fields.Many2one('account.budget.line', 'Budget Line')
    budget_available = fields.Boolean('Budget Available', compute='_compute_budget_status')
    budget_amount = fields.Monetary('Budget Amount', compute='_compute_budget_status')
    budget_consumed = fields.Monetary('Budget Consumed', compute='_compute_budget_status')
    
    # Additional Information
    reason = fields.Text('Reason for Requisition', required=True)
    notes = fields.Text('Additional Notes')
    internal_notes = fields.Text('Internal Notes')
    
    # Emergency Fields
    is_emergency = fields.Boolean('Emergency Requisition', tracking=True)
    production_impact = fields.Selection([
        ('no_impact', 'No Production Impact'),
        ('minor_delay', 'Minor Delay (<1 hour)'),
        ('major_delay', 'Major Delay (1-4 hours)'),
        ('production_stop', 'Production Stop (>4 hours)'),
        ('safety_risk', 'Safety Risk')
    ], string='Production Impact')
    
    # AI and Analytics
    ai_recommendations = fields.Text('AI Recommendations')
    predicted_approval_time = fields.Float('Predicted Approval Time (Hours)')
    risk_score = fields.Float('Risk Score', compute='_compute_risk_score')
    
    # Tracking Fields
    auto_generated = fields.Boolean('Auto Generated', default=False)
    source_document = fields.Char('Source Document')
    
    # Shop Floor Integration
    shop_floor_terminal_id = fields.Many2one('shop.floor.terminal', 'Shop Floor Terminal')
    operator_id = fields.Many2one('res.users', 'Machine Operator')
    machine_id = fields.Many2one('maintenance.equipment', 'Machine/Equipment')
    shift_id = fields.Many2one('manufacturing.shift', 'Manufacturing Shift')
    
    # Quality Integration
    quality_check_required = fields.Boolean('Quality Check Required')
    quality_check_ids = fields.One2many('quality.check', 'requisition_id', 'Quality Checks')
    
    # Maintenance Integration
    maintenance_request_id = fields.Many2one('maintenance.request', 'Maintenance Request')
    downtime_id = fields.Many2one('maintenance.downtime', 'Related Downtime')
    
    @api.depends('name', 'requisition_type', 'manufacturing_order_id')
    def _compute_display_name(self):
        for record in self:
            if record.manufacturing_order_id:
                record.display_name = f"{record.name} - {record.manufacturing_order_id.name}"
            else:
                record.display_name = record.name or _('New')
    
    @api.depends('line_ids.price_total', 'line_ids.estimated_cost', 'line_ids.actual_cost')
    def _compute_amounts(self):
        for record in self:
            record.total_amount = sum(record.line_ids.mapped('price_total'))
            record.estimated_cost = sum(record.line_ids.mapped('estimated_cost'))
            record.actual_cost = sum(record.line_ids.mapped('actual_cost'))
    
    @api.depends('line_ids.product_id', 'location_id')
    def _compute_inventory_status(self):
        for record in self:
            if not record.line_ids:
                record.inventory_available = False
                continue
            
            available = True
            for line in record.line_ids:
                if line.product_id and line.qty_required > 0:
                    available_qty = line.product_id.with_context(
                        location=record.location_id.id
                    ).qty_available
                    if available_qty < line.qty_required:
                        available = False
                        break
            
            record.inventory_available = available
    
    @api.depends('budget_line_id', 'total_amount')
    def _compute_budget_status(self):
        for record in self:
            if record.budget_line_id:
                record.budget_available = record.budget_line_id.planned_amount >= record.total_amount
                record.budget_amount = record.budget_line_id.planned_amount
                record.budget_consumed = record.budget_line_id.practical_amount
            else:
                record.budget_available = True
                record.budget_amount = 0
                record.budget_consumed = 0
    
    @api.depends('purchase_order_ids')
    def _compute_purchase_count(self):
        for record in self:
            record.purchase_order_count = len(record.purchase_order_ids)
    
    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for record in self:
            record.picking_count = len(record.picking_ids)
    
    @api.depends('priority', 'urgency_level', 'required_date', 'total_amount')
    def _compute_risk_score(self):
        for record in self:
            risk_score = 0
            
            # Priority risk
            priority_scores = {'low': 1, 'medium': 2, 'high': 3, 'urgent': 4, 'critical': 5}
            risk_score += priority_scores.get(record.priority, 2)
            
            # Urgency risk
            urgency_scores = {'routine': 1, 'expedite': 2, 'emergency': 4, 'critical_path': 5}
            risk_score += urgency_scores.get(record.urgency_level, 1)
            
            # Time risk
            if record.required_date:
                days_until_required = (record.required_date - fields.Datetime.now()).days
                if days_until_required < 1:
                    risk_score += 5
                elif days_until_required < 3:
                    risk_score += 3
                elif days_until_required < 7:
                    risk_score += 1
            
            # Amount risk
            if record.total_amount > 10000:
                risk_score += 2
            elif record.total_amount > 5000:
                risk_score += 1
            
            record.risk_score = min(risk_score, 10)  # Cap at 10
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('manufacturing.material.requisition') or _('New')
        
        # Auto-set destination location based on manufacturing order
        if vals.get('manufacturing_order_id') and not vals.get('dest_location_id'):
            production = self.env['mrp.production'].browse(vals['manufacturing_order_id'])
            vals['dest_location_id'] = production.location_dest_id.id
        
        # Auto-set department based on work center
        if vals.get('workstation_id') and not vals.get('department_id'):
            workstation = self.env['mrp.workcenter'].browse(vals['workstation_id'])
            if workstation.department_id:
                vals['department_id'] = workstation.department_id.id
        
        requisition = super().create(vals)
        
        # Trigger AI analysis if enabled
        if self.env.company.enable_ai_requisition_analysis:
            requisition._trigger_ai_analysis()
        
        # Send notifications
        requisition._send_creation_notification()
        
        return requisition
    
    def write(self, vals):
        # Track state changes
        if 'state' in vals:
            for record in self:
                record._track_state_change(vals['state'])
        
        result = super().write(vals)
        
        # Update related documents
        if 'state' in vals and vals['state'] in ['approved', 'completed']:
            self._update_related_documents()
        
        return result
    
    def action_submit(self):
        """Submit requisition for approval"""
        for record in self:
            if not record.line_ids:
                raise UserError(_('Cannot submit requisition without line items.'))
            
            record.state = 'submitted'
            record._send_approval_notification()
    
    def action_shop_floor_approve(self):
        """Shop floor approval"""
        for record in self:
            record.write({
                'shop_floor_approved': True,
                'shop_floor_approver_id': self.env.user.id,
                'shop_floor_approval_date': fields.Datetime.now(),
                'state': 'supervisor_approval'
            })
    
    def action_supervisor_approve(self):
        """Supervisor approval"""
        for record in self:
            record.write({
                'supervisor_approved': True,
                'supervisor_id': self.env.user.id,
                'supervisor_approval_date': fields.Datetime.now(),
                'state': 'manager_approval' if record.total_amount > 5000 else 'inventory_check'
            })
    
    def action_manager_approve(self):
        """Manager approval"""
        for record in self:
            record.write({
                'manager_approved': True,
                'manager_id': self.env.user.id,
                'manager_approval_date': fields.Datetime.now(),
                'state': 'inventory_check'
            })
    
    def action_check_inventory(self):
        """Check inventory availability"""
        for record in self:
            record.inventory_check_date = fields.Datetime.now()
            
            if record.inventory_available:
                record.state = 'approved'
                record._create_internal_transfers()
            else:
                record.state = 'procurement_approval'
                record._send_procurement_notification()
    
    def action_procurement_approve(self):
        """Procurement approval"""
        for record in self:
            record.write({
                'procurement_approved': True,
                'procurement_approver_id': self.env.user.id,
                'procurement_approval_date': fields.Datetime.now(),
                'state': 'vendor_selection'
            })
    
    def action_approve(self):
        """Final approval"""
        for record in self:
            record.state = 'approved'
            record._create_purchase_orders()
            record._send_approval_confirmation()
    
    def action_reject(self):
        """Reject requisition"""
        for record in self:
            record.state = 'rejected'
            record._send_rejection_notification()
    
    def action_cancel(self):
        """Cancel requisition"""
        for record in self:
            record.state = 'cancelled'
            # Cancel related purchase orders and stock moves
            record.purchase_order_ids.button_cancel()
            record.stock_move_ids.filtered(lambda m: m.state not in ['done', 'cancel'])._action_cancel()
    
    def action_reset_to_draft(self):
        """Reset to draft"""
        for record in self:
            record.state = 'draft'
    
    def _create_internal_transfers(self):
        """Create internal stock transfers for available materials"""
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
        }
        
        picking = self.env['stock.picking'].create(picking_vals)
        
        for line in self.line_ids:
            if line.product_id and line.qty_required > 0:
                available_qty = line.product_id.with_context(
                    location=self.location_id.id
                ).qty_available
                
                if available_qty >= line.qty_required:
                    move_vals = {
                        'name': line.product_id.name,
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.qty_required,
                        'product_uom': line.product_id.uom_id.id,
                        'location_id': self.location_id.id,
                        'location_dest_id': self.dest_location_id.id,
                        'picking_id': picking.id,
                        'requisition_id': self.id,
                        'requisition_line_id': line.id,
                        'company_id': self.company_id.id,
                    }
                    self.env['stock.move'].create(move_vals)
        
        if picking.move_ids:
            picking.action_confirm()
            picking.action_assign()
    
    def _create_purchase_orders(self):
        """Create purchase orders for materials not available in inventory"""
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
                'origin': self.name,
                'company_id': self.company_id.id,
                'currency_id': vendor.property_purchase_currency_id.id or self.company_id.currency_id.id,
                'date_planned': self.required_date,
            }
            
            purchase_order = self.env['purchase.order'].create(po_vals)
            
            for line in lines:
                po_line_vals = {
                    'order_id': purchase_order.id,
                    'product_id': line.product_id.id,
                    'product_qty': line.qty_to_purchase,
                    'product_uom': line.product_id.uom_po_id.id,
                    'price_unit': line.unit_price,
                    'date_planned': self.required_date,
                    'requisition_line_id': line.id,
                }
                self.env['purchase.order.line'].create(po_line_vals)
            
            purchase_order.button_confirm()
    
    def _trigger_ai_analysis(self):
        """Trigger AI analysis for requisition optimization"""
        try:
            ai_service = self.env['manufacturing.requisition.ai']
            recommendations = ai_service.analyze_requisition(self.id)
            self.ai_recommendations = json.dumps(recommendations)
            
            # Predict approval time
            self.predicted_approval_time = ai_service.predict_approval_time(self.id)
            
        except Exception as e:
            _logger.warning(f"AI analysis failed for requisition {self.name}: {str(e)}")
    
    def _send_creation_notification(self):
        """Send notification when requisition is created"""
        template = self.env.ref('manufacturing_material_requisitions.email_template_requisition_created', False)
        if template:
            template.send_mail(self.id, force_send=True)
    
    def _send_approval_notification(self):
        """Send notification for approval"""
        # Determine next approver based on workflow
        next_approver = self._get_next_approver()
        if next_approver:
            self.activity_schedule(
                'manufacturing_material_requisitions.mail_activity_requisition_approval',
                user_id=next_approver.id,
                summary=f'Requisition {self.name} requires approval',
                note=f'Please review and approve requisition {self.name} for {self.reason}'
            )
    
    def _get_next_approver(self):
        """Get next approver based on workflow rules"""
        if self.state == 'submitted':
            if self.requisition_type in ['maintenance_material', 'tooling_equipment']:
                return self.workstation_id.supervisor_id or self.department_id.manager_id
            else:
                return self.department_id.manager_id
        elif self.state == 'supervisor_approval':
            return self.department_id.manager_id
        elif self.state == 'procurement_approval':
            return self.env['res.users'].search([
                ('groups_id', 'in', self.env.ref('purchase.group_purchase_manager').id)
            ], limit=1)
        return False
    
    def _track_state_change(self, new_state):
        """Track state changes for analytics"""
        self.env['manufacturing.requisition.state.log'].create({
            'requisition_id': self.id,
            'old_state': self.state,
            'new_state': new_state,
            'user_id': self.env.user.id,
            'change_date': fields.Datetime.now(),
        })
    
    def _update_related_documents(self):
        """Update related manufacturing orders and maintenance requests"""
        if self.manufacturing_order_id and self.state == 'completed':
            # Check if all materials are now available for production
            self.manufacturing_order_id._check_material_availability()
        
        if self.maintenance_request_id and self.state == 'completed':
            # Update maintenance request with material availability
            self.maintenance_request_id.material_available = True
    
    def _send_approval_confirmation(self):
        """Send confirmation when requisition is approved"""
        template = self.env.ref('manufacturing_material_requisitions.email_template_requisition_approved', False)
        if template:
            template.send_mail(self.id, force_send=True)
    
    def _send_rejection_notification(self):
        """Send notification when requisition is rejected"""
        template = self.env.ref('manufacturing_material_requisitions.email_template_requisition_rejected', False)
        if template:
            template.send_mail(self.id, force_send=True)
    
    def _send_procurement_notification(self):
        """Send notification to procurement team"""
        procurement_users = self.env['res.users'].search([
            ('groups_id', 'in', self.env.ref('purchase.group_purchase_user').id)
        ])
        
        for user in procurement_users:
            self.activity_schedule(
                'manufacturing_material_requisitions.mail_activity_procurement_required',
                user_id=user.id,
                summary=f'Procurement required for {self.name}',
                note=f'Materials not available in inventory. Procurement required for requisition {self.name}'
            )
    
    @api.model
    def create_from_manufacturing_order(self, production_order_id):
        """Create requisition from manufacturing order shortage analysis"""
        production = self.env['mrp.production'].browse(production_order_id)
        if not production:
            return False
        
        # Analyze material shortages
        shortages = self._analyze_material_shortage(production)
        
        if not shortages:
            return False
        
        # Create requisition
        requisition_vals = {
            'manufacturing_order_id': production.id,
            'requisition_type': 'production_material',
            'production_stage': 'raw_material',
            'department_id': production.workcenter_id.department_id.id if production.workcenter_id else False,
            'location_id': production.location_src_id.id,
            'dest_location_id': production.location_dest_id.id,
            'required_date': production.date_planned_start,
            'priority': 'high' if production.priority == '1' else 'medium',
            'reason': f'Material shortage for production order {production.name}',
            'auto_generated': True,
            'source_document': production.name,
        }
        
        requisition = self.create(requisition_vals)
        
        # Create requisition lines
        for shortage in shortages:
            line_vals = {
                'requisition_id': requisition.id,
                'product_id': shortage['product_id'],
                'qty_required': shortage['shortage_qty'],
                'required_date': shortage['required_date'],
                'reason': f"Shortage for {production.name}",
                'bom_line_id': shortage.get('bom_line_id'),
                'work_order_id': shortage.get('work_order_id'),
            }
            self.env['manufacturing.material.requisition.line'].create(line_vals)
        
        return requisition
    
    def _analyze_material_shortage(self, production):
        """Analyze material shortage for production order"""
        shortages = []
        
        for move in production.move_raw_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
            available_qty = move.product_id.with_context(
                location=production.location_src_id.id
            ).qty_available
            
            if available_qty < move.product_uom_qty:
                shortage_qty = move.product_uom_qty - available_qty
                shortages.append({
                    'product_id': move.product_id.id,
                    'shortage_qty': shortage_qty,
                    'required_date': move.date,
                    'bom_line_id': move.bom_line_id.id if move.bom_line_id else False,
                    'work_order_id': move.workorder_id.id if move.workorder_id else False
                })
        
        return shortages
    
    def action_view_purchase_orders(self):
        """View related purchase orders"""
        action = self.env.ref('purchase.purchase_order_action_generic').read()[0]
        action['domain'] = [('requisition_id', '=', self.id)]
        action['context'] = {'default_requisition_id': self.id}
        return action
    
    def action_view_pickings(self):
        """View related pickings"""
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        action['domain'] = [('requisition_id', '=', self.id)]
        action['context'] = {'default_requisition_id': self.id}
        return action
    
    def action_view_quality_checks(self):
        """View related quality checks"""
        action = self.env.ref('quality_control.quality_check_action').read()[0]
        action['domain'] = [('requisition_id', '=', self.id)]
        action['context'] = {'default_requisition_id': self.id}
        return action


class ManufacturingMaterialRequisitionLine(models.Model):
    _name = 'manufacturing.material.requisition.line'
    _description = 'Manufacturing Material Requisition Line'
    _order = 'sequence, id'

    # Basic Information
    sequence = fields.Integer('Sequence', default=10)
    requisition_id = fields.Many2one('manufacturing.material.requisition', 'Requisition',
                                    required=True, ondelete='cascade', index=True)
    
    # Product Information
    product_id = fields.Many2one('product.product', 'Product', required=True, index=True)
    product_tmpl_id = fields.Many2one('product.template', 'Product Template',
                                     related='product_id.product_tmpl_id', readonly=True)
    product_uom_id = fields.Many2one('uom.uom', 'Unit of Measure',
                                    related='product_id.uom_id', readonly=True)
    
    # Quantities
    qty_required = fields.Float('Required Quantity', required=True, default=1.0)
    qty_available = fields.Float('Available Quantity', compute='_compute_availability')
    qty_to_purchase = fields.Float('Quantity to Purchase', compute='_compute_availability')
    qty_received = fields.Float('Received Quantity', compute='_compute_received_qty')
    
    # Pricing
    unit_price = fields.Float('Unit Price')
    price_total = fields.Float('Total Price', compute='_compute_price_total', store=True)
    estimated_cost = fields.Float('Estimated Cost')
    actual_cost = fields.Float('Actual Cost', compute='_compute_actual_cost')
    
    # Vendor Information
    vendor_id = fields.Many2one('res.partner', 'Preferred Vendor',
                               domain=[('is_company', '=', True), ('supplier_rank', '>', 0)])
    vendor_price = fields.Float('Vendor Price')
    vendor_lead_time = fields.Integer('Vendor Lead Time (Days)')
    
    # Manufacturing Integration
    bom_line_id = fields.Many2one('mrp.bom.line', 'BOM Line')
    work_order_id = fields.Many2one('mrp.workorder', 'Work Order')
    operation_id = fields.Many2one('mrp.routing.workcenter', 'Operation')
    
    # Dates
    required_date = fields.Datetime('Required Date', required=True)
    promised_date = fields.Datetime('Promised Date')
    
    # Additional Information
    reason = fields.Text('Reason')
    notes = fields.Text('Notes')
    
    # Status
    state = fields.Selection(related='requisition_id.state', readonly=True, store=True)
    
    # Purchase Integration
    purchase_line_ids = fields.One2many('purchase.order.line', 'requisition_line_id', 'Purchase Lines')
    
    # Stock Integration
    stock_move_ids = fields.One2many('stock.move', 'requisition_line_id', 'Stock Moves')
    
    @api.depends('qty_required', 'product_id', 'requisition_id.location_id')
    def _compute_availability(self):
        for line in self:
            if line.product_id and line.requisition_id.location_id:
                available_qty = line.product_id.with_context(
                    location=line.requisition_id.location_id.id
                ).qty_available
                
                line.qty_available = min(available_qty, line.qty_required)
                line.qty_to_purchase = max(0, line.qty_required - available_qty)
            else:
                line.qty_available = 0
                line.qty_to_purchase = line.qty_required
    
    @api.depends('unit_price', 'qty_required')
    def _compute_price_total(self):
        for line in self:
            line.price_total = line.unit_price * line.qty_required
    
    @api.depends('purchase_line_ids.price_total')
    def _compute_actual_cost(self):
        for line in self:
            line.actual_cost = sum(line.purchase_line_ids.mapped('price_total'))
    
    @api.depends('stock_move_ids.quantity_done')
    def _compute_received_qty(self):
        for line in self:
            line.qty_received = sum(line.stock_move_ids.mapped('quantity_done'))
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            # Set default unit price from product
            self.unit_price = self.product_id.standard_price
            self.estimated_cost = self.unit_price * self.qty_required
            
            # Set preferred vendor
            if self.product_id.seller_ids:
                self.vendor_id = self.product_id.seller_ids[0].partner_id
                self.vendor_price = self.product_id.seller_ids[0].price
                self.vendor_lead_time = self.product_id.seller_ids[0].delay
    
    @api.onchange('qty_required', 'unit_price')
    def _onchange_quantities(self):
        self.estimated_cost = self.unit_price * self.qty_required


class ManufacturingRequisitionStateLog(models.Model):
    _name = 'manufacturing.requisition.state.log'
    _description = 'Manufacturing Requisition State Change Log'
    _order = 'change_date desc'

    requisition_id = fields.Many2one('manufacturing.material.requisition', 'Requisition',
                                    required=True, ondelete='cascade', index=True)
    old_state = fields.Char('Old State')
    new_state = fields.Char('New State')
    user_id = fields.Many2one('res.users', 'Changed By', required=True)
    change_date = fields.Datetime('Change Date', required=True)
    notes = fields.Text('Notes') 