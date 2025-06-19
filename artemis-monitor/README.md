# ARTEMIS Monitor

A comprehensive monitoring and analytics service that provides real-time health status, infrastructure monitoring, and BGP security analytics for ARTEMIS deployments. The service acts as a centralized monitoring system that connects to your ARTEMIS deployment and exposes monitoring data through REST APIs.

## How It Works

The service connects to your ARTEMIS deployment and monitors three key areas:

1. **Service Health**: HTTP health checks on all ARTEMIS services
2. **Container Status**: Docker API integration for uptime and container state monitoring  
3. **BGP Security**: GraphQL API queries for real-time BGP updates and hijack detection

## Docker Setup

**Prerequisites:** ARTEMIS must be running before starting the monitor.

```bash
# Start the ARTEMIS monitor (attaches to ARTEMIS network)
docker-compose -f docker-compose.artemis-monitor.yaml up -d

# View logs
docker-compose -f docker-compose.artemis-monitor.yaml logs -f artemis-monitor

# Stop the service
docker-compose -f docker-compose.artemis-monitor.yaml down
```

The ARTEMIS monitor will be available at `http://artemis-monitor:3001` and automatically connects to the ARTEMIS network for monitoring.

## Configuration

### Service Configuration

Services are configured in `config.yaml`, with environment variable support:
```yaml
services:
  configuration:
    host: configuration
    port: 3000
    endpoint: /health
  # ... more services
```

## API Endpoints & JSON Responses

### 1. Services Health Status
```
GET /health/all
```

**Response:**
```json
{
  "services": [
    {
      "service": "configuration",
      "service_status": "running",
      "response_time_ms": 123.45,
      "status_code": 200,
      "url": "http://configuration:3000/health"
    },
    {
      "service": "detection",
      "service_status": "stopped",
      "url": "http://detection:3000/health"
    }
  ],
  "summary": {
    "status_counts": {"running": 1, "stopped": 1},
    "total_services": 2,
    "running_services": 1,
    "average_response_time_ms": 106.39
  },
  "success": true,
  "overall_status": "partially_running"
}
```

### 2. Container Uptime Information
```
GET /uptime
```

**Response:**
```json
{
  "uptimes": {
    "configuration": "2 hours",
    "detection": "Not running"
  },
  "containers": [
    {
      "service": "configuration",
      "uptime": "2 hours",
      "status": "Up 2 hours",
      "state": "running",
      "image": "artemis_configuration:latest"
    }
  ],
  "summary": {
    "total_containers": 3,
    "running_containers": 2,
    "monitoring_services": 4,
    "service_coverage": 75.0
  },
  "success": true,
  "overall_status": "partially_running"
}
```

### 3. BGP Data Summary
```
GET /bgp/summary?limit=5
```

**Response:**
```json
{
  "success": true,
  "timestamp": 1679404800.123,
  "bgp_updates": [
    {
      "prefix": "192.168.1.0/24",
      "origin_as": 65001,
      "peer_asn": 65000,
      "type": "A",
      "timestamp": "2024-03-21T10:00:00Z"
    }
  ],
  "hijacks": [
    {
      "prefix": "10.0.0.0/16",
      "hijack_as": 65999,
      "active": true,
      "time_detected": "2024-03-21T09:45:00Z"
    }
  ],
  "analytics": {
    "bgp_updates": {
      "total_count": 1,
      "announcement_count": 1
    },
    "hijacks": {
      "total_count": 1,
      "active_count": 1
    },
    "summary": {
      "security_status": "warning",
      "active_threats": 1
    }
  }
}
```

### 4. BGP Updates Only
```
GET /bgp/updates?limit=10
```

**Response:**
```json
{
  "success": true,
  "bgp_updates": [
    {
      "prefix": "192.168.1.0/24",
      "origin_as": 65001,
      "type": "A",
      "timestamp": "2024-03-21T10:00:00Z"
    }
  ],
  "analytics": {
    "total_count": 1,
    "announcement_count": 1,
    "unique_prefixes": 1
  }
}
```

### 5. Hijacks Only
```
GET /bgp/hijacks?limit=10
```

**Response:**
```json
{
  "success": true,
  "hijacks": [
    {
      "prefix": "10.0.0.0/16",
      "hijack_as": 65999,
      "active": true,
      "time_detected": "2024-03-21T09:45:00Z"
    }
  ],
  "analytics": {
    "total_count": 1,
    "active_count": 1,
    "security_status": "warning"
  }
}
```

