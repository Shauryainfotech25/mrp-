# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class MaintenanceIntegration(models.Model):
    _name = 'manufacturing.maintenance.integration'
    _description = 'Manufacturing Maintenance Integration'
    _order = 'create_date desc'

    name = fields.Char('Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    
    # Requisition Link
    requisition_id = fields.Many2one('manufacturing.requisition', 'Requisition', required=True, ondelete='cascade')
    
    # Maintenance Request
    maintenance_request_id = fields.Many2one('maintenance.request', 'Maintenance Request')
    equipment_id = fields.Many2one('maintenance.equipment', 'Equipment', required=True)
    
    # Maintenance Type
    maintenance_type = fields.Selection([
        ('corrective', 'Corrective Maintenance'),
        ('preventive', 'Preventive Maintenance'),
        ('predictive', 'Predictive Maintenance'),
        ('emergency', 'Emergency Maintenance'),
        ('breakdown', 'Breakdown Maintenance')
    ], string='Maintenance Type', required=True)
    
    # Urgency and Priority
    urgency = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
        ('emergency', 'Emergency')
    ], string='Urgency', default='medium')
    
    # Equipment Details
    equipment_category_id = fields.Many2one('maintenance.equipment.category', 'Equipment Category', related='equipment_id.category_id', store=True)
    equipment_location = fields.Char('Equipment Location', related='equipment_id.location', store=True)
    work_center_id = fields.Many2one('mrp.workcenter', 'Work Center', related='equipment_id.workcenter_id', store=True)
    
    # Downtime Tracking
    downtime_start = fields.Datetime('Downtime Start')
    downtime_end = fields.Datetime('Downtime End')
    downtime_duration = fields.Float('Downtime Duration (Hours)', compute='_compute_downtime_duration', store=True)
    production_impact = fields.Selection([
        ('none', 'No Impact'),
        ('minor', 'Minor Impact'),
        ('moderate', 'Moderate Impact'),
        ('major', 'Major Impact'),
        ('critical', 'Critical Impact')
    ], string='Production Impact', default='minor')
    
    # Cost Impact
    downtime_cost = fields.Float('Downtime Cost')
    production_loss = fields.Float('Production Loss')
    total_impact_cost = fields.Float('Total Impact Cost', compute='_compute_total_impact_cost', store=True)
    
    # Material Requirements
    spare_part_required = fields.Boolean('Spare Part Required', default=True)
    consumable_required = fields.Boolean('Consumable Required', default=False)
    tool_required = fields.Boolean('Tool Required', default=False)
    
    # Maintenance Planning
    planned_maintenance_date = fields.Datetime('Planned Maintenance Date')
    actual_maintenance_date = fields.Datetime('Actual Maintenance Date')
    maintenance_duration = fields.Float('Maintenance Duration (Hours)')
    technician_id = fields.Many2one('res.users', 'Assigned Technician')
    
    # Material Specifications
    material_specification = fields.Text('Material Specification')
    part_number = fields.Char('Part Number')
    manufacturer = fields.Char('Manufacturer')
    model_number = fields.Char('Model Number')
    
    # Inventory Integration
    stock_available = fields.Boolean('Stock Available', compute='_compute_stock_available')
    current_stock_level = fields.Float('Current Stock Level', compute='_compute_stock_available')
    minimum_stock_level = fields.Float('Minimum Stock Level')
    
    # Maintenance History
    last_maintenance_date = fields.Datetime('Last Maintenance Date', related='equipment_id.last_maintenance_date', store=True)
    next_maintenance_date = fields.Datetime('Next Maintenance Date', related='equipment_id.next_action_date', store=True)
    maintenance_frequency = fields.Integer('Maintenance Frequency (Days)', default=30)
    
    # Status and Workflow
    state = fields.Selection([
        ('draft', 'Draft'),
        ('material_requested', 'Material Requested'),
        ('material_received', 'Material Received'),
        ('maintenance_scheduled', 'Maintenance Scheduled'),
        ('maintenance_in_progress', 'Maintenance in Progress'),
        ('maintenance_completed', 'Maintenance Completed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    # Performance Metrics
    mttr = fields.Float('Mean Time to Repair (Hours)')  # Mean Time to Repair
    mtbf = fields.Float('Mean Time Between Failures (Hours)')  # Mean Time Between Failures
    availability = fields.Float('Equipment Availability (%)', compute='_compute_availability')
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('manufacturing.maintenance.integration') or _('New')
        return super(MaintenanceIntegration, self).create(vals)
    
    @api.depends('downtime_start', 'downtime_end')
    def _compute_downtime_duration(self):
        for record in self:
            if record.downtime_start and record.downtime_end:
                delta = record.downtime_end - record.downtime_start
                record.downtime_duration = delta.total_seconds() / 3600.0  # Convert to hours
            else:
                record.downtime_duration = 0.0
    
    @api.depends('downtime_cost', 'production_loss')
    def _compute_total_impact_cost(self):
        for record in self:
            record.total_impact_cost = record.downtime_cost + record.production_loss
    
    @api.depends('requisition_id.product_id')
    def _compute_stock_available(self):
        for record in self:
            if record.requisition_id.product_id:
                # Get current stock level
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', record.requisition_id.product_id.id),
                    ('location_id.usage', '=', 'internal')
                ])
                record.current_stock_level = sum(quants.mapped('quantity'))
                record.stock_available = record.current_stock_level > 0
            else:
                record.current_stock_level = 0.0
                record.stock_available = False
    
    @api.depends('downtime_duration', 'maintenance_frequency')
    def _compute_availability(self):
        for record in self:
            if record.maintenance_frequency > 0:
                total_time = record.maintenance_frequency * 24  # Convert days to hours
                uptime = total_time - record.downtime_duration
                record.availability = (uptime / total_time) * 100 if total_time > 0 else 100
            else:
                record.availability = 100
    
    def action_create_maintenance_request(self):
        """Create maintenance request"""
        if self.maintenance_request_id:
            return self.action_view_maintenance_request()
        
        # Create maintenance request
        request_vals = {
            'name': f'Maintenance for {self.equipment_id.name}',
            'equipment_id': self.equipment_id.id,
            'maintenance_type': 'corrective' if self.maintenance_type == 'breakdown' else 'preventive',
            'user_id': self.technician_id.id if self.technician_id else self.env.user.id,
            'description': f'Material requisition: {self.requisition_id.name}\nMaterial: {self.requisition_id.product_id.name}',
            'priority': self._map_urgency_to_priority(),
            'schedule_date': self.planned_maintenance_date or fields.Datetime.now(),
        }
        
        maintenance_request = self.env['maintenance.request'].create(request_vals)
        self.maintenance_request_id = maintenance_request.id
        self.state = 'maintenance_scheduled'
        
        return self.action_view_maintenance_request()
    
    def _map_urgency_to_priority(self):
        """Map urgency to maintenance request priority"""
        mapping = {
            'low': '1',
            'medium': '2',
            'high': '3',
            'critical': '3',
            'emergency': '3'
        }
        return mapping.get(self.urgency, '2')
    
    def action_view_maintenance_request(self):
        """View maintenance request"""
        if not self.maintenance_request_id:
            raise UserError(_('No maintenance request created yet'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Maintenance Request',
            'res_model': 'maintenance.request',
            'res_id': self.maintenance_request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_start_maintenance(self):
        """Start maintenance work"""
        self.state = 'maintenance_in_progress'
        self.actual_maintenance_date = fields.Datetime.now()
        
        # Start downtime tracking if not already started
        if not self.downtime_start:
            self.downtime_start = fields.Datetime.now()
        
        # Update maintenance request
        if self.maintenance_request_id:
            self.maintenance_request_id.stage_id = self.env.ref('maintenance.stage_in_progress', raise_if_not_found=False)
        
        return True
    
    def action_complete_maintenance(self):
        """Complete maintenance work"""
        self.state = 'maintenance_completed'
        
        # End downtime tracking
        if not self.downtime_end:
            self.downtime_end = fields.Datetime.now()
        
        # Calculate maintenance duration
        if self.actual_maintenance_date:
            delta = fields.Datetime.now() - self.actual_maintenance_date
            self.maintenance_duration = delta.total_seconds() / 3600.0
        
        # Update maintenance request
        if self.maintenance_request_id:
            self.maintenance_request_id.stage_id = self.env.ref('maintenance.stage_done', raise_if_not_found=False)
            self.maintenance_request_id.close_date = fields.Datetime.now()
        
        # Update equipment maintenance date
        self.equipment_id.last_maintenance_date = fields.Datetime.now()
        
        # Calculate next maintenance date
        if self.maintenance_frequency > 0:
            self.equipment_id.next_action_date = fields.Datetime.now() + timedelta(days=self.maintenance_frequency)
        
        # Update requisition status
        self.requisition_id.state = 'completed'
        
        return True
    
    def action_calculate_downtime_cost(self):
        """Calculate downtime cost based on production impact"""
        if not self.downtime_duration:
            return
        
        # Get hourly production rate for the work center
        if self.work_center_id:
            hourly_rate = self.work_center_id.costs_hour or 100.0  # Default rate
            self.downtime_cost = self.downtime_duration * hourly_rate
            
            # Calculate production loss based on impact level
            impact_multipliers = {
                'none': 0.0,
                'minor': 0.1,
                'moderate': 0.3,
                'major': 0.6,
                'critical': 1.0
            }
            
            multiplier = impact_multipliers.get(self.production_impact, 0.1)
            self.production_loss = self.downtime_cost * multiplier
        
        return True
    
    def action_schedule_preventive_maintenance(self):
        """Schedule preventive maintenance"""
        if not self.equipment_id:
            raise UserError(_('Equipment must be specified'))
        
        # Create preventive maintenance schedule
        schedule_vals = {
            'equipment_id': self.equipment_id.id,
            'maintenance_type': 'preventive',
            'interval_number': self.maintenance_frequency,
            'interval_type': 'day',
            'user_id': self.technician_id.id if self.technician_id else self.env.user.id,
            'name': f'Preventive Maintenance - {self.equipment_id.name}',
        }
        
        # Check if schedule already exists
        existing_schedule = self.env['maintenance.plan'].search([
            ('equipment_id', '=', self.equipment_id.id),
            ('maintenance_type', '=', 'preventive')
        ], limit=1)
        
        if not existing_schedule:
            self.env['maintenance.plan'].create(schedule_vals)
        
        return True
    
    def action_create_spare_parts_list(self):
        """Create spare parts list for equipment"""
        if not self.equipment_id:
            raise UserError(_('Equipment must be specified'))
        
        # Get recommended spare parts for this equipment category
        spare_parts = self.env['product.product'].search([
            ('categ_id.name', 'ilike', 'spare'),
            ('default_code', 'ilike', self.equipment_category_id.name if self.equipment_category_id else '')
        ])
        
        # Create spare parts recommendations
        for part in spare_parts[:10]:  # Limit to 10 parts
            self._create_spare_part_recommendation(part)
        
        return True
    
    def _create_spare_part_recommendation(self, product):
        """Create spare part recommendation"""
        recommendation_vals = {
            'equipment_id': self.equipment_id.id,
            'product_id': product.id,
            'recommended_quantity': 1,
            'priority': 'medium',
            'notes': f'Recommended for {self.maintenance_type} maintenance',
        }
        
        # Check if recommendation already exists
        existing = self.env['manufacturing.spare.part.recommendation'].search([
            ('equipment_id', '=', self.equipment_id.id),
            ('product_id', '=', product.id)
        ], limit=1)
        
        if not existing:
            self.env['manufacturing.spare.part.recommendation'].create(recommendation_vals)
    
    def action_view_equipment_history(self):
        """View equipment maintenance history"""
        action = self.env.ref('maintenance.hr_equipment_request_action').read()[0]
        action['domain'] = [('equipment_id', '=', self.equipment_id.id)]
        action['context'] = {'default_equipment_id': self.equipment_id.id}
        return action
    
    def action_view_downtime_analysis(self):
        """View downtime analysis"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Downtime Analysis',
            'res_model': 'manufacturing.downtime.analysis',
            'view_mode': 'tree,form,graph,pivot',
            'domain': [('equipment_id', '=', self.equipment_id.id)],
            'context': {
                'default_equipment_id': self.equipment_id.id,
                'search_default_group_by_month': 1,
            }
        }

class MaintenanceRequestExtension(models.Model):
    _inherit = 'maintenance.request'
    
    maintenance_integration_id = fields.Many2one('manufacturing.maintenance.integration', 'Maintenance Integration')
    material_requisition_id = fields.Many2one('manufacturing.requisition', 'Material Requisition')
    
    def action_create_material_requisition(self):
        """Create material requisition for maintenance"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Material Requisition',
            'res_model': 'manufacturing.requisition',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_maintenance_request_id': self.id,
                'default_equipment_id': self.equipment_id.id,
                'default_requisition_type': 'maintenance',
                'default_priority': 'high' if self.priority == '3' else 'medium',
            }
        }

class SparePartRecommendation(models.Model):
    _name = 'manufacturing.spare.part.recommendation'
    _description = 'Spare Part Recommendation'
    _order = 'priority desc, create_date desc'

    equipment_id = fields.Many2one('maintenance.equipment', 'Equipment', required=True)
    product_id = fields.Many2one('product.product', 'Spare Part', required=True)
    recommended_quantity = fields.Float('Recommended Quantity', default=1.0)
    current_stock = fields.Float('Current Stock', compute='_compute_current_stock')
    
    priority = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ], string='Priority', default='medium')
    
    usage_frequency = fields.Selection([
        ('rare', 'Rare'),
        ('occasional', 'Occasional'),
        ('frequent', 'Frequent'),
        ('critical', 'Critical')
    ], string='Usage Frequency', default='occasional')
    
    lead_time_days = fields.Float('Lead Time (Days)', default=7.0)
    cost_per_unit = fields.Float('Cost per Unit', related='product_id.standard_price')
    total_cost = fields.Float('Total Cost', compute='_compute_total_cost')
    
    notes = fields.Text('Notes')
    
    @api.depends('product_id')
    def _compute_current_stock(self):
        for record in self:
            if record.product_id:
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', record.product_id.id),
                    ('location_id.usage', '=', 'internal')
                ])
                record.current_stock = sum(quants.mapped('quantity'))
            else:
                record.current_stock = 0.0
    
    @api.depends('recommended_quantity', 'cost_per_unit')
    def _compute_total_cost(self):
        for record in self:
            record.total_cost = record.recommended_quantity * record.cost_per_unit
    
    def action_create_requisition(self):
        """Create requisition for this spare part"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Requisition',
            'res_model': 'manufacturing.requisition',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_id': self.product_id.id,
                'default_quantity_required': self.recommended_quantity,
                'default_equipment_id': self.equipment_id.id,
                'default_requisition_type': 'maintenance',
                'default_priority': self.priority,
            }
        }

class DowntimeAnalysis(models.Model):
    _name = 'manufacturing.downtime.analysis'
    _description = 'Equipment Downtime Analysis'
    _auto = False
    _order = 'downtime_date desc'

    equipment_id = fields.Many2one('maintenance.equipment', 'Equipment', readonly=True)
    equipment_category_id = fields.Many2one('maintenance.equipment.category', 'Equipment Category', readonly=True)
    work_center_id = fields.Many2one('mrp.workcenter', 'Work Center', readonly=True)
    
    downtime_date = fields.Date('Downtime Date', readonly=True)
    downtime_duration = fields.Float('Downtime Duration (Hours)', readonly=True)
    downtime_cost = fields.Float('Downtime Cost', readonly=True)
    production_loss = fields.Float('Production Loss', readonly=True)
    
    maintenance_type = fields.Selection([
        ('corrective', 'Corrective'),
        ('preventive', 'Preventive'),
        ('predictive', 'Predictive'),
        ('emergency', 'Emergency'),
        ('breakdown', 'Breakdown')
    ], string='Maintenance Type', readonly=True)
    
    urgency = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
        ('emergency', 'Emergency')
    ], string='Urgency', readonly=True)
    
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    mi.equipment_id,
                    me.category_id AS equipment_category_id,
                    me.workcenter_id AS work_center_id,
                    DATE(mi.downtime_start) AS downtime_date,
                    mi.downtime_duration,
                    mi.downtime_cost,
                    mi.production_loss,
                    mi.maintenance_type,
                    mi.urgency
                FROM manufacturing_maintenance_integration mi
                LEFT JOIN maintenance_equipment me ON mi.equipment_id = me.id
                WHERE mi.downtime_start IS NOT NULL
            )
        """ % self._table) 