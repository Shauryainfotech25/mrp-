from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class BulkRequisitionWizard(models.TransientModel):
    _name = 'manufacturing.bulk.requisition.wizard'
    _description = 'Bulk Requisition Creation Wizard'

    # Basic Information
    requisition_type = fields.Selection([
        ('production_material', 'Production Material'),
        ('maintenance_material', 'Maintenance Material'),
        ('tooling_equipment', 'Tooling & Equipment'),
        ('quality_material', 'Quality Control Material'),
        ('consumables', 'Manufacturing Consumables'),
        ('safety_equipment', 'Safety Equipment'),
        ('spare_parts', 'Spare Parts')
    ], string='Requisition Type', required=True, default='production_material')
    
    department_id = fields.Many2one('hr.department', 'Department', required=True)
    location_id = fields.Many2one('stock.location', 'Source Location', required=True,
                                 domain=[('usage', '=', 'internal')])
    dest_location_id = fields.Many2one('stock.location', 'Destination Location', required=True,
                                      domain=[('usage', '=', 'internal')])
    
    # Dates and Priority
    required_date = fields.Datetime('Required Date', required=True,
                                   default=lambda self: fields.Datetime.now())
    priority = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ], string='Priority', default='medium', required=True)
    
    # Bulk Creation Options
    creation_method = fields.Selection([
        ('product_list', 'From Product List'),
        ('bom_explosion', 'From BOM Explosion'),
        ('manufacturing_orders', 'From Manufacturing Orders'),
        ('reorder_analysis', 'From Reorder Analysis'),
        ('template', 'From Template')
    ], string='Creation Method', required=True, default='product_list')
    
    # Product Selection
    product_ids = fields.Many2many('product.product', string='Products')
    product_category_ids = fields.Many2many('product.category', string='Product Categories')
    
    # BOM Selection
    bom_id = fields.Many2one('mrp.bom', 'Bill of Materials')
    bom_quantity = fields.Float('BOM Quantity', default=1.0)
    
    # Manufacturing Orders
    manufacturing_order_ids = fields.Many2many('mrp.production', string='Manufacturing Orders')
    
    # Template
    template_id = fields.Many2one('manufacturing.requisition.template', 'Template')
    
    # Options
    group_by_vendor = fields.Boolean('Group by Vendor', default=True)
    group_by_category = fields.Boolean('Group by Category', default=False)
    auto_submit = fields.Boolean('Auto Submit', default=False)
    
    # Lines
    line_ids = fields.One2many('manufacturing.bulk.requisition.line', 'wizard_id', 'Lines')
    
    # Summary
    total_lines = fields.Integer('Total Lines', compute='_compute_summary')
    total_amount = fields.Float('Total Amount', compute='_compute_summary')
    
    @api.depends('line_ids')
    def _compute_summary(self):
        for wizard in self:
            wizard.total_lines = len(wizard.line_ids)
            wizard.total_amount = sum(wizard.line_ids.mapped('total_price'))
    
    @api.onchange('creation_method')
    def _onchange_creation_method(self):
        """Clear lines when creation method changes"""
        self.line_ids = [(5, 0, 0)]
    
    @api.onchange('product_ids', 'product_category_ids')
    def _onchange_products(self):
        """Generate lines from selected products"""
        if self.creation_method == 'product_list':
            self._generate_product_lines()
    
    @api.onchange('bom_id', 'bom_quantity')
    def _onchange_bom(self):
        """Generate lines from BOM explosion"""
        if self.creation_method == 'bom_explosion' and self.bom_id:
            self._generate_bom_lines()
    
    @api.onchange('manufacturing_order_ids')
    def _onchange_manufacturing_orders(self):
        """Generate lines from manufacturing orders"""
        if self.creation_method == 'manufacturing_orders':
            self._generate_mo_lines()
    
    @api.onchange('template_id')
    def _onchange_template(self):
        """Generate lines from template"""
        if self.creation_method == 'template' and self.template_id:
            self._generate_template_lines()
    
    def _generate_product_lines(self):
        """Generate lines from selected products"""
        lines = []
        
        # Add directly selected products
        for product in self.product_ids:
            lines.append((0, 0, {
                'product_id': product.id,
                'qty_required': 1.0,
                'unit_price': product.standard_price,
            }))
        
        # Add products from categories
        if self.product_category_ids:
            category_products = self.env['product.product'].search([
                ('categ_id', 'in', self.product_category_ids.ids),
                ('type', '=', 'product')
            ])
            
            for product in category_products:
                if product.id not in self.product_ids.ids:
                    lines.append((0, 0, {
                        'product_id': product.id,
                        'qty_required': 1.0,
                        'unit_price': product.standard_price,
                    }))
        
        self.line_ids = lines
    
    def _generate_bom_lines(self):
        """Generate lines from BOM explosion"""
        if not self.bom_id:
            return
        
        lines = []
        bom_lines = self.bom_id.bom_line_ids
        
        for bom_line in bom_lines:
            qty_required = bom_line.product_qty * self.bom_quantity
            lines.append((0, 0, {
                'product_id': bom_line.product_id.id,
                'qty_required': qty_required,
                'unit_price': bom_line.product_id.standard_price,
                'bom_line_id': bom_line.id,
            }))
        
        self.line_ids = lines
    
    def _generate_mo_lines(self):
        """Generate lines from manufacturing orders"""
        lines = []
        
        for mo in self.manufacturing_order_ids:
            # Analyze material shortages
            shortages = self._analyze_mo_shortages(mo)
            
            for shortage in shortages:
                lines.append((0, 0, {
                    'product_id': shortage['product_id'],
                    'qty_required': shortage['shortage_qty'],
                    'unit_price': shortage['unit_price'],
                    'manufacturing_order_id': mo.id,
                    'reason': f"Shortage for MO {mo.name}",
                }))
        
        self.line_ids = lines
    
    def _generate_template_lines(self):
        """Generate lines from template"""
        if not self.template_id:
            return
        
        lines = []
        for template_line in self.template_id.line_ids:
            lines.append((0, 0, {
                'product_id': template_line.product_id.id,
                'qty_required': template_line.qty_required,
                'unit_price': template_line.product_id.standard_price,
            }))
        
        self.line_ids = lines
    
    def _analyze_mo_shortages(self, mo):
        """Analyze material shortages for manufacturing order"""
        shortages = []
        
        for move in mo.move_raw_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
            available_qty = move.product_id.with_context(
                location=mo.location_src_id.id
            ).qty_available
            
            if available_qty < move.product_uom_qty:
                shortage_qty = move.product_uom_qty - available_qty
                shortages.append({
                    'product_id': move.product_id.id,
                    'shortage_qty': shortage_qty,
                    'unit_price': move.product_id.standard_price,
                })
        
        return shortages
    
    def action_generate_reorder_analysis(self):
        """Generate lines from reorder analysis"""
        if self.creation_method != 'reorder_analysis':
            return
        
        # Get products below reorder point
        reorder_products = self.env['manufacturing.inventory.integration'].search([
            ('state', '=', 'low_stock'),
            ('auto_requisition_enabled', '=', True)
        ])
        
        lines = []
        for integration in reorder_products:
            qty_to_order = integration.auto_requisition_quantity or (
                integration.max_stock_level - integration.current_stock
            )
            
            lines.append((0, 0, {
                'product_id': integration.product_id.id,
                'qty_required': qty_to_order,
                'unit_price': integration.product_id.standard_price,
                'reason': 'Reorder point reached',
            }))
        
        self.line_ids = lines
    
    def action_create_requisitions(self):
        """Create requisitions from wizard lines"""
        if not self.line_ids:
            raise UserError(_('No lines to process. Please add products first.'))
        
        requisitions = []
        
        if self.group_by_vendor:
            requisitions = self._create_grouped_by_vendor()
        elif self.group_by_category:
            requisitions = self._create_grouped_by_category()
        else:
            requisitions = self._create_single_requisition()
        
        # Auto-submit if requested
        if self.auto_submit:
            for requisition in requisitions:
                try:
                    requisition.action_submit()
                except Exception as e:
                    _logger.warning(f"Failed to auto-submit requisition {requisition.name}: {str(e)}")
        
        # Return action to view created requisitions
        if len(requisitions) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Created Requisition'),
                'res_model': 'manufacturing.material.requisition',
                'res_id': requisitions[0].id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Created Requisitions'),
                'res_model': 'manufacturing.material.requisition',
                'domain': [('id', 'in', [r.id for r in requisitions])],
                'view_mode': 'tree,form',
                'target': 'current',
            }
    
    def _create_single_requisition(self):
        """Create single requisition with all lines"""
        requisition_vals = self._get_base_requisition_vals()
        requisition_vals['reason'] = f'Bulk requisition - {self.creation_method}'
        
        requisition = self.env['manufacturing.material.requisition'].create(requisition_vals)
        
        # Create lines
        for line in self.line_ids:
            self._create_requisition_line(requisition, line)
        
        return [requisition]
    
    def _create_grouped_by_vendor(self):
        """Create requisitions grouped by vendor"""
        vendor_groups = {}
        
        for line in self.line_ids:
            vendor = line.vendor_id or self.env['res.partner']
            vendor_key = vendor.id if vendor else 'no_vendor'
            
            if vendor_key not in vendor_groups:
                vendor_groups[vendor_key] = {
                    'vendor': vendor,
                    'lines': []
                }
            vendor_groups[vendor_key]['lines'].append(line)
        
        requisitions = []
        for vendor_key, group in vendor_groups.items():
            requisition_vals = self._get_base_requisition_vals()
            vendor_name = group['vendor'].name if group['vendor'] else 'No Vendor'
            requisition_vals['reason'] = f'Bulk requisition - {vendor_name}'
            
            requisition = self.env['manufacturing.material.requisition'].create(requisition_vals)
            
            for line in group['lines']:
                self._create_requisition_line(requisition, line)
            
            requisitions.append(requisition)
        
        return requisitions
    
    def _create_grouped_by_category(self):
        """Create requisitions grouped by product category"""
        category_groups = {}
        
        for line in self.line_ids:
            category = line.product_id.categ_id
            category_key = category.id
            
            if category_key not in category_groups:
                category_groups[category_key] = {
                    'category': category,
                    'lines': []
                }
            category_groups[category_key]['lines'].append(line)
        
        requisitions = []
        for category_key, group in category_groups.items():
            requisition_vals = self._get_base_requisition_vals()
            requisition_vals['reason'] = f'Bulk requisition - {group["category"].name}'
            
            requisition = self.env['manufacturing.material.requisition'].create(requisition_vals)
            
            for line in group['lines']:
                self._create_requisition_line(requisition, line)
            
            requisitions.append(requisition)
        
        return requisitions
    
    def _get_base_requisition_vals(self):
        """Get base requisition values"""
        return {
            'requisition_type': self.requisition_type,
            'department_id': self.department_id.id,
            'location_id': self.location_id.id,
            'dest_location_id': self.dest_location_id.id,
            'required_date': self.required_date,
            'priority': self.priority,
        }
    
    def _create_requisition_line(self, requisition, wizard_line):
        """Create requisition line from wizard line"""
        line_vals = {
            'requisition_id': requisition.id,
            'product_id': wizard_line.product_id.id,
            'qty_required': wizard_line.qty_required,
            'unit_price': wizard_line.unit_price,
            'required_date': self.required_date,
            'reason': wizard_line.reason or '',
        }
        
        if wizard_line.vendor_id:
            line_vals['vendor_id'] = wizard_line.vendor_id.id
        
        if wizard_line.bom_line_id:
            line_vals['bom_line_id'] = wizard_line.bom_line_id.id
        
        return self.env['manufacturing.material.requisition.line'].create(line_vals)


