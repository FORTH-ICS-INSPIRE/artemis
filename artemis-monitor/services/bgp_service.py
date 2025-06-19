"""
BGP monitoring service for ARTEMIS BGP updates and hijacks.
"""
import asyncio
import logging
import time
from typing import Dict, List, Any, Optional
import aiohttp

from auth import authenticate
from utils.graphql_client import fetch_bgp_updates, fetch_hijacks
from services.analytics_service import (
    analyze_bgp_updates, 
    analyze_hijacks, 
    generate_summary_analytics
)

logger = logging.getLogger(__name__)


async def get_bgp_summary_data(limit: int = 10) -> Dict[str, Any]:
    """
    Get comprehensive BGP summary including updates, hijacks, and analytics.
    
    Args:
        limit: Maximum number of records to fetch for each data type
        
    Returns:
        Dictionary containing BGP data and analytics
    """
    start_time = time.time()
    
    try:
        # Validate limit parameter
        limit = max(1, min(limit, 100))
        
        async with aiohttp.ClientSession() as session:
            # Authenticate and get JWT token
            jwt_token = await authenticate(session)
            if not jwt_token:
                logger.error("Authentication failed for BGP data fetch")
                return {
                    'error': 'Authentication failed',
                    'success': False,
                    'timestamp': time.time()
                }
            
            logger.info(f"Fetching BGP data with limit: {limit}")
            updates_task = fetch_bgp_updates(session, jwt_token, limit)
            hijacks_task = fetch_hijacks(session, jwt_token, limit)
            
            # Wait for both requests to complete
            updates_result, hijacks_result = await asyncio.gather(
                updates_task, hijacks_task, return_exceptions=True
            )
            
            bgp_updates = []
            hijacks = []
            
            if isinstance(updates_result, Exception):
                logger.error(f"Failed to fetch BGP updates: {str(updates_result)}")
            elif updates_result and 'data' in updates_result:
                bgp_updates = updates_result['data'].get('view_bgpupdates', [])
                logger.info(f"Fetched {len(bgp_updates)} BGP updates")
            else:
                logger.warning("No BGP updates data received")
            
            if isinstance(hijacks_result, Exception):
                logger.error(f"Failed to fetch hijacks: {str(hijacks_result)}")
            elif hijacks_result and 'data' in hijacks_result:
                hijacks = hijacks_result['data'].get('view_hijacks', [])
                logger.info(f"Fetched {len(hijacks)} hijacks")
            else:
                logger.warning("No hijacks data received")
            
            # Generate analytics
            bgp_analytics = analyze_bgp_updates(bgp_updates)
            hijack_analytics = analyze_hijacks(hijacks)
            summary_analytics = generate_summary_analytics(bgp_analytics, hijack_analytics)
            
            execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            result = {
                'success': True,
                'timestamp': time.time(),
                'query_limit': limit,
                'execution_time_ms': round(execution_time, 2),
                'bgp_updates': bgp_updates,
                'hijacks': hijacks,
                'analytics': {
                    'bgp_updates': bgp_analytics,
                    'hijacks': hijack_analytics,
                    'summary': summary_analytics
                }
            }
            
            logger.info(f"BGP summary completed in {execution_time:.2f}ms")
            return result
            
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        logger.error(f"Error getting BGP summary: {str(e)}")
        return {
            'error': f'Failed to get BGP summary: {str(e)}',
            'success': False,
            'timestamp': time.time(),
            'execution_time_ms': round(execution_time, 2)
        }


async def get_bgp_updates_only(limit: int = 10) -> Dict[str, Any]:
    """
    Get only BGP updates data with analytics.
    
    Args:
        limit: Maximum number of updates to fetch
        
    Returns:
        Dictionary containing BGP updates and analytics
    """
    try:
        limit = max(1, min(limit, 100))
        
        async with aiohttp.ClientSession() as session:
            jwt_token = await authenticate(session)
            if not jwt_token:
                return {'error': 'Authentication failed', 'success': False}
            
            updates_result = await fetch_bgp_updates(session, jwt_token, limit)
            
            if not updates_result or 'data' not in updates_result:
                return {'error': 'No BGP updates data received', 'success': False}
            
            bgp_updates = updates_result['data'].get('view_bgpupdates', [])
            analytics = analyze_bgp_updates(bgp_updates)
            
            return {
                'success': True,
                'timestamp': time.time(),
                'query_limit': limit,
                'bgp_updates': bgp_updates,
                'analytics': analytics
            }
            
    except Exception as e:
        logger.error(f"Error getting BGP updates: {str(e)}")
        return {
            'error': f'Failed to get BGP updates: {str(e)}',
            'success': False,
            'timestamp': time.time()
        }


async def get_hijacks_only(limit: int = 10) -> Dict[str, Any]:
    """
    Get only hijacks data with analytics.
    
    Args:
        limit: Maximum number of hijacks to fetch
        
    Returns:
        Dictionary containing hijacks and analytics
    """
    try:
        limit = max(1, min(limit, 100))
        
        async with aiohttp.ClientSession() as session:
            jwt_token = await authenticate(session)
            if not jwt_token:
                return {'error': 'Authentication failed', 'success': False}
            
            hijacks_result = await fetch_hijacks(session, jwt_token, limit)
            
            if not hijacks_result or 'data' not in hijacks_result:
                return {'error': 'No hijacks data received', 'success': False}
            
            hijacks = hijacks_result['data'].get('view_hijacks', [])
            analytics = analyze_hijacks(hijacks)
            
            return {
                'success': True,
                'timestamp': time.time(),
                'query_limit': limit,
                'hijacks': hijacks,
                'analytics': analytics
            }
            
    except Exception as e:
        logger.error(f"Error getting hijacks: {str(e)}")
        return {
            'error': f'Failed to get hijacks: {str(e)}',
            'success': False,
            'timestamp': time.time()
        } 
