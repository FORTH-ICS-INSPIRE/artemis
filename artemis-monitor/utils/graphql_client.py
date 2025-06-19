"""
GraphQL client utilities for ARTEMIS API communication.
"""
import asyncio
import json
import logging
import ssl
import os
from typing import Optional, Dict, Any
import aiohttp

logger = logging.getLogger(__name__)

NGINX_HOST = os.getenv('NGINX_HOST', 'nginx')
GRAPHQL_BASE_URL = f"https://{NGINX_HOST}:443"
GRAPHQL_URL = f"{GRAPHQL_BASE_URL}/api/graphql"


async def fetch_graphql_data(
    session: aiohttp.ClientSession, 
    jwt_token: str, 
    query: str
) -> Optional[Dict[str, Any]]:
    """
    Fetch data from GraphQL endpoint with JWT authentication and improved error handling.
    
    Args:
        session: Async HTTP client session
        jwt_token: JWT authentication token
        query: GraphQL query string
        
    Returns:
        GraphQL response data or None if request fails
    """
    try:
        # Create SSL context for self-signed certificates if using HTTPS
        ssl_context = None
        if GRAPHQL_URL.startswith('https://'):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {jwt_token}'
        }
        
        payload = {'query': query}
        
        async with session.post(
            GRAPHQL_URL, 
            json=payload, 
            headers=headers,
            ssl=ssl_context,
            timeout=30
        ) as response:
            response_text = await response.text()
            
            if response.status == 200:
                try:
                    data = json.loads(response_text)
                    if 'errors' in data:
                        logger.error(f"GraphQL query errors: {data['errors']}")
                        return None
                    return data
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse GraphQL response: {str(e)}")
                    return None
            else:
                logger.error(f"GraphQL request failed with status: {response.status}")
                logger.error(f"Response: {response_text}")
                return None
                
    except asyncio.TimeoutError:
        logger.error("GraphQL request timed out")
        return None
    except Exception as e:
        logger.error(f"GraphQL request error: {str(e)}")
        return None


async def fetch_bgp_updates(
    session: aiohttp.ClientSession, 
    jwt_token: str, 
    limit: int = 10
) -> Optional[Dict[str, Any]]:
    """
    Fetch recent BGP updates with improved query structure.
    
    Args:
        session: Async HTTP client session
        jwt_token: JWT authentication token
        limit: Maximum number of updates to fetch
        
    Returns:
        BGP updates data or None if request fails
    """
    query = f"""
    query GetBGPUpdates {{
        view_bgpupdates(limit: {limit}, order_by: {{timestamp: desc}}) {{
            as_path
            communities
            handled
            hijack_key
            matched_prefix
            orig_path
            origin_as
            peer_asn
            prefix
            service
            timestamp
            type
        }}
    }}
    """
    return await fetch_graphql_data(session, jwt_token, query)


async def fetch_hijacks(
    session: aiohttp.ClientSession, 
    jwt_token: str, 
    limit: int = 10
) -> Optional[Dict[str, Any]]:
    """
    Fetch recent hijacks with improved query structure.
    
    Args:
        session: Async HTTP client session
        jwt_token: JWT authentication token
        limit: Maximum number of hijacks to fetch
        
    Returns:
        Hijacks data or None if request fails
    """
    query = f"""
    query GetHijacks {{
        view_hijacks(limit: {limit}, order_by: {{time_last: desc}}) {{
            active
            comment
            configured_prefix
            hijack_as
            ignored
            dormant
            key
            mitigation_started
            num_asns_inf
            num_peers_seen
            outdated
            peers_seen
            peers_withdrawn
            prefix
            resolved
            seen
            time_detected
            time_ended
            time_last
            time_started
            timestamp_of_config
            type
            under_mitigation
            withdrawn
            community_annotation
            rpki_status
        }}
    }}
    """
    return await fetch_graphql_data(session, jwt_token, query) 
