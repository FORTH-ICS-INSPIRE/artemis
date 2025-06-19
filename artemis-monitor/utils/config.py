"""
Configuration management utilities for health monitor.
"""
import logging
import yaml
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


def load_config(config_path: str = 'config.yaml') -> Optional[Dict[str, Any]]:
    """
    Load service configuration from YAML file.
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        Dictionary containing configuration or None if loading fails
    """
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            logger.info(f"Successfully loaded configuration from {config_path}")
            return config
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        return None
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML in {config_path}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Failed to load {config_path}: {str(e)}")
        return None


def build_service_url(host: str, port: int, endpoint: str) -> str:
    """
    Build service URL from components.
    
    Args:
        host: Service hostname
        port: Service port number
        endpoint: API endpoint path
        
    Returns:
        Complete service URL
    """
    return f"http://{host}:{port}{endpoint}"


def get_services_map(config: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """
    Create mapping of service IDs to their health check URLs.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Dictionary mapping service IDs to URLs
    """
    if not config or 'services' not in config:
        logger.warning("No services configuration found")
        return {}
        
    services = {}
    for service_id, info in config['services'].items():
        try:
            url = build_service_url(
                host=info['host'],
                port=info['port'],
                endpoint=info['endpoint']
            )
            services[service_id] = url
            logger.debug(f"Configured service {service_id}: {url}")
        except KeyError as e:
            logger.error(f"Missing required field {e} for service {service_id}")
        except Exception as e:
            logger.error(f"Error processing service {service_id}: {str(e)}")
            
    logger.info(f"Configured {len(services)} services")
    return services 
