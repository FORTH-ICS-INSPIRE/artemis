"""
ARTEMIS Health Monitor Service

A comprehensive monitoring service for ARTEMIS BGP hijack detection system.
Provides health checks, uptime monitoring, and BGP data analytics.
"""
import logging
import os
from flask import Flask

from routes.health import health_bp
from routes.uptime import uptime_bp
from routes.bgp import bgp_bp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('health-monitor.log')
    ]
)

logger = logging.getLogger(__name__)


def create_app():
    """
    Create and configure the Flask application.
    
    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Configure Flask app
    app.config['JSON_SORT_KEYS'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
    
    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(uptime_bp)
    app.register_blueprint(bgp_bp)
    
    logger.info("Flask application created and configured")
    logger.info("Registered blueprints: health, uptime, bgp")
    
    return app


app = create_app()


@app.route('/health')
def basic_health():
    """Health check endpoint."""
    from flask import jsonify
    return jsonify({'status': 'running', 'service': 'health-monitor'})


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return {
        'error': 'Endpoint not found',
        'message': 'The requested endpoint does not exist',
        'available_endpoints': [
            '/health',
            '/health/all',
            '/uptime',
            '/bgp/summary',
            '/bgp/updates',
            '/bgp/hijacks'
        ]
    }, 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {str(error)}")
    return {
        'error': 'Internal server error',
        'message': 'An unexpected error occurred'
    }, 500


if __name__ == '__main__':
    logger.info("Starting ARTEMIS Health Monitor Service")
    logger.info("Available endpoints:")
    logger.info("  GET  /health                 - Basic health check")
    logger.info("  GET  /health/all             - Services health summary")
    logger.info("  GET  /uptime                 - Containers uptime summary")
    logger.info("  GET  /bgp/summary            - BGP data summary")
    logger.info("  GET  /bgp/updates            - BGP updates only")
    logger.info("  GET  /bgp/hijacks            - Hijacks updates only")
 
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 3000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Server starting on {host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug) 
