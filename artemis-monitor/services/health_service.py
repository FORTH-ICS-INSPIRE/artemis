"""
Health monitoring service for ARTEMIS services.
"""
import asyncio
import logging
import time
from typing import Dict, List, Any, Optional
import aiohttp

logger = logging.getLogger(__name__)


async def check_service_health(
    session: aiohttp.ClientSession, 
    service_name: str, 
    url: str
) -> Dict[str, Any]:
    """
    Check health status of a single service.
    
    Args:
        session: Async HTTP client session
        service_name: Name of the service being checked
        url: Health check URL for the service
        
    Returns:
        Dictionary containing service health information
    """
    try:
        start_time = time.time()
        async with session.get(url, timeout=5) as response:
            response_time = (time.time() - start_time) * 1000
            
            try:
                response_json = await response.json()
                service_status = response_json.get('status', 'unknown')
            except Exception:
                # If JSON parsing fails, determine status from HTTP code
                service_status = 'running' if response.status == 200 else 'error'
            
            result = {
                'service': service_name,
                'service_status': service_status,
                'response_time_ms': round(response_time, 2),
                'status_code': response.status,
                'url': url
            }
            
            logger.debug(f"Health check for {service_name}: {service_status} ({response_time:.2f}ms)")
            return result
            
    except asyncio.TimeoutError:
        logger.warning(f"Health check timeout for {service_name}")
        return {
            'service': service_name,
            'service_status': 'timeout',
            'error': f'Request timed out after 5 seconds',
            'url': url
        }
    except Exception as e:
        logger.error(f"Error checking {service_name}: {str(e)}")
        return {
            'service': service_name,
            'service_status': 'unreachable',
            'error': str(e),
            'url': url
        }


async def check_all_services_health(services: Dict[str, str]) -> Dict[str, Any]:
    """
    Check health status for all services concurrently.
    
    Args:
        services: Dictionary mapping service names to health check URLs
        
    Returns:
        Dictionary containing all service health results and summary
    """
    if not services:
        logger.warning("No services registered for health checking")
        return {
            'services': [],
            'summary': {
                'status_counts': {},
                'total_services': 0,
                'running_services': 0,
                'average_response_time_ms': 0
            }
        }
    
    results = []
    async with aiohttp.ClientSession() as session:
        tasks = [
            check_service_health(session, service_name, url)
            for service_name, url in services.items()
        ]
        
        # Execute all health checks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                service_name = list(services.keys())[i]
                logger.error(f"Health check failed for {service_name}: {str(result)}")
                processed_results.append({
                    'service': service_name,
                    'service_status': 'error',
                    'error': str(result),
                    'url': services[service_name]
                })
            else:
                processed_results.append(result)
        
        results = processed_results
    
    # Generate summary statistics
    summary = _generate_health_summary(results)
    
    logger.info(f"Health check completed: {summary['running_services']}/{summary['total_services']} services healthy")
    
    return {
        'services': results,
        'summary': summary
    }


def _generate_health_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate summary statistics from health check results.
    
    Args:
        results: List of health check results
        
    Returns:
        Dictionary containing summary statistics
    """
    if not results:
        return {
            'status_counts': {},
            'total_services': 0,
            'running_services': 0,
            'average_response_time_ms': 0
        }
    
    # Count statuses
    status_counts = {}
    response_times = []
    healthy_statuses = {'running'}
    running_count = 0
    
    for result in results:
        status = result.get('service_status', 'unknown')
        
        if ',' in status:
            status = status.split(',')[0].strip()
        
        status_counts[status] = status_counts.get(status, 0) + 1
        
        if status.lower() in healthy_statuses:
            running_count += 1
        
        response_time = result.get('response_time_ms')
        if response_time is not None:
            response_times.append(response_time)
    
    avg_response_time = (
        sum(response_times) / len(response_times) 
        if response_times else 0
    )
    
    return {
        'status_counts': status_counts,
        'total_services': len(results),
        'running_services': running_count,
        'average_response_time_ms': round(avg_response_time, 2)
    } 
