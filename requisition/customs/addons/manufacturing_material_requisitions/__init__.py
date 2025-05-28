from . import models
from . import controllers
from . import wizards
from . import reports

def post_init_hook(cr, registry):
    """Post-installation hook to set up initial data and configurations"""
    from odoo import api, SUPERUSER_ID
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Create default manufacturing requisition categories
    categories = [
        {'name': 'Raw Materials', 'code': 'RAW', 'sequence': 10},
        {'name': 'Components', 'code': 'COMP', 'sequence': 20},
        {'name': 'Consumables', 'code': 'CONS', 'sequence': 30},
        {'name': 'Maintenance Parts', 'code': 'MAINT', 'sequence': 40},
        {'name': 'Tooling', 'code': 'TOOL', 'sequence': 50},
        {'name': 'Safety Equipment', 'code': 'SAFE', 'sequence': 60},
        {'name': 'Quality Control', 'code': 'QC', 'sequence': 70},
    ]
    
    for cat_data in categories:
        existing = env['manufacturing.requisition.category'].search([('code', '=', cat_data['code'])])
        if not existing:
            env['manufacturing.requisition.category'].create(cat_data)
    
    # Set up default approval workflows
    env['manufacturing.requisition.workflow'].setup_default_workflows()
    
    # Initialize AI models if available
    try:
        env['manufacturing.requisition.ai'].initialize_models()
    except Exception:
        pass  # AI features are optional

def uninstall_hook(cr, registry):
    """Clean up hook when module is uninstalled"""
    from odoo import api, SUPERUSER_ID
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Clean up any scheduled jobs
    crons = env['ir.cron'].search([
        ('model_id.model', 'like', 'manufacturing.requisition%')
    ])
    crons.unlink()
    
    # Clean up any webhook configurations
    webhooks = env['webhook.endpoint'].search([
        ('trigger', 'like', 'manufacturing.requisition%')
    ])
    webhooks.unlink() 