"""
ARTEMIS Authentication Module
Handles login and JWT token management for ARTEMIS API access
"""
import os
import logging
import ssl

logger = logging.getLogger(__name__)

NGINX_HOST = os.getenv('NGINX_HOST', 'nginx')
BASE_URL = f"https://{NGINX_HOST}:443"
LOGIN_URL = f"{BASE_URL}/api/auth/login/credentials"
JWT_URL = f"{BASE_URL}/api/auth/jwt"

DEFAULT_EMAIL = os.getenv('ADMIN_EMAIL')
DEFAULT_PASS = os.getenv('ADMIN_PASS')
API_KEY = os.getenv('API_KEY')

async def authenticate(session):
    """
    Authenticate with ARTEMIS and return JWT token
    Returns: JWT token string or None if authentication fails
    """
    try:
        # Create SSL context that allows self-signed certificates for internal Docker communication
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        login_headers = {
            'x-artemis-api-key': API_KEY,
            'Content-Type': 'application/json'
        }
        
        login_data = {
            'email': DEFAULT_EMAIL,
            'password': DEFAULT_PASS
        }
        
        async with session.post(LOGIN_URL, json=login_data, headers=login_headers, ssl=ssl_context) as response:
            if response.status != 200:
                logger.error(f"Step 1 - Login failed with status: {response.status}")
                response_text = await response.text()
                logger.error(f"Response: {response_text}")
                return None
            
            user_data = await response.json()
            session_id = user_data.get('user', {}).get('sessionId')
            
            if not session_id:
                logger.error("No session ID in login response")
                return None
                
            logger.info("Login successful")
        
        jwt_headers = {
            'x-artemis-api-key': API_KEY,
            'Content-Type': 'application/json',
            'Cookie': f'sid={session_id}'
        }
        
        async with session.get(JWT_URL, headers=jwt_headers, ssl=ssl_context) as response:
            if response.status == 200:
                jwt_data = await response.json()
                if 'accessToken' in jwt_data:
                    logger.info("JWT token obtained successfully")
                    return jwt_data['accessToken']
                else:
                    logger.error("Step 2 - No accessToken in response")
                    return None
            else:
                logger.error(f"JWT request failed with status: {response.status}")
                response_text = await response.text()
                logger.error(f"Response: {response_text}")
                return None
                
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        return None 
