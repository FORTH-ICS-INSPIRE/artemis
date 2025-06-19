#!/usr/bin/env python
import aiohttp
import asyncio
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import sys
from rich import box
import time
import argparse
import json

console = Console()

MONITOR_BASE_URL = None

def get_health_api():
    return f"{MONITOR_BASE_URL}/health/all"

def get_uptime_api():
    return f"{MONITOR_BASE_URL}/uptime"

def get_bgp_summary_api():
    return f"{MONITOR_BASE_URL}/bgp/summary"

async def get_health_status(session):
    try:
        async with session.get(get_health_api(), timeout=10) as response:
            if response.status == 200:
                return await response.json()
            else:
                console.print(f"[red]Health API returned status {response.status}[/red]")
                return None
    except Exception as e:
        console.print(f"[red]Error getting health status: {str(e)}[/red]")
        return None

async def get_uptime_status(session):
    try:
        async with session.get(get_uptime_api(), timeout=10) as response:
            if response.status == 200:
                return await response.json()
            else:
                console.print(f"[yellow]Uptime API returned status {response.status}[/yellow]")
                return None
    except Exception as e:
        console.print(f"[yellow]Error getting uptime status: {str(e)}[/yellow]")
        return None

async def get_bgp_data(session):
    try:
        async with session.get(f"{get_bgp_summary_api()}?limit=10", timeout=15) as response:
            if response.status == 200:
                return await response.json()
            else:
                console.print(f"[yellow]BGP API returned status {response.status}[/yellow]")
                return None
    except Exception as e:
        console.print(f"[yellow]Error getting BGP data: {str(e)}[/yellow]")
        return None

def combine_health_and_uptime(health_data, uptime_data):
    """Combine health and uptime data for each service"""
    if not health_data or 'services' not in health_data:
        return health_data
    
    if not uptime_data or 'uptimes' not in uptime_data:
        return health_data
        
    # Add uptime information to health data
    for service in health_data['services']:
        service_name = service['service']
        if service_name in uptime_data['uptimes']:
            uptime_value = uptime_data['uptimes'][service_name]
            service['uptime'] = uptime_value if uptime_value != 'Not running' else 'N/A'
        else:
            service['uptime'] = 'N/A'
    
    return health_data

def print_service_table(services, status_filter, title):
    """Print a table of services filtered by status"""
    filtered_services = [s for s in services if s['service_status'] == status_filter]
    if not filtered_services:
        return False

    table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
    table.add_column("Service", no_wrap=True, width=20)
    table.add_column("Status", no_wrap=True, width=12)
    table.add_column("Code", no_wrap=True, width=8)
    table.add_column("Uptime", no_wrap=True, width=15)
    table.add_column("Response (ms)", no_wrap=True, width=15)
    table.add_column("Error", width=30)

    for service in filtered_services:
        status_color = {
            'running': 'green',
            'unconfigured': 'yellow',
            'unreachable': 'red',
            'error': 'red',
            'stopped': 'red',
            'timeout': 'red'
        }.get(service['service_status'], 'white')

        error_text = service.get('error', 'N/A')
        if error_text != 'N/A' and len(error_text) > 30:
            error_text = error_text[:27] + '...'

        table.add_row(
            service['service'],
            f"[{status_color}]{service['service_status']}[/{status_color}]",
            str(service.get('status_code', 'N/A')),
            service.get('uptime', 'N/A'),
            str(round(service.get('response_time_ms', 0), 1)),
            error_text
        )
    
    # Determine panel color based on status
    panel_color = {
        'running': 'bold green',
        'unconfigured': 'bold yellow',
        'stopped': 'bold red',
        'unreachable': 'bold red',
        'error': 'bold red',
        'timeout': 'bold red'
    }.get(status_filter, 'bold white')
    
    console.print(Panel(title, style=panel_color, box=box.SIMPLE))
    console.print(table)
    console.print()
    return True