## CLI Usage

The CLI script requires a `--url` parameter to specify the monitor service URL:

```bash
# Basic health check (local)
python artemis_monitor.py --url http://localhost:3001

# Basic health check (ngrok)
python artemis_monitor.py --url https://your-monitor.ngrok.io

# JSON output for scripting
python artemis_monitor.py --url http://localhost:3001 --json

# Periodic monitoring
python artemis_monitor.py --url http://localhost:3001 --periodic 60

# Limited runs
python artemis_monitor.py --url http://localhost:3001 --periodic 60 --max-runs 10

# Periodic with JSON output
python artemis_monitor.py --url http://localhost:3001 --periodic 30 --json

# Save results to file
python artemis_monitor.py --url http://localhost:3001 --json > status.json
```

**Key Features:**
- **Visual Reports**: Rich console output with colored tables and status indicators
- **Periodic Monitoring**: Configurable intervals (minimum 10 seconds)
- **JSON Export**: Machine-readable output for automation and logging
- **Flexible Control**: Limit monitoring runs or run continuously

### Output Example
```
┌─ ARTEMIS Status Report - 2024-03-21 14:30:15 ─┐
└─────────────────────────────────────────────────┘

┌─ SERVICES SUMMARY ─┐
│ Status      │ Count │ Percent │
│ running     │ 12    │ 85.7%   │
│ stopped     │ 2     │ 14.3%   │
│ Total Services │ 14 │ 100.0%  │
└─────────────────────┘

┌─ Running Services ─────────────────────────────────────────────┐
│ Service       │ Status  │ Code │ Uptime │ Response │ Error │
│ configuration │ running │ 200  │ 3 days │ 45.2ms   │ N/A   │
│ detection     │ running │ 200  │ 3 days │ 67.1ms   │ N/A   │
│ database      │ running │ 200  │ 3 days │ 23.8ms   │ N/A   │
│ bgpstreamlive │ running │ 200  │ 3 days │ 89.3ms   │ N/A   │
└─────────────────────────────────────────────────────────────────┘

┌─ Stopped Services ─────────────────────────────────────────────┐
│ Service    │ Status  │ Code │ Uptime │ Response │ Error        │
│ mitigation │ stopped │ N/A  │ N/A    │ N/A      │ Connection...│
│ notifier   │ stopped │ N/A  │ N/A    │ N/A      │ Service un...│
└─────────────────────────────────────────────────────────────────┘

┌─ CONTAINER SUMMARY ─┐
│ Metric              │ Value  │
│ Total Containers    │ 15     │
│ UP (Running)        │ 15     │
│ DOWN (Not Found)    │ 0      │
│ Service Coverage    │ 107.1% │
└─────────────────────┘

┌─ Recent BGP Updates ─┐
│ Timestamp        │ Prefix        │ Origin ASN │ Type     │ Peer ASN │
│ 2024-03-21 14:29 │ 8.8.8.0/24    │ 15169      │ announce │ 174      │
│ 2024-03-21 14:28 │ 1.1.1.0/24    │ 13335      │ announce │ 6939     │
└─────────────────────────────────────────────────────────────────────┘

┌─ Recent Hijacks ─┐
│ Status                                           │
│ ✓ No hijacks detected - Network appears secure  │
└──────────────────────────────────────────────────┘

┌─ BGP NETWORK SUMMARY ─┐
│ Metric           │ Value │ Status   │ Details        │
│ Total BGP Updates│ 25    │ Active   │ Last 10 records│
│ Route Announcements│ 20  │ Normal   │ 80.0% of updates│
│ Route Withdrawals│ 5     │ Normal   │ 20.0% of updates│
│ Total Hijacks    │ 0     │ SECURE   │ 0 active, 0 resolved│
│ Security Status  │ SECURE│ SECURE   │ Overall network security│
└─────────────────────────────────────────────────────────────────┘

⚠️  Warning: 2 services are not running
```

## Monitoring Integration

The REST APIs are designed for integration with monitoring systems like Prometheus, Grafana, and alerting platforms. All endpoints return structured JSON for easy consumption by external tools.

### Webhook Integration
All API endpoints can be used for webhook-based monitoring:
```bash
# Example webhook for external monitoring
curl -X GET "http://artemis-monitor:3001/health/all" \
  -H "Accept: application/json" | \
  jq '.overall_status' | \
  xargs -I {} echo "ARTEMIS Status: {}"
```
