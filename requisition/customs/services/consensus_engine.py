import logging
import json
import statistics
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import numpy as np
from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class ConsensusEngine:
    """Consensus engine for combining multiple AI provider responses"""
    
    def __init__(self):
        """Initialize consensus engine"""
        self.consensus_methods = {
            'weighted_average': self._weighted_average_consensus,
            'majority_vote': self._majority_vote_consensus,
            'confidence_weighted': self._confidence_weighted_consensus,
            'provider_reliability': self._provider_reliability_consensus,
            'hybrid': self._hybrid_consensus
        }
        
        # Provider reliability scores (can be updated based on historical performance)
        self.provider_reliability = {
            'openai': 0.85,
            'claude': 0.88,
            'gemini': 0.82
        }
        
        # Task-specific provider strengths
        self.provider_strengths = {
            'sentiment_analysis': {
                'openai': 0.85,
                'claude': 0.90,
                'gemini': 0.80
            },
            'personality_assessment': {
                'openai': 0.88,
                'claude': 0.92,
                'gemini': 0.85
            },
            'resume_analysis': {
                'openai': 0.87,
                'claude': 0.89,
                'gemini': 0.86
            },
            'performance_analysis': {
                'openai': 0.86,
                'claude': 0.91,
                'gemini': 0.84
            },
            'chat_response': {
                'openai': 0.89,
                'claude': 0.87,
                'gemini': 0.83
            }
        }
    
    def generate_consensus(self, responses: List[Dict[str, Any]], 
                          task_type: str = 'general',
                          method: str = 'hybrid',
                          min_responses: int = 2) -> Dict[str, Any]:
        """Generate consensus from multiple AI responses
        
        Args:
            responses: List of responses from different AI providers
            task_type: Type of task for provider-specific weighting
            method: Consensus method to use
            min_responses: Minimum number of successful responses required
            
        Returns:
            Dict containing consensus result and metadata
        """
        try:
            # Filter successful responses
            successful_responses = [r for r in responses if r.get('success', False)]
            
            if len(successful_responses) < min_responses:
                return {
                    'success': False,
                    'error': f'Insufficient successful responses: {len(successful_responses)}/{min_responses}',
                    'responses_received': len(responses),
                    'successful_responses': len(successful_responses),
                    'timestamp': datetime.now().isoformat()
                }
            
            # Apply consensus method
            consensus_method = self.consensus_methods.get(method, self._hybrid_consensus)
            consensus_result = consensus_method(successful_responses, task_type)
            
            # Add metadata
            consensus_result.update({
                'consensus_method': method,
                'task_type': task_type,
                'total_responses': len(responses),
                'successful_responses': len(successful_responses),
                'providers_used': [r.get('provider', 'unknown') for r in successful_responses],
                'timestamp': datetime.now().isoformat()
            })
            
            return consensus_result
            
        except Exception as e:
            _logger.error(f"Consensus generation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _weighted_average_consensus(self, responses: List[Dict], task_type: str) -> Dict[str, Any]:
        """Generate consensus using weighted average of numerical values
        
        Args:
            responses: List of successful responses
            task_type: Task type for provider weighting
            
        Returns:
            Dict containing consensus result
        """
        try:
            # Extract numerical scores and weights
            scores = {}
            weights = {}
            
            for response in responses:
                provider = response.get('provider', 'unknown')
                weight = self.provider_strengths.get(task_type, {}).get(provider, 0.5)
                
                # Extract numerical values from response
                if isinstance(response.get('content'), dict):
                    content = response['content']
                elif isinstance(response.get('content'), str):
                    try:
                        content = json.loads(response['content'])
                    except json.JSONDecodeError:
                        continue
                else:
                    continue
                
                # Extract scores based on task type
                extracted_scores = self._extract_numerical_scores(content, task_type)
                
                for key, value in extracted_scores.items():
                    if key not in scores:
                        scores[key] = []
                        weights[key] = []
                    scores[key].append(value)
                    weights[key].append(weight)
            
            # Calculate weighted averages
            consensus_scores = {}
            for key in scores:
                if scores[key] and weights[key]:
                    weighted_sum = sum(s * w for s, w in zip(scores[key], weights[key]))
                    total_weight = sum(weights[key])
                    consensus_scores[key] = weighted_sum / total_weight if total_weight > 0 else 0
            
            return {
                'success': True,
                'consensus_scores': consensus_scores,
                'method': 'weighted_average',
                'confidence': self._calculate_confidence(responses, consensus_scores)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Weighted average consensus failed: {str(e)}'
            }
    
    def _majority_vote_consensus(self, responses: List[Dict], task_type: str) -> Dict[str, Any]:
        """Generate consensus using majority vote for categorical values
        
        Args:
            responses: List of successful responses
            task_type: Task type for context
            
        Returns:
            Dict containing consensus result
        """
        try:
            # Extract categorical values
            categorical_values = {}
            
            for response in responses:
                if isinstance(response.get('content'), dict):
                    content = response['content']
                elif isinstance(response.get('content'), str):
                    try:
                        content = json.loads(response['content'])
                    except json.JSONDecodeError:
                        continue
                else:
                    continue
                
                # Extract categorical values based on task type
                extracted_categories = self._extract_categorical_values(content, task_type)
                
                for key, value in extracted_categories.items():
                    if key not in categorical_values:
                        categorical_values[key] = []
                    categorical_values[key].append(value)
            
            # Calculate majority votes
            consensus_categories = {}
            for key, values in categorical_values.items():
                if values:
                    # Count occurrences
                    value_counts = {}
                    for value in values:
                        value_counts[value] = value_counts.get(value, 0) + 1
                    
                    # Find majority
                    max_count = max(value_counts.values())
                    majority_values = [v for v, c in value_counts.items() if c == max_count]
                    
                    consensus_categories[key] = {
                        'value': majority_values[0] if len(majority_values) == 1 else majority_values,
                        'confidence': max_count / len(values),
                        'vote_distribution': value_counts
                    }
            
            return {
                'success': True,
                'consensus_categories': consensus_categories,
                'method': 'majority_vote',
                'confidence': self._calculate_confidence(responses, consensus_categories)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Majority vote consensus failed: {str(e)}'
            }
    
    def _confidence_weighted_consensus(self, responses: List[Dict], task_type: str) -> Dict[str, Any]:
        """Generate consensus weighted by response confidence scores
        
        Args:
            responses: List of successful responses
            task_type: Task type for context
            
        Returns:
            Dict containing consensus result
        """
        try:
            weighted_responses = []
            
            for response in responses:
                # Extract confidence from response
                confidence = self._extract_confidence(response)
                provider = response.get('provider', 'unknown')
                
                # Combine response confidence with provider reliability
                provider_reliability = self.provider_reliability.get(provider, 0.5)
                combined_weight = confidence * provider_reliability
                
                weighted_responses.append({
                    'response': response,
                    'weight': combined_weight,
                    'confidence': confidence,
                    'provider_reliability': provider_reliability
                })
            
            # Sort by weight and use top responses for consensus
            weighted_responses.sort(key=lambda x: x['weight'], reverse=True)
            
            # Use weighted average with confidence weights
            return self._apply_confidence_weights(weighted_responses, task_type)
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Confidence weighted consensus failed: {str(e)}'
            }
    
    def _provider_reliability_consensus(self, responses: List[Dict], task_type: str) -> Dict[str, Any]:
        """Generate consensus based on provider reliability scores
        
        Args:
            responses: List of successful responses
            task_type: Task type for provider-specific reliability
            
        Returns:
            Dict containing consensus result
        """
        try:
            # Weight responses by provider reliability
            weighted_responses = []
            
            for response in responses:
                provider = response.get('provider', 'unknown')
                
                # Get task-specific reliability or general reliability
                task_reliability = self.provider_strengths.get(task_type, {}).get(provider)
                general_reliability = self.provider_reliability.get(provider, 0.5)
                reliability = task_reliability if task_reliability is not None else general_reliability
                
                weighted_responses.append({
                    'response': response,
                    'weight': reliability,
                    'provider': provider,
                    'reliability': reliability
                })
            
            # Generate consensus using reliability weights
            return self._apply_reliability_weights(weighted_responses, task_type)
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Provider reliability consensus failed: {str(e)}'
            }
    
    def _hybrid_consensus(self, responses: List[Dict], task_type: str) -> Dict[str, Any]:
        """Generate consensus using hybrid approach combining multiple methods
        
        Args:
            responses: List of successful responses
            task_type: Task type for context
            
        Returns:
            Dict containing consensus result
        """
        try:
            # Apply multiple consensus methods
            weighted_avg = self._weighted_average_consensus(responses, task_type)
            majority_vote = self._majority_vote_consensus(responses, task_type)
            confidence_weighted = self._confidence_weighted_consensus(responses, task_type)
            
            # Combine results intelligently
            hybrid_result = {
                'success': True,
                'method': 'hybrid',
                'numerical_consensus': weighted_avg.get('consensus_scores', {}),
                'categorical_consensus': majority_vote.get('consensus_categories', {}),
                'confidence_weighted_result': confidence_weighted,
                'overall_confidence': self._calculate_overall_confidence([
                    weighted_avg, majority_vote, confidence_weighted
                ])
            }
            
            # Generate final recommendation
            hybrid_result['final_recommendation'] = self._generate_final_recommendation(
                responses, hybrid_result, task_type
            )
            
            return hybrid_result
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Hybrid consensus failed: {str(e)}'
            }
    
    def _extract_numerical_scores(self, content: Dict, task_type: str) -> Dict[str, float]:
        """Extract numerical scores from response content
        
        Args:
            content: Response content dictionary
            task_type: Task type for context
            
        Returns:
            Dict of numerical scores
        """
        scores = {}
        
        # Common numerical fields to extract
        numerical_fields = [
            'confidence', 'score', 'rating', 'percentage', 'probability',
            'strength', 'intensity', 'level', 'match_score', 'overall_score'
        ]
        
        # Task-specific fields
        if task_type == 'personality_assessment':
            numerical_fields.extend([
                'openness', 'conscientiousness', 'extraversion', 
                'agreeableness', 'neuroticism'
            ])
        elif task_type == 'sentiment_analysis':
            numerical_fields.extend([
                'joy', 'anger', 'sadness', 'fear', 'surprise', 'disgust',
                'positive', 'negative', 'neutral'
            ])
        
        # Extract scores recursively
        def extract_recursive(obj, prefix=''):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    full_key = f"{prefix}_{key}" if prefix else key
                    if isinstance(value, (int, float)):
                        if any(field in key.lower() for field in numerical_fields):
                            scores[full_key] = float(value)
                    elif isinstance(value, dict):
                        extract_recursive(value, full_key)
                    elif isinstance(value, list) and value and isinstance(value[0], (int, float)):
                        scores[f"{full_key}_avg"] = sum(value) / len(value)
        
        extract_recursive(content)
        return scores
    
    def _extract_categorical_values(self, content: Dict, task_type: str) -> Dict[str, str]:
        """Extract categorical values from response content
        
        Args:
            content: Response content dictionary
            task_type: Task type for context
            
        Returns:
            Dict of categorical values
        """
        categories = {}
        
        # Common categorical fields
        categorical_fields = [
            'sentiment', 'category', 'classification', 'type', 'level',
            'status', 'recommendation', 'priority', 'risk_level'
        ]
        
        # Task-specific fields
        if task_type == 'sentiment_analysis':
            categorical_fields.extend(['overall_sentiment', 'tone', 'emotion'])
        elif task_type == 'performance_analysis':
            categorical_fields.extend(['performance_level', 'trend', 'status'])
        
        # Extract categories recursively
        def extract_recursive(obj, prefix=''):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    full_key = f"{prefix}_{key}" if prefix else key
                    if isinstance(value, str):
                        if any(field in key.lower() for field in categorical_fields):
                            categories[full_key] = value.lower().strip()
                    elif isinstance(value, dict):
                        extract_recursive(value, full_key)
        
        extract_recursive(content)
        return categories
    
    def _extract_confidence(self, response: Dict) -> float:
        """Extract confidence score from response
        
        Args:
            response: AI provider response
            
        Returns:
            Confidence score (0-1)
        """
        # Look for confidence in various places
        confidence_sources = [
            response.get('confidence'),
            response.get('content', {}).get('confidence') if isinstance(response.get('content'), dict) else None,
            response.get('metadata', {}).get('confidence'),
        ]
        
        for conf in confidence_sources:
            if conf is not None:
                try:
                    return float(conf) if 0 <= float(conf) <= 1 else float(conf) / 100
                except (ValueError, TypeError):
                    continue
        
        # Default confidence based on provider and response quality
        provider = response.get('provider', 'unknown')
        base_confidence = self.provider_reliability.get(provider, 0.5)
        
        # Adjust based on response completeness
        if response.get('content'):
            base_confidence += 0.1
        if response.get('tokens_used', 0) > 100:
            base_confidence += 0.05
        
        return min(base_confidence, 1.0)
    
    def _apply_confidence_weights(self, weighted_responses: List[Dict], task_type: str) -> Dict[str, Any]:
        """Apply confidence weights to generate consensus
        
        Args:
            weighted_responses: List of responses with weights
            task_type: Task type for context
            
        Returns:
            Consensus result
        """
        if not weighted_responses:
            return {'success': False, 'error': 'No weighted responses available'}
        
        # Use the highest confidence response as base
        best_response = weighted_responses[0]['response']
        
        # Calculate weighted average of numerical scores
        all_scores = {}
        total_weight = 0
        
        for wr in weighted_responses:
            weight = wr['weight']
            response = wr['response']
            
            if isinstance(response.get('content'), dict):
                content = response['content']
            elif isinstance(response.get('content'), str):
                try:
                    content = json.loads(response['content'])
                except json.JSONDecodeError:
                    continue
            else:
                continue
            
            scores = self._extract_numerical_scores(content, task_type)
            
            for key, value in scores.items():
                if key not in all_scores:
                    all_scores[key] = 0
                all_scores[key] += value * weight
            
            total_weight += weight
        
        # Normalize scores
        if total_weight > 0:
            for key in all_scores:
                all_scores[key] /= total_weight
        
        return {
            'success': True,
            'consensus_scores': all_scores,
            'best_response': best_response.get('content'),
            'confidence_weights': [wr['weight'] for wr in weighted_responses],
            'total_weight': total_weight
        }
    
    def _apply_reliability_weights(self, weighted_responses: List[Dict], task_type: str) -> Dict[str, Any]:
        """Apply reliability weights to generate consensus
        
        Args:
            weighted_responses: List of responses with reliability weights
            task_type: Task type for context
            
        Returns:
            Consensus result
        """
        # Similar to confidence weights but using reliability scores
        return self._apply_confidence_weights(weighted_responses, task_type)
    
    def _calculate_confidence(self, responses: List[Dict], consensus_result: Dict) -> float:
        """Calculate overall confidence in consensus result
        
        Args:
            responses: Original responses
            consensus_result: Generated consensus
            
        Returns:
            Confidence score (0-1)
        """
        if not responses:
            return 0.0
        
        # Base confidence on number of agreeing responses
        num_responses = len(responses)
        base_confidence = min(num_responses / 3, 1.0)  # Max confidence with 3+ responses
        
        # Adjust based on provider diversity
        providers = set(r.get('provider', 'unknown') for r in responses)
        diversity_bonus = len(providers) * 0.1
        
        # Adjust based on response consistency
        consistency_bonus = self._calculate_consistency(responses) * 0.2
        
        total_confidence = base_confidence + diversity_bonus + consistency_bonus
        return min(total_confidence, 1.0)
    
    def _calculate_overall_confidence(self, method_results: List[Dict]) -> float:
        """Calculate overall confidence across multiple consensus methods
        
        Args:
            method_results: Results from different consensus methods
            
        Returns:
            Overall confidence score
        """
        successful_methods = [r for r in method_results if r.get('success', False)]
        if not successful_methods:
            return 0.0
        
        # Average confidence across successful methods
        confidences = []
        for result in successful_methods:
            conf = result.get('confidence', 0.5)
            confidences.append(conf)
        
        return sum(confidences) / len(confidences) if confidences else 0.0
    
    def _calculate_consistency(self, responses: List[Dict]) -> float:
        """Calculate consistency score across responses
        
        Args:
            responses: List of responses to analyze
            
        Returns:
            Consistency score (0-1)
        """
        if len(responses) < 2:
            return 1.0
        
        # Extract numerical values for consistency check
        all_values = []
        for response in responses:
            if isinstance(response.get('content'), dict):
                content = response['content']
            elif isinstance(response.get('content'), str):
                try:
                    content = json.loads(response['content'])
                except json.JSONDecodeError:
                    continue
            else:
                continue
            
            values = []
            def extract_numbers(obj):
                if isinstance(obj, (int, float)):
                    values.append(float(obj))
                elif isinstance(obj, dict):
                    for v in obj.values():
                        extract_numbers(v)
                elif isinstance(obj, list):
                    for item in obj:
                        extract_numbers(item)
            
            extract_numbers(content)
            if values:
                all_values.append(values)
        
        if not all_values or len(all_values) < 2:
            return 0.5
        
        # Calculate coefficient of variation for consistency
        try:
            # Flatten all values
            flat_values = [v for sublist in all_values for v in sublist]
            if len(flat_values) < 2:
                return 0.5
            
            mean_val = statistics.mean(flat_values)
            std_val = statistics.stdev(flat_values)
            
            if mean_val == 0:
                return 1.0 if std_val == 0 else 0.0
            
            cv = std_val / abs(mean_val)
            consistency = max(0, 1 - cv)  # Lower CV = higher consistency
            return min(consistency, 1.0)
            
        except (statistics.StatisticsError, ZeroDivisionError):
            return 0.5
    
    def _generate_final_recommendation(self, responses: List[Dict], 
                                     hybrid_result: Dict, task_type: str) -> Dict[str, Any]:
        """Generate final recommendation based on consensus analysis
        
        Args:
            responses: Original responses
            hybrid_result: Hybrid consensus result
            task_type: Task type for context
            
        Returns:
            Final recommendation
        """
        try:
            recommendation = {
                'summary': 'Consensus analysis completed',
                'confidence_level': 'medium',
                'key_findings': [],
                'recommendations': [],
                'areas_of_agreement': [],
                'areas_of_disagreement': [],
                'next_steps': []
            }
            
            # Determine confidence level
            overall_confidence = hybrid_result.get('overall_confidence', 0.5)
            if overall_confidence >= 0.8:
                recommendation['confidence_level'] = 'high'
            elif overall_confidence >= 0.6:
                recommendation['confidence_level'] = 'medium'
            else:
                recommendation['confidence_level'] = 'low'
            
            # Extract key findings from numerical consensus
            numerical_consensus = hybrid_result.get('numerical_consensus', {})
            for key, value in numerical_consensus.items():
                if value > 0.7:  # High scores
                    recommendation['key_findings'].append(f"High {key}: {value:.2f}")
                elif value < 0.3:  # Low scores
                    recommendation['key_findings'].append(f"Low {key}: {value:.2f}")
            
            # Extract areas of agreement/disagreement
            categorical_consensus = hybrid_result.get('categorical_consensus', {})
            for key, data in categorical_consensus.items():
                confidence = data.get('confidence', 0)
                if confidence >= 0.8:
                    recommendation['areas_of_agreement'].append(f"{key}: {data.get('value')}")
                elif confidence <= 0.5:
                    recommendation['areas_of_disagreement'].append(f"{key}: {data.get('value')}")
            
            # Generate task-specific recommendations
            if task_type == 'sentiment_analysis':
                recommendation['recommendations'].extend([
                    'Monitor sentiment trends over time',
                    'Address any negative sentiment indicators',
                    'Leverage positive sentiment for engagement'
                ])
            elif task_type == 'performance_analysis':
                recommendation['recommendations'].extend([
                    'Focus on identified development areas',
                    'Leverage strengths for team contributions',
                    'Set specific improvement goals'
                ])
            elif task_type == 'resume_analysis':
                recommendation['recommendations'].extend([
                    'Conduct structured interview based on findings',
                    'Verify key qualifications and experience',
                    'Assess cultural fit during interview process'
                ])
            
            # Add next steps based on confidence level
            if recommendation['confidence_level'] == 'high':
                recommendation['next_steps'].append('Proceed with high confidence in analysis')
            elif recommendation['confidence_level'] == 'medium':
                recommendation['next_steps'].append('Consider additional validation')
            else:
                recommendation['next_steps'].append('Seek human expert review')
            
            return recommendation
            
        except Exception as e:
            return {
                'summary': 'Error generating recommendation',
                'error': str(e),
                'confidence_level': 'low'
            }
    
    def update_provider_reliability(self, provider: str, task_type: str, 
                                  performance_score: float):
        """Update provider reliability scores based on performance
        
        Args:
            provider: Provider name
            task_type: Task type
            performance_score: Performance score (0-1)
        """
        try:
            # Update general reliability
            current_reliability = self.provider_reliability.get(provider, 0.5)
            # Use exponential moving average for updates
            alpha = 0.1  # Learning rate
            new_reliability = alpha * performance_score + (1 - alpha) * current_reliability
            self.provider_reliability[provider] = new_reliability
            
            # Update task-specific reliability
            if task_type not in self.provider_strengths:
                self.provider_strengths[task_type] = {}
            
            current_task_reliability = self.provider_strengths[task_type].get(provider, 0.5)
            new_task_reliability = alpha * performance_score + (1 - alpha) * current_task_reliability
            self.provider_strengths[task_type][provider] = new_task_reliability
            
            _logger.info(f"Updated reliability for {provider} on {task_type}: {new_task_reliability:.3f}")
            
        except Exception as e:
            _logger.error(f"Failed to update provider reliability: {str(e)}")
    
    def get_provider_rankings(self, task_type: str = None) -> Dict[str, Any]:
        """Get provider rankings for a specific task type
        
        Args:
            task_type: Optional task type for specific rankings
            
        Returns:
            Provider rankings and statistics
        """
        if task_type and task_type in self.provider_strengths:
            rankings = self.provider_strengths[task_type]
        else:
            rankings = self.provider_reliability
        
        # Sort providers by reliability
        sorted_providers = sorted(rankings.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'task_type': task_type or 'general',
            'rankings': sorted_providers,
            'best_provider': sorted_providers[0][0] if sorted_providers else None,
            'average_reliability': sum(rankings.values()) / len(rankings) if rankings else 0,
            'timestamp': datetime.now().isoformat()
        } 