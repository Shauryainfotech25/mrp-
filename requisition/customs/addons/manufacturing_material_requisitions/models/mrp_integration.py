from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import json
import logging

_logger = logging.getLogger(__name__)


class MRPRequisitionIntegration(models.Model):
    _name = 'mrp.requisition.integration'
    _description = 'MRP and Requisition Integration'
    _auto = False

    @api.model
    def run_mrp_requisition_analysis(self):
        """Analyze MRP requirements and create requisitions automatically"""
        
        # Get all confirmed production orders within planning horizon
        planning_horizon = self.env.company.mrp_planning_horizon or 30
        cutoff_date = fields.Datetime.now() + timedelta(days=planning_horizon)
        
        production_orders = self.env['mrp.production'].search([
            ('state', 'in', ['confirmed', 'progress']),
            ('date_planned_start', '<=', cutoff_date),
            ('requisition_analyzed', '=', False)
        ])
        
        for production in production_orders:
            try:
                # Analyze material requirements
                material_analysis = self._analyze_material_requirements(production)
                
                if material_analysis['shortages']:
                    requisition = self._create_mrp_requisition(production, material_analysis)
                    if requisition:
                        production.requisition_analyzed = True
                        production.auto_requisition_id = requisition.id
                        
                        # Log analysis results
                        self._log_mrp_analysis(production, material_analysis, requisition)
                
            except Exception as e:
                _logger.error(f"MRP analysis failed for production {production.name}: {str(e)}")
                continue
    
    def _analyze_material_requirements(self, production):
        """Detailed analysis of material requirements for production order"""
        analysis = {
            'shortages': [],
            'alternatives': [],
            'suggested_actions': [],
            'total_shortage_cost': 0,
            'critical_path_impact': False
        }
        
        for move in production.move_raw_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
            # Get multi-location stock levels
            stock_levels = self._get_multilocation_stock(move.product_id, production.location_src_id)
            
            # Calculate net requirement considering reserved stock
            reserved_qty = self._get_reserved_quantity(move.product_id, production.location_src_id)
            available_qty = stock_levels['total_available'] - reserved_qty
            
            if available_qty < move.product_uom_qty:
                shortage_qty = move.product_uom_qty - available_qty
                
                # Get alternative products
                alternatives = self._find_alternative_products(move.product_id)
                
                # Get supplier information
                suppliers = self._get_preferred_suppliers(move.product_id)
                
                # Calculate procurement lead time
                lead_time = self._calculate_procurement_lead_time(move.product_id, shortage_qty)
                
                # Check if this affects critical path
                critical_path_impact = self._check_critical_path_impact(production, move, lead_time)
                
                shortage_info = {
                    'product_id': move.product_id.id,
                    'product_name': move.product_id.name,
                    'required_qty': move.product_uom_qty,
                    'available_qty': available_qty,
                    'reserved_qty': reserved_qty,
                    'shortage_qty': shortage_qty,
                    'bom_line_id': move.bom_line_id.id if move.bom_line_id else False,
                    'work_order_id': move.workorder_id.id if move.workorder_id else False,
                    'operation_id': move.operation_id.id if move.operation_id else False,
                    'locations': stock_levels['by_location'],
                    'alternatives': alternatives,
                    'suppliers': suppliers,
                    'lead_time': lead_time,
                    'critical_path_impact': critical_path_impact,
                    'estimated_cost': move.product_id.standard_price * shortage_qty,
                    'required_date': move.date,
                }
                
                analysis['shortages'].append(shortage_info)
                analysis['total_shortage_cost'] += shortage_info['estimated_cost']
                
                if critical_path_impact:
                    analysis['critical_path_impact'] = True
                
                # Generate suggestions
                if alternatives:
                    analysis['suggested_actions'].append(
                        f"Consider alternative for {move.product_id.name}: {alternatives[0]['name']}"
                    )
                
                if lead_time > (production.date_planned_start - fields.Datetime.now()).days:
                    analysis['suggested_actions'].append(
                        f"Urgent procurement needed for {move.product_id.name} - Lead time exceeds production start"
                    )
                
                # Check for bulk purchase opportunities
                if shortage_qty > move.product_id.seller_ids[0].min_qty if move.product_id.seller_ids else False:
                    analysis['suggested_actions'].append(
                        f"Bulk purchase opportunity for {move.product_id.name}"
                    )
        
        return analysis
    
    def _get_multilocation_stock(self, product, primary_location):
        """Get stock levels across all available locations"""
        # Get all internal locations in the same warehouse
        warehouse = primary_location.warehouse_id
        locations = self.env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id)
        ])
        
        stock_by_location = {}
        total_available = 0
        
        for location in locations:
            quants = self.env['stock.quant'].search([
                ('product_id', '=', product.id),
                ('location_id', '=', location.id),
                ('quantity', '>', 0)
            ])
            
            location_qty = sum(quants.mapped('quantity'))
            if location_qty > 0:
                stock_by_location[location.name] = {
                    'quantity': location_qty,
                    'location_id': location.id,
                    'transfer_time': self._calculate_transfer_time(location, primary_location)
                }
                total_available += location_qty
        
        return {
            'total_available': total_available,
            'by_location': stock_by_location
        }
    
    def _get_reserved_quantity(self, product, location):
        """Get quantity already reserved for other orders"""
        reserved_moves = self.env['stock.move'].search([
            ('product_id', '=', product.id),
            ('location_id', '=', location.id),
            ('state', 'in', ['waiting', 'confirmed', 'assigned']),
            ('date', '<=', fields.Datetime.now() + timedelta(days=7))  # Within a week
        ])
        
        return sum(reserved_moves.mapped('product_uom_qty'))
    
    def _find_alternative_products(self, product):
        """Find alternative products that can be used"""
        alternatives = []
        
        # Check product variants
        variants = product.product_tmpl_id.product_variant_ids.filtered(
            lambda p: p.id != product.id and p.active
        )
        
        for variant in variants:
            if variant.qty_available > 0:
                alternatives.append({
                    'product_id': variant.id,
                    'name': variant.name,
                    'available_qty': variant.qty_available,
                    'price_difference': variant.standard_price - product.standard_price,
                    'type': 'variant'
                })
        
        # Check products with same category and similar attributes
        similar_products = self.env['product.product'].search([
            ('categ_id', '=', product.categ_id.id),
            ('id', '!=', product.id),
            ('active', '=', True),
            ('qty_available', '>', 0)
        ], limit=5)
        
        for similar in similar_products:
            alternatives.append({
                'product_id': similar.id,
                'name': similar.name,
                'available_qty': similar.qty_available,
                'price_difference': similar.standard_price - product.standard_price,
                'type': 'similar'
            })
        
        return alternatives[:3]  # Return top 3 alternatives
    
    def _get_preferred_suppliers(self, product):
        """Get preferred suppliers with pricing and lead time"""
        suppliers = []
        
        for seller in product.seller_ids.sorted(lambda s: s.sequence):
            suppliers.append({
                'supplier_id': seller.partner_id.id,
                'supplier_name': seller.partner_id.name,
                'price': seller.price,
                'min_qty': seller.min_qty,
                'lead_time': seller.delay,
                'currency': seller.currency_id.name,
                'last_purchase_date': self._get_last_purchase_date(product, seller.partner_id),
                'performance_score': self._get_supplier_performance_score(seller.partner_id, product)
            })
        
        return suppliers
    
    def _calculate_procurement_lead_time(self, product, quantity):
        """Calculate total procurement lead time including processing"""
        base_lead_time = 0
        
        if product.seller_ids:
            # Use vendor lead time
            base_lead_time = product.seller_ids[0].delay
        else:
            # Default lead time for products without suppliers
            base_lead_time = 7
        
        # Add processing time based on quantity
        if quantity > 100:
            base_lead_time += 2  # Extra time for large quantities
        
        # Add approval time based on product cost
        if product.standard_price * quantity > 5000:
            base_lead_time += 1  # Extra approval time for expensive items
        
        return base_lead_time
    
    def _check_critical_path_impact(self, production, move, lead_time):
        """Check if material shortage affects critical path"""
        # Calculate days until production start
        days_until_production = (production.date_planned_start - fields.Datetime.now()).days
        
        # If lead time exceeds available time, it's critical
        if lead_time > days_until_production:
            return True
        
        # Check if this is a critical component (no alternatives, high cost)
        if move.product_id.standard_price > 1000 and not self._find_alternative_products(move.product_id):
            return True
        
        # Check if this operation is on critical path
        if move.workorder_id and move.workorder_id.is_critical_path:
            return True
        
        return False
    
    def _calculate_transfer_time(self, from_location, to_location):
        """Calculate time needed to transfer between locations"""
        # Simple calculation based on location hierarchy
        if from_location.location_id == to_location.location_id:
            return 0.5  # Same parent location - 30 minutes
        elif from_location.warehouse_id == to_location.warehouse_id:
            return 2  # Same warehouse - 2 hours
        else:
            return 24  # Different warehouse - 1 day
    
    def _get_last_purchase_date(self, product, supplier):
        """Get last purchase date from supplier"""
        last_po_line = self.env['purchase.order.line'].search([
            ('product_id', '=', product.id),
            ('partner_id', '=', supplier.id),
            ('state', 'in', ['purchase', 'done'])
        ], order='date_order desc', limit=1)
        
        return last_po_line.date_order if last_po_line else False
    
    def _get_supplier_performance_score(self, supplier, product):
        """Get supplier performance score for this product"""
        # Get recent purchase orders
        recent_pos = self.env['purchase.order'].search([
            ('partner_id', '=', supplier.id),
            ('state', 'in', ['purchase', 'done']),
            ('date_order', '>=', fields.Date.today() - timedelta(days=365))
        ])
        
        if not recent_pos:
            return 5.0  # Default score
        
        # Calculate performance metrics
        on_time_deliveries = 0
        total_deliveries = 0
        
        for po in recent_pos:
            for picking in po.picking_ids.filtered(lambda p: p.state == 'done'):
                total_deliveries += 1
                if picking.date_done <= po.date_planned:
                    on_time_deliveries += 1
        
        if total_deliveries == 0:
            return 5.0
        
        on_time_rate = on_time_deliveries / total_deliveries
        return round(on_time_rate * 10, 1)  # Score out of 10
    
    def _create_mrp_requisition(self, production, analysis):
        """Create requisition based on MRP analysis"""
        if not analysis['shortages']:
            return False
        
        # Determine priority based on analysis
        priority = 'urgent' if analysis['critical_path_impact'] else 'high'
        urgency = 'critical_path' if analysis['critical_path_impact'] else 'expedite'
        
        requisition_vals = {
            'name': f"MRP-{production.name}-{fields.Date.today().strftime('%Y%m%d')}",
            'manufacturing_order_id': production.id,
            'bom_id': production.bom_id.id,
            'requisition_type': 'production_material',
            'production_stage': 'raw_material',
            'department_id': production.workcenter_id.department_id.id if production.workcenter_id else False,
            'location_id': production.location_src_id.id,
            'dest_location_id': production.location_dest_id.id,
            'required_date': production.date_planned_start - timedelta(days=1),
            'priority': priority,
            'urgency_level': urgency,
            'reason': f'MRP analysis for production order {production.name}',
            'auto_generated': True,
            'source_document': production.name,
            'notes': f"Auto-generated from MRP analysis. Total shortage cost: {analysis['total_shortage_cost']:.2f}. "
                    f"Suggested actions: {'; '.join(analysis['suggested_actions'][:3])}"
        }
        
        requisition = self.env['manufacturing.material.requisition'].create(requisition_vals)
        
        # Create requisition lines
        for shortage in analysis['shortages']:
            line_vals = {
                'requisition_id': requisition.id,
                'product_id': shortage['product_id'],
                'qty_required': shortage['shortage_qty'],
                'required_date': shortage['required_date'],
                'reason': f"MRP shortage analysis for {production.name}",
                'bom_line_id': shortage.get('bom_line_id'),
                'work_order_id': shortage.get('work_order_id'),
                'operation_id': shortage.get('operation_id'),
                'estimated_cost': shortage['estimated_cost'],
                'notes': json.dumps({
                    'available_locations': shortage['locations'],
                    'alternatives': shortage['alternatives'],
                    'suppliers': shortage['suppliers'],
                    'lead_time': shortage['lead_time'],
                    'critical_path': shortage['critical_path_impact']
                })
            }
            
            line = self.env['manufacturing.material.requisition.line'].create(line_vals)
            
            # Auto-select best supplier if available
            if shortage['suppliers']:
                best_supplier = self._select_best_supplier(shortage['suppliers'], shortage['shortage_qty'])
                if best_supplier:
                    line.write({
                        'vendor_id': best_supplier['supplier_id'],
                        'vendor_price': best_supplier['price'],
                        'vendor_lead_time': best_supplier['lead_time'],
                        'unit_price': best_supplier['price']
                    })
        
        # Auto-submit if critical path is affected
        if analysis['critical_path_impact']:
            requisition.action_submit()
        
        return requisition
    
    def _select_best_supplier(self, suppliers, quantity):
        """Select best supplier based on multiple criteria"""
        if not suppliers:
            return None
        
        # Score suppliers based on multiple factors
        scored_suppliers = []
        
        for supplier in suppliers:
            score = 0
            
            # Performance score (40% weight)
            score += supplier['performance_score'] * 0.4
            
            # Price score (30% weight) - lower price is better
            if suppliers:
                min_price = min(s['price'] for s in suppliers)
                max_price = max(s['price'] for s in suppliers)
                if max_price > min_price:
                    price_score = 10 * (1 - (supplier['price'] - min_price) / (max_price - min_price))
                else:
                    price_score = 10
                score += price_score * 0.3
            
            # Lead time score (20% weight) - shorter lead time is better
            if suppliers:
                min_lead = min(s['lead_time'] for s in suppliers)
                max_lead = max(s['lead_time'] for s in suppliers)
                if max_lead > min_lead:
                    lead_score = 10 * (1 - (supplier['lead_time'] - min_lead) / (max_lead - min_lead))
                else:
                    lead_score = 10
                score += lead_score * 0.2
            
            # Minimum quantity compliance (10% weight)
            if quantity >= supplier['min_qty']:
                score += 1
            
            scored_suppliers.append({
                **supplier,
                'total_score': score
            })
        
        # Return supplier with highest score
        return max(scored_suppliers, key=lambda s: s['total_score'])
    
    def _log_mrp_analysis(self, production, analysis, requisition):
        """Log MRP analysis results for reporting"""
        self.env['mrp.analysis.log'].create({
            'production_id': production.id,
            'requisition_id': requisition.id if requisition else False,
            'analysis_date': fields.Datetime.now(),
            'shortages_count': len(analysis['shortages']),
            'total_shortage_cost': analysis['total_shortage_cost'],
            'critical_path_impact': analysis['critical_path_impact'],
            'suggested_actions': '; '.join(analysis['suggested_actions']),
            'analysis_data': json.dumps(analysis)
        })
    
    @api.model
    def run_automated_reorder_analysis(self):
        """Run automated reorder point analysis for manufacturing"""
        # Get products used in active BOMs
        active_bom_products = self.env['mrp.bom.line'].search([
            ('bom_id.active', '=', True)
        ]).mapped('product_id')
        
        reorder_suggestions = []
        
        for product in active_bom_products:
            # Calculate dynamic reorder point
            reorder_analysis = self._calculate_dynamic_reorder_point(product)
            
            if reorder_analysis['should_reorder']:
                reorder_suggestions.append(reorder_analysis)
                
                # Create automatic requisition if enabled
                if self.env.company.auto_create_reorder_requisitions:
                    self._create_automatic_reorder_requisition(reorder_analysis)
        
        return reorder_suggestions
    
    def _calculate_dynamic_reorder_point(self, product):
        """Calculate dynamic reorder point based on manufacturing demand"""
        # Get upcoming manufacturing demand
        upcoming_demand = self._get_upcoming_manufacturing_demand(product)
        
        # Get historical consumption
        historical_consumption = self._get_historical_consumption(product)
        
        # Calculate safety stock
        safety_stock = self._calculate_manufacturing_safety_stock(product, historical_consumption)
        
        # Calculate lead time demand
        lead_time = product.seller_ids[0].delay if product.seller_ids else 7
        daily_demand = historical_consumption.get('daily_average', 0)
        lead_time_demand = daily_demand * lead_time
        
        # Dynamic reorder point
        reorder_point = safety_stock + lead_time_demand + upcoming_demand['next_7_days']
        
        current_stock = product.qty_available
        
        return {
            'product_id': product.id,
            'product_name': product.name,
            'current_stock': current_stock,
            'reorder_point': reorder_point,
            'safety_stock': safety_stock,
            'lead_time_demand': lead_time_demand,
            'upcoming_demand': upcoming_demand,
            'should_reorder': current_stock < reorder_point,
            'suggested_qty': self._calculate_optimal_order_quantity(product, upcoming_demand),
            'urgency': 'high' if current_stock < safety_stock else 'medium'
        }
    
    def _get_upcoming_manufacturing_demand(self, product):
        """Get upcoming manufacturing demand for product"""
        # Get confirmed production orders
        upcoming_productions = self.env['mrp.production'].search([
            ('state', 'in', ['confirmed', 'progress']),
            ('date_planned_start', '<=', fields.Datetime.now() + timedelta(days=30))
        ])
        
        demand_7_days = 0
        demand_30_days = 0
        
        for production in upcoming_productions:
            for move in production.move_raw_ids:
                if move.product_id.id == product.id:
                    if production.date_planned_start <= fields.Datetime.now() + timedelta(days=7):
                        demand_7_days += move.product_uom_qty
                    demand_30_days += move.product_uom_qty
        
        return {
            'next_7_days': demand_7_days,
            'next_30_days': demand_30_days
        }
    
    def _get_historical_consumption(self, product):
        """Get historical consumption patterns"""
        # Get stock moves for the last 6 months
        six_months_ago = fields.Date.today() - timedelta(days=180)
        
        consumption_moves = self.env['stock.move'].search([
            ('product_id', '=', product.id),
            ('state', '=', 'done'),
            ('date', '>=', six_months_ago),
            ('location_dest_id.usage', '=', 'production')  # Consumed in production
        ])
        
        if not consumption_moves:
            return {'daily_average': 0, 'monthly_variance': 0}
        
        # Calculate monthly consumption
        monthly_consumption = {}
        for move in consumption_moves:
            month_key = move.date.strftime('%Y-%m')
            if month_key not in monthly_consumption:
                monthly_consumption[month_key] = 0
            monthly_consumption[month_key] += move.product_uom_qty
        
        if not monthly_consumption:
            return {'daily_average': 0, 'monthly_variance': 0}
        
        # Calculate statistics
        consumptions = list(monthly_consumption.values())
        avg_monthly = sum(consumptions) / len(consumptions)
        daily_average = avg_monthly / 30  # Approximate daily consumption
        
        # Calculate variance
        if len(consumptions) > 1:
            variance = sum((x - avg_monthly) ** 2 for x in consumptions) / len(consumptions)
        else:
            variance = 0
        
        return {
            'daily_average': daily_average,
            'monthly_average': avg_monthly,
            'monthly_variance': variance,
            'months_data': len(consumptions)
        }
    
    def _calculate_manufacturing_safety_stock(self, product, consumption_data):
        """Calculate safety stock for manufacturing environment"""
        if consumption_data['daily_average'] == 0:
            return product.reordering_min_qty or 0
        
        # Service level factor (95% service level = 1.65)
        service_level_factor = 1.65
        
        # Lead time in days
        lead_time = product.seller_ids[0].delay if product.seller_ids else 7
        
        # Demand variability (standard deviation)
        if consumption_data['monthly_variance'] > 0:
            monthly_std = consumption_data['monthly_variance'] ** 0.5
            daily_std = monthly_std / 30
        else:
            # Use 20% of average as default variability
            daily_std = consumption_data['daily_average'] * 0.2
        
        # Safety stock formula: Z * σ * √L
        safety_stock = service_level_factor * daily_std * (lead_time ** 0.5)
        
        # Ensure minimum safety stock
        min_safety_stock = product.reordering_min_qty or consumption_data['daily_average'] * 3
        
        return max(safety_stock, min_safety_stock)
    
    def _calculate_optimal_order_quantity(self, product, demand_data):
        """Calculate optimal order quantity using EOQ model"""
        # Annual demand
        annual_demand = demand_data['next_30_days'] * 12  # Approximate annual demand
        
        if annual_demand == 0:
            return product.reordering_max_qty or 1
        
        # Ordering cost (estimated)
        ordering_cost = 50  # Default ordering cost
        
        # Holding cost (estimated as 20% of product cost per year)
        holding_cost = product.standard_price * 0.2
        
        if holding_cost == 0:
            return product.reordering_max_qty or annual_demand / 12
        
        # EOQ formula: √(2 * D * S / H)
        eoq = ((2 * annual_demand * ordering_cost) / holding_cost) ** 0.5
        
        # Ensure minimum order quantity
        if product.seller_ids:
            min_qty = product.seller_ids[0].min_qty
            eoq = max(eoq, min_qty)
        
        # Ensure maximum order quantity
        if product.reordering_max_qty:
            eoq = min(eoq, product.reordering_max_qty)
        
        return round(eoq, 2)
    
    def _create_automatic_reorder_requisition(self, reorder_analysis):
        """Create automatic requisition for reorder"""
        product = self.env['product.product'].browse(reorder_analysis['product_id'])
        
        requisition_vals = {
            'name': f"AUTO-REORDER-{product.default_code}-{fields.Date.today().strftime('%Y%m%d')}",
            'requisition_type': 'production_material',
            'production_stage': 'raw_material',
            'priority': reorder_analysis['urgency'],
            'urgency_level': 'routine',
            'required_date': fields.Datetime.now() + timedelta(days=3),
            'reason': f'Automatic reorder based on dynamic reorder point analysis',
            'auto_generated': True,
            'source_document': 'MRP Auto-Reorder',
            'notes': f"Current stock: {reorder_analysis['current_stock']}, "
                    f"Reorder point: {reorder_analysis['reorder_point']:.2f}, "
                    f"Safety stock: {reorder_analysis['safety_stock']:.2f}"
        }
        
        requisition = self.env['manufacturing.material.requisition'].create(requisition_vals)
        
        # Create requisition line
        line_vals = {
            'requisition_id': requisition.id,
            'product_id': reorder_analysis['product_id'],
            'qty_required': reorder_analysis['suggested_qty'],
            'required_date': requisition.required_date,
            'reason': 'Automatic reorder based on manufacturing demand analysis',
            'estimated_cost': product.standard_price * reorder_analysis['suggested_qty']
        }
        
        line = self.env['manufacturing.material.requisition.line'].create(line_vals)
        
        # Auto-select supplier
        if product.seller_ids:
            best_seller = product.seller_ids[0]
            line.write({
                'vendor_id': best_seller.partner_id.id,
                'vendor_price': best_seller.price,
                'vendor_lead_time': best_seller.delay,
                'unit_price': best_seller.price
            })
        
        return requisition


class MRPAnalysisLog(models.Model):
    _name = 'mrp.analysis.log'
    _description = 'MRP Analysis Log'
    _order = 'analysis_date desc'

    production_id = fields.Many2one('mrp.production', 'Production Order', required=True)
    requisition_id = fields.Many2one('manufacturing.material.requisition', 'Generated Requisition')
    analysis_date = fields.Datetime('Analysis Date', required=True)
    shortages_count = fields.Integer('Number of Shortages')
    total_shortage_cost = fields.Float('Total Shortage Cost')
    critical_path_impact = fields.Boolean('Critical Path Impact')
    suggested_actions = fields.Text('Suggested Actions')
    analysis_data = fields.Text('Full Analysis Data')  # JSON data 