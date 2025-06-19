"""
BGP monitoring routes for ARTEMIS BGP updates and hijacks.
"""
import asyncio
import logging
from flask import Blueprint, jsonify, request

from services.bgp_service import get_bgp_summary_data, get_bgp_updates_only, get_hijacks_only

logger = logging.getLogger(__name__)

bgp_bp = Blueprint('bgp', __name__)


@bgp_bp.route('/bgp/summary')
def get_bgp_summary():
    """Get aggregated BGP data (updates and hijacks) with enhanced analytics."""
    try:
        limit = request.args.get('limit', 10, type=int)
        logger.info(f"BGP summary requested with limit: {limit}")
        
        bgp_data = asyncio.run(get_bgp_summary_data(limit))
        
        return jsonify(bgp_data)
        
    except Exception as e:
        logger.error(f"Error in BGP summary endpoint: {str(e)}")
        return jsonify({
            'error': f'BGP summary failed: {str(e)}',
            'success': False
        }), 500


@bgp_bp.route('/bgp/updates')
def get_bgp_updates():
    """Get BGP updates data with analytics."""
    try:
        limit = request.args.get('limit', 10, type=int)
        logger.info(f"BGP updates requested with limit: {limit}")
        
        updates_data = asyncio.run(get_bgp_updates_only(limit))
        
        return jsonify(updates_data)
        
    except Exception as e:
        logger.error(f"Error in BGP updates endpoint: {str(e)}")
        return jsonify({
            'error': f'BGP updates fetch failed: {str(e)}',
            'success': False
        }), 500


@bgp_bp.route('/bgp/hijacks')
def get_hijacks():
    """Get hijacks data with analytics."""
    try:
        limit = request.args.get('limit', 10, type=int)
        logger.info(f"Hijacks requested with limit: {limit}")
        
        hijacks_data = asyncio.run(get_hijacks_only(limit))
        
        return jsonify(hijacks_data)
        
    except Exception as e:
        logger.error(f"Error in hijacks endpoint: {str(e)}")
        return jsonify({
            'error': f'Hijacks fetch failed: {str(e)}',
            'success': False
        }), 500
