"""
Analytics service for BGP data analysis and statistics generation.
"""
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def analyze_bgp_updates(bgp_updates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze BGP updates and provide comprehensive summary statistics.
    
    Args:
        bgp_updates: List of BGP update records
        
    Returns:
        Dictionary containing detailed analytics
    """
    if not bgp_updates:
        return _get_empty_bgp_analytics()
    
    prefixes = set()
    origin_asns = set()
    peer_asns = set()
    services = set()
    timestamps = []
    announcement_count = 0
    withdrawal_count = 0
    handled_count = 0
    
    # Process each update
    for update in bgp_updates:
        try:
            # Count by type
            update_type = update.get('type')
            if update_type == 'A':
                announcement_count += 1
            elif update_type == 'W':
                withdrawal_count += 1
            
            if update.get('handled'):
                handled_count += 1
            
            if update.get('prefix'):
                prefixes.add(update['prefix'])
            if update.get('origin_as'):
                origin_asns.add(update['origin_as'])
            if update.get('peer_asn'):
                peer_asns.add(update['peer_asn'])
            if update.get('service'):
                services.add(update['service'])
            if update.get('timestamp'):
                timestamps.append(update['timestamp'])
                
        except Exception as e:
            logger.warning(f"Error processing BGP update: {str(e)}")
            continue
    
    analytics = {
        'total_count': len(bgp_updates),
        'announcement_count': announcement_count,
        'withdrawal_count': withdrawal_count,
        'unique_prefixes': len(prefixes),
        'unique_origin_asns': len(origin_asns),
        'unique_peer_asns': len(peer_asns),
        'handled_count': handled_count,
        'unhandled_count': len(bgp_updates) - handled_count,
        'services': sorted(list(services)),
        'latest_timestamp': max(timestamps) if timestamps else None,
        'oldest_timestamp': min(timestamps) if timestamps else None
    }
    
    logger.debug(f"BGP analytics: {analytics['total_count']} updates analyzed")
    return analytics


def analyze_hijacks(hijacks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze hijacks and provide comprehensive summary statistics.
    
    Args:
        hijacks: List of hijack records
        
    Returns:
        Dictionary containing detailed analytics
    """
    if not hijacks:
        return _get_empty_hijack_analytics()
    
    prefixes = set()
    hijacker_asns = set()
    detection_times = []
    
    active_count = 0
    resolved_count = 0
    ignored_count = 0
    withdrawn_count = 0
    under_mitigation_count = 0
    dormant_count = 0
    seen_count = 0
    
    # Process each hijack
    for hijack in hijacks:
        try:
            if hijack.get('active'):
                active_count += 1
            if hijack.get('resolved'):
                resolved_count += 1
            if hijack.get('ignored'):
                ignored_count += 1
            if hijack.get('withdrawn'):
                withdrawn_count += 1
            if hijack.get('under_mitigation'):
                under_mitigation_count += 1
            if hijack.get('dormant'):
                dormant_count += 1
            if hijack.get('seen'):
                seen_count += 1
            
            if hijack.get('prefix'):
                prefixes.add(hijack['prefix'])
            if hijack.get('hijack_as'):
                hijacker_asns.add(hijack['hijack_as'])
            if hijack.get('time_detected'):
                detection_times.append(hijack['time_detected'])
                
        except Exception as e:
            logger.warning(f"Error processing hijack: {str(e)}")
            continue
    
    analytics = {
        'total_count': len(hijacks),
        'active_count': active_count,
        'resolved_count': resolved_count,
        'ignored_count': ignored_count,
        'withdrawn_count': withdrawn_count,
        'under_mitigation_count': under_mitigation_count,
        'dormant_count': dormant_count,
        'seen_count': seen_count,
        'unique_prefixes': len(prefixes),
        'unique_hijacker_asns': len(hijacker_asns),
        'latest_detection': max(detection_times) if detection_times else None,
        'oldest_detection': min(detection_times) if detection_times else None
    }
    
    logger.debug(f"Hijack analytics: {analytics['total_count']} hijacks analyzed")
    return analytics


def generate_summary_analytics(
    bgp_analytics: Dict[str, Any], 
    hijack_analytics: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate overall summary analytics across both BGP updates and hijacks.
    
    Args:
        bgp_analytics: BGP updates analytics
        hijack_analytics: Hijacks analytics
        
    Returns:
        Dictionary containing overall summary
    """
    total_bgp_updates = bgp_analytics.get('total_count', 0)
    total_hijacks = hijack_analytics.get('total_count', 0)
    
    return {
        'total_bgp_updates': total_bgp_updates,
        'total_hijacks': total_hijacks,
        'active_threats': hijack_analytics.get('active_count', 0),
        'unhandled_updates': bgp_analytics.get('unhandled_count', 0),
        'data_freshness': 'recent' if total_bgp_updates > 0 or total_hijacks > 0 else 'no_data',
        'security_status': _determine_security_status(hijack_analytics),
        'processing_status': _determine_processing_status(bgp_analytics)
    }


def _get_empty_bgp_analytics() -> Dict[str, Any]:
    """Return empty BGP analytics structure."""
    return {
        'total_count': 0,
        'announcement_count': 0,
        'withdrawal_count': 0,
        'unique_prefixes': 0,
        'unique_origin_asns': 0,
        'unique_peer_asns': 0,
        'handled_count': 0,
        'unhandled_count': 0,
        'services': [],
        'latest_timestamp': None,
        'oldest_timestamp': None
    }


def _get_empty_hijack_analytics() -> Dict[str, Any]:
    """Return empty hijack analytics structure."""
    return {
        'total_count': 0,
        'active_count': 0,
        'resolved_count': 0,
        'ignored_count': 0,
        'withdrawn_count': 0,
        'under_mitigation_count': 0,
        'dormant_count': 0,
        'seen_count': 0,
        'unique_prefixes': 0,
        'unique_hijacker_asns': 0,
        'latest_detection': None,
        'oldest_detection': None
    }


def _determine_security_status(hijack_analytics: Dict[str, Any]) -> str:
    """Determine overall security status based on hijack data."""
    active_count = hijack_analytics.get('active_count', 0)
    under_mitigation_count = hijack_analytics.get('under_mitigation_count', 0)
    
    if active_count > 0:
        return 'critical' if active_count > 5 else 'warning'
    elif under_mitigation_count > 0:
        return 'monitoring'
    else:
        return 'secure'


def _determine_processing_status(bgp_analytics: Dict[str, Any]) -> str:
    """Determine processing status based on BGP update handling."""
    total_count = bgp_analytics.get('total_count', 0)
    unhandled_count = bgp_analytics.get('unhandled_count', 0)
    
    if total_count == 0:
        return 'no_data'
    
    unhandled_ratio = unhandled_count / total_count if total_count > 0 else 0
    
    if unhandled_ratio > 0.8:
        return 'backlog'
    elif unhandled_ratio > 0.5:
        return 'delayed'
    else:
        return 'current' 
