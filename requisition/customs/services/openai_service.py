import openai
import logging
import json
import time
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
import numpy as np
from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class OpenAIService:
    """OpenAI service provider for the OmniHR AI Platform"""
    
    def __init__(self, api_key: str, organization: Optional[str] = None):
        """Initialize OpenAI service
        
        Args:
            api_key: OpenAI API key
            organization: Optional organization ID
        """
        self.api_key = api_key
        self.organization = organization
        self.client = None
        self._initialize_client()
        
        # Rate limiting
        self.rate_limits = {
            'requests_per_minute': 3500,
            'tokens_per_minute': 90000,
            'requests_per_day': 10000
        }
        self.request_history = []
        self.token_usage = []
        
        # Model configurations
        self.models = {
            'gpt-4-turbo': {
                'max_tokens': 128000,
                'cost_per_1k_input': 0.01,
                'cost_per_1k_output': 0.03,
                'capabilities': ['text', 'analysis', 'reasoning']
            },
            'gpt-4': {
                'max_tokens': 8192,
                'cost_per_1k_input': 0.03,
                'cost_per_1k_output': 0.06,
                'capabilities': ['text', 'analysis', 'reasoning']
            },
            'gpt-3.5-turbo': {
                'max_tokens': 16385,
                'cost_per_1k_input': 0.0015,
                'cost_per_1k_output': 0.002,
                'capabilities': ['text', 'chat']
            },
            'text-embedding-3-large': {
                'max_tokens': 8191,
                'cost_per_1k_tokens': 0.00013,
                'capabilities': ['embeddings']
            },
            'text-embedding-3-small': {
                'max_tokens': 8191,
                'cost_per_1k_tokens': 0.00002,
                'capabilities': ['embeddings']
            }
        }
        
    def _initialize_client(self):
        """Initialize OpenAI client"""
        try:
            openai.api_key = self.api_key
            if self.organization:
                openai.organization = self.organization
            self.client = openai
            _logger.info("OpenAI client initialized successfully")
        except Exception as e:
            _logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise UserError(_("Failed to initialize OpenAI client: %s") % str(e))
    
    def _check_rate_limits(self, estimated_tokens: int = 1000) -> bool:
        """Check if request is within rate limits
        
        Args:
            estimated_tokens: Estimated tokens for the request
            
        Returns:
            bool: True if within limits, False otherwise
        """
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        day_ago = now - timedelta(days=1)
        
        # Clean old entries
        self.request_history = [req for req in self.request_history if req['timestamp'] > day_ago]
        self.token_usage = [usage for usage in self.token_usage if usage['timestamp'] > minute_ago]
        
        # Check requests per minute
        recent_requests = [req for req in self.request_history if req['timestamp'] > minute_ago]
        if len(recent_requests) >= self.rate_limits['requests_per_minute']:
            return False
        
        # Check tokens per minute
        recent_tokens = sum(usage['tokens'] for usage in self.token_usage)
        if recent_tokens + estimated_tokens > self.rate_limits['tokens_per_minute']:
            return False
        
        # Check requests per day
        if len(self.request_history) >= self.rate_limits['requests_per_day']:
            return False
        
        return True
    
    def _log_request(self, tokens_used: int):
        """Log request for rate limiting
        
        Args:
            tokens_used: Number of tokens used in the request
        """
        now = datetime.now()
        self.request_history.append({'timestamp': now})
        self.token_usage.append({'timestamp': now, 'tokens': tokens_used})
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text
        
        Args:
            text: Input text
            
        Returns:
            int: Estimated token count
        """
        # Rough estimation: 1 token ≈ 4 characters
        return len(text) // 4
    
    def generate_text(self, prompt: str, model: str = "gpt-4-turbo", 
                     max_tokens: Optional[int] = None, temperature: float = 0.7,
                     system_message: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Generate text using OpenAI models
        
        Args:
            prompt: Input prompt
            model: Model to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system_message: Optional system message
            **kwargs: Additional parameters
            
        Returns:
            Dict containing response and metadata
        """
        try:
            # Estimate tokens
            estimated_tokens = self._estimate_tokens(prompt)
            if system_message:
                estimated_tokens += self._estimate_tokens(system_message)
            
            # Check rate limits
            if not self._check_rate_limits(estimated_tokens):
                raise UserError(_("Rate limit exceeded. Please try again later."))
            
            # Prepare messages
            messages = []
            if system_message:
                messages.append({"role": "system", "content": system_message})
            messages.append({"role": "user", "content": prompt})
            
            # Set default max_tokens if not provided
            if max_tokens is None:
                max_tokens = min(4000, self.models.get(model, {}).get('max_tokens', 4000))
            
            # Make API call
            start_time = time.time()
            response = self.client.ChatCompletion.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            
            # Calculate metrics
            response_time = time.time() - start_time
            tokens_used = response.usage.total_tokens
            
            # Log request
            self._log_request(tokens_used)
            
            # Calculate cost
            model_config = self.models.get(model, {})
            input_cost = (response.usage.prompt_tokens / 1000) * model_config.get('cost_per_1k_input', 0)
            output_cost = (response.usage.completion_tokens / 1000) * model_config.get('cost_per_1k_output', 0)
            total_cost = input_cost + output_cost
            
            return {
                'success': True,
                'content': response.choices[0].message.content,
                'model': model,
                'tokens_used': tokens_used,
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'response_time': response_time,
                'cost': total_cost,
                'finish_reason': response.choices[0].finish_reason,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            _logger.error(f"OpenAI text generation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'model': model,
                'timestamp': datetime.now().isoformat()
            }
    
    def generate_embeddings(self, texts: Union[str, List[str]], 
                          model: str = "text-embedding-3-large") -> Dict[str, Any]:
        """Generate embeddings using OpenAI models
        
        Args:
            texts: Text or list of texts to embed
            model: Embedding model to use
            
        Returns:
            Dict containing embeddings and metadata
        """
        try:
            # Ensure texts is a list
            if isinstance(texts, str):
                texts = [texts]
            
            # Estimate tokens
            total_tokens = sum(self._estimate_tokens(text) for text in texts)
            
            # Check rate limits
            if not self._check_rate_limits(total_tokens):
                raise UserError(_("Rate limit exceeded. Please try again later."))
            
            # Make API call
            start_time = time.time()
            response = self.client.Embedding.create(
                model=model,
                input=texts
            )
            
            # Calculate metrics
            response_time = time.time() - start_time
            tokens_used = response.usage.total_tokens
            
            # Log request
            self._log_request(tokens_used)
            
            # Calculate cost
            model_config = self.models.get(model, {})
            cost = (tokens_used / 1000) * model_config.get('cost_per_1k_tokens', 0)
            
            # Extract embeddings
            embeddings = [item.embedding for item in response.data]
            
            return {
                'success': True,
                'embeddings': embeddings,
                'model': model,
                'tokens_used': tokens_used,
                'response_time': response_time,
                'cost': cost,
                'dimensions': len(embeddings[0]) if embeddings else 0,
                'count': len(embeddings),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            _logger.error(f"OpenAI embedding generation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'model': model,
                'timestamp': datetime.now().isoformat()
            }
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment using OpenAI
        
        Args:
            text: Text to analyze
            
        Returns:
            Dict containing sentiment analysis
        """
        prompt = f"""
        Analyze the sentiment of the following text and provide a detailed breakdown:
        
        Text: "{text}"
        
        Please provide:
        1. Overall sentiment (positive, negative, neutral) with confidence score (0-1)
        2. Emotional breakdown (joy, anger, sadness, fear, surprise, disgust) with scores (0-1)
        3. Key phrases that indicate sentiment
        4. Sentiment intensity (low, medium, high)
        5. Any concerns or red flags
        
        Respond in JSON format.
        """
        
        system_message = """You are an expert sentiment analysis AI. Provide accurate, 
        detailed sentiment analysis in the requested JSON format."""
        
        response = self.generate_text(
            prompt=prompt,
            system_message=system_message,
            model="gpt-4-turbo",
            temperature=0.3
        )
        
        if response['success']:
            try:
                sentiment_data = json.loads(response['content'])
                sentiment_data.update({
                    'provider': 'openai',
                    'model': response['model'],
                    'tokens_used': response['tokens_used'],
                    'cost': response['cost']
                })
                return sentiment_data
            except json.JSONDecodeError:
                return {
                    'error': 'Failed to parse sentiment analysis response',
                    'raw_response': response['content']
                }
        else:
            return response
    
    def assess_personality(self, text: str) -> Dict[str, Any]:
        """Assess personality traits using OpenAI
        
        Args:
            text: Text to analyze for personality traits
            
        Returns:
            Dict containing personality assessment
        """
        prompt = f"""
        Analyze the personality traits of the person based on the following text:
        
        Text: "{text}"
        
        Please provide:
        1. Big Five personality traits (Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism) with scores (0-100)
        2. Communication style assessment
        3. Leadership potential indicators
        4. Team collaboration traits
        5. Stress management indicators
        6. Key personality insights
        7. Potential strengths and areas for development
        
        Respond in JSON format with detailed explanations.
        """
        
        system_message = """You are an expert personality assessment AI with deep knowledge 
        of psychology and personality theory. Provide accurate, professional assessments."""
        
        response = self.generate_text(
            prompt=prompt,
            system_message=system_message,
            model="gpt-4-turbo",
            temperature=0.3
        )
        
        if response['success']:
            try:
                personality_data = json.loads(response['content'])
                personality_data.update({
                    'provider': 'openai',
                    'model': response['model'],
                    'tokens_used': response['tokens_used'],
                    'cost': response['cost']
                })
                return personality_data
            except json.JSONDecodeError:
                return {
                    'error': 'Failed to parse personality assessment response',
                    'raw_response': response['content']
                }
        else:
            return response
    
    def analyze_resume(self, resume_text: str, job_description: str = None) -> Dict[str, Any]:
        """Analyze resume using OpenAI
        
        Args:
            resume_text: Resume content to analyze
            job_description: Optional job description for matching
            
        Returns:
            Dict containing resume analysis
        """
        prompt = f"""
        Analyze the following resume and provide a comprehensive assessment:
        
        Resume: "{resume_text}"
        """
        
        if job_description:
            prompt += f"\n\nJob Description: \"{job_description}\""
            prompt += "\n\nPlease also provide job matching analysis."
        
        prompt += """
        
        Please provide:
        1. Skills extraction and categorization (technical, soft, domain-specific)
        2. Experience analysis (years, roles, progression)
        3. Education assessment
        4. Achievements and accomplishments
        5. Overall candidate strength assessment (0-100)
        6. Red flags or concerns
        7. Recommendations for improvement
        """
        
        if job_description:
            prompt += """
            8. Job match score (0-100)
            9. Matching skills and experience
            10. Gaps and missing requirements
            11. Interview focus areas
            """
        
        prompt += "\n\nRespond in JSON format with detailed analysis."
        
        system_message = """You are an expert HR recruiter and resume analyst. 
        Provide thorough, professional resume assessments."""
        
        response = self.generate_text(
            prompt=prompt,
            system_message=system_message,
            model="gpt-4-turbo",
            temperature=0.3
        )
        
        if response['success']:
            try:
                resume_data = json.loads(response['content'])
                resume_data.update({
                    'provider': 'openai',
                    'model': response['model'],
                    'tokens_used': response['tokens_used'],
                    'cost': response['cost']
                })
                return resume_data
            except json.JSONDecodeError:
                return {
                    'error': 'Failed to parse resume analysis response',
                    'raw_response': response['content']
                }
        else:
            return response
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get service health status
        
        Returns:
            Dict containing health information
        """
        try:
            # Test with a simple request
            test_response = self.generate_text(
                prompt="Hello",
                model="gpt-3.5-turbo",
                max_tokens=10
            )
            
            return {
                'status': 'healthy' if test_response['success'] else 'unhealthy',
                'provider': 'openai',
                'available_models': list(self.models.keys()),
                'rate_limit_status': {
                    'requests_remaining': max(0, self.rate_limits['requests_per_minute'] - len([
                        req for req in self.request_history 
                        if req['timestamp'] > datetime.now() - timedelta(minutes=1)
                    ])),
                    'tokens_remaining': max(0, self.rate_limits['tokens_per_minute'] - sum([
                        usage['tokens'] for usage in self.token_usage
                        if usage['timestamp'] > datetime.now() - timedelta(minutes=1)
                    ]))
                },
                'last_check': datetime.now().isoformat(),
                'test_response': test_response
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'provider': 'openai',
                'error': str(e),
                'last_check': datetime.now().isoformat()
            }
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics
        
        Returns:
            Dict containing usage stats
        """
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)
        
        recent_requests = [req for req in self.request_history if req['timestamp'] > hour_ago]
        daily_requests = [req for req in self.request_history if req['timestamp'] > day_ago]
        recent_tokens = [usage for usage in self.token_usage if usage['timestamp'] > hour_ago]
        
        return {
            'provider': 'openai',
            'requests_last_hour': len(recent_requests),
            'requests_last_day': len(daily_requests),
            'tokens_last_hour': sum(usage['tokens'] for usage in recent_tokens),
            'average_response_time': 0,  # Would need to track this
            'total_cost_estimate': 0,  # Would need to track this
            'timestamp': now.isoformat()
        } 