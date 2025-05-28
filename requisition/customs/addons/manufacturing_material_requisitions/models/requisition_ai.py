# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging
import json

_logger = logging.getLogger(__name__)

try:
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    _logger.warning("Machine learning libraries not available. AI features will be limited.")

class RequisitionAI(models.Model):
    _name = 'manufacturing.requisition.ai'
    _description = 'Manufacturing Requisition AI Engine'
    _order = 'create_date desc'

    name = fields.Char('AI Model Name', required=True)
    model_type = fields.Selection([
        ('demand_forecast', 'Demand Forecasting'),
        ('cost_prediction', 'Cost Prediction'),
        ('vendor_recommendation', 'Vendor Recommendation'),
        ('lead_time_prediction', 'Lead Time Prediction'),
        ('quality_prediction', 'Quality Prediction'),
        ('anomaly_detection', 'Anomaly Detection')
    ], string='Model Type', required=True)
    
    # Model Configuration
    algorithm = fields.Selection([
        ('linear_regression', 'Linear Regression'),
        ('random_forest', 'Random Forest'),
        ('neural_network', 'Neural Network'),
        ('time_series', 'Time Series Analysis')
    ], string='Algorithm', default='random_forest')
    
    # Training Data
    training_data_from = fields.Date('Training Data From', default=lambda self: fields.Date.today() - timedelta(days=365))
    training_data_to = fields.Date('Training Data To', default=fields.Date.today)
    training_records_count = fields.Integer('Training Records Count', readonly=True)
    
    # Model Performance
    accuracy_score = fields.Float('Accuracy Score (%)', readonly=True)
    mae_score = fields.Float('Mean Absolute Error', readonly=True)
    rmse_score = fields.Float('Root Mean Square Error', readonly=True)
    last_training_date = fields.Datetime('Last Training Date', readonly=True)
    
    # Model Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('training', 'Training'),
        ('trained', 'Trained'),
        ('active', 'Active'),
        ('error', 'Error')
    ], string='Status', default='draft', tracking=True)
    
    # Model Data
    model_data = fields.Text('Model Data (JSON)', readonly=True)
    feature_importance = fields.Text('Feature Importance (JSON)', readonly=True)
    training_log = fields.Text('Training Log', readonly=True)
    
    # Predictions
    prediction_ids = fields.One2many('manufacturing.requisition.ai.prediction', 'ai_model_id', 'Predictions')
    
    @api.model
    def create(self, vals):
        if not ML_AVAILABLE:
            raise UserError(_('Machine learning libraries are not available. Please install scikit-learn, numpy, and pandas.'))
        return super(RequisitionAI, self).create(vals)
    
    def action_train_model(self):
        """Train the AI model"""
        if not ML_AVAILABLE:
            raise UserError(_('Machine learning libraries are not available.'))
        
        self.state = 'training'
        
        try:
            if self.model_type == 'demand_forecast':
                self._train_demand_forecast_model()
            elif self.model_type == 'cost_prediction':
                self._train_cost_prediction_model()
            elif self.model_type == 'vendor_recommendation':
                self._train_vendor_recommendation_model()
            elif self.model_type == 'lead_time_prediction':
                self._train_lead_time_prediction_model()
            elif self.model_type == 'quality_prediction':
                self._train_quality_prediction_model()
            elif self.model_type == 'anomaly_detection':
                self._train_anomaly_detection_model()
            
            self.state = 'trained'
            self.last_training_date = fields.Datetime.now()
            
        except Exception as e:
            self.state = 'error'
            self.training_log = f"Training failed: {str(e)}"
            _logger.error(f"AI model training failed: {str(e)}")
            raise UserError(_('Model training failed: %s') % str(e))
        
        return True
    
    def _get_training_data(self):
        """Get training data for the model"""
        # Get requisition analytics data
        analytics = self.env['manufacturing.requisition.analytics'].search([
            ('requisition_date', '>=', self.training_data_from),
            ('requisition_date', '<=', self.training_data_to),
            ('state', '=', 'completed')
        ])
        
        if not analytics:
            raise UserError(_('No training data available for the specified period.'))
        
        self.training_records_count = len(analytics)
        
        # Convert to pandas DataFrame
        data = []
        for record in analytics:
            data.append({
                'product_id': record.product_id.id,
                'product_category_id': record.product_category_id.id,
                'quantity_required': record.quantity_required,
                'total_cost': record.total_cost,
                'processing_time_days': record.processing_time_days,
                'delivery_time_days': record.delivery_time_days,
                'total_cycle_time': record.total_cycle_time,
                'priority': self._encode_priority(record.priority),
                'requisition_type': self._encode_requisition_type(record.requisition_type),
                'department_id': record.department_id.id if record.department_id else 0,
                'vendor_id': record.vendor_id.id if record.vendor_id else 0,
                'vendor_rating': record.vendor_rating,
                'quality_score': record.quality_score,
                'on_time_delivery': 1 if record.on_time_delivery else 0,
                'month': record.requisition_date.month,
                'day_of_week': record.requisition_date.weekday(),
                'quarter': (record.requisition_date.month - 1) // 3 + 1,
            })
        
        return pd.DataFrame(data)
    
    def _encode_priority(self, priority):
        """Encode priority as numeric value"""
        mapping = {'low': 1, 'medium': 2, 'high': 3, 'urgent': 4, 'emergency': 5}
        return mapping.get(priority, 2)
    
    def _encode_requisition_type(self, req_type):
        """Encode requisition type as numeric value"""
        mapping = {
            'production': 1, 'maintenance': 2, 'quality': 3,
            'emergency': 4, 'auto_reorder': 5, 'shop_floor': 6
        }
        return mapping.get(req_type, 1)
    
    def _train_demand_forecast_model(self):
        """Train demand forecasting model"""
        df = self._get_training_data()
        
        # Prepare features for demand forecasting
        features = ['product_id', 'product_category_id', 'month', 'quarter', 'day_of_week', 
                   'priority', 'requisition_type', 'department_id']
        target = 'quantity_required'
        
        X = df[features]
        y = df[target]
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Train model
        if self.algorithm == 'random_forest':
            model = RandomForestRegressor(n_estimators=100, random_state=42)
        else:
            model = LinearRegression()
        
        model.fit(X_train, y_train)
        
        # Evaluate model
        y_pred = model.predict(X_test)
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        
        # Calculate accuracy (for regression, we use R² score)
        accuracy = model.score(X_test, y_test) * 100
        
        self.accuracy_score = accuracy
        self.mae_score = mae
        self.rmse_score = rmse
        
        # Store model data (simplified - in production, use proper model serialization)
        model_info = {
            'algorithm': self.algorithm,
            'features': features,
            'target': target,
            'feature_importance': model.feature_importances_.tolist() if hasattr(model, 'feature_importances_') else [],
            'training_samples': len(X_train)
        }
        
        self.model_data = json.dumps(model_info)
        
        if hasattr(model, 'feature_importances_'):
            feature_imp = dict(zip(features, model.feature_importances_))
            self.feature_importance = json.dumps(feature_imp)
        
        self.training_log = f"Model trained successfully. Accuracy: {accuracy:.2f}%, MAE: {mae:.2f}, RMSE: {rmse:.2f}"
    
    def _train_cost_prediction_model(self):
        """Train cost prediction model"""
        df = self._get_training_data()
        
        features = ['product_id', 'quantity_required', 'vendor_id', 'vendor_rating', 
                   'priority', 'requisition_type', 'delivery_time_days']
        target = 'total_cost'
        
        X = df[features].fillna(0)
        y = df[target]
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        if self.algorithm == 'random_forest':
            model = RandomForestRegressor(n_estimators=100, random_state=42)
        else:
            model = LinearRegression()
        
        model.fit(X_train, y_train)
        
        y_pred = model.predict(X_test)
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        accuracy = model.score(X_test, y_test) * 100
        
        self.accuracy_score = accuracy
        self.mae_score = mae
        self.rmse_score = rmse
        
        model_info = {
            'algorithm': self.algorithm,
            'features': features,
            'target': target,
            'feature_importance': model.feature_importances_.tolist() if hasattr(model, 'feature_importances_') else [],
        }
        
        self.model_data = json.dumps(model_info)
        self.training_log = f"Cost prediction model trained. Accuracy: {accuracy:.2f}%"
    
    def _train_vendor_recommendation_model(self):
        """Train vendor recommendation model"""
        df = self._get_training_data()
        
        # For vendor recommendation, we predict vendor performance score
        features = ['product_id', 'quantity_required', 'priority', 'delivery_time_days']
        target = 'vendor_rating'
        
        # Filter records with vendor data
        df_vendor = df[df['vendor_id'] > 0]
        
        if len(df_vendor) < 10:
            raise UserError(_('Insufficient vendor data for training.'))
        
        X = df_vendor[features]
        y = df_vendor[target]
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        y_pred = model.predict(X_test)
        mae = mean_absolute_error(y_test, y_pred)
        accuracy = model.score(X_test, y_test) * 100
        
        self.accuracy_score = accuracy
        self.mae_score = mae
        
        model_info = {
            'algorithm': 'random_forest',
            'features': features,
            'target': target,
            'feature_importance': model.feature_importances_.tolist(),
        }
        
        self.model_data = json.dumps(model_info)
        self.training_log = f"Vendor recommendation model trained. Accuracy: {accuracy:.2f}%"
    
    def _train_lead_time_prediction_model(self):
        """Train lead time prediction model"""
        df = self._get_training_data()
        
        features = ['product_id', 'quantity_required', 'vendor_id', 'priority', 'requisition_type']
        target = 'total_cycle_time'
        
        X = df[features].fillna(0)
        y = df[target]
        
        # Remove outliers (cycle time > 30 days)
        mask = y <= 30
        X = X[mask]
        y = y[mask]
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        y_pred = model.predict(X_test)
        mae = mean_absolute_error(y_test, y_pred)
        accuracy = model.score(X_test, y_test) * 100
        
        self.accuracy_score = accuracy
        self.mae_score = mae
        
        model_info = {
            'algorithm': 'random_forest',
            'features': features,
            'target': target,
            'feature_importance': model.feature_importances_.tolist(),
        }
        
        self.model_data = json.dumps(model_info)
        self.training_log = f"Lead time prediction model trained. Accuracy: {accuracy:.2f}%"
    
    def _train_quality_prediction_model(self):
        """Train quality prediction model"""
        df = self._get_training_data()
        
        # Filter records with quality data
        df_quality = df[df['quality_score'] > 0]
        
        if len(df_quality) < 10:
            raise UserError(_('Insufficient quality data for training.'))
        
        features = ['product_id', 'vendor_id', 'vendor_rating', 'total_cost', 'delivery_time_days']
        target = 'quality_score'
        
        X = df_quality[features].fillna(0)
        y = df_quality[target]
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        y_pred = model.predict(X_test)
        mae = mean_absolute_error(y_test, y_pred)
        accuracy = model.score(X_test, y_test) * 100
        
        self.accuracy_score = accuracy
        self.mae_score = mae
        
        model_info = {
            'algorithm': 'random_forest',
            'features': features,
            'target': target,
            'feature_importance': model.feature_importances_.tolist(),
        }
        
        self.model_data = json.dumps(model_info)
        self.training_log = f"Quality prediction model trained. Accuracy: {accuracy:.2f}%"
    
    def _train_anomaly_detection_model(self):
        """Train anomaly detection model"""
        df = self._get_training_data()
        
        # For anomaly detection, we look for unusual patterns in cost, time, or quantity
        features = ['quantity_required', 'total_cost', 'total_cycle_time', 'vendor_rating']
        
        X = df[features].fillna(0)
        
        # Use Isolation Forest for anomaly detection (simplified implementation)
        # In a real implementation, you would use sklearn.ensemble.IsolationForest
        
        # For now, we'll use statistical methods to identify outliers
        from scipy import stats
        
        # Calculate Z-scores
        z_scores = np.abs(stats.zscore(X))
        threshold = 3
        
        # Identify anomalies (Z-score > 3)
        anomalies = (z_scores > threshold).any(axis=1)
        anomaly_rate = anomalies.sum() / len(anomalies) * 100
        
        self.accuracy_score = 100 - anomaly_rate  # Inverse of anomaly rate
        
        model_info = {
            'algorithm': 'statistical_outlier',
            'features': features,
            'threshold': threshold,
            'anomaly_rate': float(anomaly_rate),
        }
        
        self.model_data = json.dumps(model_info)
        self.training_log = f"Anomaly detection model trained. Anomaly rate: {anomaly_rate:.2f}%"
    
    def predict(self, input_data):
        """Make prediction using the trained model"""
        if self.state != 'trained':
            raise UserError(_('Model must be trained before making predictions.'))
        
        if not ML_AVAILABLE:
            raise UserError(_('Machine learning libraries are not available.'))
        
        # This is a simplified prediction method
        # In production, you would load the actual trained model and make predictions
        
        model_info = json.loads(self.model_data)
        
        # Create prediction record
        prediction_vals = {
            'ai_model_id': self.id,
            'input_data': json.dumps(input_data),
            'prediction_date': fields.Datetime.now(),
        }
        
        # Simple prediction logic based on model type
        if self.model_type == 'demand_forecast':
            # Predict demand based on historical averages and trends
            predicted_value = self._predict_demand(input_data)
        elif self.model_type == 'cost_prediction':
            predicted_value = self._predict_cost(input_data)
        elif self.model_type == 'lead_time_prediction':
            predicted_value = self._predict_lead_time(input_data)
        else:
            predicted_value = 0.0
        
        prediction_vals['predicted_value'] = predicted_value
        prediction_vals['confidence_score'] = min(self.accuracy_score, 95.0)
        
        prediction = self.env['manufacturing.requisition.ai.prediction'].create(prediction_vals)
        
        return prediction
    
    def _predict_demand(self, input_data):
        """Predict demand for a product"""
        product_id = input_data.get('product_id')
        month = input_data.get('month', datetime.now().month)
        
        # Get historical demand for this product
        analytics = self.env['manufacturing.requisition.analytics'].search([
            ('product_id', '=', product_id),
            ('requisition_date', '>=', fields.Date.today() - timedelta(days=365))
        ])
        
        if not analytics:
            return 1.0  # Default prediction
        
        # Calculate average demand
        avg_demand = sum(analytics.mapped('quantity_required')) / len(analytics)
        
        # Apply seasonal adjustment (simplified)
        seasonal_factor = 1.0
        if month in [11, 12, 1]:  # Winter months
            seasonal_factor = 1.2
        elif month in [6, 7, 8]:  # Summer months
            seasonal_factor = 0.9
        
        return avg_demand * seasonal_factor
    
    def _predict_cost(self, input_data):
        """Predict cost for a requisition"""
        product_id = input_data.get('product_id')
        quantity = input_data.get('quantity', 1)
        
        # Get historical cost data
        analytics = self.env['manufacturing.requisition.analytics'].search([
            ('product_id', '=', product_id),
            ('requisition_date', '>=', fields.Date.today() - timedelta(days=180))
        ], limit=10)
        
        if not analytics:
            # Fallback to product standard price
            product = self.env['product.product'].browse(product_id)
            return product.standard_price * quantity
        
        # Calculate average unit cost
        total_cost = sum(analytics.mapped('total_cost'))
        total_quantity = sum(analytics.mapped('quantity_required'))
        
        if total_quantity > 0:
            avg_unit_cost = total_cost / total_quantity
            return avg_unit_cost * quantity
        
        return 0.0
    
    def _predict_lead_time(self, input_data):
        """Predict lead time for a requisition"""
        vendor_id = input_data.get('vendor_id')
        priority = input_data.get('priority', 'medium')
        
        # Get historical lead time data
        domain = [('requisition_date', '>=', fields.Date.today() - timedelta(days=180))]
        
        if vendor_id:
            domain.append(('vendor_id', '=', vendor_id))
        
        analytics = self.env['manufacturing.requisition.analytics'].search(domain, limit=20)
        
        if not analytics:
            return 7.0  # Default 7 days
        
        # Calculate average lead time
        avg_lead_time = sum(analytics.mapped('total_cycle_time')) / len(analytics)
        
        # Apply priority adjustment
        priority_factors = {
            'low': 1.2,
            'medium': 1.0,
            'high': 0.8,
            'urgent': 0.6,
            'emergency': 0.4
        }
        
        factor = priority_factors.get(priority, 1.0)
        return avg_lead_time * factor
    
    def action_activate_model(self):
        """Activate the model for use"""
        if self.state != 'trained':
            raise UserError(_('Model must be trained before activation.'))
        
        # Deactivate other models of the same type
        other_models = self.search([
            ('model_type', '=', self.model_type),
            ('state', '=', 'active'),
            ('id', '!=', self.id)
        ])
        other_models.write({'state': 'trained'})
        
        self.state = 'active'
        return True
    
    @api.model
    def get_active_model(self, model_type):
        """Get active model for a specific type"""
        return self.search([
            ('model_type', '=', model_type),
            ('state', '=', 'active')
        ], limit=1)

