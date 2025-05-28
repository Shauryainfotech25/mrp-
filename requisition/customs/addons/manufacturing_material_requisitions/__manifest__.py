{
    'name': 'Manufacturing Material Requisitions',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Advanced Material Purchase Requisitions for Manufacturing Operations',
    'description': """
        Manufacturing-Integrated Material Purchase Requisitions for Odoo 18.0
        
        Features:
        - Manufacturing Order Material Requisitions
        - Shop Floor Emergency Requisitions
        - MRP Integration with Auto-Requisitions
        - Quality Control Material Management
        - Maintenance Material Requisitions
        - Real-time Inventory Integration
        - AI-Powered Demand Forecasting
        - Mobile Shop Floor App (PWA)
        - Advanced Analytics Dashboard
        - Multi-location Manufacturing Support
    """,
    'author': 'Manufacturing Solutions Team',
    'website': 'https://www.odoo.com',
    'depends': [
        'base',
        'web',
        'mail',
        'mrp',
        'stock',
        'purchase',
        'maintenance',
        'quality_control',
        'hr',
        'account',
        'project',
        'fleet',
        'website',
        'portal',
        'calendar',
        'contacts',
        'product',
        'uom',
        'decimal_precision',
        'resource',
        'barcodes',
        'web_mobile',
        'mrp_workorder',
        'mrp_plm',
        'quality_mrp',
        'stock_barcode',
        'mrp_maintenance',
        'purchase_mrp',
        'stock_picking_batch',
        'mrp_subcontracting',
        'quality_control_worksheet'
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/sequence_data.xml',
        'data/mail_template_data.xml',
        'data/cron_data.xml',
        'data/manufacturing_data.xml',
        
        # Views
        'views/manufacturing_requisition_views.xml',
        'views/shop_floor_requisition_views.xml',
        'views/mrp_integration_views.xml',
        'views/quality_requisition_views.xml',
        'views/maintenance_requisition_views.xml',
        'views/requisition_dashboard_views.xml',
        'views/inventory_integration_views.xml',
        'views/purchase_integration_views.xml',
        'views/analytics_views.xml',
        'views/mobile_views.xml',
        
        # Reports
        'reports/manufacturing_requisition_reports.xml',
        'reports/shop_floor_reports.xml',
        'reports/analytics_reports.xml',
        
        # Wizards
        'wizards/bulk_requisition_wizard.xml',
        'wizards/emergency_requisition_wizard.xml',
        'wizards/mrp_requisition_wizard.xml',
        
        # Menu
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'manufacturing_material_requisitions/static/src/css/manufacturing_requisition.css',
            'manufacturing_material_requisitions/static/src/css/shop_floor.css',
            'manufacturing_material_requisitions/static/src/css/dashboard.css',
            'manufacturing_material_requisitions/static/src/js/manufacturing_requisition.js',
            'manufacturing_material_requisitions/static/src/js/shop_floor_app.js',
            'manufacturing_material_requisitions/static/src/js/dashboard.js',
            'manufacturing_material_requisitions/static/src/js/barcode_scanner.js',
            'manufacturing_material_requisitions/static/src/js/real_time_updates.js',
            'manufacturing_material_requisitions/static/src/xml/manufacturing_templates.xml',
            'manufacturing_material_requisitions/static/src/xml/shop_floor_templates.xml',
        ],
        'web.assets_frontend': [
            'manufacturing_material_requisitions/static/src/css/portal.css',
            'manufacturing_material_requisitions/static/src/js/portal.js',
        ],
        'web.assets_qweb': [
            'manufacturing_material_requisitions/static/src/xml/**/*',
        ],
    },
    'demo': [
        'demo/manufacturing_demo.xml',
        'demo/shop_floor_demo.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': ['requests', 'numpy', 'pandas', 'scikit-learn'],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
} 