def print_bgp_updates_table(bgp_updates):
    """Print detailed BGP updates table using correct field names"""
    if not bgp_updates:
        console.print(Panel("[yellow]No Recent BGP Updates Available[/yellow]", style="bold yellow", box=box.SIMPLE))
        console.print()
        return

    console.print(Panel("Recent BGP Updates", style="bold blue", box=box.SIMPLE))
    updates_table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
    updates_table.add_column("Timestamp", width=20)
    updates_table.add_column("Prefix", width=18)
    updates_table.add_column("Origin ASN", width=10)
    updates_table.add_column("Type", width=8)
    updates_table.add_column("Peer ASN", width=10)
    updates_table.add_column("Path Length", width=10)
    updates_table.add_column("Service", width=20)
    
    for update in bgp_updates[:10]:  # Show first 10
        # Map type codes to readable names
        update_type = update.get('type', 'unknown')
        if update_type == 'A':
            type_display = 'announce'
            type_color = 'green'
        elif update_type == 'W':
            type_display = 'withdraw'
            type_color = 'yellow'
        else:
            type_display = update_type
            type_color = 'white'
        
        # Extract timestamp and format it
        timestamp = update.get('timestamp', 'N/A')
        if timestamp != 'N/A' and len(timestamp) > 19:
            timestamp = timestamp[:19].replace('T', ' ')
        
        # Calculate AS path length
        as_path = update.get('as_path', [])
        path_length = len(as_path) if as_path else 0
        
        # Extract service name (remove the prefix)
        service = update.get('service', 'N/A')
        if '|' in service:
            service = service.split('|')[1]
        
        updates_table.add_row(
            timestamp,
            update.get('prefix', 'N/A'),
            str(update.get('origin_as', 'N/A')),
            f"[{type_color}]{type_display}[/{type_color}]",
            str(update.get('peer_asn', 'N/A')),
            str(path_length),
            service
        )
    
    console.print(updates_table)
    console.print()

def print_hijacks_table(hijacks):
    """Print hijacks table or empty state"""
    console.print(Panel("Recent Hijacks", style="bold red", box=box.SIMPLE))
    
    if not hijacks:
        # Show empty state with informative message
        empty_table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
        empty_table.add_column("Status", width=60, justify="center")
        empty_table.add_row("[green]✓ No hijacks detected - Network appears secure[/green]")
        console.print(empty_table)
        console.print()
        return

    hijacks_table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
    hijacks_table.add_column("Timestamp", width=20)
    hijacks_table.add_column("Prefix", width=18)
    hijacks_table.add_column("Hijacker ASN", width=12)
    hijacks_table.add_column("Victim ASN", width=10)
    hijacks_table.add_column("Type", width=12)
    hijacks_table.add_column("Confidence", width=10)
    hijacks_table.add_column("Status", width=10)
    
    for hijack in hijacks[:10]:  # Show first 10
        confidence = hijack.get('confidence', 0)
        confidence_color = 'red' if confidence > 0.8 else 'yellow' if confidence > 0.5 else 'white'
        
        timestamp = hijack.get('timestamp', 'N/A')
        if timestamp != 'N/A' and len(timestamp) > 19:
            timestamp = timestamp[:19].replace('T', ' ')
        
        status = hijack.get('status', 'unknown')
        status_color = 'red' if status == 'ongoing' else 'green' if status == 'resolved' else 'yellow'
        
        hijacks_table.add_row(
            timestamp,
            hijack.get('prefix', 'N/A'),
            str(hijack.get('hijacker_asn', 'N/A')),
            str(hijack.get('victim_asn', 'N/A')),
            hijack.get('type', 'N/A'),
            f"[{confidence_color}]{confidence:.2f}[/{confidence_color}]",
            f"[{status_color}]{status}[/{status_color}]"
        )
    
    console.print(hijacks_table)
    console.print()