class RequisitionAIPrediction(models.Model):
    _name = 'manufacturing.requisition.ai.prediction'
    _description = 'AI Prediction Record'
    _order = 'prediction_date desc'

    ai_model_id = fields.Many2one('manufacturing.requisition.ai', 'AI Model', required=True, ondelete='cascade')
    requisition_id = fields.Many2one('manufacturing.requisition', 'Requisition')
    
    prediction_date = fields.Datetime('Prediction Date', required=True)
    input_data = fields.Text('Input Data (JSON)')
    predicted_value = fields.Float('Predicted Value')
    actual_value = fields.Float('Actual Value')
    confidence_score = fields.Float('Confidence Score (%)')
    
    # Accuracy tracking
    prediction_error = fields.Float('Prediction Error', compute='_compute_prediction_error', store=True)
    accuracy_percentage = fields.Float('Accuracy %', compute='_compute_prediction_error', store=True)
    
    @api.depends('predicted_value', 'actual_value')
    def _compute_prediction_error(self):
        for record in self:
            if record.actual_value and record.predicted_value:
                error = abs(record.actual_value - record.predicted_value)
                record.prediction_error = error
                
                if record.actual_value != 0:
                    accuracy = (1 - (error / abs(record.actual_value))) * 100
                    record.accuracy_percentage = max(0, accuracy)
                else:
                    record.accuracy_percentage = 100 if error == 0 else 0
            else:
                record.prediction_error = 0
                record.accuracy_percentage = 0

