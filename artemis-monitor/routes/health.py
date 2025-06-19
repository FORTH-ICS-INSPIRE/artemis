"""
Health monitoring routes for ARTEMIS services.
"""
import asyncio
import logging
from flask import Blueprint, jsonify

from utils.config import load_config, get_services_map
from services.health_service import check_all_services_health

logger = logging.getLogger(__name__)

health_bp = Blueprint('health', __name__)


@health_bp.route('/health/all')
def get_all_services_health():
    """Get health status for all registered ARTEMIS services."""
    try:
        config = load_config()
        if not config:
            logger.error("Failed to load configuration")
            return jsonify({
                'error': 'Configuration not available',
                'success': False
            }), 500
        
        services = get_services_map(config)
        if not services:
            logger.warning("No services configured")
            return jsonify({
                'error': 'No services configured',
                'success': False
            }), 500
        
        logger.info(f"Checking health of {len(services)} services")
        health_data = asyncio.run(check_all_services_health(services))
        
        # Add metadata
        health_data['success'] = True
        
        summary = health_data.get('summary', {})
        running_count = summary.get('running_services', 0)
        total_count = summary.get('total_services', 0)
        
        if running_count == total_count and total_count > 0:
            overall_status = 'all_running'
        elif running_count > 0:
            overall_status = 'partially_running'
        else:
            overall_status = 'none_running'
        
        health_data['overall_status'] = overall_status
        
        logger.info(f"Health check completed: {overall_status}")
        return jsonify(health_data)
        
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}")
        return jsonify({
            'error': f'Health check failed: {str(e)}',
            'success': False
        }), 500 
