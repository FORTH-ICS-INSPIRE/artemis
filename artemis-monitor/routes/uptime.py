"""
Uptime monitoring routes for ARTEMIS Docker containers.
"""
import logging
from flask import Blueprint, jsonify

from utils.config import load_config, get_services_map
from services.uptime_service import get_artemis_uptime

logger = logging.getLogger(__name__)

uptime_bp = Blueprint('uptime', __name__)


@uptime_bp.route('/uptime')
def get_uptime():
    """Get uptime information for ARTEMIS containers."""
    try:
        config = load_config()
        services = get_services_map(config) if config else None
        
        logger.info("Fetching ARTEMIS container uptime data")
        uptime_data = get_artemis_uptime(services)
        
        if uptime_data is None:
            logger.error("Failed to get uptime data")
            return jsonify({
                'error': 'Failed to retrieve uptime data',
                'success': False
            }), 500
        
        # Add metadata
        uptime_data['success'] = True
        
        # Determine overall uptime status
        summary = uptime_data.get('summary', {})
        running_count = summary.get('running_containers', 0)
        total_count = summary.get('total_containers', 0)
        
        if total_count == 0:
            overall_status = 'no_containers'
        elif running_count == total_count:
            overall_status = 'all_running'
        elif running_count > 0:
            overall_status = 'partially_running'
        else:
            overall_status = 'all_stopped'
        
        uptime_data['overall_status'] = overall_status
        
        logger.info(f"Uptime check completed: {overall_status} ({running_count}/{total_count} running)")
        return jsonify(uptime_data)
        
    except Exception as e:
        logger.error(f"Error getting uptime: {str(e)}")
        return jsonify({
            'error': f'Uptime check failed: {str(e)}',
            'success': False
        }), 500 
