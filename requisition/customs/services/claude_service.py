import anthropic
import logging
import json
import time
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class ClaudeService:
    """Claude service provider for the OmniHR AI Platform"""
    
    def __init__(self, api_key: str):
        """Initialize Claude service
        
        Args:
            api_key: Anthropic API key
        """
        self.api_key = api_key
        self.client = None
        self._initialize_client()
        
        # Rate limiting
        self.rate_limits = {
            'requests_per_minute': 1000,
            'tokens_per_minute': 40000,
            'requests_per_day': 5000
        }
        self.request_history = []
        self.token_usage = []
        
        # Model configurations
        self.models = {
            'claude-3-opus-20240229': {
                'max_tokens': 200000,
                'cost_per_1k_input': 0.015,
                'cost_per_1k_output': 0.075,
                'capabilities': ['text', 'analysis', 'reasoning', 'complex_tasks']
            },
            'claude-3-sonnet-20240229': {
                'max_tokens': 200000,
                'cost_per_1k_input': 0.003,
                'cost_per_1k_output': 0.015,
                'capabilities': ['text', 'analysis', 'reasoning']
            },
            'claude-3-haiku-20240307': {
                'max_tokens': 200000,
                'cost_per_1k_input': 0.00025,
                'cost_per_1k_output': 0.00125,
                'capabilities': ['text', 'chat', 'fast_response']
            }
        }
        
    def _initialize_client(self):
        """Initialize Claude client"""
        try:
            self.client = anthropic.Anthropic(api_key=self.api_key)
            _logger.info("Claude client initialized successfully")
        except Exception as e:
            _logger.error(f"Failed to initialize Claude client: {str(e)}")
            raise UserError(_("Failed to initialize Claude client: %s") % str(e))
    
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
        # Rough estimation: 1 token ≈ 3.5 characters for Claude
        return len(text) // 3.5
    
    def generate_text(self, prompt: str, model: str = "claude-3-sonnet-20240229", 
                     max_tokens: Optional[int] = None, temperature: float = 0.7,
                     system_message: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Generate text using Claude models
        
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
            
            # Set default max_tokens if not provided
            if max_tokens is None:
                max_tokens = min(4000, self.models.get(model, {}).get('max_tokens', 4000))
            
            # Prepare messages
            messages = [{"role": "user", "content": prompt}]
            
            # Make API call
            start_time = time.time()
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_message if system_message else "",
                messages=messages,
                **kwargs
            )
            
            # Calculate metrics
            response_time = time.time() - start_time
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            total_tokens = input_tokens + output_tokens
            
            # Log request
            self._log_request(total_tokens)
            
            # Calculate cost
            model_config = self.models.get(model, {})
            input_cost = (input_tokens / 1000) * model_config.get('cost_per_1k_input', 0)
            output_cost = (output_tokens / 1000) * model_config.get('cost_per_1k_output', 0)
            total_cost = input_cost + output_cost
            
            return {
                'success': True,
                'content': response.content[0].text,
                'model': model,
                'tokens_used': total_tokens,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'response_time': response_time,
                'cost': total_cost,
                'stop_reason': response.stop_reason,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            _logger.error(f"Claude text generation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'model': model,
                'timestamp': datetime.now().isoformat()
            }
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment using Claude
        
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
        6. Contextual nuances and subtleties
        
        Respond in JSON format with detailed explanations for each assessment.
        """
        
        system_message = """You are an expert sentiment analysis AI with deep understanding 
        of human emotions and communication patterns. Provide accurate, nuanced sentiment 
        analysis in the requested JSON format. Pay attention to context, sarcasm, and 
        subtle emotional indicators."""
        
        response = self.generate_text(
            prompt=prompt,
            system_message=system_message,
            model="claude-3-sonnet-20240229",
            temperature=0.3
        )
        
        if response['success']:
            try:
                sentiment_data = json.loads(response['content'])
                sentiment_data.update({
                    'provider': 'claude',
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
        """Assess personality traits using Claude
        
        Args:
            text: Text to analyze for personality traits
            
        Returns:
            Dict containing personality assessment
        """
        prompt = f"""
        Analyze the personality traits of the person based on the following text:
        
        Text: "{text}"
        
        Please provide:
        1. Big Five personality traits (Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism) with scores (0-100) and detailed explanations
        2. Communication style assessment (direct, diplomatic, analytical, emotional, etc.)
        3. Leadership potential indicators and specific traits
        4. Team collaboration traits and working style preferences
        5. Stress management indicators and coping mechanisms
        6. Decision-making style and problem-solving approach
        7. Key personality insights and behavioral patterns
        8. Potential strengths and areas for development
        9. Cultural and contextual considerations
        
        Respond in JSON format with detailed explanations and evidence from the text.
        """
        
        system_message = """You are an expert personality assessment AI with extensive 
        knowledge of psychology, personality theory, and human behavior. Provide thorough, 
        evidence-based personality assessments while being mindful of cultural differences 
        and avoiding stereotypes. Base your analysis on observable patterns in the text."""
        
        response = self.generate_text(
            prompt=prompt,
            system_message=system_message,
            model="claude-3-sonnet-20240229",
            temperature=0.3
        )
        
        if response['success']:
            try:
                personality_data = json.loads(response['content'])
                personality_data.update({
                    'provider': 'claude',
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
        """Analyze resume using Claude
        
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
            prompt += "\n\nPlease also provide detailed job matching analysis."
        
        prompt += """
        
        Please provide:
        1. Skills extraction and categorization (technical, soft, domain-specific, transferable)
        2. Experience analysis (years, roles, progression, achievements, impact)
        3. Education assessment (relevance, quality, additional certifications)
        4. Career trajectory and growth patterns
        5. Achievements and accomplishments with quantified impact
        6. Overall candidate strength assessment (0-100) with detailed reasoning
        7. Red flags or concerns with specific examples
        8. Recommendations for improvement and development areas
        9. Cultural fit indicators and work style preferences
        """
        
        if job_description:
            prompt += """
            10. Job match score (0-100) with detailed breakdown
            11. Matching skills and experience with relevance scores
            12. Gaps and missing requirements with severity assessment
            13. Interview focus areas and recommended questions
            14. Onboarding considerations and potential challenges
            15. Long-term potential and career growth alignment
            """
        
        prompt += "\n\nRespond in JSON format with detailed analysis and evidence-based assessments."
        
        system_message = """You are an expert HR recruiter and resume analyst with deep 
        experience in talent assessment. Provide thorough, professional resume assessments 
        that are fair, unbiased, and focused on job-relevant qualifications. Consider 
        diverse backgrounds and non-traditional career paths positively."""
        
        response = self.generate_text(
            prompt=prompt,
            system_message=system_message,
            model="claude-3-sonnet-20240229",
            temperature=0.3
        )
        
        if response['success']:
            try:
                resume_data = json.loads(response['content'])
                resume_data.update({
                    'provider': 'claude',
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
    
    def analyze_performance(self, performance_data: str) -> Dict[str, Any]:
        """Analyze performance data using Claude
        
        Args:
            performance_data: Performance information to analyze
            
        Returns:
            Dict containing performance analysis
        """
        prompt = f"""
        Analyze the following performance data and provide comprehensive insights:
        
        Performance Data: "{performance_data}"
        
        Please provide:
        1. Performance trends and patterns over time
        2. Strengths and areas of excellence
        3. Areas for improvement and development needs
        4. Goal achievement analysis
        5. Behavioral indicators and work patterns
        6. Risk factors and early warning signs
        7. Recommendations for performance improvement
        8. Career development suggestions
        9. Management and support strategies
        10. Predictive insights for future performance
        
        Respond in JSON format with actionable insights and recommendations.
        """
        
        system_message = """You are an expert performance analyst with deep understanding 
        of human performance, motivation, and development. Provide constructive, actionable 
        insights that focus on growth and improvement while being fair and supportive."""
        
        response = self.generate_text(
            prompt=prompt,
            system_message=system_message,
            model="claude-3-sonnet-20240229",
            temperature=0.3
        )
        
        if response['success']:
            try:
                performance_analysis = json.loads(response['content'])
                performance_analysis.update({
                    'provider': 'claude',
                    'model': response['model'],
                    'tokens_used': response['tokens_used'],
                    'cost': response['cost']
                })
                return performance_analysis
            except json.JSONDecodeError:
                return {
                    'error': 'Failed to parse performance analysis response',
                    'raw_response': response['content']
                }
        else:
            return response
    
    def generate_chat_response(self, message: str, context: str = None, 
                              conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Generate chat response using Claude
        
        Args:
            message: User message
            context: Optional context information
            conversation_history: Previous conversation messages
            
        Returns:
            Dict containing chat response
        """
        # Build conversation context
        conversation_context = ""
        if conversation_history:
            for msg in conversation_history[-10:]:  # Last 10 messages
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                conversation_context += f"{role}: {content}\n"
        
        prompt = f"""
        Previous conversation:
        {conversation_context}
        
        Current context: {context if context else 'General HR assistance'}
        
        User message: "{message}"
        
        Please provide a helpful, professional response as an HR AI assistant.
        """
        
        system_message = """You are a helpful HR AI assistant. Provide accurate, 
        professional, and empathetic responses to HR-related questions. Be supportive 
        while maintaining appropriate boundaries. If you're unsure about something, 
        acknowledge it and suggest consulting with HR professionals."""
        
        response = self.generate_text(
            prompt=prompt,
            system_message=system_message,
            model="claude-3-haiku-20240307",  # Faster model for chat
            temperature=0.7
        )
        
        if response['success']:
            return {
                'success': True,
                'response': response['content'],
                'provider': 'claude',
                'model': response['model'],
                'tokens_used': response['tokens_used'],
                'cost': response['cost'],
                'timestamp': response['timestamp']
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
                model="claude-3-haiku-20240307",
                max_tokens=10
            )
            
            return {
                'status': 'healthy' if test_response['success'] else 'unhealthy',
                'provider': 'claude',
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
                'provider': 'claude',
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
            'provider': 'claude',
            'requests_last_hour': len(recent_requests),
            'requests_last_day': len(daily_requests),
            'tokens_last_hour': sum(usage['tokens'] for usage in recent_tokens),
            'average_response_time': 0,  # Would need to track this
            'total_cost_estimate': 0,  # Would need to track this
            'timestamp': now.isoformat()
        } 