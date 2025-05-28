# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class QualityIntegration(models.Model):
    _name = 'manufacturing.quality.integration'
    _description = 'Manufacturing Quality Integration'
    _order = 'create_date desc'

    name = fields.Char('Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    
    # Requisition Link
    requisition_id = fields.Many2one('manufacturing.requisition', 'Requisition', required=True, ondelete='cascade')
    
    # Product and Quality Requirements
    product_id = fields.Many2one('product.product', 'Product', related='requisition_id.product_id', store=True)
    quality_required = fields.Boolean('Quality Control Required', compute='_compute_quality_required', store=True)
    quality_level = fields.Selection([
        ('basic', 'Basic Inspection'),
        ('standard', 'Standard Quality Control'),
        ('advanced', 'Advanced Testing'),
        ('critical', 'Critical Component Testing')
    ], string='Quality Level', default='standard')
    
    # Quality Points
    quality_point_ids = fields.Many2many('quality.point', string='Quality Control Points')
    quality_check_ids = fields.One2many('quality.check', 'quality_integration_id', 'Quality Checks')
    
    # Inspection Requirements
    incoming_inspection_required = fields.Boolean('Incoming Inspection Required', default=True)
    certificate_required = fields.Boolean('Certificate Required', default=False)
    batch_testing_required = fields.Boolean('Batch Testing Required', default=False)
    vendor_audit_required = fields.Boolean('Vendor Audit Required', default=False)
    
    # Quality Status
    quality_status = fields.Selection([
        ('pending', 'Pending Inspection'),
        ('in_progress', 'Inspection in Progress'),
        ('passed', 'Quality Passed'),
        ('failed', 'Quality Failed'),
        ('conditional', 'Conditional Approval'),
        ('exempted', 'Quality Exempted')
    ], string='Quality Status', default='pending', tracking=True)
    
    # Quality Results
    overall_quality_score = fields.Float('Overall Quality Score', default=0.0)
    quality_grade = fields.Selection([
        ('A', 'Grade A - Excellent'),
        ('B', 'Grade B - Good'),
        ('C', 'Grade C - Acceptable'),
        ('D', 'Grade D - Poor'),
        ('F', 'Grade F - Failed')
    ], string='Quality Grade')
    
    # Inspection Details
    inspector_id = fields.Many2one('res.users', 'Quality Inspector')
    inspection_date = fields.Datetime('Inspection Date')
    inspection_deadline = fields.Datetime('Inspection Deadline')
    inspection_notes = fields.Text('Inspection Notes')
    
    # Certificates and Documentation
    certificate_ids = fields.One2many('manufacturing.quality.certificate', 'quality_integration_id', 'Certificates')
    test_report_ids = fields.One2many('manufacturing.quality.test.report', 'quality_integration_id', 'Test Reports')
    
    # Non-Conformance
    non_conformance_ids = fields.One2many('manufacturing.quality.non.conformance', 'quality_integration_id', 'Non-Conformances')
    corrective_action_required = fields.Boolean('Corrective Action Required', default=False)
    
    # Vendor Quality
    vendor_id = fields.Many2one('res.partner', 'Vendor', related='requisition_id.vendor_id', store=True)
    vendor_quality_rating = fields.Float('Vendor Quality Rating', compute='_compute_vendor_quality_rating')
    vendor_certification_status = fields.Selection([
        ('certified', 'Certified Vendor'),
        ('approved', 'Approved Vendor'),
        ('conditional', 'Conditional Approval'),
        ('not_approved', 'Not Approved')
    ], string='Vendor Certification Status')
    
    # Quality Costs
    inspection_cost = fields.Float('Inspection Cost')
    testing_cost = fields.Float('Testing Cost')
    certification_cost = fields.Float('Certification Cost')
    total_quality_cost = fields.Float('Total Quality Cost', compute='_compute_total_quality_cost')
    
    # Approval and Workflow
    quality_approval_required = fields.Boolean('Quality Approval Required', default=True)
    quality_approved_by = fields.Many2one('res.users', 'Quality Approved By')
    quality_approval_date = fields.Datetime('Quality Approval Date')
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('manufacturing.quality.integration') or _('New')
        return super(QualityIntegration, self).create(vals)
    
    @api.depends('product_id')
    def _compute_quality_required(self):
        for record in self:
            if record.product_id:
                # Check if product has quality control requirements
                quality_points = self.env['quality.point'].search([
                    ('product_ids', 'in', record.product_id.id)
                ])
                record.quality_required = bool(quality_points)
                
                # Set quality points
                record.quality_point_ids = [(6, 0, quality_points.ids)]
            else:
                record.quality_required = False
    
    @api.depends('vendor_id')
    def _compute_vendor_quality_rating(self):
        for record in self:
            if record.vendor_id:
                # Calculate vendor quality rating based on historical data
                past_integrations = self.search([
                    ('vendor_id', '=', record.vendor_id.id),
                    ('quality_status', 'in', ['passed', 'failed']),
                    ('id', '!=', record.id)
                ], limit=20)
                
                if past_integrations:
                    passed_count = len(past_integrations.filtered(lambda x: x.quality_status == 'passed'))
                    total_count = len(past_integrations)
                    record.vendor_quality_rating = (passed_count / total_count) * 10
                else:
                    record.vendor_quality_rating = 5.0  # Default rating
            else:
                record.vendor_quality_rating = 0.0
    
    @api.depends('inspection_cost', 'testing_cost', 'certification_cost')
    def _compute_total_quality_cost(self):
        for record in self:
            record.total_quality_cost = record.inspection_cost + record.testing_cost + record.certification_cost
    
    def action_start_quality_inspection(self):
        """Start quality inspection process"""
        if not self.quality_required:
            self.quality_status = 'exempted'
            return True
        
        self.quality_status = 'in_progress'
        self.inspection_date = fields.Datetime.now()
        
        # Create quality checks based on quality points
        for quality_point in self.quality_point_ids:
            self._create_quality_check(quality_point)
        
        # Set inspection deadline
        if not self.inspection_deadline:
            self.inspection_deadline = fields.Datetime.now() + timedelta(days=2)
        
        return True
    
    def _create_quality_check(self, quality_point):
        """Create quality check for a quality point"""
        check_vals = {
            'quality_point_id': quality_point.id,
            'product_id': self.product_id.id,
            'lot_id': False,  # Will be set when lot is available
            'quality_integration_id': self.id,
            'user_id': self.inspector_id.id if self.inspector_id else self.env.user.id,
        }
        
        return self.env['quality.check'].create(check_vals)
    
    def action_complete_inspection(self):
        """Complete quality inspection"""
        # Check if all quality checks are completed
        pending_checks = self.quality_check_ids.filtered(lambda x: x.quality_state not in ['pass', 'fail'])
        
        if pending_checks:
            raise UserError(_('Please complete all quality checks before finishing inspection'))
        
        # Calculate overall quality score
        self._calculate_quality_score()
        
        # Determine quality status
        failed_checks = self.quality_check_ids.filtered(lambda x: x.quality_state == 'fail')
        
        if failed_checks:
            self.quality_status = 'failed'
            self._create_non_conformance(failed_checks)
        else:
            self.quality_status = 'passed'
        
        # Update requisition status
        if self.quality_status == 'passed':
            self.requisition_id.quality_approved = True
        else:
            self.requisition_id.quality_approved = False
        
        return True
    
    def _calculate_quality_score(self):
        """Calculate overall quality score"""
        if not self.quality_check_ids:
            self.overall_quality_score = 0.0
            return
        
        total_score = 0
        total_weight = 0
        
        for check in self.quality_check_ids:
            weight = 1.0  # Default weight
            if check.quality_point_id.test_type == 'measure':
                # For measurement checks, calculate score based on tolerance
                if check.measure and check.quality_point_id.norm_unit:
                    tolerance = check.quality_point_id.tolerance_max - check.quality_point_id.tolerance_min
                    if tolerance > 0:
                        deviation = abs(check.measure - ((check.quality_point_id.tolerance_max + check.quality_point_id.tolerance_min) / 2))
                        score = max(0, 10 - (deviation / tolerance * 10))
                    else:
                        score = 10 if check.quality_state == 'pass' else 0
                else:
                    score = 10 if check.quality_state == 'pass' else 0
            else:
                # For pass/fail checks
                score = 10 if check.quality_state == 'pass' else 0
            
            total_score += score * weight
            total_weight += weight
        
        if total_weight > 0:
            self.overall_quality_score = total_score / total_weight
        else:
            self.overall_quality_score = 0.0
        
        # Set quality grade
        if self.overall_quality_score >= 9:
            self.quality_grade = 'A'
        elif self.overall_quality_score >= 7:
            self.quality_grade = 'B'
        elif self.overall_quality_score >= 5:
            self.quality_grade = 'C'
        elif self.overall_quality_score >= 3:
            self.quality_grade = 'D'
        else:
            self.quality_grade = 'F'
    
    def _create_non_conformance(self, failed_checks):
        """Create non-conformance record for failed checks"""
        for check in failed_checks:
            nc_vals = {
                'quality_integration_id': self.id,
                'quality_check_id': check.id,
                'product_id': self.product_id.id,
                'vendor_id': self.vendor_id.id,
                'description': f'Quality check failed: {check.quality_point_id.title}',
                'severity': self._determine_severity(check),
                'corrective_action_required': True,
            }
            
            self.env['manufacturing.quality.non.conformance'].create(nc_vals)
        
        self.corrective_action_required = True
    
    def _determine_severity(self, quality_check):
        """Determine severity of non-conformance"""
        if quality_check.quality_point_id.test_type == 'measure':
            return 'medium'
        else:
            return 'high'
    
    def action_approve_quality(self):
        """Approve quality for the requisition"""
        if self.quality_status != 'passed':
            raise UserError(_('Quality must pass before approval'))
        
        self.quality_approved_by = self.env.user
        self.quality_approval_date = fields.Datetime.now()
        
        # Update requisition
        self.requisition_id.quality_approved = True
        
        return True
    
    def action_reject_quality(self):
        """Reject quality for the requisition"""
        self.quality_status = 'failed'
        self.requisition_id.quality_approved = False
        
        return True
    
    def action_request_certificate(self):
        """Request quality certificate from vendor"""
        if not self.vendor_id:
            raise UserError(_('No vendor specified for certificate request'))
        
        # Create certificate request
        cert_vals = {
            'quality_integration_id': self.id,
            'certificate_type': 'vendor_certificate',
            'requested_date': fields.Datetime.now(),
            'vendor_id': self.vendor_id.id,
            'status': 'requested',
        }
        
        self.env['manufacturing.quality.certificate'].create(cert_vals)
        
        # Send email to vendor
        self._send_certificate_request_email()
        
        return True
    
    def _send_certificate_request_email(self):
        """Send certificate request email to vendor"""
        template = self.env.ref('manufacturing_material_requisitions.email_template_certificate_request', raise_if_not_found=False)
        if template and self.vendor_id:
            template.send_mail(self.id, force_send=True)
    
    def action_view_quality_checks(self):
        """View quality checks"""
        action = self.env.ref('quality_control.quality_check_action_main').read()[0]
        action['domain'] = [('quality_integration_id', '=', self.id)]
        action['context'] = {'default_quality_integration_id': self.id}
        return action
    
    def action_view_certificates(self):
        """View certificates"""
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Quality Certificates',
            'res_model': 'manufacturing.quality.certificate',
            'view_mode': 'tree,form',
            'domain': [('quality_integration_id', '=', self.id)],
            'context': {'default_quality_integration_id': self.id}
        }
        return action

