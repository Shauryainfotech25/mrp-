odoo.define('manufacturing_material_requisitions.dashboard', function (require) {
'use strict';

var AbstractAction = require('web.AbstractAction');
var core = require('web.core');
var rpc = require('web.rpc');
var session = require('web.session');
var framework = require('web.framework');
var Dialog = require('web.Dialog');

var QWeb = core.qweb;
var _t = core._t;

/**
 * Manufacturing Requisitions Dashboard
 */
var ManufacturingDashboard = AbstractAction.extend({
    template: 'manufacturing_requisitions.Dashboard',
    
    events: {
        'click .emergency-requisition-btn': '_onEmergencyRequisition',
        'click .refresh-dashboard': '_onRefreshDashboard',
        'click .kpi-card': '_onKpiCardClick',
        'click .requisition-card': '_onRequisitionCardClick',
        'change .dashboard-filter': '_onFilterChange',
    },
    
    init: function(parent, context) {
        this._super(parent, context);
        this.dashboardData = {};
        this.refreshInterval = null;
        this.websocket = null;
    },
    
    willStart: function() {
        var self = this;
        return this._super().then(function() {
            return self._loadDashboardData();
        });
    },
    
    start: function() {
        var self = this;
        return this._super().then(function() {
            self._renderDashboard();
            self._setupRealTimeUpdates();
            self._startAutoRefresh();
        });
    },
    
    destroy: function() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        if (this.websocket) {
            this.websocket.close();
        }
        this._super();
    },
    
    _loadDashboardData: function() {
        var self = this;
        return rpc.query({
            route: '/manufacturing/dashboard/data',
            params: {
                context: session.user_context,
            }
        }).then(function(data) {
            self.dashboardData = data;
        });
    },
    
    _renderDashboard: function() {
        var self = this;
        
        // Render KPI cards
        this._renderKpiCards();
        
        // Render recent requisitions
        this._renderRecentRequisitions();
        
        // Render charts
        this._renderCharts();
        
        // Render emergency alerts
        this._renderEmergencyAlerts();
    },
    
    _renderKpiCards: function() {
        var self = this;
        var $kpiContainer = this.$('.kpi-container');
        
        if (!$kpiContainer.length) return;
        
        var kpis = this.dashboardData.kpis || {};
        
        var kpiCards = [
            {
                title: _t('Total Requisitions'),
                value: kpis.total_requisitions || 0,
                trend: kpis.requisitions_trend || 0,
                icon: 'fa-file-text',
                color: 'primary'
            },
            {
                title: _t('Pending Approvals'),
                value: kpis.pending_approvals || 0,
                trend: kpis.approvals_trend || 0,
                icon: 'fa-clock-o',
                color: 'warning'
            },
            {
                title: _t('Emergency Requests'),
                value: kpis.emergency_count || 0,
                trend: kpis.emergency_trend || 0,
                icon: 'fa-exclamation-triangle',
                color: 'emergency'
            },
            {
                title: _t('Completion Rate'),
                value: (kpis.completion_rate || 0) + '%',
                trend: kpis.completion_trend || 0,
                icon: 'fa-check-circle',
                color: 'success'
            }
        ];
        
        $kpiContainer.empty();
        
        kpiCards.forEach(function(kpi) {
            var $card = $(QWeb.render('manufacturing_requisitions.KpiCard', {
                kpi: kpi
            }));
            $kpiContainer.append($card);
        });
    },
    
    _renderRecentRequisitions: function() {
        var self = this;
        var $container = this.$('.recent-requisitions');
        
        if (!$container.length) return;
        
        var requisitions = this.dashboardData.recent_requisitions || [];
        
        $container.empty();
        
        requisitions.forEach(function(req) {
            var $card = $(QWeb.render('manufacturing_requisitions.RequisitionCard', {
                requisition: req
            }));
            $container.append($card);
        });
    },
    
    _renderCharts: function() {
        var self = this;
        
        // Render requisition trend chart
        this._renderTrendChart();
        
        // Render department performance chart
        this._renderDepartmentChart();
        
        // Render cost analysis chart
        this._renderCostChart();
    },
    
    _renderTrendChart: function() {
        var $canvas = this.$('#requisition-trend-chart');
        if (!$canvas.length) return;
        
        var ctx = $canvas[0].getContext('2d');
        var data = this.dashboardData.trend_data || {};
        
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels || [],
                datasets: [{
                    label: _t('Requisitions'),
                    data: data.values || [],
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: _t('Requisition Trend (Last 30 Days)')
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    },
    
    _renderDepartmentChart: function() {
        var $canvas = this.$('#department-performance-chart');
        if (!$canvas.length) return;
        
        var ctx = $canvas[0].getContext('2d');
        var data = this.dashboardData.department_data || {};
        
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels || [],
                datasets: [{
                    label: _t('Requisitions'),
                    data: data.values || [],
                    backgroundColor: [
                        '#667eea', '#764ba2', '#f093fb', '#f5576c',
                        '#4facfe', '#00f2fe', '#43e97b', '#38f9d7'
                    ]
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: _t('Department Performance')
                    }
                }
            }
        });
    },
    
    _renderCostChart: function() {
        var $canvas = this.$('#cost-analysis-chart');
        if (!$canvas.length) return;
        
        var ctx = $canvas[0].getContext('2d');
        var data = this.dashboardData.cost_data || {};
        
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.labels || [],
                datasets: [{
                    data: data.values || [],
                    backgroundColor: [
                        '#667eea', '#764ba2', '#f093fb', '#f5576c',
                        '#4facfe', '#00f2fe', '#43e97b', '#38f9d7'
                    ]
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: _t('Cost Distribution by Category')
                    }
                }
            }
        });
    },
    
    _renderEmergencyAlerts: function() {
        var self = this;
        var $container = this.$('.emergency-alerts');
        
        if (!$container.length) return;
        
        var alerts = this.dashboardData.emergency_alerts || [];
        
        $container.empty();
        
        if (alerts.length === 0) {
            $container.append('<div class="no-alerts">' + _t('No emergency alerts') + '</div>');
            return;
        }
        
        alerts.forEach(function(alert) {
            var $alert = $(QWeb.render('manufacturing_requisitions.EmergencyAlert', {
                alert: alert
            }));
            $container.append($alert);
        });
    },
    
    _setupRealTimeUpdates: function() {
        var self = this;
        
        // Setup WebSocket connection for real-time updates
        if (window.WebSocket) {
            var wsUrl = 'ws://' + window.location.host + '/manufacturing/websocket';
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onmessage = function(event) {
                var data = JSON.parse(event.data);
                self._handleRealTimeUpdate(data);
            };
            
            this.websocket.onerror = function(error) {
                console.error('WebSocket error:', error);
            };
        }
    },
    
    _handleRealTimeUpdate: function(data) {
        switch (data.type) {
            case 'emergency_requisition':
                this._showEmergencyNotification(data);
                this._refreshEmergencyAlerts();
                break;
            case 'requisition_approved':
                this._showNotification(_t('Requisition approved'), 'success');
                this._refreshKpis();
                break;
            case 'requisition_rejected':
                this._showNotification(_t('Requisition rejected'), 'warning');
                this._refreshKpis();
                break;
            case 'inventory_update':
                this._refreshInventoryStatus();
                break;
        }
    },
    
    _startAutoRefresh: function() {
        var self = this;
        this.refreshInterval = setInterval(function() {
            self._loadDashboardData().then(function() {
                self._renderKpiCards();
                self._renderRecentRequisitions();
            });
        }, 30000); // Refresh every 30 seconds
    },
    
    _showEmergencyNotification: function(data) {
        var self = this;
        
        // Play alert sound
        this._playAlertSound();
        
        // Show emergency dialog
        var dialog = new Dialog(this, {
            title: _t('🚨 EMERGENCY REQUISITION ALERT'),
            size: 'medium',
            $content: $(QWeb.render('manufacturing_requisitions.EmergencyDialog', {
                data: data
            })),
            buttons: [
                {
                    text: _t('View Details'),
                    classes: 'btn-primary',
                    click: function() {
                        self._openRequisition(data.requisition_id);
                        dialog.close();
                    }
                },
                {
                    text: _t('Acknowledge'),
                    classes: 'btn-secondary',
                    click: function() {
                        dialog.close();
                    }
                }
            ]
        });
        
        dialog.open();
        
        // Auto-close after 10 seconds if not acknowledged
        setTimeout(function() {
            if (dialog.isDestroyed()) return;
            dialog.close();
        }, 10000);
    },
    
    _playAlertSound: function() {
        try {
            var audio = new Audio('/manufacturing_material_requisitions/static/src/audio/emergency_alert.mp3');
            audio.play();
        } catch (e) {
            console.warn('Could not play alert sound:', e);
        }
    },
    
    _showNotification: function(message, type) {
        var $notification = $('<div class="notification ' + type + '">' + message + '</div>');
        this.$('.notifications-container').append($notification);
        
        setTimeout(function() {
            $notification.fadeOut(function() {
                $notification.remove();
            });
        }, 5000);
    },
    
    _onEmergencyRequisition: function(ev) {
        ev.preventDefault();
        
        var self = this;
        var dialog = new Dialog(this, {
            title: _t('Create Emergency Requisition'),
            size: 'large',
            $content: $(QWeb.render('manufacturing_requisitions.EmergencyForm')),
            buttons: [
                {
                    text: _t('Create Emergency Request'),
                    classes: 'btn-danger',
                    click: function() {
                        self._createEmergencyRequisition(dialog);
                    }
                },
                {
                    text: _t('Cancel'),
                    classes: 'btn-secondary',
                    close: true
                }
            ]
        });
        
        dialog.open();
    },
    
    _createEmergencyRequisition: function(dialog) {
        var self = this;
        var $form = dialog.$('.emergency-form');
        
        var formData = {
            machine_id: $form.find('[name="machine_id"]').val(),
            materials: this._getSelectedMaterials($form),
            production_impact: $form.find('[name="production_impact"]').val(),
            description: $form.find('[name="description"]').val()
        };
        
        if (!formData.machine_id || formData.materials.length === 0) {
            this._showNotification(_t('Please fill all required fields'), 'error');
            return;
        }
        
        framework.blockUI();
        
        rpc.query({
            route: '/shop_floor/emergency/create',
            params: formData
        }).then(function(result) {
            framework.unblockUI();
            
            if (result.success) {
                self._showNotification(_t('Emergency requisition created successfully'), 'success');
                dialog.close();
                self._refreshDashboard();
            } else {
                self._showNotification(result.error || _t('Failed to create emergency requisition'), 'error');
            }
        }).catch(function(error) {
            framework.unblockUI();
            self._showNotification(_t('Error creating emergency requisition'), 'error');
            console.error(error);
        });
    },
    
    _getSelectedMaterials: function($form) {
        var materials = [];
        $form.find('.material-line').each(function() {
            var $line = $(this);
            var productId = $line.find('[name="product_id"]').val();
            var quantity = $line.find('[name="quantity"]').val();
            
            if (productId && quantity) {
                materials.push({
                    product_id: parseInt(productId),
                    quantity: parseFloat(quantity)
                });
            }
        });
        return materials;
    },
    
    _onRefreshDashboard: function(ev) {
        ev.preventDefault();
        this._refreshDashboard();
    },
    
    _refreshDashboard: function() {
        var self = this;
        framework.blockUI();
        
        this._loadDashboardData().then(function() {
            self._renderDashboard();
            framework.unblockUI();
            self._showNotification(_t('Dashboard refreshed'), 'success');
        }).catch(function(error) {
            framework.unblockUI();
            self._showNotification(_t('Failed to refresh dashboard'), 'error');
            console.error(error);
        });
    },
    
    _refreshKpis: function() {
        var self = this;
        rpc.query({
            route: '/manufacturing/dashboard/kpis',
            params: {}
        }).then(function(kpis) {
            self.dashboardData.kpis = kpis;
            self._renderKpiCards();
        });
    },
    
    _refreshEmergencyAlerts: function() {
        var self = this;
        rpc.query({
            route: '/manufacturing/dashboard/emergency_alerts',
            params: {}
        }).then(function(alerts) {
            self.dashboardData.emergency_alerts = alerts;
            self._renderEmergencyAlerts();
        });
    },
    
    _refreshInventoryStatus: function() {
        // Refresh inventory-related components
        this._refreshKpis();
    },
    
    _onKpiCardClick: function(ev) {
        var $card = $(ev.currentTarget);
        var kpiType = $card.data('kpi-type');
        
        // Navigate to detailed view based on KPI type
        switch (kpiType) {
            case 'total_requisitions':
                this._openRequisitionsList();
                break;
            case 'pending_approvals':
                this._openPendingApprovals();
                break;
            case 'emergency_count':
                this._openEmergencyRequisitions();
                break;
            case 'completion_rate':
                this._openAnalytics();
                break;
        }
    },
    
    _onRequisitionCardClick: function(ev) {
        var $card = $(ev.currentTarget);
        var requisitionId = $card.data('requisition-id');
        this._openRequisition(requisitionId);
    },
    
    _onFilterChange: function(ev) {
        var $filter = $(ev.currentTarget);
        var filterType = $filter.data('filter-type');
        var filterValue = $filter.val();
        
        // Apply filter and refresh dashboard
        this._applyFilter(filterType, filterValue);
    },
    
    _applyFilter: function(filterType, filterValue) {
        var self = this;
        
        var params = {};
        params[filterType] = filterValue;
        
        rpc.query({
            route: '/manufacturing/dashboard/data',
            params: params
        }).then(function(data) {
            self.dashboardData = data;
            self._renderDashboard();
        });
    },
    
    _openRequisition: function(requisitionId) {
        this.do_action({
            type: 'ir.actions.act_window',
            res_model: 'manufacturing.material.requisition',
            res_id: requisitionId,
            views: [[false, 'form']],
            target: 'current'
        });
    },
    
    _openRequisitionsList: function() {
        this.do_action({
            type: 'ir.actions.act_window',
            res_model: 'manufacturing.material.requisition',
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        });
    },
    
    _openPendingApprovals: function() {
        this.do_action({
            type: 'ir.actions.act_window',
            res_model: 'manufacturing.material.requisition',
            domain: [['state', 'in', ['submitted', 'supervisor_approval', 'manager_approval', 'procurement_approval']]],
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        });
    },
    
    _openEmergencyRequisitions: function() {
        this.do_action({
            type: 'ir.actions.act_window',
            res_model: 'shop.floor.requisition',
            domain: [['is_emergency', '=', true]],
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        });
    },
    
    _openAnalytics: function() {
        this.do_action({
            type: 'ir.actions.act_window',
            res_model: 'manufacturing.requisition.analytics',
            views: [[false, 'pivot'], [false, 'graph']],
            target: 'current'
        });
    }
});

