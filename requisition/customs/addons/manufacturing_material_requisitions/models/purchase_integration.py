# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class PurchaseIntegration(models.Model):
    _name = 'manufacturing.purchase.integration'
    _description = 'Manufacturing Purchase Integration'
    _order = 'create_date desc'

    name = fields.Char('Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    
    # Requisition Link
    requisition_id = fields.Many2one('manufacturing.requisition', 'Requisition', required=True, ondelete='cascade')
    
    # Purchase Order
    purchase_order_id = fields.Many2one('purchase.order', 'Purchase Order')
    purchase_order_line_id = fields.Many2one('purchase.order.line', 'Purchase Order Line')
    
    # Vendor Selection
    vendor_id = fields.Many2one('res.partner', 'Selected Vendor', domain=[('is_company', '=', True), ('supplier_rank', '>', 0)])
    vendor_selection_method = fields.Selection([
        ('manual', 'Manual Selection'),
        ('auto_cheapest', 'Automatic - Cheapest'),
        ('auto_fastest', 'Automatic - Fastest Delivery'),
        ('auto_best_rating', 'Automatic - Best Rating'),
        ('auto_preferred', 'Automatic - Preferred Vendor'),
        ('rfq_process', 'RFQ Process')
    ], string='Vendor Selection Method', default='auto_preferred')
    
    # Vendor Analysis
    vendor_analysis_ids = fields.One2many('manufacturing.vendor.analysis', 'purchase_integration_id', 'Vendor Analysis')
    
    # Purchase Details
    product_id = fields.Many2one('product.product', 'Product', related='requisition_id.product_id', store=True)
    quantity = fields.Float('Quantity', related='requisition_id.quantity_required', store=True)
    unit_price = fields.Float('Unit Price')
    total_price = fields.Float('Total Price', compute='_compute_total_price', store=True)
    currency_id = fields.Many2one('res.currency', 'Currency', default=lambda self: self.env.company.currency_id)
    
    # Delivery
    expected_delivery_date = fields.Datetime('Expected Delivery Date')
    actual_delivery_date = fields.Datetime('Actual Delivery Date')
    delivery_delay_days = fields.Float('Delivery Delay (Days)', compute='_compute_delivery_delay')
    
    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('vendor_selection', 'Vendor Selection'),
        ('rfq_sent', 'RFQ Sent'),
        ('po_created', 'PO Created'),
        ('po_confirmed', 'PO Confirmed'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    # Auto-Purchase Settings
    auto_purchase_enabled = fields.Boolean('Auto Purchase Enabled', default=True)
    auto_confirm_po = fields.Boolean('Auto Confirm PO', default=False)
    approval_required = fields.Boolean('Approval Required', compute='_compute_approval_required')
    approval_limit = fields.Float('Approval Limit', default=1000.0)
    
    # RFQ Process
    rfq_count = fields.Integer('RFQ Count', default=3)
    rfq_deadline = fields.Datetime('RFQ Deadline')
    rfq_responses = fields.Integer('RFQ Responses', compute='_compute_rfq_responses')
    
    # Performance Tracking
    lead_time_days = fields.Float('Lead Time (Days)')
    quality_rating = fields.Float('Quality Rating', default=5.0)
    delivery_rating = fields.Float('Delivery Rating', default=5.0)
    price_competitiveness = fields.Float('Price Competitiveness', default=5.0)
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('manufacturing.purchase.integration') or _('New')
        return super(PurchaseIntegration, self).create(vals)
    
    @api.depends('quantity', 'unit_price')
    def _compute_total_price(self):
        for record in self:
            record.total_price = record.quantity * record.unit_price
    
    @api.depends('expected_delivery_date', 'actual_delivery_date')
    def _compute_delivery_delay(self):
        for record in self:
            if record.expected_delivery_date and record.actual_delivery_date:
                delta = record.actual_delivery_date - record.expected_delivery_date
                record.delivery_delay_days = delta.days
            else:
                record.delivery_delay_days = 0
    
    @api.depends('total_price', 'approval_limit')
    def _compute_approval_required(self):
        for record in self:
            record.approval_required = record.total_price > record.approval_limit
    
    @api.depends('vendor_analysis_ids')
    def _compute_rfq_responses(self):
        for record in self:
            record.rfq_responses = len(record.vendor_analysis_ids.filtered(lambda x: x.response_received))
    
    def action_start_vendor_selection(self):
        """Start vendor selection process"""
        self.state = 'vendor_selection'
        
        if self.vendor_selection_method == 'manual':
            return self._open_vendor_selection_wizard()
        elif self.vendor_selection_method == 'rfq_process':
            return self.action_send_rfq()
        else:
            return self._auto_select_vendor()
    
    def _auto_select_vendor(self):
        """Automatically select vendor based on method"""
        vendors = self._get_potential_vendors()
        
        if not vendors:
            raise UserError(_('No suitable vendors found for product %s') % self.product_id.name)
        
        selected_vendor = None
        
        if self.vendor_selection_method == 'auto_cheapest':
            selected_vendor = self._select_cheapest_vendor(vendors)
        elif self.vendor_selection_method == 'auto_fastest':
            selected_vendor = self._select_fastest_vendor(vendors)
        elif self.vendor_selection_method == 'auto_best_rating':
            selected_vendor = self._select_best_rated_vendor(vendors)
        elif self.vendor_selection_method == 'auto_preferred':
            selected_vendor = self._select_preferred_vendor(vendors)
        
        if selected_vendor:
            self.vendor_id = selected_vendor
            self._get_vendor_pricing()
            if self.auto_purchase_enabled:
                return self.action_create_purchase_order()
        
        return True
    
    def _get_potential_vendors(self):
        """Get potential vendors for the product"""
        # Get vendors from product supplier info
        supplier_infos = self.env['product.supplierinfo'].search([
            ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
            ('partner_id.supplier_rank', '>', 0)
        ])
        
        vendors = supplier_infos.mapped('partner_id')
        
        # If no specific suppliers, get all suppliers
        if not vendors:
            vendors = self.env['res.partner'].search([
                ('is_company', '=', True),
                ('supplier_rank', '>', 0)
            ])
        
        return vendors
    
    def _select_cheapest_vendor(self, vendors):
        """Select vendor with lowest price"""
        best_vendor = None
        best_price = float('inf')
        
        for vendor in vendors:
            price = self._get_vendor_price(vendor)
            if price < best_price:
                best_price = price
                best_vendor = vendor
        
        self.unit_price = best_price
        return best_vendor
    
    def _select_fastest_vendor(self, vendors):
        """Select vendor with fastest delivery"""
        best_vendor = None
        best_lead_time = float('inf')
        
        for vendor in vendors:
            lead_time = self._get_vendor_lead_time(vendor)
            if lead_time < best_lead_time:
                best_lead_time = lead_time
                best_vendor = vendor
        
        self.lead_time_days = best_lead_time
        return best_vendor
    
    def _select_best_rated_vendor(self, vendors):
        """Select vendor with best overall rating"""
        best_vendor = None
        best_rating = 0
        
        for vendor in vendors:
            rating = self._get_vendor_rating(vendor)
            if rating > best_rating:
                best_rating = rating
                best_vendor = vendor
        
        return best_vendor
    
    def _select_preferred_vendor(self, vendors):
        """Select preferred vendor based on business rules"""
        # Check for preferred vendors (custom field or tag)
        preferred_vendors = vendors.filtered(lambda v: v.is_preferred_vendor if hasattr(v, 'is_preferred_vendor') else False)
        
        if preferred_vendors:
            return preferred_vendors[0]
        
        # Fallback to best rated vendor
        return self._select_best_rated_vendor(vendors)
    
    def _get_vendor_price(self, vendor):
        """Get vendor price for the product"""
        supplier_info = self.env['product.supplierinfo'].search([
            ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
            ('partner_id', '=', vendor.id)
        ], limit=1)
        
        if supplier_info:
            return supplier_info.price
        
        # Fallback to product cost
        return self.product_id.standard_price or 0.0
    
    def _get_vendor_lead_time(self, vendor):
        """Get vendor lead time"""
        supplier_info = self.env['product.supplierinfo'].search([
            ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
            ('partner_id', '=', vendor.id)
        ], limit=1)
        
        if supplier_info:
            return supplier_info.delay
        
        return 7.0  # Default 7 days
    
    def _get_vendor_rating(self, vendor):
        """Get vendor overall rating"""
        # Calculate based on historical performance
        past_orders = self.env['purchase.order'].search([
            ('partner_id', '=', vendor.id),
            ('state', 'in', ['purchase', 'done'])
        ], limit=10)
        
        if not past_orders:
            return 3.0  # Default rating
        
        # Calculate average rating based on delivery performance
        total_rating = 0
        for order in past_orders:
            # Simple rating based on on-time delivery
            if order.date_planned and order.effective_date:
                if order.effective_date <= order.date_planned:
                    total_rating += 5
                else:
                    delay_days = (order.effective_date - order.date_planned).days
                    rating = max(1, 5 - delay_days)
                    total_rating += rating
            else:
                total_rating += 3
        
        return total_rating / len(past_orders)
    
    def _get_vendor_pricing(self):
        """Get pricing from selected vendor"""
        if self.vendor_id:
            self.unit_price = self._get_vendor_price(self.vendor_id)
            self.lead_time_days = self._get_vendor_lead_time(self.vendor_id)
            self.expected_delivery_date = fields.Datetime.now() + timedelta(days=self.lead_time_days)
    
    def action_send_rfq(self):
        """Send RFQ to multiple vendors"""
        self.state = 'rfq_sent'
        vendors = self._get_potential_vendors()[:self.rfq_count]
        
        self.rfq_deadline = fields.Datetime.now() + timedelta(days=7)
        
        for vendor in vendors:
            self._create_vendor_analysis(vendor)
            self._send_rfq_to_vendor(vendor)
        
        return True
    
    def _create_vendor_analysis(self, vendor):
        """Create vendor analysis record"""
        return self.env['manufacturing.vendor.analysis'].create({
            'purchase_integration_id': self.id,
            'vendor_id': vendor.id,
            'product_id': self.product_id.id,
            'quantity': self.quantity,
            'estimated_price': self._get_vendor_price(vendor),
            'estimated_lead_time': self._get_vendor_lead_time(vendor),
            'vendor_rating': self._get_vendor_rating(vendor),
        })
    
    def _send_rfq_to_vendor(self, vendor):
        """Send RFQ email to vendor"""
        template = self.env.ref('manufacturing_material_requisitions.email_template_rfq', raise_if_not_found=False)
        if template:
            template.with_context(vendor_id=vendor.id).send_mail(self.id, force_send=True)
    
    def action_create_purchase_order(self):
        """Create purchase order"""
        if not self.vendor_id:
            raise UserError(_('Please select a vendor first'))
        
        # Check if PO already exists
        if self.purchase_order_id:
            return self.action_view_purchase_order()
        
        # Create purchase order
        po_vals = {
            'partner_id': self.vendor_id.id,
            'origin': self.requisition_id.name,
            'date_planned': self.expected_delivery_date,
            'requisition_id': self.requisition_id.id,
        }
        
        purchase_order = self.env['purchase.order'].create(po_vals)
        
        # Create purchase order line
        pol_vals = {
            'order_id': purchase_order.id,
            'product_id': self.product_id.id,
            'product_qty': self.quantity,
            'price_unit': self.unit_price,
            'date_planned': self.expected_delivery_date,
            'name': self.product_id.name,
            'product_uom': self.product_id.uom_po_id.id,
        }
        
        po_line = self.env['purchase.order.line'].create(pol_vals)
        
        self.purchase_order_id = purchase_order.id
        self.purchase_order_line_id = po_line.id
        self.state = 'po_created'
        
        # Auto-confirm if enabled and no approval required
        if self.auto_confirm_po and not self.approval_required:
            purchase_order.button_confirm()
            self.state = 'po_confirmed'
        
        # Update requisition
        self.requisition_id.purchase_order_id = purchase_order.id
        self.requisition_id.state = 'purchase_order_created'
        
        return self.action_view_purchase_order()
    
    def action_view_purchase_order(self):
        """View purchase order"""
        if not self.purchase_order_id:
            raise UserError(_('No purchase order created yet'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Order',
            'res_model': 'purchase.order',
            'res_id': self.purchase_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _open_vendor_selection_wizard(self):
        """Open vendor selection wizard"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Select Vendor',
            'res_model': 'manufacturing.vendor.selection.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_purchase_integration_id': self.id,
                'default_product_id': self.product_id.id,
            }
        }
    
    def action_receive_goods(self):
        """Mark goods as received"""
        if self.purchase_order_id and self.purchase_order_id.state == 'purchase':
            # Auto-receive if configured
            for picking in self.purchase_order_id.picking_ids:
                if picking.state in ['assigned', 'confirmed']:
                    picking.action_confirm()
                    picking.action_assign()
                    for move in picking.move_ids:
                        move.quantity_done = move.product_uom_qty
                    picking.button_validate()
            
            self.state = 'received'
            self.actual_delivery_date = fields.Datetime.now()
            
            # Update requisition
            self.requisition_id.state = 'completed'
            
        return True

class VendorAnalysis(models.Model):
    _name = 'manufacturing.vendor.analysis'
    _description = 'Vendor Analysis for Purchase Integration'
    _order = 'total_score desc'

    purchase_integration_id = fields.Many2one('manufacturing.purchase.integration', 'Purchase Integration', required=True, ondelete='cascade')
    vendor_id = fields.Many2one('res.partner', 'Vendor', required=True)
    product_id = fields.Many2one('product.product', 'Product', required=True)
    quantity = fields.Float('Quantity', required=True)
    
    # Pricing
    estimated_price = fields.Float('Estimated Unit Price')
    quoted_price = fields.Float('Quoted Unit Price')
    total_price = fields.Float('Total Price', compute='_compute_total_price')
    
    # Delivery
    estimated_lead_time = fields.Float('Estimated Lead Time (Days)')
    quoted_lead_time = fields.Float('Quoted Lead Time (Days)')
    delivery_date = fields.Datetime('Quoted Delivery Date')
    
    # Ratings
    vendor_rating = fields.Float('Vendor Rating', default=5.0)
    price_score = fields.Float('Price Score', compute='_compute_scores')
    delivery_score = fields.Float('Delivery Score', compute='_compute_scores')
    quality_score = fields.Float('Quality Score', default=5.0)
    total_score = fields.Float('Total Score', compute='_compute_scores')
    
    # RFQ Response
    response_received = fields.Boolean('Response Received', default=False)
    response_date = fields.Datetime('Response Date')
    notes = fields.Text('Notes')
    
    # Selection
    selected = fields.Boolean('Selected', default=False)
    
    @api.depends('quantity', 'quoted_price', 'estimated_price')
    def _compute_total_price(self):
        for record in self:
            price = record.quoted_price or record.estimated_price
            record.total_price = record.quantity * price
    
    @api.depends('quoted_price', 'estimated_price', 'quoted_lead_time', 'estimated_lead_time', 'vendor_rating', 'quality_score')
    def _compute_scores(self):
        for record in self:
            # Price score (lower is better, normalized to 1-10)
            price = record.quoted_price or record.estimated_price
            if price > 0:
                # Compare with average price of all vendors
                avg_price = record.purchase_integration_id.vendor_analysis_ids.mapped(lambda x: x.quoted_price or x.estimated_price)
                if avg_price:
                    avg_price = sum(avg_price) / len(avg_price)
                    record.price_score = max(1, 10 - ((price - avg_price) / avg_price * 10))
                else:
                    record.price_score = 5.0
            else:
                record.price_score = 1.0
            
            # Delivery score (faster is better)
            lead_time = record.quoted_lead_time or record.estimated_lead_time
            if lead_time > 0:
                record.delivery_score = max(1, 10 - (lead_time / 7))  # 7 days = score 9
            else:
                record.delivery_score = 10.0
            
            # Total score (weighted average)
            record.total_score = (
                record.price_score * 0.4 +
                record.delivery_score * 0.3 +
                record.vendor_rating * 0.2 +
                record.quality_score * 0.1
            )
    
    def action_select_vendor(self):
        """Select this vendor"""
        # Unselect other vendors
        self.purchase_integration_id.vendor_analysis_ids.write({'selected': False})
        
        # Select this vendor
        self.selected = True
        self.purchase_integration_id.vendor_id = self.vendor_id
        self.purchase_integration_id.unit_price = self.quoted_price or self.estimated_price
        self.purchase_integration_id.lead_time_days = self.quoted_lead_time or self.estimated_lead_time
        
        if self.delivery_date:
            self.purchase_integration_id.expected_delivery_date = self.delivery_date
        
        return True

class PurchaseOrderExtension(models.Model):
    _inherit = 'purchase.order'
    
    requisition_id = fields.Many2one('manufacturing.requisition', 'Manufacturing Requisition')
    
    def button_confirm(self):
        """Override to update purchase integration"""
        result = super(PurchaseOrderExtension, self).button_confirm()
        
        # Update related purchase integration
        if self.requisition_id:
            integration = self.env['manufacturing.purchase.integration'].search([
                ('requisition_id', '=', self.requisition_id.id),
                ('purchase_order_id', '=', self.id)
            ], limit=1)
            
            if integration:
                integration.state = 'po_confirmed'
        
        return result 