def print_bgp_summary_table(bgp_data):
    """Print BGP summary as a separate table at the end using correct field names"""
    if not bgp_data or not bgp_data.get('success'):
        console.print(Panel("[red]BGP Summary Unavailable[/red]", style="bold red", box=box.SIMPLE))
        console.print()
        return

    analytics = bgp_data.get('analytics', {})
    bgp_analytics = analytics.get('bgp_updates', {})
    hijack_analytics = analytics.get('hijacks', {})
    summary_analytics = analytics.get('summary', {})

    console.print(Panel("[blue bold]BGP NETWORK SUMMARY[/]", style="bold", box=box.SIMPLE, expand=False))
    
    # Create comprehensive summary table
    summary_table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
    summary_table.add_column("Metric", width=25)
    summary_table.add_column("Value", width=15)
    summary_table.add_column("Status", width=20)
    summary_table.add_column("Details", width=25)
    
    # BGP Updates metrics (using correct field names)
    total_updates = bgp_analytics.get('total_count', 0)
    announcements = bgp_analytics.get('announcement_count', 0)
    withdrawals = bgp_analytics.get('withdrawal_count', 0)
    unique_prefixes = bgp_analytics.get('unique_prefixes', 0)
    unique_origin_asns = bgp_analytics.get('unique_origin_asns', 0)
    unique_peer_asns = bgp_analytics.get('unique_peer_asns', 0)
    
    # Hijacks metrics
    total_hijacks = hijack_analytics.get('total_count', 0)
    active_hijacks = hijack_analytics.get('active_count', 0)
    resolved_hijacks = hijack_analytics.get('resolved_count', 0)
    
    # Summary metrics
    security_status = summary_analytics.get('security_status', 'unknown')
    processing_status = summary_analytics.get('processing_status', 'unknown')
    data_freshness = summary_analytics.get('data_freshness', 'unknown')
    
    security_color = {
        'secure': 'green',
        'warning': 'yellow', 
        'critical': 'red'
    }.get(security_status, 'white')
    
    # Add rows to summary table
    summary_table.add_row(
        "Total BGP Updates", 
        str(total_updates), 
        "[green]Active[/green]" if total_updates > 0 else "[yellow]Inactive[/yellow]",
        f"Last {bgp_data.get('query_limit', 10)} records"
    )
    summary_table.add_row(
        "Route Announcements", 
        str(announcements), 
        "[green]Normal[/green]" if announcements > 0 else "[yellow]None[/yellow]",
        f"{(announcements/total_updates*100):.1f}% of updates" if total_updates > 0 else "N/A"
    )
    summary_table.add_row(
        "Route Withdrawals", 
        str(withdrawals), 
        "[yellow]Caution[/yellow]" if withdrawals > announcements else "[green]Normal[/green]",
        f"{(withdrawals/total_updates*100):.1f}% of updates" if total_updates > 0 else "N/A"
    )
    summary_table.add_row(
        "Unique Prefixes", 
        str(unique_prefixes), 
        "[green]Diverse[/green]" if unique_prefixes > 1 else "[yellow]Limited[/yellow]",
        "Network coverage"
    )
    summary_table.add_row(
        "Unique Origin ASNs", 
        str(unique_origin_asns), 
        "[green]Multi-AS[/green]" if unique_origin_asns > 1 else "[yellow]Single-AS[/yellow]",
        "Origin autonomous systems"
    )
    summary_table.add_row(
        "Unique Peer ASNs", 
        str(unique_peer_asns), 
        "[green]Multi-Peer[/green]" if unique_peer_asns > 1 else "[yellow]Single-Peer[/yellow]",
        "Peer autonomous systems"
    )
    summary_table.add_row(
        "Total Hijacks", 
        str(total_hijacks), 
        "[red]ALERT[/red]" if total_hijacks > 0 else "[green]SECURE[/green]",
        f"{active_hijacks} active, {resolved_hijacks} resolved"
    )
    summary_table.add_row(
        "Security Status", 
        security_status.upper(), 
        f"[{security_color}]{security_status.upper()}[/{security_color}]",
        "Overall network security"
    )
    summary_table.add_row(
        "Processing Status", 
        processing_status.upper(), 
        "[green]OK[/green]" if processing_status == 'current' else "[yellow]BACKLOG[/yellow]",
        "Data processing state"
    )
    summary_table.add_row(
        "Data Freshness", 
        data_freshness.upper(), 
        "[green]FRESH[/green]" if data_freshness == 'recent' else "[yellow]STALE[/yellow]",
        "Data recency status"
    )
    
    console.print(summary_table)
    console.print()

