# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class InventoryIntegration(models.Model):
    _name = 'manufacturing.inventory.integration'
    _description = 'Manufacturing Inventory Integration'
    _order = 'create_date desc'

    name = fields.Char('Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    
    # Product and Location
    product_id = fields.Many2one('product.product', 'Product', required=True)
    location_id = fields.Many2one('stock.location', 'Location', required=True)
    warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse', required=True)
    
    # Stock Levels
    current_stock = fields.Float('Current Stock', compute='_compute_stock_levels', store=True)
    available_stock = fields.Float('Available Stock', compute='_compute_stock_levels', store=True)
    reserved_stock = fields.Float('Reserved Stock', compute='_compute_stock_levels', store=True)
    incoming_stock = fields.Float('Incoming Stock', compute='_compute_stock_levels', store=True)
    outgoing_stock = fields.Float('Outgoing Stock', compute='_compute_stock_levels', store=True)
    
    # Thresholds
    min_stock_level = fields.Float('Minimum Stock Level', required=True)
    max_stock_level = fields.Float('Maximum Stock Level', required=True)
    reorder_point = fields.Float('Reorder Point', required=True)
    safety_stock = fields.Float('Safety Stock', required=True)
    
    # Auto-Requisition Settings
    auto_requisition_enabled = fields.Boolean('Auto Requisition Enabled', default=True)
    auto_requisition_quantity = fields.Float('Auto Requisition Quantity')
    auto_requisition_rule = fields.Selection([
        ('min_level', 'When Below Minimum Level'),
        ('reorder_point', 'When Below Reorder Point'),
        ('safety_stock', 'When Below Safety Stock'),
        ('custom', 'Custom Rule')
    ], string='Auto Requisition Rule', default='reorder_point')
    
    # Monitoring
    last_check_date = fields.Datetime('Last Check Date', default=fields.Datetime.now)
    next_check_date = fields.Datetime('Next Check Date', compute='_compute_next_check_date', store=True)
    check_frequency = fields.Selection([
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('real_time', 'Real Time')
    ], string='Check Frequency', default='daily')
    
    # Status and Alerts
    state = fields.Selection([
        ('normal', 'Normal'),
        ('low_stock', 'Low Stock'),
        ('critical', 'Critical'),
        ('out_of_stock', 'Out of Stock'),
        ('overstock', 'Overstock')
    ], string='Stock Status', compute='_compute_stock_status', store=True)
    
    alert_level = fields.Selection([
        ('none', 'No Alert'),
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('critical', 'Critical')
    ], string='Alert Level', compute='_compute_alert_level', store=True)
    
    # Related Records
    requisition_ids = fields.One2many('manufacturing.requisition', 'inventory_integration_id', 'Generated Requisitions')
    stock_move_ids = fields.One2many('stock.move', 'inventory_integration_id', 'Related Stock Moves')
    
    # Analytics
    average_consumption = fields.Float('Average Daily Consumption', compute='_compute_consumption_analytics')
    lead_time_days = fields.Float('Lead Time (Days)', default=7.0)
    stock_turnover = fields.Float('Stock Turnover', compute='_compute_consumption_analytics')
    days_of_stock = fields.Float('Days of Stock', compute='_compute_consumption_analytics')
    
    # Manufacturing Integration
    mrp_production_ids = fields.Many2many('mrp.production', string='Related Productions')
    work_center_ids = fields.Many2many('mrp.workcenter', string='Related Work Centers')
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('manufacturing.inventory.integration') or _('New')
        return super(InventoryIntegration, self).create(vals)
    
    @api.depends('product_id', 'location_id')
    def _compute_stock_levels(self):
        for record in self:
            if record.product_id and record.location_id:
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', record.product_id.id),
                    ('location_id', '=', record.location_id.id)
                ])
                
                record.current_stock = sum(quants.mapped('quantity'))
                record.available_stock = sum(quants.mapped('available_quantity'))
                record.reserved_stock = sum(quants.mapped('reserved_quantity'))
                
                # Calculate incoming/outgoing stock
                incoming_moves = self.env['stock.move'].search([
                    ('product_id', '=', record.product_id.id),
                    ('location_dest_id', '=', record.location_id.id),
                    ('state', 'in', ['confirmed', 'assigned', 'partially_available'])
                ])
                record.incoming_stock = sum(incoming_moves.mapped('product_uom_qty'))
                
                outgoing_moves = self.env['stock.move'].search([
                    ('product_id', '=', record.product_id.id),
                    ('location_id', '=', record.location_id.id),
                    ('state', 'in', ['confirmed', 'assigned', 'partially_available'])
                ])
                record.outgoing_stock = sum(outgoing_moves.mapped('product_uom_qty'))
            else:
                record.current_stock = 0
                record.available_stock = 0
                record.reserved_stock = 0
                record.incoming_stock = 0
                record.outgoing_stock = 0
    
    @api.depends('current_stock', 'min_stock_level', 'max_stock_level', 'reorder_point', 'safety_stock')
    def _compute_stock_status(self):
        for record in self:
            if record.current_stock <= 0:
                record.state = 'out_of_stock'
            elif record.current_stock <= record.safety_stock:
                record.state = 'critical'
            elif record.current_stock <= record.min_stock_level:
                record.state = 'low_stock'
            elif record.current_stock >= record.max_stock_level:
                record.state = 'overstock'
            else:
                record.state = 'normal'
    
    @api.depends('state')
    def _compute_alert_level(self):
        for record in self:
            if record.state == 'out_of_stock':
                record.alert_level = 'critical'
            elif record.state == 'critical':
                record.alert_level = 'critical'
            elif record.state == 'low_stock':
                record.alert_level = 'warning'
            elif record.state == 'overstock':
                record.alert_level = 'info'
            else:
                record.alert_level = 'none'
    
    @api.depends('last_check_date', 'check_frequency')
    def _compute_next_check_date(self):
        for record in self:
            if record.last_check_date:
                if record.check_frequency == 'hourly':
                    record.next_check_date = record.last_check_date + timedelta(hours=1)
                elif record.check_frequency == 'daily':
                    record.next_check_date = record.last_check_date + timedelta(days=1)
                elif record.check_frequency == 'weekly':
                    record.next_check_date = record.last_check_date + timedelta(weeks=1)
                else:  # real_time
                    record.next_check_date = fields.Datetime.now()
            else:
                record.next_check_date = fields.Datetime.now()
    
    @api.depends('product_id', 'location_id')
    def _compute_consumption_analytics(self):
        for record in self:
            if record.product_id and record.location_id:
                # Calculate average consumption over last 30 days
                thirty_days_ago = fields.Datetime.now() - timedelta(days=30)
                moves = self.env['stock.move'].search([
                    ('product_id', '=', record.product_id.id),
                    ('location_id', '=', record.location_id.id),
                    ('state', '=', 'done'),
                    ('date', '>=', thirty_days_ago)
                ])
                
                total_consumed = sum(moves.mapped('product_uom_qty'))
                record.average_consumption = total_consumed / 30.0
                
                # Calculate stock turnover
                if record.current_stock > 0:
                    record.stock_turnover = total_consumed / record.current_stock
                    record.days_of_stock = record.current_stock / (record.average_consumption or 1)
                else:
                    record.stock_turnover = 0
                    record.days_of_stock = 0
            else:
                record.average_consumption = 0
                record.stock_turnover = 0
                record.days_of_stock = 0
    
    def action_check_stock_levels(self):
        """Manual stock level check"""
        self._compute_stock_levels()
        self.last_check_date = fields.Datetime.now()
        
        # Trigger auto-requisition if needed
        if self.auto_requisition_enabled:
            self._check_auto_requisition()
        
        return True
    
    def _check_auto_requisition(self):
        """Check if auto-requisition should be triggered"""
        for record in self:
            should_create = False
            
            if record.auto_requisition_rule == 'min_level' and record.current_stock <= record.min_stock_level:
                should_create = True
            elif record.auto_requisition_rule == 'reorder_point' and record.current_stock <= record.reorder_point:
                should_create = True
            elif record.auto_requisition_rule == 'safety_stock' and record.current_stock <= record.safety_stock:
                should_create = True
            
            if should_create:
                record._create_auto_requisition()
    
    def _create_auto_requisition(self):
        """Create automatic requisition"""
        for record in self:
            # Check if there's already a pending requisition
            existing_requisition = self.env['manufacturing.requisition'].search([
                ('product_id', '=', record.product_id.id),
                ('location_id', '=', record.location_id.id),
                ('state', 'in', ['draft', 'submitted', 'approved']),
                ('requisition_type', '=', 'auto_reorder')
            ], limit=1)
            
            if not existing_requisition:
                quantity = record.auto_requisition_quantity or (record.max_stock_level - record.current_stock)
                
                requisition_vals = {
                    'product_id': record.product_id.id,
                    'quantity_required': quantity,
                    'location_id': record.location_id.id,
                    'warehouse_id': record.warehouse_id.id,
                    'requisition_type': 'auto_reorder',
                    'priority': 'high' if record.state == 'critical' else 'medium',
                    'description': f'Auto-generated requisition for {record.product_id.name} - Stock level: {record.current_stock}',
                    'inventory_integration_id': record.id,
                    'auto_approve': True if record.state != 'critical' else False,
                }
                
                requisition = self.env['manufacturing.requisition'].create(requisition_vals)
                
                # Auto-submit if configured
                if record.state in ['critical', 'out_of_stock']:
                    requisition.action_submit()
                
                _logger.info(f'Auto-requisition created: {requisition.name} for product {record.product_id.name}')
    
    @api.model
    def cron_check_stock_levels(self):
        """Cron job to check stock levels"""
        integrations = self.search([
            ('next_check_date', '<=', fields.Datetime.now()),
            ('auto_requisition_enabled', '=', True)
        ])
        
        for integration in integrations:
            try:
                integration.action_check_stock_levels()
            except Exception as e:
                _logger.error(f'Error checking stock levels for {integration.name}: {str(e)}')
        
        return True
    
    def action_view_requisitions(self):
        """View related requisitions"""
        action = self.env.ref('manufacturing_material_requisitions.action_manufacturing_requisition').read()[0]
        action['domain'] = [('inventory_integration_id', '=', self.id)]
        action['context'] = {'default_inventory_integration_id': self.id}
        return action
    
    def action_view_stock_moves(self):
        """View related stock moves"""
        action = self.env.ref('stock.stock_move_action').read()[0]
        action['domain'] = [
            ('product_id', '=', self.product_id.id),
            ('location_id', '=', self.location_id.id)
        ]
        return action
    
    def action_create_manual_requisition(self):
        """Create manual requisition"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Requisition',
            'res_model': 'manufacturing.requisition',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_id': self.product_id.id,
                'default_location_id': self.location_id.id,
                'default_warehouse_id': self.warehouse_id.id,
                'default_inventory_integration_id': self.id,
            }
        }

class StockMoveExtension(models.Model):
    _inherit = 'stock.move'
    
    inventory_integration_id = fields.Many2one('manufacturing.inventory.integration', 'Inventory Integration')
    
    def _action_done(self, cancel_backorder=False):
        """Override to trigger inventory integration updates"""
        result = super(StockMoveExtension, self)._action_done(cancel_backorder)
        
        # Update related inventory integrations
        for move in self:
            integrations = self.env['manufacturing.inventory.integration'].search([
                ('product_id', '=', move.product_id.id),
                ('location_id', 'in', [move.location_id.id, move.location_dest_id.id])
            ])
            
            for integration in integrations:
                integration._compute_stock_levels()
                integration._check_auto_requisition()
        
        return result

class StockQuantExtension(models.Model):
    _inherit = 'stock.quant'
    
    def _update_available_quantity(self, product_id, location_id, quantity, lot_id=None, package_id=None, owner_id=None, in_date=None):
        """Override to trigger inventory integration updates"""
        result = super(StockQuantExtension, self)._update_available_quantity(
            product_id, location_id, quantity, lot_id, package_id, owner_id, in_date
        )
        
        # Update related inventory integrations
        integrations = self.env['manufacturing.inventory.integration'].search([
            ('product_id', '=', product_id.id),
            ('location_id', '=', location_id.id)
        ])
        
        for integration in integrations:
            integration._compute_stock_levels()
            integration._check_auto_requisition()
        
        return result 