class RequisitionAIRecommendation(models.Model):
    _name = 'manufacturing.requisition.ai.recommendation'
    _description = 'AI Recommendation'
    _order = 'create_date desc'

    requisition_id = fields.Many2one('manufacturing.requisition', 'Requisition', required=True, ondelete='cascade')
    recommendation_type = fields.Selection([
        ('vendor', 'Vendor Recommendation'),
        ('quantity', 'Quantity Optimization'),
        ('timing', 'Timing Optimization'),
        ('cost', 'Cost Optimization'),
        ('quality', 'Quality Improvement'),
        ('risk', 'Risk Mitigation')
    ], string='Recommendation Type', required=True)
    
    title = fields.Char('Recommendation Title', required=True)
    description = fields.Text('Description', required=True)
    confidence_score = fields.Float('Confidence Score (%)')
    potential_savings = fields.Float('Potential Savings')
    
    # Recommendation Data
    recommended_vendor_id = fields.Many2one('res.partner', 'Recommended Vendor')
    recommended_quantity = fields.Float('Recommended Quantity')
    recommended_date = fields.Date('Recommended Date')
    
    # Status
    state = fields.Selection([
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('implemented', 'Implemented')
    ], string='Status', default='pending', tracking=True)
    
    # Implementation tracking
    implemented_by = fields.Many2one('res.users', 'Implemented By')
    implementation_date = fields.Datetime('Implementation Date')
    implementation_notes = fields.Text('Implementation Notes')
    
    def action_accept_recommendation(self):
        """Accept the recommendation"""
        self.state = 'accepted'
        return True
    
    def action_reject_recommendation(self):
        """Reject the recommendation"""
        self.state = 'rejected'
        return True
    
    def action_implement_recommendation(self):
        """Implement the recommendation"""
        self.state = 'implemented'
        self.implemented_by = self.env.user
        self.implementation_date = fields.Datetime.now()
        
        # Apply recommendation to requisition
        if self.recommendation_type == 'vendor' and self.recommended_vendor_id:
            self.requisition_id.vendor_id = self.recommended_vendor_id
        elif self.recommendation_type == 'quantity' and self.recommended_quantity:
            self.requisition_id.quantity_required = self.recommended_quantity
        elif self.recommendation_type == 'timing' and self.recommended_date:
            self.requisition_id.required_date = self.recommended_date
        
        return True 