async def run_single_check(json_output=False):
    """Run a single health check"""
    try:
        # Get all data concurrently
        async with aiohttp.ClientSession() as session:
            health_task = get_health_status(session)
            uptime_task = get_uptime_status(session)
            bgp_task = get_bgp_data(session)
            
            health_data, uptime_data, bgp_data = await asyncio.gather(
                health_task, uptime_task, bgp_task, return_exceptions=True
            )
            
            if not health_data or isinstance(health_data, Exception):
                if json_output:
                    error_result = {
                        "success": False,
                        "error": "Failed to get health data",
                        "timestamp": time.time(),
                        "datetime": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    print(json.dumps(error_result, indent=2))
                    return False
                else:
                    console.print("[red]Failed to get health data - cannot continue[/red]")
                    return False

            # Combine health and uptime data
            if uptime_data and not isinstance(uptime_data, Exception):
                health_data = combine_health_and_uptime(health_data, uptime_data)

            # Prepare structured data for JSON output
            if json_output:
                result = {
                    "success": True,
                    "timestamp": time.time(),
                    "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "health": health_data if health_data else {},
                    "uptime": uptime_data if uptime_data and not isinstance(uptime_data, Exception) else {},
                    "bgp": bgp_data if bgp_data and not isinstance(bgp_data, Exception) else {},
                    "summary": {
                        "total_services": health_data.get('summary', {}).get('total_services', 0),
                        "running_services": health_data.get('summary', {}).get('running_services', 0),
                        "service_status_counts": health_data.get('summary', {}).get('status_counts', {}),
                        "overall_status": health_data.get('overall_status', 'unknown'),
                        "all_services_running": False
                    }
                }
                
                # Add container summary if available
                if uptime_data and not isinstance(uptime_data, Exception):
                    uptime_summary = uptime_data.get('summary', {})
                    result["summary"]["containers"] = {
                        "total_containers": uptime_summary.get('total_containers', 0),
                        "running_containers": uptime_summary.get('running_containers', 0),
                        "monitoring_services": uptime_summary.get('monitoring_services', 0),
                        "service_coverage": uptime_summary.get('service_coverage', 0),
                        "missing_services": uptime_summary.get('missing_services', [])
                    }
                
                # Add BGP summary if available
                if bgp_data and not isinstance(bgp_data, Exception):
                    analytics = bgp_data.get('analytics', {})
                    result["summary"]["bgp"] = {
                        "total_updates": analytics.get('bgp_updates', {}).get('total_count', 0),
                        "total_hijacks": analytics.get('hijacks', {}).get('total_count', 0),
                        "active_hijacks": analytics.get('hijacks', {}).get('active_count', 0),
                        "security_status": analytics.get('summary', {}).get('security_status', 'unknown'),
                        "processing_status": analytics.get('summary', {}).get('processing_status', 'unknown')
                    }
                
                # Determine if all services are running
                summary = health_data.get('summary', {})
                total_services = summary.get('total_services', 0)
                running_services = summary.get('running_services', 0)
                result["summary"]["all_services_running"] = running_services == total_services and total_services > 0
                
                print(json.dumps(result, indent=2))
                return result["summary"]["all_services_running"]
            
            # Regular console output (existing code)
            # Create header
            console.print(Panel("ARTEMIS Status Report - " + time.strftime("%Y-%m-%d %H:%M:%S"), 
                              style="bold", 
                              box=box.SIMPLE))
            console.print()

            # Print service status summary
            summary = health_data.get('summary', {})
            console.print(Panel("[blue bold]SERVICES SUMMARY[/]", style="bold", box=box.SIMPLE, expand=False))
            
            summary_table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
            summary_table.add_column("Status", width=15)
            summary_table.add_column("Count", width=8)
            summary_table.add_column("Percent", width=10)
            
            total_services = summary.get('total_services', 0)
            status_counts = summary.get('status_counts', {})
            
            for status, count in status_counts.items():
                status_color = {
                    'running': 'green',
                    'unconfigured': 'yellow',
                    'unreachable': 'red',
                    'error': 'red',
                    'stopped': 'red',
                    'timeout': 'red'
                }.get(status, 'white')
                
                percentage = (count / total_services) * 100 if total_services > 0 else 0
                
                summary_table.add_row(
                    f"[{status_color}]{status}[/{status_color}]",
                    str(count),
                    f"[{status_color}]{percentage:.1f}%[/{status_color}]"
                )
            
            # Add total services row
            summary_table.add_row(
                "[bold]Total Services[/bold]",
                f"[bold]{total_services}[/bold]",
                "[bold]100.0%[/bold]"
            )
            console.print(summary_table)
            console.print()

            # Print service details by status category
            services = health_data.get('services', [])
            
            # Show all service categories
            print_service_table(services, 'running', "Running Services")
            print_service_table(services, 'stopped', "Stopped Services")
            print_service_table(services, 'unconfigured', "Unconfigured Services")
            print_service_table(services, 'unreachable', "Unreachable Services")
            print_service_table(services, 'error', "Error Services")
            print_service_table(services, 'timeout', "Timeout Services")

            # Container uptime summary
            if uptime_data and not isinstance(uptime_data, Exception):
                uptime_summary = uptime_data.get('summary', {})
                if uptime_summary:
                    console.print(Panel("[blue bold]CONTAINER SUMMARY[/]", style="bold", box=box.SIMPLE, expand=False))
                    
                    container_table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
                    container_table.add_column("Metric", width=25)
                    container_table.add_column("Value", width=15)
                    
                    total_containers = uptime_summary.get('total_containers', 0)
                    running_containers = uptime_summary.get('running_containers', 0)
                    monitoring_services = uptime_summary.get('monitoring_services', 0)
                    
                    # Calculate down containers
                    down_containers = monitoring_services - running_containers if monitoring_services > running_containers else 0
                    
                    # Use the service coverage directly from the API response
                    api_coverage = uptime_summary.get('service_coverage', 0)
                    actual_coverage = min(api_coverage, 100.0)
                    
                    container_table.add_row("Total Containers", str(total_containers))
                    container_table.add_row("UP (Running)", f"[green]{running_containers}[/green]")
                    container_table.add_row("DOWN (Not Found)", f"[red]{down_containers}[/red]" if down_containers > 0 else "[green]0[/green]")
                    container_table.add_row("Service Coverage", f"[green]{actual_coverage:.1f}%[/green]" if actual_coverage >= 90 else f"[yellow]{actual_coverage:.1f}%[/yellow]")
                    
                    console.print(container_table)
                    console.print()

            # BGP Data Section
            if bgp_data and not isinstance(bgp_data, Exception):
                # Show BGP updates
                bgp_updates = bgp_data.get('bgp_updates', [])
                print_bgp_updates_table(bgp_updates)
                
                # Show hijacks
                hijacks = bgp_data.get('hijacks', [])
                print_hijacks_table(hijacks)
                
                # Show BGP summary at the end
                print_bgp_summary_table(bgp_data)

            # Final status check
            running_services = status_counts.get('running', 0)
            if running_services != total_services:
                not_running = total_services - running_services
                console.print(f"[red]⚠️  Warning: {not_running} services are not running[/red]")
                return False
            else:
                console.print("[green]✅ All services are running[/green]")
                return True

    except Exception as e:
        if json_output:
            error_result = {
                "success": False,
                "error": str(e),
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            print(json.dumps(error_result, indent=2))
        else:
            console.print(f"[red]Fatal Error: {str(e)}[/red]", style="bold red")
        return False


async def run_periodic_monitoring(interval_seconds, max_runs=None, json_output=False):
    """Run periodic monitoring with specified interval"""
    run_count = 0
    
    try:
        if not json_output:
            console.print(Panel(f"[blue bold]ARTEMIS Periodic Monitoring Started[/blue bold]\n"
                              f"Interval: {interval_seconds} seconds\n"
                              f"Max runs: {'Unlimited' if max_runs is None else max_runs}\n"
                              f"Press Ctrl+C to stop", 
                              style="bold blue", box=box.SIMPLE))
            console.print()
        
        results = []
        
        while True:
            run_count += 1
            
            if not json_output:
                console.print(f"[cyan]--- Check #{run_count} ---[/cyan]")
            
            success = await run_single_check(json_output)
            
            # For JSON output, collect results
            if json_output:
                # The result is already printed by run_single_check, just track success
                pass
            
            # Exit if max runs reached
            if max_runs and run_count >= max_runs:
                if not json_output:
                    console.print(f"\n[yellow]Completed {max_runs} monitoring runs[/yellow]")
                break
            
            if not json_output:
                # Show next check info
                next_check = time.strftime("%H:%M:%S", time.localtime(time.time() + interval_seconds))
                console.print(f"\n[dim]Next check at {next_check} (in {interval_seconds}s). Press Ctrl+C to stop.[/dim]")
                console.print("=" * 80)
                console.print()
            
            # Wait for next interval
            await asyncio.sleep(interval_seconds)
            
    except KeyboardInterrupt:
        if not json_output:
            console.print(f"\n[yellow]Monitoring stopped by user after {run_count} checks[/yellow]")
    except Exception as e:
        if json_output:
            error_result = {
                "success": False,
                "error": f"Periodic monitoring error: {str(e)}",
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "run_count": run_count
            }
            print(json.dumps(error_result, indent=2))
        else:
            console.print(f"\n[red]Periodic monitoring error: {str(e)}[/red]")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="ARTEMIS Health Monitor - Monitor ARTEMIS BGP security services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Use default http://localhost:3001
  %(prog)s --url http://localhost:3001        # Explicit local URL
  %(prog)s --url localhost:3001 --periodic 30  # Periodic monitoring
  %(prog)s --url localhost:3001 --periodic 60 --max-runs 10  # Limited runs
  %(prog)s --json                             # JSON output
        """
    )
    
    parser.add_argument(
        '--url',
        type=str,
        help='Monitor service URL'
    )
   
    parser.add_argument(
        '--periodic', '-p',
        type=int,
        metavar='SECONDS',
        help='Run periodic monitoring with specified interval in seconds (e.g., 30, 60, 300)'
    )
    
    parser.add_argument(
        '--max-runs', '-m',
        type=int,
        metavar='COUNT',
        help='Maximum number of monitoring runs (only with --periodic). Default: unlimited'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results in JSON format for programmatic consumption'
    )
    
    return parser.parse_args()


async def main():
    """Main function with argument parsing"""
    args = parse_arguments()
    
    if not args.url:
        console.print("[red]Error: --url parameter is required[/red]")
        console.print("[yellow]Example: python3 artemis_monitor.py --url http://localhost:3001[/yellow]")
        sys.exit(1)
    
    # Set API endpoints from command line argument
    global MONITOR_BASE_URL
    MONITOR_BASE_URL = args.url
    
    # Validate arguments
    if args.max_runs and not args.periodic:
        if args.json:
            error_result = {
                "success": False,
                "error": "--max-runs can only be used with --periodic",
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            print(json.dumps(error_result, indent=2))
        else:
            console.print("[red]Error: --max-runs can only be used with --periodic[/red]")
        sys.exit(1)
    
    if args.periodic:
        if args.periodic < 10:
            if args.json:
                error_result = {
                    "success": False,
                    "error": "Periodic interval must be at least 10 seconds",
                    "timestamp": time.time(),
                    "datetime": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                print(json.dumps(error_result, indent=2))
            else:
                console.print("[red]Error: Periodic interval must be at least 10 seconds[/red]")
            sys.exit(1)
        
        # Run periodic monitoring
        await run_periodic_monitoring(args.periodic, args.max_runs, args.json)
    else:
        # Run single check
        success = await run_single_check(args.json)
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    asyncio.run(main()) 
