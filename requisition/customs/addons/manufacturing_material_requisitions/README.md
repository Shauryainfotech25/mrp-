# Manufacturing Material Requisitions for Odoo 18.0

## Overview

The Manufacturing Material Requisitions module is a comprehensive solution designed for Odoo.sh 18.0 that provides advanced material requisition management with deep integration into manufacturing operations. This module transforms how manufacturing organizations handle material requests, from shop floor emergency needs to planned production requirements.

## Key Features

### 🏭 Manufacturing Integration
- **Manufacturing Order Material Requisitions**: Automatic material requisition generation from production orders
- **Shop Floor Emergency Requisitions**: Real-time emergency material requests with immediate notifications
- **MRP Integration**: Seamless integration with Material Requirements Planning
- **Bill of Materials Integration**: Automatic material explosion from BOMs
- **Work Center Integration**: Material requests tied to specific work centers

### 📱 Modern User Experience
- **Progressive Web App (PWA)**: Offline-capable mobile interface for shop floor operators
- **Voice-to-Text Requisitions**: Voice command support for hands-free operation
- **Barcode Scanning**: Quick material identification and quantity entry
- **Photo Documentation**: Visual documentation for emergency situations
- **Real-time Notifications**: Instant alerts for emergency requisitions

### 🤖 AI-Powered Intelligence
- **Demand Forecasting**: Machine learning models predict material requirements
- **Cost Prediction**: AI-driven cost estimation and optimization
- **Vendor Recommendations**: Intelligent vendor selection based on performance
- **Lead Time Prediction**: Accurate delivery time estimates
- **Anomaly Detection**: Automatic identification of unusual patterns

### 📊 Advanced Analytics
- **Real-time Dashboard**: Executive and operational dashboards with KPIs
- **Performance Metrics**: Cycle time, approval time, delivery performance
- **Cost Analysis**: Multi-dimensional cost tracking and analysis
- **Trend Analysis**: Historical data analysis and forecasting
- **Department Performance**: Comparative analysis across departments

### 🔄 Comprehensive Workflow Management
- **Multi-level Approvals**: Configurable approval workflows
- **Emergency Escalation**: Automatic escalation for critical requests
- **Budget Integration**: Multi-dimensional budget tracking and control
- **Quality Control Integration**: Quality requirements and compliance tracking
- **Maintenance Integration**: Equipment maintenance material management

## Module Structure

```
manufacturing_material_requisitions/
├── __init__.py                     # Module initialization
├── __manifest__.py                 # Module manifest and dependencies
├── controllers/                    # Web controllers
│   ├── __init__.py
│   ├── main.py                    # Main dashboard controller
│   ├── api.py                     # REST API endpoints
│   ├── shop_floor.py              # Shop floor interface
│   ├── mobile.py                  # Mobile PWA controller
│   ├── portal.py                  # Customer portal integration
│   └── webhook.py                 # External system webhooks
├── models/                        # Data models
│   ├── __init__.py
│   ├── manufacturing_requisition.py      # Core requisition model
│   ├── shop_floor_requisition.py         # Emergency requisitions
│   ├── mrp_integration.py                # MRP integration
│   ├── inventory_integration.py          # Inventory integration
│   ├── purchase_integration.py           # Purchase integration
│   ├── quality_integration.py            # Quality control integration
│   ├── maintenance_integration.py        # Maintenance integration
│   ├── requisition_analytics.py          # Analytics and reporting
│   └── requisition_ai.py                 # AI/ML models
├── views/                         # User interface views
│   ├── manufacturing_requisition_views.xml
│   ├── shop_floor_requisition_views.xml
│   └── analytics_dashboard_views.xml
├── wizards/                       # Wizard interfaces
│   ├── __init__.py
│   ├── bulk_requisition_wizard.py        # Bulk creation wizard
│   ├── emergency_requisition_wizard.py   # Emergency wizard
│   ├── mrp_requisition_wizard.py         # MRP integration wizard
│   ├── vendor_selection_wizard.py        # Vendor selection
│   └── material_shortage_wizard.py       # Shortage analysis
├── data/                          # Default data
│   └── requisition_categories.xml        # Categories and templates
├── security/                      # Access control
│   └── ir.model.access.csv              # Access rights
├── static/                        # Static assets
│   ├── src/
│   │   ├── css/
│   │   │   └── manufacturing_requisitions.css
│   │   ├── js/
│   │   │   └── manufacturing_requisitions.js
│   │   └── audio/
│   │       └── emergency_alert.mp3
│   └── description/
│       ├── icon.png
│       └── banner.png
└── README.md                      # This file
```

