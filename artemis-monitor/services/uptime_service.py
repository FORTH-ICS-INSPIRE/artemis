"""
Uptime monitoring service for ARTEMIS Docker containers.
"""
import logging
from typing import Dict, Optional, Tuple, Any
import docker

logger = logging.getLogger(__name__)


def get_container_uptime(container: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract uptime from a container if it's running.
    
    Args:
        container: Docker container information dictionary
        
    Returns:
        Tuple of (service_name, uptime) or (None, None) if extraction fails
    """
    try:
        container_names = container.get('Names', [])
        if not container_names:
            logger.warning("Container has no names")
            return None, None
            
        name = container_names[0].lstrip('/')  # Remove leading slash
        service_name = name.replace('artemis_', '').split('_')[0]
        
        # Get container state and status
        state = container.get('State', '')
        status = container.get('Status', '')
        
        if state == 'running' and status.startswith('Up '):
            # Extract uptime from status string (e.g., "Up 2 hours")
            uptime = status.replace('Up ', '').split(' (')[0]
            logger.debug(f"Container {name} uptime: {uptime}")
            return service_name, uptime
        else:
            logger.debug(f"Container {name} not running: state={state}, status={status}")
            return service_name, None
            
    except Exception as e:
        container_name = container.get('Names', ['unknown'])[0] if container.get('Names') else 'unknown'
        logger.error(f"Failed to get uptime for container {container_name}: {str(e)}")
        return None, None


def get_artemis_uptime(services: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    """
    Get uptime of ARTEMIS containers using Docker Python API.
    
    Args:
        services: Optional dictionary of configured services for filtering
        
    Returns:
        Dictionary containing uptime information or None if operation fails
    """
    try:
        # Connect to Docker daemon
        try:
            client = docker.APIClient(base_url='unix://var/run/docker.sock')
            logger.debug("Connected to Docker daemon")
        except Exception as e:
            logger.error(f"Failed to connect to Docker daemon: {str(e)}")
            return None

        try:
            containers = client.containers(filters={'name': 'artemis_'})
            logger.info(f"Found {len(containers)} ARTEMIS containers")
        except Exception as e:
            logger.error(f"Failed to list containers: {str(e)}")
            return None

        # Process containers and collect uptimes
        uptimes = {}
        container_details = []
        
        for container in containers:
            service_name, uptime = get_container_uptime(container)
            
            if service_name:
                uptimes[service_name] = uptime if uptime else 'Not running'
                
                # Collect additional container details
                container_info = {
                    'service': service_name,
                    'uptime': uptime,
                    'status': container.get('Status', 'unknown'),
                    'state': container.get('State', 'unknown'),
                    'image': container.get('Image', 'unknown'),
                    'created': container.get('Created', 0)
                }
                container_details.append(container_info)
                
                if uptime:
                    logger.info(f"Service {service_name} uptime: {uptime}")
                else:
                    logger.warning(f"Service {service_name} is not running")

        # Filter by configured services if provided
        if services:
            filtered_uptimes = {}
            for service_name in services.keys():
                filtered_uptimes[service_name] = uptimes.get(service_name, 'Not found')
            uptimes = filtered_uptimes

        summary = _generate_uptime_summary(container_details, services)

        return {
            'uptimes': uptimes,
            'containers': container_details,
            'summary': summary
        }

    except Exception as e:
        logger.error(f"Unexpected error getting ARTEMIS uptime: {str(e)}")
        return None


def _generate_uptime_summary(
    container_details: list, 
    services: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Generate summary statistics for container uptimes.
    
    Args:
        container_details: List of container information dictionaries
        services: Optional configured services for comparison
        
    Returns:
        Dictionary containing uptime summary statistics
    """
    if not container_details:
        return {
            'total_containers': 0,
            'running_containers': 0,
            'stopped_containers': 0,
            'monitoring_services': len(services) if services else 0,
            'missing_services': []
        }
    
    running_count = 0
    stopped_count = 0
    found_services = set()
    
    for container in container_details:
        if container.get('uptime'):
            running_count += 1
        else:
            stopped_count += 1
        
        service_name = container.get('service')
        if service_name:
            found_services.add(service_name)
    
    # Identify missing services
    missing_services = []
    if services:
        configured_services = set(services.keys())
        missing_services = list(configured_services - found_services)
    
    return {
        'total_containers': len(container_details),
        'running_containers': running_count,
        'stopped_containers': stopped_count,
        'monitoring_services': len(services) if services else 0,
        'missing_services': missing_services,
        'service_coverage': (
            len(found_services) / len(services) * 100 
            if services else 100
        )
    } 