class QualityCheckExtension(models.Model):
    _inherit = 'quality.check'
    
    quality_integration_id = fields.Many2one('manufacturing.quality.integration', 'Quality Integration')

class QualityCertificate(models.Model):
    _name = 'manufacturing.quality.certificate'
    _description = 'Quality Certificate'
    _order = 'create_date desc'

    name = fields.Char('Certificate Number', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    quality_integration_id = fields.Many2one('manufacturing.quality.integration', 'Quality Integration', required=True, ondelete='cascade')
    
    certificate_type = fields.Selection([
        ('vendor_certificate', 'Vendor Certificate'),
        ('test_certificate', 'Test Certificate'),
        ('compliance_certificate', 'Compliance Certificate'),
        ('material_certificate', 'Material Certificate')
    ], string='Certificate Type', required=True)
    
    vendor_id = fields.Many2one('res.partner', 'Vendor')
    product_id = fields.Many2one('product.product', 'Product', related='quality_integration_id.product_id')
    
    status = fields.Selection([
        ('requested', 'Requested'),
        ('received', 'Received'),
        ('verified', 'Verified'),
        ('expired', 'Expired'),
        ('rejected', 'Rejected')
    ], string='Status', default='requested', tracking=True)
    
    requested_date = fields.Datetime('Requested Date')
    received_date = fields.Datetime('Received Date')
    expiry_date = fields.Date('Expiry Date')
    
    certificate_file = fields.Binary('Certificate File')
    certificate_filename = fields.Char('Certificate Filename')
    
    notes = fields.Text('Notes')
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('manufacturing.quality.certificate') or _('New')
        return super(QualityCertificate, self).create(vals)

class QualityTestReport(models.Model):
    _name = 'manufacturing.quality.test.report'
    _description = 'Quality Test Report'
    _order = 'create_date desc'

    name = fields.Char('Report Number', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    quality_integration_id = fields.Many2one('manufacturing.quality.integration', 'Quality Integration', required=True, ondelete='cascade')
    
    test_type = fields.Selection([
        ('dimensional', 'Dimensional Testing'),
        ('material', 'Material Testing'),
        ('functional', 'Functional Testing'),
        ('environmental', 'Environmental Testing'),
        ('safety', 'Safety Testing')
    ], string='Test Type', required=True)
    
    test_date = fields.Datetime('Test Date', default=fields.Datetime.now)
    tester_id = fields.Many2one('res.users', 'Tester', default=lambda self: self.env.user)
    
    test_results = fields.Text('Test Results')
    test_conclusion = fields.Selection([
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('conditional', 'Conditional Pass')
    ], string='Test Conclusion')
    
    test_file = fields.Binary('Test Report File')
    test_filename = fields.Char('Test Report Filename')
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('manufacturing.quality.test.report') or _('New')
        return super(QualityTestReport, self).create(vals)

class QualityNonConformance(models.Model):
    _name = 'manufacturing.quality.non.conformance'
    _description = 'Quality Non-Conformance'
    _order = 'create_date desc'

    name = fields.Char('NC Number', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    quality_integration_id = fields.Many2one('manufacturing.quality.integration', 'Quality Integration', required=True, ondelete='cascade')
    quality_check_id = fields.Many2one('quality.check', 'Quality Check')
    
    product_id = fields.Many2one('product.product', 'Product', required=True)
    vendor_id = fields.Many2one('res.partner', 'Vendor')
    
    description = fields.Text('Description', required=True)
    severity = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ], string='Severity', required=True)
    
    status = fields.Selection([
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('corrective_action', 'Corrective Action'),
        ('closed', 'Closed')
    ], string='Status', default='open', tracking=True)
    
    root_cause = fields.Text('Root Cause Analysis')
    corrective_action = fields.Text('Corrective Action')
    corrective_action_required = fields.Boolean('Corrective Action Required', default=True)
    
    responsible_id = fields.Many2one('res.users', 'Responsible Person')
    due_date = fields.Date('Due Date')
    closure_date = fields.Date('Closure Date')
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('manufacturing.quality.non.conformance') or _('New')
        return super(QualityNonConformance, self).create(vals) 