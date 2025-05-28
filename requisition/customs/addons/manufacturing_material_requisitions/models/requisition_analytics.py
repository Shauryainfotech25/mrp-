# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class RequisitionAnalytics(models.Model):
    _name = 'manufacturing.requisition.analytics'
    _description = 'Manufacturing Requisition Analytics'
    _auto = False
    _order = 'requisition_date desc'

    # Basic Information
    requisition_id = fields.Many2one('manufacturing.requisition', 'Requisition', readonly=True)
    requisition_date = fields.Date('Requisition Date', readonly=True)
    completion_date = fields.Date('Completion Date', readonly=True)
    
    # Product and Category
    product_id = fields.Many2one('product.product', 'Product', readonly=True)
    product_category_id = fields.Many2one('product.category', 'Product Category', readonly=True)
    
    # Quantities and Costs
    quantity_required = fields.Float('Quantity Required', readonly=True)
    quantity_received = fields.Float('Quantity Received', readonly=True)
    unit_cost = fields.Float('Unit Cost', readonly=True)
    total_cost = fields.Float('Total Cost', readonly=True)
    
    # Timing Metrics
    processing_time_days = fields.Float('Processing Time (Days)', readonly=True)
    approval_time_days = fields.Float('Approval Time (Days)', readonly=True)
    delivery_time_days = fields.Float('Delivery Time (Days)', readonly=True)
    total_cycle_time = fields.Float('Total Cycle Time (Days)', readonly=True)
    
    # Status and Type
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('purchase_order_created', 'Purchase Order Created'),
        ('received', 'Received'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], string='Status', readonly=True)
    
    requisition_type = fields.Selection([
        ('production', 'Production'),
        ('maintenance', 'Maintenance'),
        ('quality', 'Quality Control'),
        ('emergency', 'Emergency'),
        ('auto_reorder', 'Auto Reorder'),
        ('shop_floor', 'Shop Floor')
    ], string='Type', readonly=True)
    
    priority = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
        ('emergency', 'Emergency')
    ], string='Priority', readonly=True)
    
    # Department and User
    department_id = fields.Many2one('hr.department', 'Department', readonly=True)
    requested_by = fields.Many2one('res.users', 'Requested By', readonly=True)
    approved_by = fields.Many2one('res.users', 'Approved By', readonly=True)
    
    # Vendor Information
    vendor_id = fields.Many2one('res.partner', 'Vendor', readonly=True)
    vendor_rating = fields.Float('Vendor Rating', readonly=True)
    
    # Manufacturing Context
    production_id = fields.Many2one('mrp.production', 'Production Order', readonly=True)
    work_center_id = fields.Many2one('mrp.workcenter', 'Work Center', readonly=True)
    equipment_id = fields.Many2one('maintenance.equipment', 'Equipment', readonly=True)
    
    # Quality Metrics
    quality_approved = fields.Boolean('Quality Approved', readonly=True)
    quality_score = fields.Float('Quality Score', readonly=True)
    
    # Performance Indicators
    on_time_delivery = fields.Boolean('On Time Delivery', readonly=True)
    budget_variance = fields.Float('Budget Variance (%)', readonly=True)
    
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    mr.id AS requisition_id,
                    DATE(mr.create_date) AS requisition_date,
                    DATE(mr.completion_date) AS completion_date,
                    mr.product_id,
                    pt.categ_id AS product_category_id,
                    mr.quantity_required,
                    mr.quantity_received,
                    mr.estimated_cost / NULLIF(mr.quantity_required, 0) AS unit_cost,
                    mr.estimated_cost AS total_cost,
                    EXTRACT(EPOCH FROM (mr.approval_date - mr.create_date)) / 86400 AS processing_time_days,
                    EXTRACT(EPOCH FROM (mr.approval_date - mr.submission_date)) / 86400 AS approval_time_days,
                    EXTRACT(EPOCH FROM (mr.completion_date - mr.approval_date)) / 86400 AS delivery_time_days,
                    EXTRACT(EPOCH FROM (mr.completion_date - mr.create_date)) / 86400 AS total_cycle_time,
                    mr.state,
                    mr.requisition_type,
                    mr.priority,
                    mr.department_id,
                    mr.requested_by,
                    mr.approved_by,
                    mr.vendor_id,
                    COALESCE(rp.supplier_rank, 0) AS vendor_rating,
                    mr.production_id,
                    mr.work_center_id,
                    mr.equipment_id,
                    mr.quality_approved,
                    COALESCE(qi.overall_quality_score, 0) AS quality_score,
                    CASE 
                        WHEN mr.required_date IS NOT NULL AND mr.completion_date IS NOT NULL 
                        THEN mr.completion_date <= mr.required_date
                        ELSE FALSE
                    END AS on_time_delivery,
                    CASE 
                        WHEN mr.budget_amount > 0 
                        THEN ((mr.estimated_cost - mr.budget_amount) / mr.budget_amount) * 100
                        ELSE 0
                    END AS budget_variance
                FROM manufacturing_requisition mr
                LEFT JOIN product_product pp ON mr.product_id = pp.id
                LEFT JOIN product_template pt ON pp.product_tmpl_id = pt.id
                LEFT JOIN res_partner rp ON mr.vendor_id = rp.id
                LEFT JOIN manufacturing_quality_integration qi ON mr.id = qi.requisition_id
                WHERE mr.create_date IS NOT NULL
            )
        """ % self._table)

class RequisitionKPI(models.Model):
    _name = 'manufacturing.requisition.kpi'
    _description = 'Manufacturing Requisition KPIs'
    _order = 'period_start desc'

    name = fields.Char('KPI Name', required=True)
    period_start = fields.Date('Period Start', required=True)
    period_end = fields.Date('Period End', required=True)
    
    # Volume Metrics
    total_requisitions = fields.Integer('Total Requisitions')
    completed_requisitions = fields.Integer('Completed Requisitions')
    cancelled_requisitions = fields.Integer('Cancelled Requisitions')
    pending_requisitions = fields.Integer('Pending Requisitions')
    
    # Performance Metrics
    average_cycle_time = fields.Float('Average Cycle Time (Days)')
    average_approval_time = fields.Float('Average Approval Time (Days)')
    on_time_delivery_rate = fields.Float('On Time Delivery Rate (%)')
    completion_rate = fields.Float('Completion Rate (%)')
    
    # Cost Metrics
    total_cost = fields.Float('Total Cost')
    average_cost_per_requisition = fields.Float('Average Cost per Requisition')
    budget_variance_avg = fields.Float('Average Budget Variance (%)')
    cost_savings = fields.Float('Cost Savings')
    
    # Quality Metrics
    quality_approval_rate = fields.Float('Quality Approval Rate (%)')
    average_quality_score = fields.Float('Average Quality Score')
    vendor_performance_score = fields.Float('Vendor Performance Score')
    
    # Emergency and Priority Metrics
    emergency_requisitions = fields.Integer('Emergency Requisitions')
    emergency_response_time = fields.Float('Emergency Response Time (Hours)')
    high_priority_completion_rate = fields.Float('High Priority Completion Rate (%)')
    
    # Department Performance
    department_id = fields.Many2one('hr.department', 'Department')
    department_efficiency_score = fields.Float('Department Efficiency Score')
    
    @api.model
    def calculate_kpis(self, period_start, period_end, department_id=None):
        """Calculate KPIs for a given period"""
        domain = [
            ('requisition_date', '>=', period_start),
            ('requisition_date', '<=', period_end)
        ]
        
        if department_id:
            domain.append(('department_id', '=', department_id))
        
        analytics = self.env['manufacturing.requisition.analytics'].search(domain)
        
        if not analytics:
            return {}
        
        # Volume Metrics
        total_requisitions = len(analytics)
        completed_requisitions = len(analytics.filtered(lambda x: x.state == 'completed'))
        cancelled_requisitions = len(analytics.filtered(lambda x: x.state == 'cancelled'))
        pending_requisitions = len(analytics.filtered(lambda x: x.state not in ['completed', 'cancelled']))
        
        # Performance Metrics
        completed_analytics = analytics.filtered(lambda x: x.total_cycle_time > 0)
        average_cycle_time = sum(completed_analytics.mapped('total_cycle_time')) / len(completed_analytics) if completed_analytics else 0
        
        approved_analytics = analytics.filtered(lambda x: x.approval_time_days > 0)
        average_approval_time = sum(approved_analytics.mapped('approval_time_days')) / len(approved_analytics) if approved_analytics else 0
        
        on_time_deliveries = len(analytics.filtered(lambda x: x.on_time_delivery))
        on_time_delivery_rate = (on_time_deliveries / total_requisitions) * 100 if total_requisitions > 0 else 0
        
        completion_rate = (completed_requisitions / total_requisitions) * 100 if total_requisitions > 0 else 0
        
        # Cost Metrics
        total_cost = sum(analytics.mapped('total_cost'))
        average_cost_per_requisition = total_cost / total_requisitions if total_requisitions > 0 else 0
        
        budget_variances = analytics.filtered(lambda x: x.budget_variance != 0).mapped('budget_variance')
        budget_variance_avg = sum(budget_variances) / len(budget_variances) if budget_variances else 0
        
        # Quality Metrics
        quality_approved_count = len(analytics.filtered(lambda x: x.quality_approved))
        quality_approval_rate = (quality_approved_count / total_requisitions) * 100 if total_requisitions > 0 else 0
        
        quality_scores = analytics.filtered(lambda x: x.quality_score > 0).mapped('quality_score')
        average_quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        # Emergency Metrics
        emergency_requisitions = len(analytics.filtered(lambda x: x.priority == 'emergency'))
        high_priority_requisitions = len(analytics.filtered(lambda x: x.priority in ['high', 'urgent', 'emergency']))
        high_priority_completed = len(analytics.filtered(lambda x: x.priority in ['high', 'urgent', 'emergency'] and x.state == 'completed'))
        high_priority_completion_rate = (high_priority_completed / high_priority_requisitions) * 100 if high_priority_requisitions > 0 else 0
        
        return {
            'total_requisitions': total_requisitions,
            'completed_requisitions': completed_requisitions,
            'cancelled_requisitions': cancelled_requisitions,
            'pending_requisitions': pending_requisitions,
            'average_cycle_time': average_cycle_time,
            'average_approval_time': average_approval_time,
            'on_time_delivery_rate': on_time_delivery_rate,
            'completion_rate': completion_rate,
            'total_cost': total_cost,
            'average_cost_per_requisition': average_cost_per_requisition,
            'budget_variance_avg': budget_variance_avg,
            'quality_approval_rate': quality_approval_rate,
            'average_quality_score': average_quality_score,
            'emergency_requisitions': emergency_requisitions,
            'high_priority_completion_rate': high_priority_completion_rate,
        }
    
    @api.model
    def generate_monthly_kpis(self):
        """Generate monthly KPIs for all departments"""
        # Get current month
        today = fields.Date.today()
        period_start = today.replace(day=1)
        period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        # Get all departments
        departments = self.env['hr.department'].search([])
        
        for department in departments:
            kpi_data = self.calculate_kpis(period_start, period_end, department.id)
            
            if kpi_data.get('total_requisitions', 0) > 0:
                kpi_vals = {
                    'name': f'Monthly KPI - {department.name} - {period_start.strftime("%B %Y")}',
                    'period_start': period_start,
                    'period_end': period_end,
                    'department_id': department.id,
                    **kpi_data
                }
                
                # Check if KPI already exists
                existing_kpi = self.search([
                    ('period_start', '=', period_start),
                    ('period_end', '=', period_end),
                    ('department_id', '=', department.id)
                ], limit=1)
                
                if existing_kpi:
                    existing_kpi.write(kpi_vals)
                else:
                    self.create(kpi_vals)
        
        # Generate overall company KPIs
        overall_kpi_data = self.calculate_kpis(period_start, period_end)
        
        if overall_kpi_data.get('total_requisitions', 0) > 0:
            overall_kpi_vals = {
                'name': f'Monthly KPI - Company - {period_start.strftime("%B %Y")}',
                'period_start': period_start,
                'period_end': period_end,
                **overall_kpi_data
            }
            
            existing_overall_kpi = self.search([
                ('period_start', '=', period_start),
                ('period_end', '=', period_end),
                ('department_id', '=', False)
            ], limit=1)
            
            if existing_overall_kpi:
                existing_overall_kpi.write(overall_kpi_vals)
            else:
                self.create(overall_kpi_vals)

class RequisitionDashboard(models.Model):
    _name = 'manufacturing.requisition.dashboard'
    _description = 'Manufacturing Requisition Dashboard'

    name = fields.Char('Dashboard Name', required=True)
    user_id = fields.Many2one('res.users', 'User', default=lambda self: self.env.user)
    department_id = fields.Many2one('hr.department', 'Department')
    
    # Dashboard Configuration
    date_range = fields.Selection([
        ('today', 'Today'),
        ('week', 'This Week'),
        ('month', 'This Month'),
        ('quarter', 'This Quarter'),
        ('year', 'This Year'),
        ('custom', 'Custom Range')
    ], string='Date Range', default='month')
    
    date_from = fields.Date('Date From')
    date_to = fields.Date('Date To')
    
    # Widget Configuration
    show_kpi_cards = fields.Boolean('Show KPI Cards', default=True)
    show_charts = fields.Boolean('Show Charts', default=True)
    show_tables = fields.Boolean('Show Tables', default=True)
    show_alerts = fields.Boolean('Show Alerts', default=True)
    
    # Computed Dashboard Data
    dashboard_data = fields.Text('Dashboard Data', compute='_compute_dashboard_data')
    
    @api.depends('date_range', 'date_from', 'date_to', 'department_id')
    def _compute_dashboard_data(self):
        for record in self:
            record.dashboard_data = record._get_dashboard_data()
    
    def _get_date_range(self):
        """Get date range based on selection"""
        today = fields.Date.today()
        
        if self.date_range == 'today':
            return today, today
        elif self.date_range == 'week':
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return start, end
        elif self.date_range == 'month':
            start = today.replace(day=1)
            end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            return start, end
        elif self.date_range == 'quarter':
            quarter = (today.month - 1) // 3 + 1
            start = today.replace(month=(quarter - 1) * 3 + 1, day=1)
            end = (start + timedelta(days=93)).replace(day=1) - timedelta(days=1)
            return start, end
        elif self.date_range == 'year':
            start = today.replace(month=1, day=1)
            end = today.replace(month=12, day=31)
            return start, end
        else:  # custom
            return self.date_from or today, self.date_to or today
    
    def _get_dashboard_data(self):
        """Get dashboard data"""
        date_from, date_to = self._get_date_range()
        
        # Get analytics data
        domain = [
            ('requisition_date', '>=', date_from),
            ('requisition_date', '<=', date_to)
        ]
        
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        
        analytics = self.env['manufacturing.requisition.analytics'].search(domain)
        
        # Calculate KPIs
        kpi_model = self.env['manufacturing.requisition.kpi']
        kpis = kpi_model.calculate_kpis(date_from, date_to, self.department_id.id if self.department_id else None)
        
        # Get trend data (last 6 months)
        trend_data = self._get_trend_data(date_from, date_to)
        
        # Get alerts
        alerts = self._get_alerts()
        
        # Get top products
        top_products = self._get_top_products(analytics)
        
        # Get vendor performance
        vendor_performance = self._get_vendor_performance(analytics)
        
        dashboard_data = {
            'kpis': kpis,
            'trend_data': trend_data,
            'alerts': alerts,
            'top_products': top_products,
            'vendor_performance': vendor_performance,
            'date_range': {
                'from': date_from.strftime('%Y-%m-%d'),
                'to': date_to.strftime('%Y-%m-%d')
            }
        }
        
        return str(dashboard_data)
    
    def _get_trend_data(self, date_from, date_to):
        """Get trend data for charts"""
        # Get monthly data for the last 6 months
        months = []
        current_date = date_to
        
        for i in range(6):
            month_start = current_date.replace(day=1)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            
            domain = [
                ('requisition_date', '>=', month_start),
                ('requisition_date', '<=', month_end)
            ]
            
            if self.department_id:
                domain.append(('department_id', '=', self.department_id.id))
            
            analytics = self.env['manufacturing.requisition.analytics'].search(domain)
            
            months.append({
                'month': month_start.strftime('%B %Y'),
                'total_requisitions': len(analytics),
                'completed_requisitions': len(analytics.filtered(lambda x: x.state == 'completed')),
                'total_cost': sum(analytics.mapped('total_cost')),
                'average_cycle_time': sum(analytics.mapped('total_cycle_time')) / len(analytics) if analytics else 0
            })
            
            # Move to previous month
            current_date = month_start - timedelta(days=1)
        
        return list(reversed(months))
    
    def _get_alerts(self):
        """Get dashboard alerts"""
        alerts = []
        
        # Check for overdue requisitions
        overdue_requisitions = self.env['manufacturing.requisition'].search([
            ('state', 'not in', ['completed', 'cancelled']),
            ('required_date', '<', fields.Date.today())
        ])
        
        if overdue_requisitions:
            alerts.append({
                'type': 'warning',
                'title': 'Overdue Requisitions',
                'message': f'{len(overdue_requisitions)} requisitions are overdue',
                'action': 'view_overdue_requisitions'
            })
        
        # Check for emergency requisitions
        emergency_requisitions = self.env['manufacturing.requisition'].search([
            ('priority', '=', 'emergency'),
            ('state', 'not in', ['completed', 'cancelled'])
        ])
        
        if emergency_requisitions:
            alerts.append({
                'type': 'danger',
                'title': 'Emergency Requisitions',
                'message': f'{len(emergency_requisitions)} emergency requisitions pending',
                'action': 'view_emergency_requisitions'
            })
        
        # Check for low stock items
        low_stock_integrations = self.env['manufacturing.inventory.integration'].search([
            ('state', 'in', ['low_stock', 'critical', 'out_of_stock'])
        ])
        
        if low_stock_integrations:
            alerts.append({
                'type': 'info',
                'title': 'Low Stock Alert',
                'message': f'{len(low_stock_integrations)} items have low stock levels',
                'action': 'view_low_stock'
            })
        
        return alerts
    
    def _get_top_products(self, analytics):
        """Get top requested products"""
        product_data = {}
        
        for record in analytics:
            if record.product_id:
                if record.product_id.id not in product_data:
                    product_data[record.product_id.id] = {
                        'product_name': record.product_id.name,
                        'quantity': 0,
                        'cost': 0,
                        'count': 0
                    }
                
                product_data[record.product_id.id]['quantity'] += record.quantity_required
                product_data[record.product_id.id]['cost'] += record.total_cost
                product_data[record.product_id.id]['count'] += 1
        
        # Sort by quantity and return top 10
        sorted_products = sorted(product_data.values(), key=lambda x: x['quantity'], reverse=True)
        return sorted_products[:10]
    
    def _get_vendor_performance(self, analytics):
        """Get vendor performance data"""
        vendor_data = {}
        
        for record in analytics.filtered(lambda x: x.vendor_id):
            if record.vendor_id.id not in vendor_data:
                vendor_data[record.vendor_id.id] = {
                    'vendor_name': record.vendor_id.name,
                    'total_orders': 0,
                    'on_time_deliveries': 0,
                    'total_cost': 0,
                    'average_quality_score': 0,
                    'quality_scores': []
                }
            
            vendor_data[record.vendor_id.id]['total_orders'] += 1
            vendor_data[record.vendor_id.id]['total_cost'] += record.total_cost
            
            if record.on_time_delivery:
                vendor_data[record.vendor_id.id]['on_time_deliveries'] += 1
            
            if record.quality_score > 0:
                vendor_data[record.vendor_id.id]['quality_scores'].append(record.quality_score)
        
        # Calculate performance metrics
        for vendor_id, data in vendor_data.items():
            data['on_time_rate'] = (data['on_time_deliveries'] / data['total_orders']) * 100 if data['total_orders'] > 0 else 0
            data['average_quality_score'] = sum(data['quality_scores']) / len(data['quality_scores']) if data['quality_scores'] else 0
            del data['quality_scores']  # Remove raw scores
        
        # Sort by on-time rate and return top 10
        sorted_vendors = sorted(vendor_data.values(), key=lambda x: x['on_time_rate'], reverse=True)
        return sorted_vendors[:10]
    
    def action_refresh_dashboard(self):
        """Refresh dashboard data"""
        self._compute_dashboard_data()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        } 