## Installation

### Prerequisites
- Odoo 18.0 Enterprise or Community Edition
- Python packages: `requests`, `numpy`, `pandas`, `scikit-learn`
- PostgreSQL 12+ (for materialized views)

### Installation Steps

1. **Clone or download the module** to your Odoo addons directory:
   ```bash
   cd /path/to/odoo/addons
   git clone <repository-url> manufacturing_material_requisitions
   ```

2. **Install Python dependencies**:
   ```bash
   pip install requests numpy pandas scikit-learn
   ```

3. **Update the addons list** in Odoo:
   - Go to Apps → Update Apps List
   - Search for "Manufacturing Material Requisitions"
   - Click Install

4. **Configure the module**:
   - Go to Manufacturing → Configuration → Material Requisitions
   - Set up default categories, workflows, and AI models

## Configuration

### Initial Setup

1. **Product Categories**: The module creates default categories for manufacturing materials
2. **Stock Locations**: Default locations for raw materials, WIP, and finished goods
3. **Approval Workflows**: Standard, emergency, and high-value approval workflows
4. **Budget Categories**: Production, maintenance, tooling, quality, and safety budgets
5. **AI Models**: Pre-configured machine learning models for predictions

### User Groups and Permissions

The module defines several user groups:

- **Manufacturing User**: Basic requisition creation and viewing
- **Manufacturing Manager**: Full access to requisitions and approvals
- **Shop Floor Operator**: Emergency requisitions and mobile interface
- **Procurement Manager**: Purchase integration and vendor management
- **Quality Manager**: Quality control requirements and compliance

### API Configuration

For external integrations, configure API access:

1. Generate API keys for users
2. Set up webhook endpoints for real-time updates
3. Configure external system integrations

### AI Service Configuration

AI-powered features rely on external providers. Set the following environment
variables so the platform can authenticate:

1. `OPENAI_API_KEY` – OpenAI models
2. `CLAUDE_API_KEY` – Anthropic Claude models
3. `GEMINI_API_KEY` – Google Gemini models

Example configuration:

```bash
export OPENAI_API_KEY=your-openai-key
export CLAUDE_API_KEY=your-claude-key
export GEMINI_API_KEY=your-gemini-key
```

## Usage

### Creating Standard Requisitions

1. Navigate to **Manufacturing → Material Requisitions → Create**
2. Select requisition type and department
3. Add material lines with quantities and requirements
4. Submit for approval workflow

### Emergency Requisitions

1. Use the **Emergency Button** on shop floor interface
2. Select machine and describe the issue
3. Add required materials with photos if needed
4. System automatically escalates and notifies relevant personnel

### Bulk Requisitions

1. Go to **Manufacturing → Material Requisitions → Bulk Create**
2. Choose creation method:
   - From product list
   - From BOM explosion
   - From manufacturing orders
   - From reorder analysis
   - From template
3. Configure grouping and auto-submission options

### Analytics and Reporting

1. Access **Manufacturing → Analytics → Requisition Dashboard**
2. View real-time KPIs and performance metrics
3. Use filters for department, date range, and requisition type
4. Export data for external analysis

## API Documentation

### REST API Endpoints

The module provides comprehensive REST API access:

#### Authentication
All API calls require an API key in the header:
```
X-API-Key: your-api-key-here
```

#### Get Requisitions
```http
GET /api/v1/manufacturing/requisitions
```

Parameters:
- `limit`: Number of records (default: 50)
- `offset`: Pagination offset
- `state`: Filter by state
- `department_id`: Filter by department
- `date_from`: Start date filter
- `date_to`: End date filter

#### Create Requisition
```http
POST /api/v1/manufacturing/requisitions
```

Body:
```json
{
  "requisition_type": "production_material",
  "department_id": 1,
  "required_date": "2024-01-15T10:00:00Z",
  "reason": "Production line startup",
  "lines": [
    {
      "product_id": 123,
      "qty_required": 10.0,
      "vendor_id": 456
    }
  ]
}
```

#### Emergency Requisition
```http
POST /api/v1/shop_floor/emergency
```

Body:
```json
{
  "machine_id": 789,
  "materials": [
    {
      "product_id": 123,
      "quantity": 5.0
    }
  ],
  "production_impact": "Line stoppage - critical"
}
```

### WebSocket Integration

Real-time updates are available via WebSocket:
```javascript
const ws = new WebSocket('ws://your-domain/manufacturing/websocket');
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    // Handle real-time updates
};
```