class BulkRequisitionLine(models.TransientModel):
    _name = 'manufacturing.bulk.requisition.line'
    _description = 'Bulk Requisition Line'

    wizard_id = fields.Many2one('manufacturing.bulk.requisition.wizard', 'Wizard', required=True, ondelete='cascade')
    
    product_id = fields.Many2one('product.product', 'Product', required=True)
    qty_required = fields.Float('Quantity Required', required=True, default=1.0)
    unit_price = fields.Float('Unit Price')
    total_price = fields.Float('Total Price', compute='_compute_total_price', store=True)
    
    vendor_id = fields.Many2one('res.partner', 'Preferred Vendor',
                               domain=[('is_company', '=', True), ('supplier_rank', '>', 0)])
    
    # References
    bom_line_id = fields.Many2one('mrp.bom.line', 'BOM Line')
    manufacturing_order_id = fields.Many2one('mrp.production', 'Manufacturing Order')
    
    reason = fields.Text('Reason')
    
    @api.depends('qty_required', 'unit_price')
    def _compute_total_price(self):
        for line in self:
            line.total_price = line.qty_required * line.unit_price
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.unit_price = self.product_id.standard_price
            
            # Set preferred vendor
            if self.product_id.seller_ids:
                self.vendor_id = self.product_id.seller_ids[0].partner_id