core.action_registry.add('manufacturing_requisitions.dashboard', ManufacturingDashboard);

/**
 * Shop Floor Interface
 */
var ShopFloorInterface = AbstractAction.extend({
    template: 'manufacturing_requisitions.ShopFloor',
    
    events: {
        'click .emergency-btn': '_onEmergencyClick',
        'click .scan-barcode': '_onScanBarcode',
        'click .voice-input': '_onVoiceInput',
        'click .photo-capture': '_onPhotoCapture',
    },
    
    init: function(parent, context) {
        this._super(parent, context);
        this.machineId = context.machine_id;
        this.operatorId = session.uid;
    },
    
    start: function() {
        var self = this;
        return this._super().then(function() {
            self._loadMachineStatus();
            self._setupVoiceRecognition();
            self._setupBarcodeScanner();
        });
    },
    
    _loadMachineStatus: function() {
        var self = this;
        
        rpc.query({
            route: '/shop_floor/machine_status',
            params: {
                machine_id: this.machineId
            }
        }).then(function(status) {
            self._updateMachineStatus(status);
        });
    },
    
    _updateMachineStatus: function(status) {
        var $statusIndicator = this.$('.status-indicator');
        var $statusText = this.$('.status-text');
        
        $statusIndicator.removeClass('status-running status-stopped status-maintenance');
        $statusIndicator.addClass('status-' + status.state);
        $statusText.text(status.state_label);
    },
    
    _setupVoiceRecognition: function() {
        if (!('webkitSpeechRecognition' in window)) {
            this.$('.voice-input').hide();
            return;
        }
        
        this.recognition = new webkitSpeechRecognition();
        this.recognition.continuous = false;
        this.recognition.interimResults = false;
        this.recognition.lang = 'en-US';
        
        var self = this;
        this.recognition.onresult = function(event) {
            var transcript = event.results[0][0].transcript;
            self._processVoiceCommand(transcript);
        };
    },
    
    _setupBarcodeScanner: function() {
        // Setup barcode scanner integration
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            this.barcodeScanner = true;
        } else {
            this.$('.scan-barcode').hide();
        }
    },
    
    _onEmergencyClick: function(ev) {
        ev.preventDefault();
        this._showEmergencyForm();
    },
    
    _onScanBarcode: function(ev) {
        ev.preventDefault();
        this._startBarcodeScanning();
    },
    
    _onVoiceInput: function(ev) {
        ev.preventDefault();
        this._startVoiceRecognition();
    },
    
    _onPhotoCapture: function(ev) {
        ev.preventDefault();
        this._capturePhoto();
    },
    
    _showEmergencyForm: function() {
        var self = this;
        
        var dialog = new Dialog(this, {
            title: _t('🚨 EMERGENCY REQUISITION'),
            size: 'large',
            $content: $(QWeb.render('manufacturing_requisitions.ShopFloorEmergencyForm', {
                machine_id: this.machineId
            })),
            buttons: [
                {
                    text: _t('SUBMIT EMERGENCY REQUEST'),
                    classes: 'btn-danger btn-lg',
                    click: function() {
                        self._submitEmergencyRequisition(dialog);
                    }
                },
                {
                    text: _t('Cancel'),
                    classes: 'btn-secondary',
                    close: true
                }
            ]
        });
        
        dialog.open();
    },
    
    _submitEmergencyRequisition: function(dialog) {
        var self = this;
        var $form = dialog.$('.emergency-form');
        
        var formData = {
            machine_id: this.machineId,
            operator_id: this.operatorId,
            materials: this._getSelectedMaterials($form),
            production_impact: $form.find('[name="production_impact"]').val(),
            estimated_downtime: $form.find('[name="estimated_downtime"]').val(),
            description: $form.find('[name="description"]').val(),
            photos: this._getAttachedPhotos($form)
        };
        
        framework.blockUI();
        
        rpc.query({
            route: '/api/v1/shop_floor/emergency',
            params: formData
        }).then(function(result) {
            framework.unblockUI();
            
            if (result.success) {
                self._showSuccessMessage(_t('Emergency requisition submitted successfully'));
                dialog.close();
            } else {
                self._showErrorMessage(result.error || _t('Failed to submit emergency requisition'));
            }
        }).catch(function(error) {
            framework.unblockUI();
            self._showErrorMessage(_t('Error submitting emergency requisition'));
            console.error(error);
        });
    },
    
    _startBarcodeScanning: function() {
        var self = this;
        
        // Implementation would depend on barcode scanning library
        // This is a placeholder for the actual implementation
        
        var dialog = new Dialog(this, {
            title: _t('Scan Barcode'),
            size: 'medium',
            $content: $('<div class="barcode-scanner"><video id="barcode-video" autoplay></video></div>'),
            buttons: [
                {
                    text: _t('Cancel'),
                    classes: 'btn-secondary',
                    close: true
                }
            ]
        });
        
        dialog.open();
        
        // Start camera for barcode scanning
        navigator.mediaDevices.getUserMedia({ video: true })
            .then(function(stream) {
                var video = dialog.$('#barcode-video')[0];
                video.srcObject = stream;
                
                // Implement barcode detection logic here
                // This would typically use a library like QuaggaJS or ZXing
            })
            .catch(function(error) {
                console.error('Error accessing camera:', error);
                dialog.close();
            });
    },
    
    _startVoiceRecognition: function() {
        if (!this.recognition) return;
        
        var $voiceBtn = this.$('.voice-input');
        $voiceBtn.addClass('recording');
        $voiceBtn.find('.fa').removeClass('fa-microphone').addClass('fa-stop');
        
        this.recognition.start();
        
        var self = this;
        setTimeout(function() {
            self.recognition.stop();
            $voiceBtn.removeClass('recording');
            $voiceBtn.find('.fa').removeClass('fa-stop').addClass('fa-microphone');
        }, 5000);
    },
    
    _processVoiceCommand: function(transcript) {
        // Process voice commands for creating requisitions
        // This is a simplified implementation
        
        var command = transcript.toLowerCase();
        
        if (command.includes('emergency')) {
            this._showEmergencyForm();
        } else if (command.includes('material') || command.includes('part')) {
            this._showMaterialRequestForm(transcript);
        } else {
            this._showMessage(_t('Voice command not recognized: ') + transcript, 'warning');
        }
    },
    
    _capturePhoto: function() {
        var self = this;
        
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            this._showErrorMessage(_t('Camera not available'));
            return;
        }
        
        var dialog = new Dialog(this, {
            title: _t('Capture Photo'),
            size: 'medium',
            $content: $(QWeb.render('manufacturing_requisitions.PhotoCapture')),
            buttons: [
                {
                    text: _t('Capture'),
                    classes: 'btn-primary',
                    click: function() {
                        self._takePhoto(dialog);
                    }
                },
                {
                    text: _t('Cancel'),
                    classes: 'btn-secondary',
                    close: true
                }
            ]
        });
        
        dialog.open();
        
        // Start camera
        navigator.mediaDevices.getUserMedia({ video: true })
            .then(function(stream) {
                var video = dialog.$('#photo-video')[0];
                video.srcObject = stream;
            })
            .catch(function(error) {
                console.error('Error accessing camera:', error);
                dialog.close();
            });
    },
    
    _takePhoto: function(dialog) {
        var video = dialog.$('#photo-video')[0];
        var canvas = dialog.$('#photo-canvas')[0];
        var context = canvas.getContext('2d');
        
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0);
        
        var dataURL = canvas.toDataURL('image/jpeg');
        
        // Store photo for attachment to requisition
        this.capturedPhoto = dataURL;
        
        dialog.close();
        this._showMessage(_t('Photo captured successfully'), 'success');
    },
    
    _showMessage: function(message, type) {
        var $message = $('<div class="shop-floor-message ' + type + '">' + message + '</div>');
        this.$('.messages-container').append($message);
        
        setTimeout(function() {
            $message.fadeOut(function() {
                $message.remove();
            });
        }, 3000);
    },
    
    _showSuccessMessage: function(message) {
        this._showMessage(message, 'success');
    },
    
    _showErrorMessage: function(message) {
        this._showMessage(message, 'error');
    }
});

core.action_registry.add('manufacturing_requisitions.shop_floor', ShopFloorInterface);

return {
    ManufacturingDashboard: ManufacturingDashboard,
    ShopFloorInterface: ShopFloorInterface
};

}); 