## AI and Machine Learning

### Demand Forecasting

The module includes several AI models:

1. **Linear Regression**: Basic demand prediction
2. **Random Forest**: Complex pattern recognition
3. **Gradient Boosting**: Advanced time series forecasting

### Model Training

Models are automatically retrained based on:
- Historical requisition data
- Seasonal patterns
- Production schedules
- External factors

### Accuracy Monitoring

- Models track prediction accuracy
- Automatic retraining when accuracy drops
- Performance metrics in analytics dashboard

## Mobile and PWA Features

### Progressive Web App

The module includes a PWA for offline functionality:

- **Offline Mode**: Create requisitions without internet
- **Background Sync**: Automatic sync when connection restored
- **Push Notifications**: Real-time alerts on mobile devices
- **App-like Experience**: Install on mobile home screen

### Voice Commands

Supported voice commands:
- "Emergency requisition for machine 5"
- "Request 10 units of part ABC123"
- "Check inventory status"
- "Show pending approvals"

### Barcode Scanning

- Product identification via barcode
- Quantity entry with scanner
- Batch processing for multiple items
- Integration with warehouse management

## Integration Points

### Manufacturing (MRP)

- Automatic requisition from production orders
- Material shortage analysis
- Work center material requirements
- Production schedule integration

### Inventory Management

- Real-time stock level monitoring
- Automatic reorder point triggers
- Location-based availability
- Reservation and allocation

### Purchase Management

- Automatic vendor selection
- RFQ generation
- Purchase order creation
- Delivery tracking

### Quality Control

- Quality requirements specification
- Inspection process integration
- Certificate tracking
- Non-conformance management

### Maintenance

- Equipment maintenance materials
- Spare parts management
- Downtime tracking
- Preventive maintenance scheduling

## Performance Optimization

### Database Optimization

- Materialized views for analytics
- Proper indexing on frequently queried fields
- Partitioning for large datasets
- Query optimization

### Caching Strategy

- Redis caching for frequently accessed data
- Session-based caching for user preferences
- API response caching
- Static asset optimization

### Scalability Features

- Horizontal scaling support
- Load balancing compatibility
- Database read replicas
- CDN integration for static assets

## Security Features

### Data Protection

- Field-level encryption for sensitive data
- Audit logging for all changes
- Role-based access control
- API rate limiting

### Compliance

- GDPR compliance features
- Data retention policies
- Export/import controls
- Audit trail maintenance

## Troubleshooting

### Common Issues

1. **AI Models Not Training**
   - Check data availability (minimum 30 days)
   - Verify Python dependencies
   - Check system resources

2. **WebSocket Connection Issues**
   - Verify proxy configuration
   - Check firewall settings
   - Ensure WebSocket support

3. **Mobile PWA Not Working**
   - Check HTTPS configuration
   - Verify service worker registration
   - Clear browser cache

### Debug Mode

Enable debug mode for detailed logging:
```python
_logger.setLevel(logging.DEBUG)
```

### Performance Monitoring

Monitor performance with:
- Database query analysis
- API response times
- Memory usage tracking
- User session monitoring

## Support and Maintenance

### Regular Maintenance

- Weekly AI model retraining
- Monthly performance optimization
- Quarterly security updates
- Annual feature reviews

### Backup Strategy

- Daily database backups
- Configuration file backups
- AI model checkpoints
- Static asset backups

### Monitoring

- System health checks
- Performance metrics
- Error rate monitoring
- User activity tracking

## Contributing

### Development Guidelines

1. Follow Odoo development standards
2. Include comprehensive tests
3. Document all new features
4. Maintain backward compatibility

### Testing

Run tests with:
```bash
python -m pytest tests/
```

### Code Quality

- Use pylint for code analysis
- Follow PEP 8 style guidelines
- Include type hints
- Write comprehensive docstrings

## License

This module is licensed under LGPL-3.0. See LICENSE file for details.

## Changelog

### Version 1.0.0 (2024-01-01)
- Initial release
- Core requisition functionality
- Manufacturing integration
- AI-powered recommendations
- Mobile PWA interface
- Comprehensive analytics

### Version 1.1.0 (Planned)
- Enhanced AI models
- Additional integrations
- Performance improvements
- Extended API functionality

## Support

For support and questions:
- Email: support@example.com
- Documentation: https://docs.example.com
- Community Forum: https://community.example.com
- GitHub Issues: https://github.com/example/manufacturing-requisitions

---

**Manufacturing Material Requisitions** - Transforming manufacturing material management with intelligent automation and real-time insights. 