class RequisitionTemplate(models.Model):
    _name = 'manufacturing.requisition.template'
    _description = 'Requisition Template'

    name = fields.Char('Template Name', required=True)
    description = fields.Text('Description')
    
    requisition_type = fields.Selection([
        ('production_material', 'Production Material'),
        ('maintenance_material', 'Maintenance Material'),
        ('tooling_equipment', 'Tooling & Equipment'),
        ('quality_material', 'Quality Control Material'),
        ('consumables', 'Manufacturing Consumables'),
        ('safety_equipment', 'Safety Equipment'),
        ('spare_parts', 'Spare Parts')
    ], string='Requisition Type', required=True)
    
    department_id = fields.Many2one('hr.department', 'Default Department')
    
    line_ids = fields.One2many('manufacturing.requisition.template.line', 'template_id', 'Template Lines')
    
    active = fields.Boolean('Active', default=True)


class RequisitionTemplateLine(models.Model):
    _name = 'manufacturing.requisition.template.line'
    _description = 'Requisition Template Line'

    template_id = fields.Many2one('manufacturing.requisition.template', 'Template', required=True, ondelete='cascade')
    sequence = fields.Integer('Sequence', default=10)
    
    product_id = fields.Many2one('product.product', 'Product', required=True)
    qty_required = fields.Float('Default Quantity', required=True, default=1.0)
    
    notes = fields.Text('Notes') 