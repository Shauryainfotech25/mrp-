import logging
import json
import time
import statistics
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
from collections import defaultdict, deque
import threading
from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """Performance monitoring service for the OmniHR AI Platform"""
    
    def __init__(self, max_history_size: int = 10000):
        """Initialize performance monitor
        
        Args:
            max_history_size: Maximum number of records to keep in memory
        """
        self.max_history_size = max_history_size
        self.lock = threading.Lock()
        
        # Performance metrics storage
        self.request_history = deque(maxlen=max_history_size)
        self.provider_metrics = defaultdict(lambda: {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_response_time': 0,
            'total_tokens': 0,
            'total_cost': 0,
            'error_types': defaultdict(int),
            'response_times': deque(maxlen=1000),
            'success_rate_history': deque(maxlen=100),
            'last_updated': datetime.now()
        })
        
        # System-wide metrics
        self.system_metrics = {
            'total_requests': 0,
            'total_successful': 0,
            'total_failed': 0,
            'total_cost': 0,
            'total_tokens': 0,
            'uptime_start': datetime.now(),
            'last_health_check': None,
            'consensus_accuracy': deque(maxlen=1000),
            'user_satisfaction': deque(maxlen=1000)
        }
        
        # Performance thresholds
        self.thresholds = {
            'response_time_warning': 5.0,  # seconds
            'response_time_critical': 10.0,  # seconds
            'success_rate_warning': 0.9,  # 90%
            'success_rate_critical': 0.8,  # 80%
            'cost_per_request_warning': 0.1,  # $0.10
            'cost_per_request_critical': 0.5,  # $0.50
            'token_efficiency_warning': 0.7,  # tokens used / max tokens
            'token_efficiency_critical': 0.9
        }
        
        # Alert history
        self.alerts = deque(maxlen=1000)
        
        # Performance trends
        self.trends = {
            'hourly_stats': defaultdict(lambda: defaultdict(list)),
            'daily_stats': defaultdict(lambda: defaultdict(list)),
            'weekly_stats': defaultdict(lambda: defaultdict(list))
        }
    
    def log_request(self, provider: str, task_type: str, request_data: Dict[str, Any], 
                   response_data: Dict[str, Any]):
        """Log a request and response for performance tracking
        
        Args:
            provider: AI provider name
            task_type: Type of task performed
            request_data: Request information
            response_data: Response information
        """
        try:
            with self.lock:
                timestamp = datetime.now()
                
                # Create request record
                record = {
                    'timestamp': timestamp,
                    'provider': provider,
                    'task_type': task_type,
                    'success': response_data.get('success', False),
                    'response_time': response_data.get('response_time', 0),
                    'tokens_used': response_data.get('tokens_used', 0),
                    'cost': response_data.get('cost', 0),
                    'error': response_data.get('error'),
                    'model': response_data.get('model'),
                    'request_size': len(str(request_data)),
                    'response_size': len(str(response_data))
                }
                
                # Add to history
                self.request_history.append(record)
                
                # Update provider metrics
                self._update_provider_metrics(provider, record)
                
                # Update system metrics
                self._update_system_metrics(record)
                
                # Update trends
                self._update_trends(record)
                
                # Check for alerts
                self._check_alerts(provider, record)
                
        except Exception as e:
            _logger.error(f"Failed to log request: {str(e)}")
    
    def _update_provider_metrics(self, provider: str, record: Dict[str, Any]):
        """Update metrics for a specific provider
        
        Args:
            provider: Provider name
            record: Request record
        """
        metrics = self.provider_metrics[provider]
        
        # Update counters
        metrics['total_requests'] += 1
        if record['success']:
            metrics['successful_requests'] += 1
        else:
            metrics['failed_requests'] += 1
            if record['error']:
                error_type = type(record['error']).__name__ if isinstance(record['error'], Exception) else str(record['error'])
                metrics['error_types'][error_type] += 1
        
        # Update totals
        metrics['total_response_time'] += record['response_time']
        metrics['total_tokens'] += record['tokens_used']
        metrics['total_cost'] += record['cost']
        
        # Update time series data
        metrics['response_times'].append(record['response_time'])
        success_rate = metrics['successful_requests'] / metrics['total_requests']
        metrics['success_rate_history'].append(success_rate)
        
        metrics['last_updated'] = record['timestamp']
    
    def _update_system_metrics(self, record: Dict[str, Any]):
        """Update system-wide metrics
        
        Args:
            record: Request record
        """
        self.system_metrics['total_requests'] += 1
        if record['success']:
            self.system_metrics['total_successful'] += 1
        else:
            self.system_metrics['total_failed'] += 1
        
        self.system_metrics['total_cost'] += record['cost']
        self.system_metrics['total_tokens'] += record['tokens_used']
    
    def _update_trends(self, record: Dict[str, Any]):
        """Update performance trends
        
        Args:
            record: Request record
        """
        timestamp = record['timestamp']
        provider = record['provider']
        
        # Hourly trends
        hour_key = timestamp.strftime('%Y-%m-%d-%H')
        self.trends['hourly_stats'][hour_key][provider].append(record)
        
        # Daily trends
        day_key = timestamp.strftime('%Y-%m-%d')
        self.trends['daily_stats'][day_key][provider].append(record)
        
        # Weekly trends
        week_key = timestamp.strftime('%Y-W%U')
        self.trends['weekly_stats'][week_key][provider].append(record)
    
    def _check_alerts(self, provider: str, record: Dict[str, Any]):
        """Check for performance alerts
        
        Args:
            provider: Provider name
            record: Request record
        """
        alerts = []
        
        # Response time alerts
        if record['response_time'] > self.thresholds['response_time_critical']:
            alerts.append({
                'type': 'critical',
                'category': 'response_time',
                'provider': provider,
                'message': f"Critical response time: {record['response_time']:.2f}s",
                'value': record['response_time'],
                'threshold': self.thresholds['response_time_critical']
            })
        elif record['response_time'] > self.thresholds['response_time_warning']:
            alerts.append({
                'type': 'warning',
                'category': 'response_time',
                'provider': provider,
                'message': f"High response time: {record['response_time']:.2f}s",
                'value': record['response_time'],
                'threshold': self.thresholds['response_time_warning']
            })
        
        # Success rate alerts
        metrics = self.provider_metrics[provider]
        success_rate = metrics['successful_requests'] / metrics['total_requests']
        
        if success_rate < self.thresholds['success_rate_critical']:
            alerts.append({
                'type': 'critical',
                'category': 'success_rate',
                'provider': provider,
                'message': f"Critical success rate: {success_rate:.2%}",
                'value': success_rate,
                'threshold': self.thresholds['success_rate_critical']
            })
        elif success_rate < self.thresholds['success_rate_warning']:
            alerts.append({
                'type': 'warning',
                'category': 'success_rate',
                'provider': provider,
                'message': f"Low success rate: {success_rate:.2%}",
                'value': success_rate,
                'threshold': self.thresholds['success_rate_warning']
            })
        
        # Cost alerts
        avg_cost = metrics['total_cost'] / metrics['total_requests']
        if avg_cost > self.thresholds['cost_per_request_critical']:
            alerts.append({
                'type': 'critical',
                'category': 'cost',
                'provider': provider,
                'message': f"High cost per request: ${avg_cost:.4f}",
                'value': avg_cost,
                'threshold': self.thresholds['cost_per_request_critical']
            })
        elif avg_cost > self.thresholds['cost_per_request_warning']:
            alerts.append({
                'type': 'warning',
                'category': 'cost',
                'provider': provider,
                'message': f"Elevated cost per request: ${avg_cost:.4f}",
                'value': avg_cost,
                'threshold': self.thresholds['cost_per_request_warning']
            })
        
        # Log alerts
        for alert in alerts:
            alert['timestamp'] = record['timestamp']
            self.alerts.append(alert)
            _logger.warning(f"Performance alert: {alert['message']}")
    
    def get_provider_performance(self, provider: str, 
                               time_range: Optional[timedelta] = None) -> Dict[str, Any]:
        """Get performance metrics for a specific provider
        
        Args:
            provider: Provider name
            time_range: Optional time range for filtering
            
        Returns:
            Provider performance metrics
        """
        try:
            with self.lock:
                if provider not in self.provider_metrics:
                    return {
                        'provider': provider,
                        'error': 'Provider not found',
                        'timestamp': datetime.now().isoformat()
                    }
                
                metrics = self.provider_metrics[provider]
                
                # Filter by time range if specified
                if time_range:
                    cutoff_time = datetime.now() - time_range
                    filtered_records = [
                        r for r in self.request_history 
                        if r['provider'] == provider and r['timestamp'] > cutoff_time
                    ]
                else:
                    filtered_records = [
                        r for r in self.request_history 
                        if r['provider'] == provider
                    ]
                
                if not filtered_records:
                    return {
                        'provider': provider,
                        'error': 'No data available for time range',
                        'timestamp': datetime.now().isoformat()
                    }
                
                # Calculate metrics from filtered records
                total_requests = len(filtered_records)
                successful_requests = sum(1 for r in filtered_records if r['success'])
                failed_requests = total_requests - successful_requests
                
                response_times = [r['response_time'] for r in filtered_records]
                costs = [r['cost'] for r in filtered_records]
                tokens = [r['tokens_used'] for r in filtered_records]
                
                return {
                    'provider': provider,
                    'time_range': str(time_range) if time_range else 'all_time',
                    'total_requests': total_requests,
                    'successful_requests': successful_requests,
                    'failed_requests': failed_requests,
                    'success_rate': successful_requests / total_requests if total_requests > 0 else 0,
                    'average_response_time': statistics.mean(response_times) if response_times else 0,
                    'median_response_time': statistics.median(response_times) if response_times else 0,
                    'p95_response_time': self._percentile(response_times, 95) if response_times else 0,
                    'p99_response_time': self._percentile(response_times, 99) if response_times else 0,
                    'total_cost': sum(costs),
                    'average_cost_per_request': statistics.mean(costs) if costs else 0,
                    'total_tokens': sum(tokens),
                    'average_tokens_per_request': statistics.mean(tokens) if tokens else 0,
                    'error_distribution': self._get_error_distribution(filtered_records),
                    'task_type_distribution': self._get_task_distribution(filtered_records),
                    'performance_grade': self._calculate_performance_grade(provider, filtered_records),
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            _logger.error(f"Failed to get provider performance: {str(e)}")
            return {
                'provider': provider,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_system_performance(self, time_range: Optional[timedelta] = None) -> Dict[str, Any]:
        """Get system-wide performance metrics
        
        Args:
            time_range: Optional time range for filtering
            
        Returns:
            System performance metrics
        """
        try:
            with self.lock:
                # Filter by time range if specified
                if time_range:
                    cutoff_time = datetime.now() - time_range
                    filtered_records = [
                        r for r in self.request_history 
                        if r['timestamp'] > cutoff_time
                    ]
                else:
                    filtered_records = list(self.request_history)
                
                if not filtered_records:
                    return {
                        'error': 'No data available for time range',
                        'timestamp': datetime.now().isoformat()
                    }
                
                # Calculate system metrics
                total_requests = len(filtered_records)
                successful_requests = sum(1 for r in filtered_records if r['success'])
                failed_requests = total_requests - successful_requests
                
                response_times = [r['response_time'] for r in filtered_records]
                costs = [r['cost'] for r in filtered_records]
                tokens = [r['tokens_used'] for r in filtered_records]
                
                # Provider distribution
                provider_counts = defaultdict(int)
                for record in filtered_records:
                    provider_counts[record['provider']] += 1
                
                # Task type distribution
                task_counts = defaultdict(int)
                for record in filtered_records:
                    task_counts[record['task_type']] += 1
                
                uptime = datetime.now() - self.system_metrics['uptime_start']
                
                return {
                    'time_range': str(time_range) if time_range else 'all_time',
                    'uptime': str(uptime),
                    'total_requests': total_requests,
                    'successful_requests': successful_requests,
                    'failed_requests': failed_requests,
                    'success_rate': successful_requests / total_requests if total_requests > 0 else 0,
                    'requests_per_hour': total_requests / (uptime.total_seconds() / 3600) if uptime.total_seconds() > 0 else 0,
                    'average_response_time': statistics.mean(response_times) if response_times else 0,
                    'median_response_time': statistics.median(response_times) if response_times else 0,
                    'p95_response_time': self._percentile(response_times, 95) if response_times else 0,
                    'p99_response_time': self._percentile(response_times, 99) if response_times else 0,
                    'total_cost': sum(costs),
                    'average_cost_per_request': statistics.mean(costs) if costs else 0,
                    'cost_per_hour': sum(costs) / (uptime.total_seconds() / 3600) if uptime.total_seconds() > 0 else 0,
                    'total_tokens': sum(tokens),
                    'average_tokens_per_request': statistics.mean(tokens) if tokens else 0,
                    'provider_distribution': dict(provider_counts),
                    'task_type_distribution': dict(task_counts),
                    'system_health': self._calculate_system_health(filtered_records),
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            _logger.error(f"Failed to get system performance: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_performance_trends(self, period: str = 'hourly', 
                             days_back: int = 7) -> Dict[str, Any]:
        """Get performance trends over time
        
        Args:
            period: Trend period ('hourly', 'daily', 'weekly')
            days_back: Number of days to look back
            
        Returns:
            Performance trends data
        """
        try:
            with self.lock:
                cutoff_time = datetime.now() - timedelta(days=days_back)
                
                if period == 'hourly':
                    trend_data = self.trends['hourly_stats']
                    time_format = '%Y-%m-%d-%H'
                elif period == 'daily':
                    trend_data = self.trends['daily_stats']
                    time_format = '%Y-%m-%d'
                elif period == 'weekly':
                    trend_data = self.trends['weekly_stats']
                    time_format = '%Y-W%U'
                else:
                    return {'error': 'Invalid period. Use hourly, daily, or weekly'}
                
                # Filter and process trend data
                trends = {}
                for time_key, provider_data in trend_data.items():
                    try:
                        if period == 'weekly':
                            # Parse week format
                            year, week = time_key.split('-W')
                            time_obj = datetime.strptime(f"{year}-W{week}-1", "%Y-W%U-%w")
                        else:
                            time_obj = datetime.strptime(time_key, time_format)
                        
                        if time_obj >= cutoff_time:
                            trends[time_key] = {}
                            for provider, records in provider_data.items():
                                if records:
                                    success_rate = sum(1 for r in records if r['success']) / len(records)
                                    avg_response_time = statistics.mean([r['response_time'] for r in records])
                                    total_cost = sum(r['cost'] for r in records)
                                    total_tokens = sum(r['tokens_used'] for r in records)
                                    
                                    trends[time_key][provider] = {
                                        'requests': len(records),
                                        'success_rate': success_rate,
                                        'avg_response_time': avg_response_time,
                                        'total_cost': total_cost,
                                        'total_tokens': total_tokens
                                    }
                    except ValueError:
                        continue  # Skip invalid time keys
                
                return {
                    'period': period,
                    'days_back': days_back,
                    'trends': trends,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            _logger.error(f"Failed to get performance trends: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_alerts(self, severity: Optional[str] = None, 
                  time_range: Optional[timedelta] = None) -> List[Dict[str, Any]]:
        """Get performance alerts
        
        Args:
            severity: Optional severity filter ('warning', 'critical')
            time_range: Optional time range for filtering
            
        Returns:
            List of alerts
        """
        try:
            with self.lock:
                alerts = list(self.alerts)
                
                # Filter by time range
                if time_range:
                    cutoff_time = datetime.now() - time_range
                    alerts = [a for a in alerts if a['timestamp'] > cutoff_time]
                
                # Filter by severity
                if severity:
                    alerts = [a for a in alerts if a['type'] == severity]
                
                # Sort by timestamp (newest first)
                alerts.sort(key=lambda x: x['timestamp'], reverse=True)
                
                return alerts
                
        except Exception as e:
            _logger.error(f"Failed to get alerts: {str(e)}")
            return []
    
    def get_provider_comparison(self, time_range: Optional[timedelta] = None) -> Dict[str, Any]:
        """Compare performance across providers
        
        Args:
            time_range: Optional time range for filtering
            
        Returns:
            Provider comparison data
        """
        try:
            providers = list(self.provider_metrics.keys())
            comparison = {}
            
            for provider in providers:
                performance = self.get_provider_performance(provider, time_range)
                if 'error' not in performance:
                    comparison[provider] = {
                        'success_rate': performance['success_rate'],
                        'avg_response_time': performance['average_response_time'],
                        'avg_cost_per_request': performance['average_cost_per_request'],
                        'total_requests': performance['total_requests'],
                        'performance_grade': performance['performance_grade']
                    }
            
            # Calculate rankings
            rankings = {
                'success_rate': sorted(comparison.items(), 
                                     key=lambda x: x[1]['success_rate'], reverse=True),
                'response_time': sorted(comparison.items(), 
                                      key=lambda x: x[1]['avg_response_time']),
                'cost_efficiency': sorted(comparison.items(), 
                                        key=lambda x: x[1]['avg_cost_per_request']),
                'overall_performance': sorted(comparison.items(), 
                                            key=lambda x: x[1]['performance_grade'], reverse=True)
            }
            
            return {
                'time_range': str(time_range) if time_range else 'all_time',
                'comparison': comparison,
                'rankings': rankings,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            _logger.error(f"Failed to get provider comparison: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of data
        
        Args:
            data: List of values
            percentile: Percentile to calculate (0-100)
            
        Returns:
            Percentile value
        """
        if not data:
            return 0
        
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        
        if index.is_integer():
            return sorted_data[int(index)]
        else:
            lower = sorted_data[int(index)]
            upper = sorted_data[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))
    
    def _get_error_distribution(self, records: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get distribution of error types
        
        Args:
            records: List of request records
            
        Returns:
            Error distribution
        """
        error_counts = defaultdict(int)
        for record in records:
            if not record['success'] and record['error']:
                error_type = type(record['error']).__name__ if isinstance(record['error'], Exception) else str(record['error'])
                error_counts[error_type] += 1
        return dict(error_counts)
    
    def _get_task_distribution(self, records: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get distribution of task types
        
        Args:
            records: List of request records
            
        Returns:
            Task type distribution
        """
        task_counts = defaultdict(int)
        for record in records:
            task_counts[record['task_type']] += 1
        return dict(task_counts)
    
    def _calculate_performance_grade(self, provider: str, 
                                   records: List[Dict[str, Any]]) -> str:
        """Calculate performance grade for a provider
        
        Args:
            provider: Provider name
            records: List of request records
            
        Returns:
            Performance grade (A, B, C, D, F)
        """
        if not records:
            return 'N/A'
        
        # Calculate metrics
        success_rate = sum(1 for r in records if r['success']) / len(records)
        response_times = [r['response_time'] for r in records]
        avg_response_time = statistics.mean(response_times) if response_times else 0
        
        # Grade based on success rate and response time
        score = 0
        
        # Success rate component (60% of grade)
        if success_rate >= 0.95:
            score += 60
        elif success_rate >= 0.90:
            score += 50
        elif success_rate >= 0.85:
            score += 40
        elif success_rate >= 0.80:
            score += 30
        else:
            score += 20
        
        # Response time component (40% of grade)
        if avg_response_time <= 2.0:
            score += 40
        elif avg_response_time <= 5.0:
            score += 30
        elif avg_response_time <= 10.0:
            score += 20
        else:
            score += 10
        
        # Convert to letter grade
        if score >= 90:
            return 'A'
        elif score >= 80:
            return 'B'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'
    
    def _calculate_system_health(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate overall system health
        
        Args:
            records: List of request records
            
        Returns:
            System health metrics
        """
        if not records:
            return {'status': 'unknown', 'score': 0}
        
        # Calculate health metrics
        success_rate = sum(1 for r in records if r['success']) / len(records)
        response_times = [r['response_time'] for r in records]
        avg_response_time = statistics.mean(response_times) if response_times else 0
        
        # Calculate health score
        health_score = 0
        
        # Success rate (50% of health)
        if success_rate >= 0.95:
            health_score += 50
        elif success_rate >= 0.90:
            health_score += 40
        elif success_rate >= 0.85:
            health_score += 30
        else:
            health_score += 20
        
        # Response time (30% of health)
        if avg_response_time <= 2.0:
            health_score += 30
        elif avg_response_time <= 5.0:
            health_score += 25
        elif avg_response_time <= 10.0:
            health_score += 15
        else:
            health_score += 5
        
        # Provider diversity (20% of health)
        providers = set(r['provider'] for r in records)
        if len(providers) >= 3:
            health_score += 20
        elif len(providers) >= 2:
            health_score += 15
        else:
            health_score += 5
        
        # Determine status
        if health_score >= 90:
            status = 'excellent'
        elif health_score >= 80:
            status = 'good'
        elif health_score >= 70:
            status = 'fair'
        elif health_score >= 60:
            status = 'poor'
        else:
            status = 'critical'
        
        return {
            'status': status,
            'score': health_score,
            'success_rate': success_rate,
            'avg_response_time': avg_response_time,
            'provider_count': len(providers)
        }
    
    def reset_metrics(self, provider: Optional[str] = None):
        """Reset performance metrics
        
        Args:
            provider: Optional provider to reset (if None, reset all)
        """
        try:
            with self.lock:
                if provider:
                    if provider in self.provider_metrics:
                        del self.provider_metrics[provider]
                        _logger.info(f"Reset metrics for provider: {provider}")
                else:
                    self.provider_metrics.clear()
                    self.system_metrics = {
                        'total_requests': 0,
                        'total_successful': 0,
                        'total_failed': 0,
                        'total_cost': 0,
                        'total_tokens': 0,
                        'uptime_start': datetime.now(),
                        'last_health_check': None,
                        'consensus_accuracy': deque(maxlen=1000),
                        'user_satisfaction': deque(maxlen=1000)
                    }
                    self.request_history.clear()
                    self.alerts.clear()
                    self.trends = {
                        'hourly_stats': defaultdict(lambda: defaultdict(list)),
                        'daily_stats': defaultdict(lambda: defaultdict(list)),
                        'weekly_stats': defaultdict(lambda: defaultdict(list))
                    }
                    _logger.info("Reset all performance metrics")
                    
        except Exception as e:
            _logger.error(f"Failed to reset metrics: {str(e)}")
    
    def export_metrics(self, format: str = 'json') -> Union[str, Dict[str, Any]]:
        """Export performance metrics
        
        Args:
            format: Export format ('json', 'dict')
            
        Returns:
            Exported metrics
        """
        try:
            with self.lock:
                export_data = {
                    'system_metrics': dict(self.system_metrics),
                    'provider_metrics': dict(self.provider_metrics),
                    'recent_alerts': list(self.alerts)[-100:],  # Last 100 alerts
                    'export_timestamp': datetime.now().isoformat()
                }
                
                # Convert deques to lists for JSON serialization
                for provider, metrics in export_data['provider_metrics'].items():
                    for key, value in metrics.items():
                        if isinstance(value, deque):
                            metrics[key] = list(value)
                
                for key, value in export_data['system_metrics'].items():
                    if isinstance(value, deque):
                        export_data['system_metrics'][key] = list(value)
                
                if format == 'json':
                    return json.dumps(export_data, indent=2, default=str)
                else:
                    return export_data
                    
        except Exception as e:
            _logger.error(f"Failed to export metrics: {str(e)}")
            return {'error': str(e)} 